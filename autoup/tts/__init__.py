"""TTS 引擎统一入口: 主引擎失败自动切换备用引擎。"""
from __future__ import annotations

import logging
from pathlib import Path

from .. import config
from . import edge, gpt_sovits

log = logging.getLogger("autoup.tts")


def synth(text: str, out_path: Path) -> tuple[Path | None, str]:
    """合成一句语音。返回 (音频文件, 实际使用的引擎); 全失败返回 (None, 'all_engines_failed')。"""
    engines = [str(config.get("voice.engine", "gpt_sovits"))]
    fb = config.get("voice.fallback_engine", "edge_tts")
    if fb and fb not in engines:
        engines.append(str(fb))
    for name in engines:
        if name == "gpt_sovits":
            # 未配置参考音频时直接跳过, 避免白白拉起服务
            voices = config.get("voice.gpt_sovits.voices", {}) or {}
            vcfg = voices.get("default") or {}
            if not vcfg.get("ref_audio_path"):
                log.info("GPT-SoVITS 未配置参考音频, 跳过 (用 %s)", fb)
                continue
            if not gpt_sovits.ensure_server():
                log.warning("GPT-SoVITS 不可用, 尝试下一引擎")
                continue
            if gpt_sovits.synth(text, out_path):
                return out_path, "gpt_sovits"
            log.warning("GPT-SoVITS 合成失败, 尝试下一引擎")
        elif name == "edge_tts":
            if edge.synth(text, out_path):
                return out_path, "edge_tts"
    return None, "all_engines_failed"
