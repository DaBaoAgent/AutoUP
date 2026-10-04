"""通用工具：进程、媒体探测、SRT、文本、JSON 与稳定指纹。"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import config

log = logging.getLogger("autoup")


def run(
    cmd: list[Any],
    desc: str = "",
    timeout: int | None = None,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    shown = " ".join(str(c) for c in cmd[:12]) + (" ..." if len(cmd) > 12 else "")
    log.info("$ %s", shown)
    proc = subprocess.run(
        [str(c) for c in cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
    )
    if proc.returncode != 0:
        log.error("[%s] 失败(%d): %s", desc or cmd[0], proc.returncode, (proc.stderr or "")[-800:])
    return proc


def ffprobe_json(media: Path) -> dict:
    proc = run(
        [
            config.ffprobe(),
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(media),
        ],
        desc="ffprobe",
    )
    try:
        return json.loads(proc.stdout or "{}")
    except ValueError:
        return {}


def probe_video(path: Path) -> dict:
    info = ffprobe_json(path)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    try:
        num, den = str(video.get("avg_frame_rate", "30/1")).split("/")
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    return {
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "duration": float(info.get("format", {}).get("duration", 0) or 0),
        "fps": fps if fps > 0 else 30.0,
        "has_audio": audio is not None,
    }


def audio_duration(path: Path) -> float:
    info = ffprobe_json(path)
    try:
        return float(info["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        pass
    ensure_pydub_ffmpeg()
    from pydub import AudioSegment

    return len(AudioSegment.from_file(str(path))) / 1000.0


def ensure_pydub_ffmpeg() -> None:
    import os

    ff = config.ffmpeg()
    ff_path = Path(ff)
    if ff_path.parent != Path("."):
        ff_dir = str(ff_path.parent)
        current = os.environ.get("PATH", "")
        if ff_dir not in current.split(os.pathsep):
            os.environ["PATH"] = ff_dir + os.pathsep + current

    from pydub import AudioSegment

    AudioSegment.converter = ff
    AudioSegment.ffmpeg = ff
    AudioSegment.ffprobe = config.ffprobe()


@lru_cache(maxsize=1)
def nvenc_available() -> bool:
    proc = run([config.ffmpeg(), "-hide_banner", "-encoders"], desc="查编码器")
    return "h264_nvenc" in (proc.stdout or "")


_SRT_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _srt_seconds(ts: str) -> float:
    match = _SRT_TIME.match(ts.strip())
    if not match:
        raise ValueError(f"无法解析 SRT 时间: {ts!r}")
    hours, minutes, seconds, millis = (int(group) for group in match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def parse_srt(path: Path) -> list[dict]:
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.strip())
    items: list[dict] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        cursor = 0
        if re.fullmatch(r"\d+", lines[0]):
            index = int(lines[0])
            cursor = 1
        else:
            index = len(items) + 1
        if cursor >= len(lines):
            continue
        match = re.match(r"([\d:,.]+)\s*-->\s*([\d:,.]+)", lines[cursor])
        if not match:
            continue
        start = _srt_seconds(match.group(1))
        end = _srt_seconds(match.group(2))
        text = " ".join(lines[cursor + 1 :])
        items.append(
            {
                "index": index,
                "start": start,
                "end": end,
                "duration": round(max(end - start, 0.0), 3),
                "text": text,
            }
        )
    return items


_STOP = "。！？；!?;"
_SOFT = "，、,:：—…"


def split_sentences(text: str, max_len: int = 60) -> list[str]:
    sentences: list[str] = []
    buffer = ""
    for char in text:
        buffer += char
        if char in _STOP:
            if buffer.strip():
                sentences.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        sentences.append(buffer.strip())

    output: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_len:
            output.append(sentence)
            continue
        current = ""
        for char in sentence:
            current += char
            if len(current) >= max_len and (char in _SOFT or len(current) >= max_len + 20):
                output.append(current.strip())
                current = ""
        if current.strip():
            output.append(current.strip())
    return [item for item in output if item]


def estimate_duration(text: str) -> float:
    zh = re.sub(r"[^\u4e00-\u9fff]", "", text)
    duration = len(zh) * 0.21
    duration += sum(0.15 for char in text if char in _STOP)
    duration += sum(0.08 for char in text if char in _SOFT)
    return round(duration, 2)


def fmt_ts(seconds: float) -> str:
    millis = int(round(max(seconds, 0.0) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours}:{minutes:02d}:{secs:02d}.{millis:03d}"


def stable_hash(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_fingerprint(path: Path, sample_bytes: int = 1_048_576) -> dict[str, Any]:
    """小文件全量哈希；大文件只哈希首尾采样，避免断点检查反复读取整部视频。"""
    path = Path(path)
    if not path.exists() or not path.is_file():
        return {"exists": False}
    size = path.stat().st_size
    digest = hashlib.sha256()
    digest.update(str(size).encode("ascii"))
    with path.open("rb") as handle:
        if size <= sample_bytes * 2:
            digest.update(handle.read())
        else:
            digest.update(handle.read(sample_bytes))
            handle.seek(max(size - sample_bytes, 0))
            digest.update(handle.read(sample_bytes))
    return {"exists": True, "size": size, "sha256": digest.hexdigest()}


def write_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
