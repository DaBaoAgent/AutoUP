"""S6 合成: ED 段剪切 → concat → 配音轨(pydub) → BGM 闪避 → 烧字幕 → 一次终编码。

剪切/编码器回退思想参考 NarratoAI app/services/clip_video.py 与 generate_video.py (MIT)。
时间轴模型(纯解说压剪):
  - 画面: 按 edit_decision.json 顺序拼接, 句末段多剪 gap_seconds 作为句间停顿画面
  - 配音: 每句语音从该句首段画面的起点开始铺放(pyekub 混入静音底轨)
  - 字幕: ASS, 时间 = 配音起点 → 配音起点+句长
"""
from __future__ import annotations

import logging
import random
from pathlib import Path

from .. import config, utils
from ..stages.dub import SCRIPT_NAME

log = logging.getLogger("autoup.s6")

VIDEO_EXTS = {".mp4", ".mkv", ".webm"}
SEG_BASENAME = "seg_{:04d}.mp4"


# ---------- 时间轴规划 ----------

def plan_timeline(ed: dict, timing: dict, source_duration: float) -> dict:
    """把 ED 段 + timing 展开为输出时间轴:
    cuts:   [{src_start, src_end, out_start, out_end}]  画面剪切段(句末含 gap)
    voice:  [{index, text, audio, t_start, duration}]   配音铺放
    subs:   [{start, end, text}]                        ASS 字幕事件
    """
    gap = float(config.get("voice.gap_seconds", 0.3))
    sents = {s["index"]: s for s in timing["sentences"]}
    items = sorted(ed["items"], key=lambda x: x["start"])
    covered = {it["sentence_index"] for it in items}
    missing = sorted(set(sents) - covered)

    cuts: list[dict] = []
    voice: list[dict] = []
    subs: list[dict] = []
    cursor = 0.0

    def append_cut(src_start: float, src_end: float) -> None:
        nonlocal cursor
        src_end = min(src_end, source_duration)
        if src_end - src_start < 0.3:
            return
        cuts.append({"src_start": round(src_start, 3), "src_end": round(src_end, 3),
                     "out_start": round(cursor, 3), "out_end": round(cursor + src_end - src_start, 3)})
        cursor += src_end - src_start

    for pos, it in enumerate(items):
        si = it["sentence_index"]
        is_sentence_end = (pos + 1 == len(items)) or (items[pos + 1]["sentence_index"] != si)
        if si not in voice and si in sents:
            voice.append({"index": si, "text": sents[si]["text"],
                          "audio": sents[si]["audio"], "t_start": round(cursor, 3),
                          "duration": sents[si]["duration"]})
            subs.append({"start": round(cursor, 3),
                         "end": round(cursor + sents[si]["duration"], 3),
                         "text": sents[si]["text"]})
        extend = gap if is_sentence_end else 0.0
        append_cut(it["start"], it["end"] + extend)

    # 未覆盖句: 挂在最后一段之后, 延长末段画面
    for si in missing:
        s = sents[si]
        need = s["duration"] + gap
        if cuts:
            cuts[-1]["src_end"] = round(min(cuts[-1]["src_end"] + need, source_duration), 3)
            cuts[-1]["out_end"] = round(cuts[-1]["out_start"] + cuts[-1]["src_end"] - cuts[-1]["src_start"], 3)
            cursor = cuts[-1]["out_end"]
        else:
            append_cut(0.0, min(need, source_duration))
        voice.append({"index": si, "text": s["text"], "audio": s["audio"],
                      "t_start": round(cursor - need, 3), "duration": s["duration"]})
        subs.append({"start": round(cursor - need, 3), "end": round(cursor - gap, 3), "text": s["text"]})
        log.warning("第 %d 句无匹配画面, 延续末段画面", si)

    return {"cuts": cuts, "voice": voice, "subs": subs, "total": round(cursor, 3)}


# ---------- 画面段剪切与拼接 ----------

def _video_codec_args() -> tuple[str, list[str]]:
    """(编码器名, 编码参数); NVENC 可用且配置允许则用 NVENC, 否则 libx264。"""
    crf = str(config.get("video.crf", 18))
    preset = str(config.get("video.preset", "medium"))
    if config.get("video.prefer_gpu", True) and utils.nvenc_available():
        return "h264_nvenc", ["-preset", "p5", "-rc", "vbr", "-cq", crf, "-b:v", "0"]
    return "libx264", ["-preset", preset, "-crf", crf]


