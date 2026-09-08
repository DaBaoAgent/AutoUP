"""S9 验收: 选题目录完整性 + 各产物规格校验 → 验收报告.json。"""
from __future__ import annotations

import logging
from pathlib import Path

from .. import config, utils

log = logging.getLogger("autoup.s9")

VIDEO_EXTS = {".mp4", ".mkv", ".webm"}


def run(topic_dir: Path) -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"item": name, "ok": bool(ok), "detail": detail})

    # 素材
    src = next((f for f in (topic_dir / "素材").glob("*") if f.suffix.lower() in VIDEO_EXTS), None)
    check("源视频", src is not None and src.stat().st_size > 1e6, str(src))

    # 字幕
    srt = topic_dir / "字幕" / "字幕.srt"
    cues = utils.parse_srt(srt) if srt.exists() else []
    check("字幕SRT", len(cues) > 10, f"{len(cues)} 条")

    # 文案
    script = topic_dir / "文案" / "爆款口播稿.txt"
    n_chars = 0
    if script.exists():
        import re
        n_chars = len(re.sub(r"\s", "", script.read_text(encoding="utf-8-sig")))
    lo = int(config.get("script.target_chars", 4500) * (1 - config.get("script.tolerance", 0.12)))
    check("解说文案", n_chars >= lo, f"{n_chars} 字 (下限 {lo})")

    # 配音
    timing = utils.read_json(topic_dir / "配音" / "timing.json") or {}
    sents = timing.get("sentences", [])
    missing_audio = [s["audio"] for s in sents
                     if not (topic_dir / "配音" / s["audio"]).exists()]
    check("配音timing", len(sents) > 0 and not missing_audio,
          f"{len(sents)} 句" + (f", 缺音频 {missing_audio[:3]}" if missing_audio else ""))

    # 匹配
    ed = utils.read_json(topic_dir / "edit_decision.json") or {}
    covered = {i.get("sentence_index") for i in ed.get("items", [])}
    check("画面匹配", len(covered) >= max(len(sents) - 1, 1),
          f"覆盖 {len(covered)}/{len(sents)} 句")

    # 成片
    final = topic_dir / "成片.mp4"
    if final.exists() and final.stat().st_size > 1e6:
        info = utils.probe_video(final)
        expect = float((ed.get("total_picture_duration") or 0)) or float(timing.get("total_duration") or 0)
        dur_ok = not expect or abs(info["duration"] - expect) < max(expect * 0.15, 5)
        res_ok = info["width"] == int(config.get("video.width", 1920)) and \
                 info["height"] == int(config.get("video.height", 1080))
        check("成片分辨率", res_ok, f"{info['width']}x{info['height']}")
        check("成片时长", dur_ok, f"{info['duration']:.0f}s vs 计划 {expect:.0f}s")
        check("成片音轨", info["has_audio"])
    else:
        check("成片", False, "文件缺失或过小")

    # 发布信息
    cn = topic_dir / "发布" / "国内平台.txt"
    if cn.exists():
        lines = [l for l in cn.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
        check("国内标题≤25字", len(lines) >= 1 and len(lines[0]) <= 25, f"{len(lines[0]) if lines else 0} 字符")
        check("国内标签5个", len(lines) >= 2 and len(lines[1].split()) == 5, lines[1] if len(lines) > 1 else "")
    else:
        check("国内平台.txt", False, "缺失")
    check("海外平台.txt", (topic_dir / "发布" / "海外平台.txt").exists())

    # 封面
    for name in ("9x16", "16x9", "1x1"):
        f = topic_dir / "封面" / f"封面-{name}.png"
        ok = f.exists() and f.stat().st_size > 50_000
        check(f"封面{name}", ok)

    report = {
        "topic": topic_dir.name,
        "passed": all(c["ok"] for c in checks),
        "failed": [c["item"] for c in checks if not c["ok"]],
        "checks": checks,
    }
    utils.write_json(topic_dir / "验收报告.json", report)
    ok_n = sum(c["ok"] for c in checks)
    log.info("验收: %d/%d 项通过%s — 失败: %s", ok_n, len(checks),
             " ✅" if report["passed"] else " ❌", report["failed"])
    return report
