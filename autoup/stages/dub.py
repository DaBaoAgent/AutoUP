"""S4 配音: 文案分句 → 逐句 TTS(双引擎自动降级) → 实测时长 → timing.json。

输入: <选题>/文案/爆款口播稿.txt
输出: <选题>/配音/0001.wav... + <选题>/配音/timing.json
幂等: 已存在且大于 1KB 的单句音频直接复用(断点续传)。
"""
from __future__ import annotations

import logging
from pathlib import Path

from .. import config, utils
from ..tts import synth as tts_synthesize

log = logging.getLogger("autoup.s4")

SCRIPT_NAME = "爆款口播稿.txt"
MIN_WAV_BYTES = 1024


def run(topic_dir: Path, voice: str = "default", max_sentences: int | None = None) -> Path:
    script = topic_dir / "文案" / SCRIPT_NAME
    if not script.exists():
        raise FileNotFoundError(f"缺少文案: {script}")
    text = script.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise ValueError(f"文案为空: {script}")

    out_dir = topic_dir / "配音"
    out_dir.mkdir(parents=True, exist_ok=True)

    sentences = utils.split_sentences(text)
    if max_sentences:
        sentences = sentences[:max_sentences]
        log.warning("测试模式: 仅处理前 %d 句", max_sentences)
    total = utils.estimate_duration("".join(sentences))
    log.info("分句 %d 段, 预估总时长 %.0fs (%.1f 分钟)", len(sentences), total, total / 60)

    entries: list[dict] = []
    for i, sent in enumerate(sentences, 1):
        wav = out_dir / f"{i:04d}.wav"
        if wav.exists() and wav.stat().st_size > MIN_WAV_BYTES:
            dur = utils.audio_duration(wav)
            entries.append({"index": i, "text": sent, "audio": wav.name,
                            "duration": round(dur, 3), "engine": "cached"})
            log.info("[%d/%d] 复用已有音频 %.1fs", i, len(sentences), dur)
            continue
        audio, engine = tts_synthesize(sent, wav)
        if audio is None:
            raise RuntimeError(f"第 {i} 句全部 TTS 引擎失败: {sent[:50]}…")
        dur = utils.audio_duration(wav)
        entries.append({"index": i, "text": sent, "audio": wav.name,
                        "duration": round(dur, 3), "engine": engine})
        log.info("[%d/%d] %s %.1fs: %s", i, len(sentences), engine, dur, sent[:30])

    timing = {
        "voice": voice,
        "gap_seconds": float(config.get("voice.gap_seconds", 0.3)),
        "total_duration": round(sum(e["duration"] for e in entries)
                                + config.get("voice.gap_seconds", 0.3) * max(len(entries) - 1, 0), 3),
        "sentences": entries,
    }
    out = out_dir / "timing.json"
    utils.write_json(out, timing)
    log.info("timing.json 完成: %d 句, 配音净时长 %.1fs", len(entries), timing["total_duration"])
    return out
