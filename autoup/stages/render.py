"""S6 合成：剪切画面、配音、字幕与 BGM，严格要求 S5 已覆盖全部句子。"""
from __future__ import annotations

import logging
from pathlib import Path

from .. import config, utils

log = logging.getLogger("autoup.s6")

VIDEO_EXTS = {".mp4", ".mkv", ".webm"}
SEG_BASENAME = "seg_{:04d}.mp4"


def plan_timeline(ed: dict, timing: dict, source_duration: float) -> dict:
    gap = float(config.get("voice.gap_seconds", 0.3))
    sentences = {int(item["index"]): item for item in timing["sentences"]}
    items = sorted(ed["items"], key=lambda item: item["start"])
    covered = {int(item["sentence_index"]) for item in items}
    missing = sorted(set(sentences) - covered)
    if missing:
        raise ValueError(f"S6 拒绝渲染：S5 仍缺少句子 {missing[:20]}")
    if len(items) != len(sentences):
        raise ValueError("S6 拒绝渲染：必须满足一语句一画面")

    cuts: list[dict] = []
    voice: list[dict] = []
    subtitles: list[dict] = []
    cursor = 0.0

    for item in items:
        sentence_index = int(item["sentence_index"])
        sentence = sentences[sentence_index]
        src_start = max(float(item["start"]), 0.0)
        src_end = min(float(item["end"]) + gap, source_duration)
        if src_end - src_start < 0.3:
            raise ValueError(f"第 {sentence_index} 句画面段过短")

        out_start = cursor
        out_end = cursor + (src_end - src_start)
        cuts.append(
            {
                "src_start": round(src_start, 3),
                "src_end": round(src_end, 3),
                "out_start": round(out_start, 3),
                "out_end": round(out_end, 3),
            }
        )
        voice.append(
            {
                "index": sentence_index,
                "text": sentence["text"],
                "audio": sentence["audio"],
                "t_start": round(out_start, 3),
                "duration": float(sentence["duration"]),
            }
        )
        subtitles.append(
            {
                "start": round(out_start, 3),
                "end": round(out_start + float(sentence["duration"]), 3),
                "text": sentence["text"],
            }
        )
        cursor = out_end

    return {
        "cuts": cuts,
        "voice": voice,
        "subs": subtitles,
        "total": round(cursor, 3),
    }


def _video_codec_args() -> tuple[str, list[str]]:
    crf = str(config.get("video.crf", 18))
    preset = str(config.get("video.preset", "medium"))
    if config.get("video.prefer_gpu", True) and utils.nvenc_available():
        return "h264_nvenc", ["-preset", "p5", "-rc", "vbr", "-cq", crf, "-b:v", "0"]
    return "libx264", ["-preset", preset, "-crf", crf]


