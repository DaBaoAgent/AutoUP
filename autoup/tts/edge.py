"""edge-tts 备用引擎 (本机 edge_tts 7.2.7)。"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import edge_tts

from .. import config

log = logging.getLogger("autoup.tts.edge")


async def _synth(text: str, out: Path, voice: str, rate: str, volume: str) -> None:
    com = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
    await com.save(str(out))


def synth(text: str, out_path: Path, voice: str = "default") -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    v = str(config.get("voice.edge_tts.voice", "zh-CN-YunjianNeural"))
    try:
        asyncio.run(_synth(text, out_path, v,
                           str(config.get("voice.edge_tts.rate", "+0%")),
                           str(config.get("voice.edge_tts.volume", "+0%"))))
        ok = out_path.exists() and out_path.stat().st_size > 1000
        if not ok:
            log.error("edge-tts 输出异常: %s", out_path)
        return ok
    except Exception as e:  # noqa: BLE001
        log.error("edge-tts 合成失败: %s", e)
        return False
