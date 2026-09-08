"""S1/S2 源核验与下载 (yt-dlp)。

规则(docs/requirements.md #13/#14):
  - 半自动选题: 入口为人工提供的 URL 清单(manifest)
  - 只接受 YouTube 自带字幕(手动 en 优先, 自动 en 兜底), 无 en 字幕直接拒
  - 时长 ≥ min_duration 且最高分辨率 ≥ min_height 才接单
"""
from __future__ import annotations

import csv
import logging
import re
import shutil
from pathlib import Path

from .. import config, utils

log = logging.getLogger("autoup.s12")

YT_SUB_LANGS = ["en", "en-US", "en-GB", "en-orig"]


def _fix_curl_ca() -> None:
    """yt-dlp curl 后端在非 ASCII 路径下加载 certifi 失败(WinError curl:77),
    把 CA 串复制到纯 ASCII 路径并指给 curl/SSL。"""
    import os
    import shutil
    import tempfile
    try:
        import certifi
        src = certifi.where()
    except ImportError:
        return
    try:
        str(src).encode("ascii")
        return  # 路径已纯 ASCII, 无需处理
    except UnicodeEncodeError:
        pass
    dst = Path(tempfile.gettempdir()) / "autoup_cacert.pem"
    try:
        if not dst.exists() or dst.stat().st_size != Path(src).stat().st_size:
            shutil.copy(str(src), str(dst))
        os.environ.setdefault("CURL_CA_BUNDLE", str(dst))
        os.environ["SSL_CERT_FILE"] = str(dst)
    except OSError as e:
        log.warning("CA 证书复制失败: %s", e)


def _ensure_ffmpeg_on_path() -> None:
    """yt-dlp 合并格式需要能找到 ffmpeg。"""
    import os
    ff_dir = str(Path(config.ffmpeg()).parent)
    if ff_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ff_dir + os.pathsep + os.environ.get("PATH", "")


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


def fetch_meta(url: str) -> dict:
    """元数据探测(不下载)。返回 {ok, url, title, duration, height, has_en_sub, sub_kind, error}"""
    import yt_dlp
    opts = _base_opts()
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "url": url, "error": str(e)[:300]}
    manual = set((info.get("subtitles") or {}).keys())
    auto = set((info.get("automatic_captions") or {}).keys())

    def has_en(pool: set[str]) -> bool:
        return any(l.split("-")[0] == "en" for l in pool)

    formats = info.get("formats") or []
    height = max((f.get("height") or 0) for f in formats) if formats else 0
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
        "has_en_sub": has_en(manual),
        "sub_kind": "manual" if has_en(manual) else ("auto" if has_en(auto) else "none"),
    }


def verify_url(url: str) -> dict:
    """S1 单链接核验: 时长/分辨率/字幕门禁。"""
    meta = fetch_meta(url)
    if not meta.get("ok"):
        return {**meta, "verdict": "reject", "reason": "无法获取元数据"}
    min_dur = int(config.get("download.min_duration", 1800))
    min_h = int(config.get("download.min_height", 720))
    if meta["duration"] < min_dur:
        return {**meta, "verdict": "reject", "reason": f"时长 {meta['duration']:.0f}s < {min_dur}s"}
    if meta["height"] < min_h:
        return {**meta, "verdict": "reject", "reason": f"最高 {meta['height']}p < {min_h}p"}
    if meta["sub_kind"] == "none":
        return {**meta, "verdict": "reject", "reason": "无英文字幕(规则: 只接受 YouTube 自带字幕)"}
    return {**meta, "verdict": "approve", "reason": "通过"}


def verify_batch(urls: list[str], report_csv: Path) -> list[dict]:
    """S1 批量核验, 写 CSV 报告, 返回通过行。"""
    rows = [verify_url(u) for u in urls]
    report_csv.parent.mkdir(parents=True, exist_ok=True)
    cols = ["verdict", "reason", "url", "vid", "title", "channel", "duration",
            "height", "view_count", "upload_date", "sub_kind", "has_en_sub", "error"]
    with open(report_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    ok = [r for r in rows if r["verdict"] == "approve"]
    log.info("核验完成: %d 通过 / %d 拒绝, 报告 %s", len(ok), len(rows) - len(ok), report_csv)
    return ok


def _safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()[:80] or "untitled"


def download_topic(url: str, topic_dir: Path) -> dict:
    """S2 下载: 1080p 视频入 素材/, en 字幕转 srt 入 字幕/。返回 {video, subtitle}。"""
    import yt_dlp
    mat = topic_dir / "素材"
    sub_dir = topic_dir / "字幕"
    mat.mkdir(parents=True, exist_ok=True)
    sub_dir.mkdir(parents=True, exist_ok=True)
    mh = int(config.get("download.max_height", 1080))
    opts = _base_opts() | {
        "outtmpl": str(mat / "高清源视频.%(ext)s"),
        "format": (f"b[height<={mh}][vcodec!=none][acodec!=none]/"
                   f"bv*[height<={mh}][ext=mp4]+ba[ext=m4a]/"
                   f"bv*[height<={mh}]+ba/"
                   f"b[height<={mh}]/b"),
        "merge_output_format": "mp4",
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": YT_SUB_LANGS,
        "convert_subtitles": "srt",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    video = next((f for f in mat.iterdir()
                  if f.stem.startswith("高清源视频") and f.suffix.lower() in
                  {".mp4", ".mkv", ".webm"}), None)
    if video is None:
        raise RuntimeError(f"下载后未找到视频: {topic_dir}")
    if video.suffix.lower() != ".mp4":
        fix = video.with_suffix(".mp4")
        shutil.move(str(video), str(fix))
        video = fix

    srt_src = next((f for f in mat.iterdir() if f.suffix.lower() == ".srt"), None)
    if srt_src is None:
        # yt-dlp 中途失败会留下 vtt, 用 ffmpeg 兜底转换
        vtt = next((f for f in mat.iterdir() if f.suffix.lower() == ".vtt"), None)
        if vtt is not None:
            srt_src = vtt.with_suffix(".srt")
            p = utils.run([config.ffmpeg(), "-y", "-loglevel", "error", "-i", vtt, srt_src],
                          desc="vtt→srt")
            if p.returncode != 0:
                srt_src = None
    if srt_src is None:
        raise RuntimeError("下载后未找到字幕(核验时明明有——可能被平台移除)")
    # 多语言回退时保证拿到的是 en: 文件名形如 高清源视频.en.srt
    cands = [f for f in mat.iterdir() if f.suffix.lower() == ".srt"]
    srt_src = next((f for f in cands if f.stem.endswith(".en")), cands[0])
    srt_dst = sub_dir / "字幕.srt"
    shutil.move(str(srt_src), str(srt_dst))
    log.info("下载完成: %s (%.1f MB) + %s",
             video.name, video.stat().st_size / 1e6, srt_dst.name)
    return {"video": video, "subtitle": srt_dst}


def read_manifest(path: Path) -> list[str]:
    """manifest: 每行一个 URL (# 注释), 或 CSV 含 url 列。"""
    urls: list[str] = []
    text = Path(path).read_text(encoding="utf-8-sig")
    if "," in text and not text.strip().startswith("http"):
        for row in csv.DictReader(text.splitlines()):
            u = (row.get("url") or row.get("URL") or "").strip()
            if u:
                urls.append(u)
    else:
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith("http"):
                urls.append(line)
    return urls
