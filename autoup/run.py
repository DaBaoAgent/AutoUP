"""AutoUP 一键流水线编排，支持可验证的断点续跑与精确阶段重跑。"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import time
import traceback
from pathlib import Path
from time import perf_counter

from . import config, state as stage_state, utils
from .stages import cover, download, dub, match, publish, render, script, validate

log = logging.getLogger("autoup.run")

STAGES = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9"]
TOPIC_STAGES = ["s3", "s4", "s5", "s6", "s7", "s8", "s9"]


def _load_state(topic_dir: Path) -> dict:
    return utils.read_json(topic_dir / "state.json", default={}) or {}


def _save_state(topic_dir: Path, state: dict) -> None:
    state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    utils.write_json(topic_dir / "state.json", state)


def _stage_artifacts_ok(topic_dir: Path, stage: str) -> bool:
    checks = {
        "s2": lambda: (topic_dir / "字幕" / "字幕.srt").exists()
        and any(
            file.suffix.lower() in {".mp4", ".mkv", ".webm"}
            for file in (topic_dir / "素材").glob("高清源视频.*")
        ),
        "s3": lambda: (topic_dir / "文案" / "爆款口播稿.txt").exists()
        and (topic_dir / "文案" / "爆款口播稿.txt").stat().st_size > 0,
        "s4": lambda: _timing_artifacts_ok(topic_dir),
        "s5": lambda: bool((utils.read_json(topic_dir / "edit_decision.json") or {}).get("items")),
        "s6": lambda: (topic_dir / "成片.mp4").exists()
        and (topic_dir / "成片.mp4").stat().st_size > 1_000_000,
        "s7": lambda: all(
            (topic_dir / "发布" / name).exists()
            for name in ("国内平台.txt", "海外平台.txt", "封面文案.txt")
        ),
        "s8": lambda: all(
            (topic_dir / "封面" / f"封面-{name}.png").exists()
            for name in ("9x16", "16x9", "1x1")
        ),
        "s9": lambda: (topic_dir / "验收报告.json").exists(),
    }
    try:
        return checks.get(stage, lambda: True)()
    except OSError:
        return False


def _timing_artifacts_ok(topic_dir: Path) -> bool:
    timing = utils.read_json(topic_dir / "配音" / "timing.json") or {}
    sentences = timing.get("sentences", [])
    return bool(sentences) and all(
        (topic_dir / "配音" / str(item.get("audio", ""))).exists()
        and (topic_dir / "配音" / str(item.get("audio", ""))).stat().st_size > 1024
        for item in sentences
    )


def _stage_done(
    topic_dir: Path,
    state: dict,
    stage: str,
    force: bool,
    *,
    voice: str = "default",
    url: str = "",
) -> bool:
    if force:
        return False
    entry = state.get("stages", {}).get(stage)
    if not isinstance(entry, dict) or entry.get("status") != "done":
        return False
    if not _stage_artifacts_ok(topic_dir, stage):
        log.warning("%s 已标记完成但产物不完整，将重新执行", stage.upper())
        return False
    current = stage_state.stage_fingerprint(topic_dir, stage, voice=voice, url=url)
    if entry.get("fingerprint") != current:
        log.info("%s 输入或配置已变化，旧断点失效", stage.upper())
        return False
    return True


def _mark(
    topic_dir: Path,
    state: dict,
    stage: str,
    status: str = "done",
    *,
    voice: str = "default",
    url: str = "",
    error: str | None = None,
) -> None:
    entry = {
        "status": status,
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if status == "done":
        entry["fingerprint"] = stage_state.stage_fingerprint(topic_dir, stage, voice=voice, url=url)
    if error:
        entry["error"] = error[:500]
    state.setdefault("stages", {})[stage] = entry
    _save_state(topic_dir, state)


def _record_metric(topic_dir: Path, state: dict, stage: str, seconds: float) -> None:
    state.setdefault("metrics", {})[stage] = {"seconds": round(seconds, 3)}
    _save_state(topic_dir, state)


def _topic_name(url: str, meta: dict, idx: int) -> str:
    del url
    try:
        from . import llm

        data = llm.chat_json(
            "把以下纪录片标题浓缩为不超过10个汉字的中文选题名(用于文件夹名, 无标点空格):\n"
            f"{meta.get('title', '')}\n输出 JSON: {{\"name\": \"...\"}}",
            temperature=0.3,
        )
        name = re.sub(r"[^\u4e00-\u9fff]", "", str(data.get("name", "")))[:10]
        if name:
            return f"{idx:02d}-{name}"
    except Exception as exc:  # noqa: BLE001
        log.warning("选题命名失败: %s", exc)
    return f"{idx:02d}-选题"


def _run_topic_stage(
    topic_dir: Path,
    state: dict,
    stage: str,
    action,
    *,
    force: bool,
    voice: str,
) -> None:
    if _stage_done(topic_dir, state, stage, force, voice=voice):
        return
    started = perf_counter()
    try:
        action()
    except Exception as exc:
        _mark(topic_dir, state, stage, "failed", voice=voice, error=str(exc))
        raise
    finally:
        _record_metric(topic_dir, state, stage, perf_counter() - started)
    _mark(topic_dir, state, stage, voice=voice)


def process_topic(topic_dir: Path, only: list[str] | None, force: bool, voice: str) -> dict:
    """执行 S3-S9；部分阶段运行成功不等价于完整验收通过。"""
    state = _load_state(topic_dir)
    selected = set(only or TOPIC_STAGES)

    actions = {
        "s3": lambda: script.run(topic_dir),
        "s4": lambda: dub.run(topic_dir, voice=voice),
        "s5": lambda: match.run(topic_dir),
        "s6": lambda: render.run(topic_dir),
        "s7": lambda: publish.run(topic_dir),
        "s8": lambda: cover.run(topic_dir),
    }
    for stage in TOPIC_STAGES[:-1]:
        if stage in selected:
            _run_topic_stage(topic_dir, state, stage, actions[stage], force=force, voice=voice)

    if "s9" not in selected:
        return {"passed": True, "partial": True, "stages": sorted(selected)}

    report: dict = {}
    started = perf_counter()
    try:
        report = validate.run(topic_dir)
    finally:
        _record_metric(topic_dir, state, "s9", perf_counter() - started)
    _mark(
        topic_dir,
        state,
        "s9",
        "done" if report.get("passed") else "failed",
        voice=voice,
        error=None if report.get("passed") else ", ".join(report.get("failed", [])),
    )
    return report


def _s2_ready(topic_dir: Path) -> bool:
    material = topic_dir / "素材"
    return (
        (topic_dir / "字幕" / "字幕.srt").exists()
        and material.exists()
        and any(
            file.suffix.lower() in {".mp4", ".mkv", ".webm"}
            for file in material.glob("高清源视频.*")
        )
    )


def _clear_s2_outputs(topic_dir: Path) -> None:
    material = topic_dir / "素材"
    if material.exists():
        for file in material.glob("高清源视频.*"):
            if file.is_file():
                file.unlink()
    subtitle = topic_dir / "字幕" / "字幕.srt"
    if subtitle.exists():
        subtitle.unlink()


def _ensure_downloaded(td: Path, url: str, state: dict, force: bool) -> None:
    if _stage_done(td, state, "s2", force, url=url):
        return

    existing_entry = state.get("stages", {}).get("s2")
    if _s2_ready(td) and not force and not isinstance(existing_entry, dict):
        log.info("S2 旧版断点无指纹，采用现有下载产物并写入新指纹")
        _mark(td, state, "s2", url=url)
        return

    if force or isinstance(existing_entry, dict):
        _clear_s2_outputs(td)

    started = perf_counter()
    try:
        meta = state.get("meta") or {}
        files = download.download_topic(url, td, sub_lang=meta.get("sub_lang"))
        state["video"] = files["video"].name
    except Exception as exc:
        _mark(td, state, "s2", "failed", url=url, error=str(exc))
        raise
    finally:
        _record_metric(td, state, "s2", perf_counter() - started)
    _mark(td, state, "s2", url=url)


def run_batch(
    manifest: Path | None,
    batch: str,
    only: list[str] | None,
    force: bool,
    voice: str,
    limit: int | None,
) -> list[dict]:
    root = config.output_root() / batch
    root.mkdir(parents=True, exist_ok=True)
    selected = set(only or STAGES)
    existing = sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith("_"))
    results: list[dict] = []

    if existing and manifest is None:
        if selected == {"s1"}:
            raise SystemExit("S1 是 manifest 级核验，续跑批次执行 S1 时必须提供 --manifest")
        log.info("续跑批次 %s: %d 个已有选题", batch, len(existing))
        for topic_dir in existing:
            state = _load_state(topic_dir)
            try:
                if "s2" in selected:
                    url = str(state.get("url") or "")
                    if not url:
                        raise RuntimeError("state.json 缺少源 URL，无法重跑 S2")
                    _ensure_downloaded(topic_dir, url, state, force)
                report = process_topic(topic_dir, only, force, voice)
                results.append({"topic": topic_dir.name, "passed": bool(report.get("passed", True))})
            except Exception as exc:  # noqa: BLE001
                log.error("选题 %s 失败: %s", topic_dir.name, exc)
                results.append({"topic": topic_dir.name, "passed": False, "error": str(exc)[:300]})
        return results

    if manifest is None:
        raise SystemExit("新批次需要 --manifest；续跑则只给 --batch")

    urls = download.read_manifest(manifest)
    log.info("manifest: %d 个 URL", len(urls))
    report_csv = root / "_核验报告.csv"
    approved = download.verify_batch(urls, report_csv)
    if limit:
        approved = approved[:limit]

    if selected == {"s1"}:
        return [{"topic": "_S1核验", "passed": True, "approved": len(approved), "total": len(urls)}]

    for index, meta in enumerate(approved, 1):
        name = _topic_name(meta["url"], meta, index)
        topic_dir = root / name
        topic_dir.mkdir(parents=True, exist_ok=True)
        state = _load_state(topic_dir)
        state["url"] = meta["url"]
        state["meta"] = {
            key: meta.get(key)
            for key in ("vid", "title", "channel", "duration", "height", "sub_kind", "sub_lang")
        }
        _save_state(topic_dir, state)
        try:
            if "s2" in selected:
                _ensure_downloaded(topic_dir, meta["url"], state, force)
            report = process_topic(topic_dir, only, force, voice)
            results.append(
                {
                    "topic": name,
                    "url": meta["url"],
                    "passed": bool(report.get("passed", True)),
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.error("选题 %s 失败: %s\n%s", name, exc, traceback.format_exc()[-1500:])
            results.append(
                {
                    "topic": name,
                    "url": meta["url"],
                    "passed": False,
                    "error": str(exc)[:300],
                }
            )
    return results


def _parse_override(value: str):
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"none", "null"}:
        return None
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="autoup", description="AutoUP 纪录片解说全自动生产线")
    parser.add_argument("--manifest", type=Path, help="URL 清单(每行一个或 CSV)")
    parser.add_argument("--batch", required=True, help="批次名(产出根下的子目录)")
    parser.add_argument("--only", help="只跑指定阶段，逗号分隔: s3,s4,s5")
    parser.add_argument("--force", action="store_true", help="强制重跑指定阶段")
    parser.add_argument("--allow-partial", action="store_true", help="批次存在失败项时仍返回退出码 0")
    parser.add_argument("--voice", default="default", help="GPT-SoVITS 音色名(config)")
    parser.add_argument("--limit", type=int, help="本次最多处理几个选题")
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        help="运行期配置覆盖，如 --set script.target_chars=400 (可多次)",
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    for override in args.overrides:
        key, sep, raw_value = override.partition("=")
        if not sep or not key.strip():
            parser.error(f"无效 --set: {override!r}，格式应为 key=value")
        node = config.load()
        parts = key.strip().split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        value = _parse_override(raw_value.strip())
        node[parts[-1]] = value
        log.info("配置覆盖: %s = %r", key, value)

    only = [stage.strip().lower() for stage in args.only.split(",") if stage.strip()] if args.only else None
    invalid = sorted(set(only or []) - set(STAGES))
    if invalid:
        parser.error(f"未知阶段: {', '.join(invalid)}；可选值: {', '.join(STAGES)}")

    results = run_batch(args.manifest, args.batch, only, args.force, args.voice, args.limit)
    print("\n===== 批次结果 =====")
    for result in results:
        print(("✅" if result.get("passed") else "❌"), result.get("topic"), result.get("error", ""))
    failed = [result for result in results if not result.get("passed")]
    print(f"\n完成: {len(results) - len(failed)}/{len(results)} 个任务成功")
    if failed and not args.allow_partial:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