def cut_segments(src: Path, cuts: list[dict], workdir: Path) -> list[Path]:
    """逐段精确剪切(-ss/-to 快速定位) + 统一参数重编码 + 去原声。"""
    codec, codec_args = _video_codec_args()
    w, h = int(config.get("video.width", 1920)), int(config.get("video.height", 1080))
    fps = str(config.get("video.fps", 30))
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}")
    files: list[Path] = []
    for i, c in enumerate(cuts):
        out = workdir / SEG_BASENAME.format(i + 1)
        cmd = [config.ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
               "-ss", c["src_start"], "-to", c["src_end"], "-i", src,
               "-an", "-vf", vf, "-c:v", codec, *codec_args,
               "-pix_fmt", "yuv420p", "-avoid_negative_ts", "make_zero", out]
        p = utils.run(cmd, desc=f"剪切段 {i + 1}/{len(cuts)}", timeout=600)
        if p.returncode != 0:
            raise RuntimeError(f"段 {i + 1} 剪切失败")
        files.append(out)
    return files


def concat_segments(files: list[Path], workdir: Path) -> Path:
    """concat demuxer 拼接(各段编码参数一致, 流复制零损耗)。"""
    lst = workdir / "concat.txt"
    lst.write_text("".join(f"file '{f.as_posix()}'\n" for f in files), encoding="utf-8")
    out = workdir / "picture.mp4"
    p = utils.run([config.ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                   "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                   "-movflags", "+faststart", out], desc="拼接画面", timeout=600)
    if p.returncode != 0:
        raise RuntimeError("画面拼接失败")
    return out


# ---------- 配音轨与字幕 ----------

def build_voice_track(voice: list[dict], topic_dir: Path, total: float, workdir: Path) -> Path:
    """静音底轨 + 逐句铺放配音 → voice_full.wav (44.1kHz 立体声)。"""
    utils.ensure_pydub_ffmpeg()
    from pydub import AudioSegment
    base = AudioSegment.silent(duration=int(total * 1000) + 500, frame_rate=44100)
    base = base.set_frame_rate(44100).set_channels(2)
    for v in voice:
        wav = topic_dir / "配音" / v["audio"]
        seg = AudioSegment.from_file(str(wav))
        seg = seg.set_frame_rate(44100).set_channels(2)
        pos_ms = max(int(v["t_start"] * 1000), 0)
        base = base.overlay(seg, position=pos_ms)
    out = workdir / "voice_full.wav"
    base.export(str(out), format="wav")
    return out


def _ass_time(t: float) -> str:
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _font_family(path: str) -> str:
    """读字体内部 family 名, 供 ASS FontName 匹配(fontsdir)。"""
    try:
        from PIL import ImageFont
        return ImageFont.truetype(path, 20).getname()[0]
    except Exception:  # noqa: BLE001
        return "Microsoft YaHei"


def _stage_font(workdir: Path) -> Path:
    """把字幕字体硬链/复制进工作目录(相对路径引用, 避开盘符冒号)。"""
    import os
    import shutil
    src = Path(str(config.get("subtitle.font_path")
                   or config.get("cover.font_path") or "C:/Windows/Fonts/simhei.ttf"))
    fonts_dir = workdir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    dst = fonts_dir / "subtitle.ttf"
    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy(str(src), str(dst))
    return fonts_dir


def _split_lines(text: str, max_chars: int) -> list[str]:
    """把句子切成 ≤max_chars 的行: 先按标点切段→段内去标点→打包; 超长段才硬切。
    字幕内不保留任何标点(断句信息由换行和轮显节奏承担)。"""
    import re as _re
    PUNCT = "，。！？；：、,.!?;:…—“”‘’()（）[]【】《》<>\"'~～·"
    phrases = [p for p in _re.split(r"[，。！？；：、,.!?;:…]", text) if p]
    lines: list[str] = []
    buf = ""
    for raw in phrases:
        ph = "".join(ch for ch in raw if ch not in PUNCT)
        if not ph:
            continue
        while len(ph) > max_chars:          # 超长短语硬切
            if buf:
                lines.append(buf)
                buf = ""
            lines.append(ph[:max_chars])
            ph = ph[max_chars:]
        if len(buf) + len(ph) <= max_chars:
            buf += ph
        else:
            if buf:
                lines.append(buf)
            buf = ph
    if buf:
        lines.append(buf)
    return lines or [text]


def build_ass(subs: list[dict], out: Path) -> Path:
    """按 config.subtitle 生成 ASS(封面同款手写体, 单行≤15字, 长句分段轮显)。"""
    st = config.get("subtitle", {}) or {}
    font_path = str(st.get("font_path") or config.get("cover.font_path") or "C:/Windows/Fonts/simhei.ttf")
    family = _font_family(font_path)
    size = int(st.get("font_size", 85))
    max_chars = int(st.get("max_chars_per_line", 15))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {int(config.get('video.width', 1920))}
PlayResY: {int(config.get('video.height', 1080))}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Narr,{family},{size},{st.get('primary_colour', '&H00FFFFFF')},&H000000FF,{st.get('outline_colour', '&H00000000')},&H80000000,0,0,0,0,100,100,0,0,1,{float(st.get('outline', 2.0)) * 2:.1f},{st.get('shadow', 1.0)},2,60,60,{int(st.get('margin_v', 60))},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for s in subs:
        text = str(s["text"]).replace("\n", " ").replace("{", "(").replace("}", ")")
        chunks = _split_lines(text, max_chars)
        total_chars = sum(len(c) for c in chunks) or 1
        dur = max(float(s["end"]) - float(s["start"]), 0.4)
        t = float(s["start"])
        for ch in chunks:
            dt = dur * len(ch) / total_chars
            lines.append(f"Dialogue: 0,{_ass_time(t)},{_ass_time(t + dt)},Narr,,0,0,0,,{ch}\n")
            t += dt
    out.write_text("".join(lines), encoding="utf-8")
    return out


# ---------- BGM ----------

def _pick_bgm() -> Path | None:
    d = config.get("bgm.directory")
    bgm_dir = Path(d) if d else Path(config.repo_root()) / "assets" / "bgm"
    if not bgm_dir.exists():
        return None
    files = [f for f in bgm_dir.iterdir()
             if f.suffix.lower() in {".mp3", ".wav", ".m4a", ".flac", ".ogg"}
             and not f.name.startswith(".")]
    return random.choice(files) if files else None


# ---------- 主流程 ----------

def run(topic_dir: Path) -> Path:
    timing = utils.read_json(topic_dir / "配音" / "timing.json")
    ed = utils.read_json(topic_dir / "edit_decision.json")
    if not timing or not ed:
        raise FileNotFoundError("缺少 timing.json 或 edit_decision.json (先跑 S4/S5)")
    src = next((f for f in (topic_dir / "素材").iterdir()
                if f.suffix.lower() in VIDEO_EXTS), None) \
        if (topic_dir / "素材").exists() else None
    if src is None:
        raise FileNotFoundError(f"缺少源视频: {topic_dir}/素材/")

    workdir = topic_dir / "成片工程"
    workdir.mkdir(parents=True, exist_ok=True)
    src_info = utils.probe_video(src)

    plan = plan_timeline(ed, timing, src_info["duration"])
    log.info("时间轴: %d 画面段, 总时长 %.1fs (%.1f 分钟)",
             len(plan["cuts"]), plan["total"], plan["total"] / 60)

    seg_files = cut_segments(src, plan["cuts"], workdir)
    picture = concat_segments(seg_files, workdir)
    voice_wav = build_voice_track(plan["voice"], topic_dir, plan["total"], workdir)
    ass = build_ass(plan["subs"], workdir / "subs.ass")

    # 终编码: 字幕烧录 + 配音/BGM 混音(闪避)
    codec, codec_args = _video_codec_args()
    total = plan["total"]
    fade = float(config.get("bgm.fade_out_seconds", 3.0))
    bgm_vol = float(config.get("bgm.volume", 0.12))
    duck = float(config.get("bgm.duck_ratio", 0.35))

    cmd = [config.ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
           "-i", picture, "-i", voice_wav]
    bgm = _pick_bgm() if config.get("bgm.enabled", True) else None
    if bgm:
        log.info("BGM: %s", bgm.name)
        cmd += ["-stream_loop", "-1", "-i", bgm]
        # BGM: 压到配置音量 → sidechaincompress 随解说闪避 → 尾部淡出
        ratio = round(bgm_vol / max(duck, 0.01), 2)  # 闪避后落在 duck*线性电平
        afilter = (f"[2:a]volume={ratio},"
                   f"sidechaincompress=threshold=0.02:ratio=6:attack=80:release=600:makeup=1[bgm];"
                   f"[bgm]afade=t=out:st={max(total - fade, 0):.2f}:d={fade}[bgmF];"
                   f"[1:a][bgmF]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]")
    else:
        afilter = "[1:a]anull[aout]"
    # ass 滤镜参数含 Windows 盘符冒号会被解析器截断 → cwd=workdir 用相对路径
    # 自定义字体未装系统 → fontsdir 指向工作目录内字体副本
    fonts_dir = _stage_font(workdir)
    cmd += ["-filter_complex", f"[0:v]ass=subs.ass:fontsdir={fonts_dir.name}[v];{afilter}",
            "-map", "[v]", "-map", "[aout]",
            "-c:v", codec, *codec_args, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total:.3f}", "-movflags", "+faststart",
            topic_dir / "成片.mp4"]
    p = utils.run(cmd, desc="终编码", timeout=3600, cwd=workdir)
    if p.returncode != 0:
        raise RuntimeError("终编码失败")

    report = {"total": total, "cuts": len(plan["cuts"]),
              "voice_count": len(plan["voice"]), "bgm": bgm.name if bgm else None,
              "codec": codec}
    utils.write_json(workdir / "render_report.json", report)
    log.info("成片完成: %s (%.1fs, %d 段, BGM=%s)",
             topic_dir / "成片.mp4", total, len(plan["cuts"]), bool(bgm))
    return topic_dir / "成片.mp4"
