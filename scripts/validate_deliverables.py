#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
BANNED_PATTERNS = [
    r"【开场钩子】",
    r"【核心悬念】",
    r"【推进",
    r"【结尾升华】",
    r"【补充叙事】",
    r"镜头切到",
    r"画面来到",
    r"这段视频最容易",
    r"回看整条因果链",
    r"前面三条线索共同指向",
    r"点赞",
    r"关注我",
    r"转发给",
]


def image_size(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as handle:
        head = handle.read(32)
        if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
            return struct.unpack(">II", head[16:24])
        if head[:2] != b"\xff\xd8":
            return None
        handle.seek(2)
        while True:
            marker_start = handle.read(1)
            if not marker_start:
                return None
            if marker_start != b"\xff":
                continue
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if marker in {b"\xd8", b"\xd9"}:
                continue
            length_data = handle.read(2)
            if len(length_data) != 2:
                return None
            length = struct.unpack(">H", length_data)[0]
            if marker and marker[0] in {
                0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
            }:
                payload = handle.read(5)
                if len(payload) != 5:
                    return None
                height, width = struct.unpack(">HH", payload[1:5])
                return width, height
            handle.seek(length - 2, 1)


def find_cover(folder: Path, stem: str) -> Path | None:
    for extension in IMAGE_EXTENSIONS:
        candidate = folder / f"{stem}{extension}"
        if candidate.exists():
            return candidate
    return None


def duplicate_paragraphs(text: str) -> list[str]:
    paragraphs = [
        re.sub(r"\s+", " ", item.strip())
        for item in re.split(r"\r?\n\s*\r?\n", text)
        if item.strip()
    ]
    seen: set[str] = set()
    duplicates: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) >= 50 and paragraph in seen:
            duplicates.append(paragraph[:80])
        seen.add(paragraph)
    return duplicates


def validate_topic(folder: Path, min_script_chars: int, max_script_chars: int) -> dict:
    issues: list[str] = []
    videos = [
        item for item in folder.iterdir()
        if item.is_file()
        and item.stem == "高清源视频"
        and item.suffix.lower() in VIDEO_EXTENSIONS
        and item.stat().st_size > 0
    ]
    subtitles = [
        item for item in folder.glob("*.srt")
        if item.is_file() and item.stat().st_size > 0
    ]
    if len(videos) != 1:
        issues.append(f"primary video count is {len(videos)}, expected 1")
    if not subtitles:
        issues.append("subtitle SRT missing")

    publish_path = folder / "发布信息.txt"
    script_path = folder / "爆款口播稿.txt"
    superseded_scripts = sorted(
        item.name
        for item in folder.iterdir()
        if item.is_file()
        and (
            item.name == "爆款钩子文案.txt"
            or (
                item.name.startswith("爆款口播稿-")
                and item.suffix.lower() == ".txt"
            )
        )
    )
    if superseded_scripts:
        issues.append(
            "superseded voiceover files remain: "
            + ", ".join(superseded_scripts)
        )
    if not publish_path.exists() or publish_path.stat().st_size == 0:
        issues.append("发布信息.txt missing or empty")
    else:
        publish_text = publish_path.read_text(encoding="utf-8-sig", errors="replace")
        lines = [line.strip() for line in publish_text.splitlines() if line.strip()]
        if len(lines) != 2:
            issues.append(
                f"publication non-empty line count is {len(lines)}, expected 2"
            )
        if lines:
            title = lines[0]
            if len(title) > 25:
                issues.append(
                    f"publication title length is {len(title)}, expected at most 25"
                )
            if re.match(r"^(?:爆款)?标题[:：]", title):
                issues.append("publication title must not include a field label")
        if len(lines) >= 2:
            tag_tokens = lines[1].split()
            valid_tags = [
                token for token in tag_tokens
                if re.fullmatch(r"#[^\s#]+", token)
            ]
            if len(tag_tokens) != 5 or len(valid_tags) != 5:
                issues.append(
                    f"hashtag count is {len(valid_tags)}, expected exactly 5 "
                    "space-separated hashtags on line 2"
                )
        else:
            issues.append("publication hashtag line missing")

    script_chars = 0
    if not script_path.exists() or script_path.stat().st_size == 0:
        issues.append("爆款口播稿.txt missing or empty")
    else:
        script_text = script_path.read_text(encoding="utf-8-sig", errors="replace")
        script_chars = len(re.sub(r"\s+", "", script_text))
        if script_chars < min_script_chars or script_chars > max_script_chars:
            issues.append(
                f"script non-whitespace characters {script_chars}, "
                f"expected {min_script_chars}-{max_script_chars}"
            )
        matches = [
            pattern for pattern in BANNED_PATTERNS
            if re.search(pattern, script_text)
        ]
        if matches:
            issues.append("banned voiceover patterns: " + ", ".join(matches))
        duplicates = duplicate_paragraphs(script_text)
        if duplicates:
            issues.append(f"duplicate long paragraphs: {len(duplicates)}")

    cover_results = {}
    for stem, expected_ratio in (("封面-3比4", 3 / 4), ("封面-4比3", 4 / 3)):
        cover = find_cover(folder, stem)
        if cover is None or cover.stat().st_size == 0:
            issues.append(f"{stem} missing or empty")
            cover_results[stem] = None
            continue
        size = image_size(cover)
        if size is None:
            issues.append(f"{cover.name} dimensions unreadable")
            cover_results[stem] = None
            continue
        width, height = size
        ratio = width / height
        ok = abs(ratio - expected_ratio) <= 0.01
        if not ok:
            issues.append(
                f"{cover.name} ratio {ratio:.4f}, expected {expected_ratio:.4f}"
            )
        cover_results[stem] = {
            "file": cover.name,
            "width": width,
            "height": height,
            "ratio_ok": ok,
        }

    return {
        "folder": folder.name,
        "complete": not issues,
        "issues": issues,
        "script_chars": script_chars,
        "video_count": len(videos),
        "subtitle_count": len(subtitles),
        "covers": cover_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate documentary topic deliverable folders."
    )
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--min-script-chars", type=int, default=4500)
    parser.add_argument("--max-script-chars", type=int, default=5500)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    root = args.output_root.resolve()
    if not root.is_dir():
        print(f"Output root does not exist: {root}", file=sys.stderr)
        return 2

    folders = sorted(
        item for item in root.iterdir()
        if item.is_dir() and re.match(r"^\d{2}-", item.name)
    )
    results = [
        validate_topic(folder, args.min_script_chars, args.max_script_chars)
        for folder in folders
    ]
    summary = {
        "output_root": str(root),
        "topic_count": len(results),
        "complete_count": sum(item["complete"] for item in results),
        "incomplete_count": sum(not item["complete"] for item in results),
        "results": results,
    }

    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if summary["incomplete_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
