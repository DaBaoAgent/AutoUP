"""一键全链路编排: manifest → S1核验 → S2下载 → S3文案 → S4配音 → S5匹配 → S6合成 → S7发布 → S8封面 → S9验收。

断点续传: 每个选题目录 state.json 记录阶段状态; 重跑自动跳过已完成阶段
(阶段成功即标记, 产物存在且 state 标记 done 就不再重做; --force 重跑指定阶段)。
用法:
  python -m autoup.run --manifest urls.txt --batch 20260908-A
  python -m autoup.run --manifest urls.txt --batch B --only s3,s4 --voice default
  python -m autoup.run --batch B --set download.max_height=360 --set script.target_chars=400
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import time
import traceback
from pathlib import Path

from . import config, utils
from .stages import cover, download, dub, match, publish, render, script, validate

log = logging.getLogger("autoup.run")

STAGES = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9"]


# ---------- state ----------

def _load_state(topic_dir: Path) -> dict:
    return utils.read_json(topic_dir / "state.json", default={}) or {}


def _save_state(topic_dir: Path, state: dict) -> None:
    state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    utils.write_json(topic_dir / "state.json", state)


def _stage_done(state: dict, stage: str, force: bool) -> bool:
    return not force and state.get("stages", {}).get(stage) == "done"


def _mark(topic_dir: Path, state: dict, stage: str, status: str = "done") -> None:
    state.setdefault("stages", {})[stage] = status
    _save_state(topic_dir, state)


# ---------- 选题命名 ----------

def _topic_name(url: str, meta: dict, idx: int) -> str:
    """LLM 把英文标题缩成 ≤10 字中文选题名, 失败退回 选题NN。"""
    try:
        from . import llm
        data = llm.chat_json(
            f"把以下纪录片标题浓缩为不超过10个汉字的中文选题名(用于文件夹名, 无标点空格):\n"
            f"{meta.get('title', '')}\n输出 JSON: {{\"name\": \"...\"}}", temperature=0.3)
        name = re.sub(r"[^\u4e00-\u9fff]", "", str(data.get("name", "")))[:10]
        if name:
            return f"{idx:02d}-{name}"
    except Exception as e:  # noqa: BLE001
        log.warning("选题命名失败: %s", e)
    return f"{idx:02d}-选题"


# ---------- 主流程 ----------

def process_topic(topic_dir: Path, only: list[str] | None, force: bool, voice: str) -> dict:
    """对单个选题目录跑完剩余阶段, 返回最终验收报告(或抛异常)。"""
    state = _load_state(topic_dir)
    stages = only or STAGES

    def todo(stage: str) -> bool:
        return stage in stages and not _stage_done(state, stage, force)

    if todo("s3"):
        script.run(topic_dir)
        _mark(topic_dir, state, "s3")
    if todo("s4"):
        dub.run(topic_dir, voice=voice)
        _mark(topic_dir, state, "s4")
    if todo("s5"):
        match.run(topic_dir)
        _mark(topic_dir, state, "s5")
    if todo("s6"):
        render.run(topic_dir)
        _mark(topic_dir, state, "s6")
    if todo("s7"):
        publish.run(topic_dir)
        _mark(topic_dir, state, "s7")
    if todo("s8"):
        cover.run(topic_dir)
        _mark(topic_dir, state, "s8")
    report = validate.run(topic_dir)
    _mark(topic_dir, state, "s9", "done" if report["passed"] else "failed")
    return report


def _ensure_downloaded(td: Path, url: str, state: dict, force: bool) -> None:
    """S2 幂等: 视频+字幕齐则标记完成, 缺则(续)下载。"""
    if _stage_done(state, "s2", force):
        return
    mat = td / "素材"
    has_video = mat.exists() and any(
        f.suffix.lower() in {".mp4", ".mkv", ".webm"}
        for f in mat.glob("高清源视频.*"))
    has_sub = (td / "字幕" / "字幕.srt").exists()
    if has_video and has_sub:
        _mark(td, state, "s2")
        return
    files = download.download_topic(url, td)
    state["video"] = files["video"].name
    _mark(td, state, "s2")


def run_batch(manifest: Path | None, batch: str, only: list[str] | None,
              force: bool, voice: str, limit: int | None) -> list[dict]:
    root = config.output_root() / batch
    root.mkdir(parents=True, exist_ok=True)

    # 已有选题目录 → 续跑模式
    existing = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_"))
    results: list[dict] = []

    if existing and manifest is None:
        log.info("续跑批次 %s: %d 个已有选题", batch, len(existing))
        for td in existing:
            state = _load_state(td)
            try:
                url = state.get("url")
                if url:
                    _ensure_downloaded(td, url, state, force)
                report = process_topic(td, only, force, voice)
                results.append({"topic": td.name, "passed": report["passed"]})
            except Exception as e:  # noqa: BLE001
                log.error("选题 %s 失败: %s", td.name, e)
                _mark(td, state, "error", f"failed: {str(e)[:200]}")
                results.append({"topic": td.name, "passed": False, "error": str(e)[:200]})
        return results

    if manifest is None:
        raise SystemExit("新批次需要 --manifest; 续跑则只给 --batch")

    urls = download.read_manifest(manifest)
    log.info("manifest: %d 个 URL", len(urls))
    report_csv = root / "_核验报告.csv"
    approved = download.verify_batch(urls, report_csv)
    if limit:
        approved = approved[:limit]

    for i, meta in enumerate(approved, 1):
        name = _topic_name(meta["url"], meta, i)
        td = root / name
        td.mkdir(parents=True, exist_ok=True)
        state = _load_state(td)
        state["url"] = meta["url"]
        state["meta"] = {k: meta.get(k) for k in
                         ("vid", "title", "channel", "duration", "height", "sub_kind")}
        try:
            _ensure_downloaded(td, meta["url"], state, force)
            report = process_topic(td, only, force, voice)
            results.append({"topic": name, "url": meta["url"], "passed": report["passed"]})
        except Exception as e:  # noqa: BLE001
            log.error("选题 %s 失败: %s\n%s", name, e, traceback.format_exc()[-1500:])
            _mark(td, state, "error", f"failed: {str(e)[:200]}")
            results.append({"topic": name, "url": meta["url"], "passed": False,
                            "error": str(e)[:200]})
    return results


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="autoup", description="AutoUP 纪录片解说全自动生产线")
    ap.add_argument("--manifest", type=Path, help="URL 清单(每行一个或 CSV)")
    ap.add_argument("--batch", required=True, help="批次名(产出根下的子目录)")
    ap.add_argument("--only", help="只跑指定阶段, 逗号分隔: s3,s4,s5")
    ap.add_argument("--force", action="store_true", help="强制重跑指定阶段")
    ap.add_argument("--voice", default="default", help="GPT-SoVITS 音色名(config)")
    ap.add_argument("--limit", type=int, help="本次最多处理几个选题")
    ap.add_argument("--set", dest="overrides", action="append", default=[],
                    help="运行期配置覆盖, 如 --set script.target_chars=400 (可多次)")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    for ov in args.overrides:
        key, _, val = ov.partition("=")
        node = config.load()
        parts = key.strip().split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        try:
            val = int(val)
        except ValueError:
            try:
                val = float(val)
            except ValueError:
                pass
        node[parts[-1]] = val
        log.info("配置覆盖: %s = %r", key, val)

    results = run_batch(args.manifest, args.batch,
                        [s.strip() for s in args.only.split(",")] if args.only else None,
                        args.force, args.voice, args.limit)
    print("\n===== 批次结果 =====")
    for r in results:
        print(("✅" if r.get("passed") else "❌"), r.get("topic"),
              r.get("error", ""))
    failed = [r for r in results if not r.get("passed")]
    print(f"\n完成: {len(results) - len(failed)}/{len(results)} 个选题通过验收")


if __name__ == "__main__":
    main()
