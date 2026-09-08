"""通用工具: ffmpeg 封装、时长探测、SRT 解析、中文估时、分句、JSON 读写。"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

from . import config

log = logging.getLogger("autoup")

# ---------- 进程与探测 ----------

def run(cmd: list, desc: str = "", timeout: int | None = None,
        cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    log.info("$ %s", " ".join(str(c) for c in cmd[:12]) + (" ..." if len(cmd) > 12 else ""))
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, cwd=str(cwd) if cwd else None)
    if p.returncode != 0:
        log.error("[%s] 失败(%d): %s", desc or cmd[0], p.returncode, (p.stderr or "")[-800:])
    return p


def ffprobe_json(media: Path) -> dict:
    p = run([config.ffprobe(), "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(media)], desc="ffprobe")
    try:
        return json.loads(p.stdout or "{}")
    except ValueError:
        return {}


def probe_video(path: Path) -> dict:
    """返回 {width,height,duration,fps,has_audio}"""
    info = ffprobe_json(path)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    try:
        num, den = str(v.get("avg_frame_rate", "30/1")).split("/")
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    return {
        "width": int(v.get("width", 0)),
        "height": int(v.get("height", 0)),
        "duration": float(info.get("format", {}).get("duration", 0) or 0),
        "fps": fps if fps > 0 else 30.0,
        "has_audio": a is not None,
    }


def audio_duration(path: Path) -> float:
    """音频/视频时长(秒); ffprobe 失败用 pydub 兜底。"""
    info = ffprobe_json(path)
    try:
        return float(info["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        pass
    ensure_pydub_ffmpeg()
    from pydub import AudioSegment
    return len(AudioSegment.from_file(str(path))) / 1000.0


def ensure_pydub_ffmpeg() -> None:
    """pydub 在调用时动态 which() 探测 ffmpeg/ffprobe, 需要目录在 PATH 里。"""
    import os
    ff_dir = str(Path(config.ffmpeg()).parent)
    if ff_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ff_dir + os.pathsep + os.environ.get("PATH", "")
    from pydub import AudioSegment
    AudioSegment.converter = config.ffmpeg()
    AudioSegment.ffmpeg = config.ffmpeg()
    AudioSegment.ffprobe = config.ffprobe()


def nvenc_available() -> bool:
    p = run([config.ffmpeg(), "-hide_banner", "-encoders"], desc="查编码器")
    return "h264_nvenc" in (p.stdout or "")


# ---------- SRT ----------

_SRT_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _srt_seconds(ts: str) -> float:
    m = _SRT_TIME.match(ts.strip())
    if not m:
        raise ValueError(f"无法解析 SRT 时间: {ts!r}")
    h, mnt, s, ms = (int(g) for g in m.groups())
    return h * 3600 + mnt * 60 + s + ms / 1000.0


def parse_srt(path: Path) -> list[dict]:
    """解析 SRT 为 [{index,start,end,duration,text}] (start/end/duration 为秒)。"""
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.strip())
    items: list[dict] = []
    for b in blocks:
        lines = [l.strip() for l in b.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        i = 0
        if re.fullmatch(r"\d+", lines[0]):
            idx = int(lines[0])
            i = 1
        else:
            idx = len(items) + 1
        mm = re.match(r"([\d:,.]+)\s*-->\s*([\d:,.]+)", lines[i])
        if not mm:
            continue
        text = " ".join(lines[i + 1:])
        start, end = _srt_seconds(mm.group(1)), _srt_seconds(mm.group(2))
        items.append({"index": idx, "start": start, "end": end,
                      "duration": round(max(end - start, 0.0), 3), "text": text})
    return items


# ---------- 中文文本 ----------

_STOP = "。！？；!?;"
_SOFT = "，、,:：—…"


def split_sentences(text: str, max_len: int = 60) -> list[str]:
    """解说文案分句: 句末标点优先; 超长句在软标点/硬上限处二次切分。"""
    sents: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in _STOP:
            if buf.strip():
                sents.append(buf.strip())
            buf = ""
    if buf.strip():
        sents.append(buf.strip())
    out: list[str] = []
    for s in sents:
        if len(s) <= max_len:
            out.append(s)
            continue
        cur = ""
        for ch in s:
            cur += ch
            if len(cur) >= max_len and (ch in _SOFT or len(cur) >= max_len + 20):
                out.append(cur.strip())
                cur = ""
        if cur.strip():
            out.append(cur.strip())
    return [s for s in out if s]


def estimate_duration(text: str) -> float:
    """中文配音时长预估(秒): 每汉字 1 音节 × 0.21s + 标点停顿(VideoLingo 参数)。"""
    zh = re.sub(r"[^\u4e00-\u9fff]", "", text)
    dur = len(zh) * 0.21
    dur += sum(0.15 for ch in text if ch in _STOP)
    dur += sum(0.08 for ch in text if ch in _SOFT)
    return round(dur, 2)


def fmt_ts(seconds: float) -> str:
    ms = int(round(max(seconds, 0.0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h}:{m:02d}:{s:02d}.{ms:03d}"


# ---------- JSON ----------

def write_json(path: Path, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
