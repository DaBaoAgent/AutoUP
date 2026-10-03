"""阶段输入指纹：让断点续跑能识别上游内容或配置变化。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import config, utils

VIDEO_EXTS = {".mp4", ".mkv", ".webm"}


def _sig(path: Path) -> dict[str, Any]:
    return utils.file_fingerprint(path)


def _first_video(topic_dir: Path) -> Path | None:
    material = topic_dir / "素材"
    if not material.exists():
        return None
    return next((p for p in material.glob("高清源视频.*") if p.suffix.lower() in VIDEO_EXTS), None)


def _llm_descriptor() -> dict[str, Any]:
    return {
        "base_url": config.get("llm.base_url"),
        "model": config.get("llm.model"),
        "temperature": config.get("llm.temperature"),
        "max_retries": config.get("llm.max_retries"),
    }


def _cfg(*keys: str) -> dict[str, Any]:
    return {key: config.get(key) for key in keys}


def stage_fingerprint(topic_dir: Path, stage: str, *, voice: str = "default", url: str = "") -> str:
    topic_dir = Path(topic_dir)
    subtitle = topic_dir / "字幕" / "字幕.srt"
    script = topic_dir / "文案" / "爆款口播稿.txt"
    timing = topic_dir / "配音" / "timing.json"
    edit = topic_dir / "edit_decision.json"
    video = _first_video(topic_dir)
    payload: dict[str, Any] = {"version": 1, "stage": stage}

    if stage == "s2":
        payload.update({"url": url, "config": _cfg("download")})
    elif stage == "s3":
        payload.update({"subtitle": _sig(subtitle), "config": _cfg("script"), "llm": _llm_descriptor()})
    elif stage == "s4":
        payload.update(
            {
                "script": _sig(script),
                "voice_name": voice,
                "config": _cfg("voice"),
            }
        )
    elif stage == "s5":
        payload.update(
            {
                "subtitle": _sig(subtitle),
                "timing": _sig(timing),
                "config": _cfg("match", "voice.gap_seconds"),
                "llm": _llm_descriptor(),
            }
        )
    elif stage == "s6":
        payload.update(
            {
                "video": _sig(video) if video else {"exists": False},
                "timing": _sig(timing),
                "edit": _sig(edit),
                "config": _cfg("video", "subtitle", "bgm", "voice.gap_seconds"),
            }
        )
    elif stage == "s7":
        payload.update({"script": _sig(script), "llm": _llm_descriptor()})
    elif stage == "s8":
        payload.update(
            {
                "video": _sig(video) if video else {"exists": False},
                "edit": _sig(edit),
                "copy": _sig(topic_dir / "发布" / "封面文案.txt"),
                "config": _cfg("cover"),
            }
        )
    elif stage == "s9":
        payload.update(
            {
                "video": _sig(video) if video else {"exists": False},
                "subtitle": _sig(subtitle),
                "script": _sig(script),
                "timing": _sig(timing),
                "edit": _sig(edit),
                "final": _sig(topic_dir / "成片.mp4"),
                "cn": _sig(topic_dir / "发布" / "国内平台.txt"),
                "en": _sig(topic_dir / "发布" / "海外平台.txt"),
                "covers": {
                    name: _sig(topic_dir / "封面" / f"封面-{name}.png")
                    for name in ("9x16", "16x9", "1x1")
                },
                "config": _cfg("script", "video"),
            }
        )
    else:
        payload["unknown"] = True

    return utils.stable_hash(payload)
