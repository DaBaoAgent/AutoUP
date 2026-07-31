#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


LEGACY_FIELDS = (
    "爆款标题：",
    "匹配标签：",
    "发布建议：",
    "版权提醒：",
    "封面正标题",
    "封面副标题",
)
EMOJI_RE = re.compile(
    "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF]"
)
HASHTAG_RE = re.compile(r"#[^\s#]+")


def validate_file(path: Path, root: Path) -> dict:
    issues: list[str] = []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()

    if len(lines) != 2:
        issues.append(f"physical line count is {len(lines)}, expected 2")
    if any(not line.strip() for line in lines):
        issues.append("blank line found")

    title = lines[0].strip() if lines else ""
    tag_line = lines[1].strip() if len(lines) >= 2 else ""

    if not title:
        issues.append("title missing")
    if len(title) > 25:
        issues.append(f"title length is {len(title)}, expected at most 25")
    if re.match(r"^(?:爆款)?标题[:：]", title):
        issues.append("title contains a field label")
    if EMOJI_RE.search(text):
        issues.append("emoji found")

    tag_tokens = tag_line.split()
    valid_tags = [token for token in tag_tokens if HASHTAG_RE.fullmatch(token)]
    if len(tag_tokens) != 5 or len(valid_tags) != 5:
        issues.append(
            f"valid hashtag count is {len(valid_tags)}, expected exactly 5"
        )

    found_legacy = [field for field in LEGACY_FIELDS if field in text]
    if found_legacy:
        issues.append("legacy fields: " + ", ".join(found_legacy))

    return {
        "file": str(path.relative_to(root)),
        "valid": not issues,
        "title": title,
        "title_length": len(title),
        "hashtag_count": len(valid_tags),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recursively validate AutoYY publication information files."
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"Root does not exist: {root}", file=sys.stderr)
        return 2

    files = sorted(root.rglob("发布信息.txt"))
    results = [validate_file(path, root) for path in files]
    summary = {
        "root": str(root),
        "file_count": len(results),
        "valid_count": sum(item["valid"] for item in results),
        "invalid_count": sum(not item["valid"] for item in results),
        "results": results,
    }

    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if results and summary["invalid_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
