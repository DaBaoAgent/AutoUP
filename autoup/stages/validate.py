"""S9 验收：只要关键契约有一项不满足就失败。"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from PIL import Image

from .. import config, utils

log = logging.getLogger("autoup.s9")

VIDEO_EXTS = {".mp4", ".mkv", ".webm"}
BANNED_PATTERNS = (
    r"【开场钩子】",
    r"【核心悬念】",
    r"【结尾升华】",
    r"镜头切到",
    r"画面来到",
    r"点赞",
    r"关注我",
    r"转发给",
)


def run(topic_dir: Path) -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"item": name, "ok": bool(ok), "detail": detail})

    material = topic_dir / "素材"
    source = next(
        (
            file
            for file in material.glob("*")
            if file.suffix.lower() in VIDEO_EXTS
        ),
        None,
    )
    source_ok = source is not None and source.stat().st_size > 1_000_000
    check("源视频", source_ok, str(source) if source else "缺失")

    srt_path = topic_dir / "字幕" / "字幕.srt"
    cues = utils.parse_srt(srt_path) if srt_path.exists() else []
    check("字幕SRT", len(cues) > 10, f"{len(cues)} 条")

    script_path = topic_dir / "文案" / "爆款口播稿.txt"
    script_text = (
        script_path.read_text(encoding="utf-8-sig") if script_path.exists() else ""
    )
    script_chars = len(re.sub(r"\s", "", script_text))
    target = int(config.get("script.target_chars", 4500))
    tolerance = float(config.get("script.tolerance", 0.12))
    lower = int(target * (1 - tolerance))
    upper = int(target * (1 + tolerance))
    banned = [
        pattern for pattern in BANNED_PATTERNS if re.search(pattern, script_text)
    ]
    check(
        "解说文案字数",
        lower <= script_chars <= upper,
        f"{script_chars} 字，要求 {lower}-{upper}",
    )
    check(
        "解说文案无生产标签",
        not banned,
        "命中: " + ", ".join(banned) if banned else "",
    )

    timing = utils.read_json(topic_dir / "配音" / "timing.json") or {}
    sentences = timing.get("sentences", [])
    missing_audio = []
    missing_fingerprints = []
    for sentence in sentences:
        audio = topic_dir / "配音" / str(sentence.get("audio", ""))
        if not audio.exists() or audio.stat().st_size <= 1024:
            missing_audio.append(str(sentence.get("audio", "")))
        if not sentence.get("fingerprint"):
            missing_fingerprints.append(int(sentence.get("index", 0) or 0))
    check(
        "配音timing",
        bool(sentences) and not missing_audio,
        f"{len(sentences)} 句"
        + (f"，缺音频 {missing_audio[:3]}" if missing_audio else ""),
    )
    check(
        "配音缓存指纹",
        bool(sentences) and not missing_fingerprints,
        f"缺指纹句 {missing_fingerprints[:5]}" if missing_fingerprints else "",
    )

    edit = utils.read_json(topic_dir / "edit_decision.json") or {}
    items = edit.get("items", [])
    expected = {int(sentence.get("index", 0)) for sentence in sentences}
    covered = {int(item.get("sentence_index", 0)) for item in items}
    one_to_one = len(items) == len(sentences) and covered == expected
    chronological = True
    previous_end = -1.0
    for item in items:
        start = float(item.get("start", -1))
        end = float(item.get("end", -1))
        if start < previous_end or end <= start:
            chronological = False
            break
        previous_end = end
    check(
        "画面匹配全覆盖",
        bool(sentences)
        and one_to_one
        and not edit.get("uncovered_sentences"),
        f"覆盖 {len(covered)}/{len(sentences)} 句",
    )
    check("画面时间轴递增无重叠", chronological)

    final = topic_dir / "成片.mp4"
    if final.exists() and final.stat().st_size > 1_000_000:
        info = utils.probe_video(final)
        expected_duration = float(timing.get("total_duration") or 0)
        duration_ok = (
            not expected_duration
            or abs(info["duration"] - expected_duration)
            < max(expected_duration * 0.20, 8)
        )
        resolution_ok = (
            info["width"] == int(config.get("video.width", 1920))
            and info["height"] == int(config.get("video.height", 1080))
        )
        check(
            "成片分辨率",
            resolution_ok,
            f"{info['width']}x{info['height']}",
        )
        check(
            "成片时长",
            duration_ok,
            f"{info['duration']:.1f}s vs 配音 {expected_duration:.1f}s",
        )
        check("成片音轨", bool(info["has_audio"]))
    else:
        check("成片文件", False, "缺失或过小")

    cn_path = topic_dir / "发布" / "国内平台.txt"
    if cn_path.exists():
        lines = [
            line.strip()
            for line in cn_path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        title = lines[0] if lines else ""
        tags = lines[1].split() if len(lines) >= 2 else []
        valid_tags = [
            tag for tag in tags if re.fullmatch(r"#[^\s#]+", tag)
        ]
        check(
            "国内标题",
            bool(title) and len(title) <= 25 and "#" not in title,
            f"{len(title)} 字符",
        )
        check(
            "国内标签",
            len(tags) == 5
            and len(valid_tags) == 5
            and len(set(tags)) == 5,
            " ".join(tags),
        )
    else:
        check("国内平台.txt", False, "缺失")

    en_path = topic_dir / "发布" / "海外平台.txt"
    if en_path.exists():
        en_lines = [
            line.strip()
            for line in en_path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        en_title = en_lines[0] if en_lines else ""
        en_text = " ".join(en_lines)
        check(
            "海外平台信息",
            bool(en_title)
            and len(en_title) <= 90
            and not re.search(r"[\u4e00-\u9fff]", en_text),
            f"标题 {len(en_title)} 字符",
        )
    else:
        check("海外平台.txt", False, "缺失")

    expected_sizes = {
        "9x16": (1080, 1920),
        "16x9": (1920, 1080),
        "1x1": (1080, 1080),
    }
    for name, expected_size in expected_sizes.items():
        cover = topic_dir / "封面" / f"封面-{name}.png"
        size = None
        if cover.exists() and cover.stat().st_size > 50_000:
            try:
                with Image.open(cover) as image:
                    size = image.size
            except OSError:
                size = None
        check(
            f"封面{name}",
            size == expected_size,
            f"{size}，要求 {expected_size}",
        )

    report = {
        "topic": topic_dir.name,
        "passed": all(item["ok"] for item in checks),
        "failed": [item["item"] for item in checks if not item["ok"]],
        "checks": checks,
    }
    utils.write_json(topic_dir / "验收报告.json", report)
    passed = sum(item["ok"] for item in checks)
    log.info(
        "验收: %d/%d 项通过%s",
        passed,
        len(checks),
        " ✅" if report["passed"] else f" ❌ {report['failed']}",
    )
    return report
