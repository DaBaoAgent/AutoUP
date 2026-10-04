"""S1/S2 源核验与下载：精确记录字幕语言，下载失败可恢复，容器转换不伪装扩展名。"""
from __future__ import annotations

import csv
import logging
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import config, utils

log = logging.getLogger("autoup.s12")

YT_SUB_LANGS = ["en", "en-US", "en-GB", "en-orig"]
VIDEO_EXTS = {".mp4", ".mkv", ".webm"}


def _fix_curl_ca() -> None:
    import os
    import tempfile

    try:
        import certifi

        source = certifi.where()
    except ImportError:
        return
    try:
        str(source).encode("ascii")
        return
    except UnicodeEncodeError:
        pass

    destination = Path(tempfile.gettempdir()) / "autoup_cacert.pem"
    try:
        if not destination.exists() or destination.stat().st_size != Path(source).stat().st_size:
            shutil.copy(str(source), str(destination))
        os.environ.setdefault("CURL_CA_BUNDLE", str(destination))
        os.environ["SSL_CERT_FILE"] = str(destination)
    except OSError as exc:
        log.warning("CA 证书复制失败: %s", exc)


def _ensure_ffmpeg_on_path() -> None:
    import os

    ff_path = Path(config.ffmpeg())
    if ff_path.parent == Path("."):
        return
    ff_dir = str(ff_path.parent)
    current = os.environ.get("PATH", "")
    if ff_dir not in current.split(os.pathsep):
        os.environ["PATH"] = ff_dir + os.pathsep + current


def _base_opts() -> dict:
    _fix_curl_ca()
    _ensure_ffmpeg_on_path()
    proxy = config.get("download.proxy") or None
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 5,
        "continuedl": True,
        "socket_timeout": 30,
        **({"proxy": str(proxy)} if proxy else {}),
    }


def _choose_english_language(manual: set[str], automatic: set[str]) -> tuple[str, str]:
    def choose(pool: set[str]) -> str:
        for preferred in YT_SUB_LANGS:
            if preferred in pool:
                return preferred
        candidates = sorted(lang for lang in pool if lang.lower().startswith("en"))
        return candidates[0] if candidates else ""

    language = choose(manual)
    if language:
        return language, "manual"
    language = choose(automatic)
    if language:
        return language, "auto"
    return "", "none"


def fetch_meta(url: str) -> dict:
    import yt_dlp

    try:
        with yt_dlp.YoutubeDL(_base_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": url, "error": str(exc)[:300]}

    manual = set((info.get("subtitles") or {}).keys())
    automatic = set((info.get("automatic_captions") or {}).keys())
    sub_lang, sub_kind = _choose_english_language(manual, automatic)
    formats = info.get("formats") or []
    height = max((fmt.get("height") or 0) for fmt in formats) if formats else 0
    return {
        "ok": True,
        "url": url,
        "vid": info.get("id", ""),
        "title": info.get("title", ""),
        "channel": info.get("uploader") or info.get("channel") or "",
        "duration": float(info.get("duration") or 0),
        "height": int(height),
        "view_count": int(info.get("view_count") or 0),
        "upload_date": info.get("upload_date") or "",
        "has_en_sub": bool(sub_lang),
        "sub_kind": sub_kind,
        "sub_lang": sub_lang,
    }


def verify_url(url: str) -> dict:
    meta = fetch_meta(url)
    if not meta.get("ok"):
        return {**meta, "verdict": "reject", "reason": "无法获取元数据"}
    min_duration = int(config.get("download.min_duration", 1800))
    min_height = int(config.get("download.min_height", 720))
    if meta["duration"] < min_duration:
        return {
            **meta,
            "verdict": "reject",
            "reason": f"时长 {meta['duration']:.0f}s < {min_duration}s",
        }
    if meta["height"] < min_height:
        return {
            **meta,
            "verdict": "reject",
            "reason": f"最高 {meta['height']}p < {min_height}p",
        }
    if meta["sub_kind"] == "none":
        return {
            **meta,
            "verdict": "reject",
            "reason": "无英文字幕（只接受 YouTube 自带字幕）",
        }
    return {**meta, "verdict": "approve", "reason": "通过"}


def verify_batch(urls: list[str], report_csv: Path) -> list[dict]:
    workers = max(int(config.get("download.verify_workers", 4)), 1)
    if workers == 1 or len(urls) <= 1:
        rows = [verify_url(url) for url in urls]
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(urls))) as executor:
            rows = list(executor.map(verify_url, urls))

    report_csv.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "verdict",
        "reason",
        "url",
        "vid",
        "title",
        "channel",
        "duration",
        "height",
        "view_count",
        "upload_date",
        "sub_kind",
        "sub_lang",
        "has_en_sub",
        "error",
    ]
    with report_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    approved = [row for row in rows if row.get("verdict") == "approve"]
    log.info(
        "核验完成: %d 通过 / %d 拒绝，报告 %s",
        len(approved),
        len(rows) - len(approved),
        report_csv,
    )
    return approved