def cut_segments(src: Path, cuts: list[dict], workdir: Path) -> list[Path]:
    codec, codec_args = _video_codec_args()
    width = int(config.get("video.width", 1920))
    height = int(config.get("video.height", 1080))
    fps = str(config.get("video.fps", 30))
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
    )
    files: list[Path] = []
    for index, cut in enumerate(cuts, 1):
        output = workdir / SEG_BASENAME.format(index)
        command = [
            config.ffmpeg(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            cut["src_start"],
            "-to",
            cut["src_end"],
            "-i",
            src,
            "-an",
            "-vf",
            video_filter,
            "-c:v",
            codec,
            *codec_args,
            "-pix_fmt",
            "yuv420p",
            "-avoid_negative_ts",
            "make_zero",
            output,
        ]
        proc = utils.run(command, desc=f"剪切段 {index}/{len(cuts)}", timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(f"段 {index} 剪切失败")
        files.append(output)
    return files


def _concat_entry(path: Path) -> str:
    escaped = path.as_posix().replace("'", r"'\''")
    return f"file '{escaped}'\n"


def concat_segments(files: list[Path], workdir: Path) -> Path:
    if not files:
        raise ValueError("没有可拼接的画面段")
    listing = workdir / "concat.txt"
    listing.write_text("".join(_concat_entry(file) for file in files), encoding="utf-8")
    output = workdir / "picture.mp4"
    proc = utils.run(
        [
            config.ffmpeg(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            listing,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            output,
        ],
        desc="拼接画面",
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError("画面拼接失败")
    return output


def build_voice_track(voice: list[dict], topic_dir: Path, total: float, workdir: Path) -> Path:
    utils.ensure_pydub_ffmpeg()
    from pydub import AudioSegment

    base = AudioSegment.silent(duration=int(total * 1000) + 500, frame_rate=44100)
    base = base.set_frame_rate(44100).set_channels(2)
    for item in voice:
        wav = topic_dir / "配音" / item["audio"]
        if not wav.exists():
            raise FileNotFoundError(f"缺少配音文件: {wav}")
        segment = AudioSegment.from_file(str(wav)).set_frame_rate(44100).set_channels(2)
        base = base.overlay(segment, position=max(int(item["t_start"] * 1000), 0))
    output = workdir / "voice_full.wav"
    base.export(str(output), format="wav")
    return output


def _ass_time(value: float) -> str:
    hours = int(value // 3600)
    minutes = int(value % 3600 // 60)
    seconds = value % 60
    return f"{hours:d}:{minutes:02d}:{seconds:05.2f}"


def _resolve_font(raw: str | None) -> Path:
    if raw:
        path = Path(str(raw)).expanduser()
        if not path.is_absolute():
            path = config.repo_root() / path
        if path.exists():
            return path
    bundled = config.repo_root() / "assets" / "fonts" / "05_江西拙楷.ttf"
    if bundled.exists():
        return bundled
    raise FileNotFoundError("找不到字幕字体，请在 subtitle.font_path 配置有效字体")


def _font_family(path: Path) -> str:
    try:
        from PIL import ImageFont

        return ImageFont.truetype(str(path), 20).getname()[0]
    except Exception:  # noqa: BLE001
        return "Microsoft YaHei"


def _stage_font(workdir: Path) -> Path:
    import os
    import shutil

    source = _resolve_font(config.get("subtitle.font_path") or config.get("cover.font_path"))
    fonts_dir = workdir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    target = fonts_dir / "subtitle.ttf"
    if not target.exists() or target.stat().st_size != source.stat().st_size:
        if target.exists():
            target.unlink()
        try:
            os.link(source, target)
        except OSError:
            shutil.copy(str(source), str(target))
    return fonts_dir


def _split_lines(text: str, max_chars: int) -> list[str]:
    punctuation = "，。！？；：、,.!?;:…—“”‘’()（）[]【】《》<>\"'~～·"
    phrases = [part for part in re_split(text) if part]
    lines: list[str] = []
    buffer = ""
    for raw in phrases:
        phrase = "".join(char for char in raw if char not in punctuation)
        if not phrase:
            continue
        while len(phrase) > max_chars:
            if buffer:
                lines.append(buffer)
                buffer = ""
            lines.append(phrase[:max_chars])
            phrase = phrase[max_chars:]
        if len(buffer) + len(phrase) <= max_chars:
            buffer += phrase
        else:
            if buffer:
                lines.append(buffer)
            buffer = phrase
    if buffer:
        lines.append(buffer)
    return lines or [text]


def re_split(text: str) -> list[str]:
    import re

    return re.split(r"[，。！？；：、,.!?;:…]", text)


def build_ass(subs: list[dict], out: Path) -> Path:
    subtitle_config = config.get("subtitle", {}) or {}
    font_path = _resolve_font(
        subtitle_config.get("font_path") or config.get("cover.font_path")
    )
    family = _font_family(font_path)
    size = int(subtitle_config.get("font_size", 85))
    max_chars = int(subtitle_config.get("max_chars_per_line", 15))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {int(config.get('video.width', 1920))}
PlayResY: {int(config.get('video.height', 1080))}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Narr,{family},{size},{subtitle_config.get('primary_colour', '&H00FFFFFF')},&H000000FF,{subtitle_config.get('outline_colour', '&H00000000')},&H80000000,0,0,0,0,100,100,0,0,1,{float(subtitle_config.get('outline', 2.0)) * 2:.1f},{subtitle_config.get('shadow', 1.0)},2,60,60,{int(subtitle_config.get('margin_v', 60))},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for subtitle in subs:
        text = str(subtitle["text"]).replace("\n", " ").replace("{", "(").replace("}", ")")
        chunks = _split_lines(text, max_chars)
        total_chars = sum(len(chunk) for chunk in chunks) or 1
        duration = max(float(subtitle["end"]) - float(subtitle["start"]), 0.4)
        cursor = float(subtitle["start"])
        for chunk in chunks:
            chunk_duration = duration * len(chunk) / total_chars
            lines.append(
                f"Dialogue: 0,{_ass_time(cursor)},{_ass_time(cursor + chunk_duration)},Narr,,0,0,0,,{chunk}\n"
            )
            cursor += chunk_duration
    out.write_text("".join(lines), encoding="utf-8")
    return out


def _pick_bgm(topic_dir: Path) -> Path | None:
    configured = config.get("bgm.directory")
    bgm_dir = Path(str(configured)).expanduser() if configured else config.repo_root() / "assets" / "bgm"
    if configured and not bgm_dir.is_absolute():
        bgm_dir = config.repo_root() / bgm_dir
    if not bgm_dir.exists():
        return None

    files = sorted(
        file
        for file in bgm_dir.iterdir()
        if file.suffix.lower() in {".mp3", ".wav", ".m4a", ".flac", ".ogg"}
        and not file.name.startswith(".")
    )
    if not files:
        return None

    pick = str(config.get("bgm.pick", "random") or "random")
    if pick != "random":
        exact = bgm_dir / pick
        if not exact.exists():
            raise FileNotFoundError(f"指定 BGM 不存在: {exact}")
        return exact

    index = int(utils.stable_hash(topic_dir.name)[:12], 16) % len(files)
    return files[index]


def run(topic_dir: Path) -> Path:
    timing = utils.read_json(topic_dir / "配音" / "timing.json")
    edit = utils.read_json(topic_dir / "edit_decision.json")
    if not timing or not edit:
        raise FileNotFoundError("缺少 timing.json 或 edit_decision.json（先跑 S4/S5）")

    material = topic_dir / "素材"
    source = next(
        (file for file in material.iterdir() if file.suffix.lower() in VIDEO_EXTS),
        None,
    ) if material.exists() else None
    if source is None:
        raise FileNotFoundError(f"缺少源视频: {material}")

    workdir = topic_dir / "成片工程"
    workdir.mkdir(parents=True, exist_ok=True)
    source_info = utils.probe_video(source)
    plan = plan_timeline(edit, timing, source_info["duration"])
    log.info("时间轴: %d 段，总时长 %.1f 分钟", len(plan["cuts"]), plan["total"] / 60)

    segment_files = cut_segments(source, plan["cuts"], workdir)
    picture = concat_segments(segment_files, workdir)
    voice_wav = build_voice_track(plan["voice"], topic_dir, plan["total"], workdir)
    build_ass(plan["subs"], workdir / "subs.ass")

    codec, codec_args = _video_codec_args()
    total = plan["total"]
    fade = float(config.get("bgm.fade_out_seconds", 3.0))
    bgm_volume = float(config.get("bgm.volume", 0.12))
    duck = float(config.get("bgm.duck_ratio", 0.35))

    command = [
        config.ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        picture,
        "-i",
        voice_wav,
    ]
    bgm = _pick_bgm(topic_dir) if config.get("bgm.enabled", True) else None
    if bgm:
        log.info("BGM: %s", bgm.name)
        command += ["-stream_loop", "-1", "-i", bgm]
        pre_volume = round(bgm_volume / max(duck, 0.01), 2)
        audio_filter = (
            f"[2:a]volume={pre_volume},"
            "sidechaincompress=threshold=0.02:ratio=6:attack=80:release=600:makeup=1[bgm];"
            f"[bgm]afade=t=out:st={max(total - fade, 0):.2f}:d={fade}[bgmF];"
            "[1:a][bgmF]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
        )
    else:
        audio_filter = "[1:a]anull[aout]"

    fonts_dir = _stage_font(workdir)
    output = topic_dir / "成片.mp4"
    command += [
        "-filter_complex",
        f"[0:v]ass=subs.ass:fontsdir={fonts_dir.name}[v];{audio_filter}",
        "-map",
        "[v]",
        "-map",
        "[aout]",
        "-c:v",
        codec,
        *codec_args,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-t",
        f"{total:.3f}",
        "-movflags",
        "+faststart",
        output,
    ]
    proc = utils.run(command, desc="终编码", timeout=3600, cwd=workdir)
    if proc.returncode != 0:
        raise RuntimeError("终编码失败")

    utils.write_json(
        workdir / "render_report.json",
        {
            "total": total,
            "cuts": len(plan["cuts"]),
            "voice_count": len(plan["voice"]),
            "bgm": bgm.name if bgm else None,
            "codec": codec,
        },
    )
    log.info("S6 完成: %s", output)
    return output
