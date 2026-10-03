"""TTS 统一入口：主引擎失败后自动降级备用引擎。"""
from __future__ import annotations

import logging
from pathlib import Path

from .. import config
from . import edge, gpt_sovits

log = logging.getLogger("autoup.tts")


def synth(text: str, out_path: Path, voice: str = "default") -> tuple[Path | None, str]:
    engines = [str(config.get("voice.engine", "gpt_sovits"))]
    fallback = config.get("voice.fallback_engine", "edge_tts")
    if fallback and str(fallback) not in engines:
        engines.append(str(fallback))

    for name in engines:
        if name == "gpt_sovits":
            voices = config.get("voice.gpt_sovits.voices", {}) or {}
            voice_cfg = voices.get(voice) or {}
            if not voice_cfg.get("ref_audio_path"):
                log.info("GPT-SoVITS 音色 %r 未配置参考音频，跳过", voice)
                continue
            if not gpt_sovits.ensure_server():
                log.warning("GPT-SoVITS 不可用，尝试下一引擎")
                continue
            if gpt_sovits.synth(text, out_path, voice=voice):
                return out_path, "gpt_sovits"
            log.warning("GPT-SoVITS 合成失败，尝试下一引擎")
        elif name == "edge_tts":
            if edge.synth(text, out_path):
                return out_path, "edge_tts"
        else:
            log.warning("未知 TTS 引擎: %s", name)
    return None, "all_engines_failed"