def _remux_to_mp4(video: Path) -> Path:
    if video.suffix.lower() == ".mp4":
        return video

    target = video.with_suffix(".mp4")
    if target.exists():
        target.unlink()
    copy_cmd = [
        config.ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        video,
        "-map",
        "0",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        target,
    ]
    proc = utils.run(copy_cmd, desc="封装为 mp4", timeout=1800)
    if proc.returncode != 0:
        if target.exists():
            target.unlink()
        transcode_cmd = [
            config.ffmpeg(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            video,
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            target,
        ]
        proc = utils.run(transcode_cmd, desc="转码为 mp4", timeout=7200)
    if proc.returncode != 0 or not target.exists():
        raise RuntimeError(f"无法生成有效 mp4: {video}")
    video.unlink()
    return target


def download_topic(url: str, topic_dir: Path, sub_lang: str | None = None) -> dict:
    import yt_dlp

    material = topic_dir / "素材"
    subtitle_dir = topic_dir / "字幕"
    material.mkdir(parents=True, exist_ok=True)
    subtitle_dir.mkdir(parents=True, exist_ok=True)

    max_height = int(config.get("download.max_height", 1080))
    subtitle_languages = [sub_lang] if sub_lang else YT_SUB_LANGS
    options = _base_opts() | {
        "outtmpl": str(material / "高清源视频.%(ext)s"),
        "format": (
            f"b[height<={max_height}][vcodec!=none][acodec!=none]/"
            f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={max_height}]+ba/"
            f"b[height<={max_height}]/b"
        ),
        "merge_output_format": "mp4",
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": subtitle_languages,
        "convert_subtitles": "srt",
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    video = next(
        (
            file
            for file in material.iterdir()
            if file.stem.startswith("高清源视频") and file.suffix.lower() in VIDEO_EXTS
        ),
        None,
    )
    if video is None:
        raise RuntimeError(f"下载后未找到视频: {topic_dir}")
    video = _remux_to_mp4(video)

    candidates = sorted(material.glob("*.srt"))
    if not candidates:
        vtt = next(iter(sorted(material.glob("*.vtt"))), None)
        if vtt:
            converted = vtt.with_suffix(".srt")
            proc = utils.run(
                [config.ffmpeg(), "-y", "-loglevel", "error", "-i", vtt, converted],
                desc="vtt→srt",
            )
            if proc.returncode == 0 and converted.exists():
                candidates = [converted]

    if not candidates:
        raise RuntimeError("下载后未找到字幕；字幕可能已被平台移除")

    selected = None
    if sub_lang:
        selected = next(
            (
                file
                for file in candidates
                if file.stem.lower().endswith("." + sub_lang.lower())
            ),
            None,
        )
    if selected is None:
        selected = next(
            (
                file
                for file in candidates
                if re.search(r"\.en(?:[-_.]|$)", file.stem, re.I)
            ),
            candidates[0],
        )

    subtitle = subtitle_dir / "字幕.srt"
    if subtitle.exists():
        subtitle.unlink()
    shutil.move(str(selected), str(subtitle))
    for extra in candidates:
        if extra.exists() and extra != selected:
            extra.unlink()

    log.info(
        "下载完成: %s (%.1f MB) + %s [%s]",
        video.name,
        video.stat().st_size / 1e6,
        subtitle.name,
        sub_lang or "auto",
    )
    return {"video": video, "subtitle": subtitle}


def read_manifest(path: Path) -> list[str]:
    urls: list[str] = []
    text = Path(path).read_text(encoding="utf-8-sig")
    if "," in text and not text.strip().startswith("http"):
        for row in csv.DictReader(text.splitlines()):
            url = (row.get("url") or row.get("URL") or "").strip()
            if url:
                urls.append(url)
    else:
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("http"):
                urls.append(line)
    return list(dict.fromkeys(urls))
