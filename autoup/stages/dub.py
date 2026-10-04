"""S4 配音：逐句 TTS + 输入指纹缓存，避免文案/音色变化后误复用旧音频。"""
from __future__ import annotations

import logging
from pathlib import Path

from .. import config, utils
from ..tts import synth as tts_synthesize

log = logging.getLogger("autoup.s4")

SCRIPT_NAME = "爆款口播稿.txt"
MIN_WAV_BYTES = 1024


def _voice_fingerprint(text: str, voice: str) -> str:
    voice_config = config.get("voice", {}) or {}
    ref_sig = None
    ref = config.get(f"voice.gpt_sovits.voices.{voice}.ref_audio_path")
    if ref:
        ref_path = Path(str(ref)).expanduser()
        if ref_path.exists():
            ref_sig = utils.file_fingerprint(ref_path)
    return utils.stable_hash(
        {
            "text": text,
            "voice": voice,
            "voice_config": voice_config,
            "reference_audio": ref_sig,
        }
    )


def run(topic_dir: Path, voice: str = "default", max_sentences: int | None = None) -> Path:
    script = topic_dir / "文案" / SCRIPT_NAME
    if not script.exists():
        raise FileNotFoundError(f"缺少文案: {script}")
    text = script.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise ValueError(f"文案为空: {script}")

    out_dir = topic_dir / "配音"
    out_dir.mkdir(parents=True, exist_ok=True)
    previous = utils.read_json(out_dir / "timing.json", default={}) or {}
    previous_by_index = {
        int(item.get("index", 0)): item
        for item in previous.get("sentences", [])
        if item.get("index")
    }

    sentences = utils.split_sentences(text)
    if max_sentences:
        sentences = sentences[:max_sentences]
        log.warning("测试模式: 仅处理前 %d 句", max_sentences)

    entries: list[dict] = []
    expected_files: set[str] = set()
    for index, sentence in enumerate(sentences, 1):
        wav = out_dir / f"{index:04d}.wav"
        expected_files.add(wav.name)
        fingerprint = _voice_fingerprint(sentence, voice)
        old = previous_by_index.get(index) or {}
        cache_ok = (
            wav.exists()
            and wav.stat().st_size > MIN_WAV_BYTES
            and old.get("fingerprint") == fingerprint
        )
        if cache_ok:
            duration = utils.audio_duration(wav)
            entries.append(
                {
                    "index": index,
                    "text": sentence,
                    "audio": wav.name,
                    "duration": round(duration, 3),
                    "engine": old.get("engine", "cached"),
                    "fingerprint": fingerprint,
                }
            )
            log.info("[%d/%d] 复用缓存 %.1fs", index, len(sentences), duration)
            continue

        if wav.exists():
            wav.unlink()
        audio, engine = tts_synthesize(sentence, wav, voice=voice)
        if audio is None or not wav.exists() or wav.stat().st_size <= MIN_WAV_BYTES:
            raise RuntimeError(f"第 {index} 句全部 TTS 引擎失败: {sentence[:50]}…")
        duration = utils.audio_duration(wav)
        entries.append(
            {
                "index": index,
                "text": sentence,
                "audio": wav.name,
                "duration": round(duration, 3),
                "engine": engine,
                "fingerprint": fingerprint,
            }
        )
        log.info("[%d/%d] %s %.1fs: %s", index, len(sentences), engine, duration, sentence[:30])

    for wav in out_dir.glob("*.wav"):
        if wav.name not in expected_files and wav.stem.isdigit():
            wav.unlink()

    gap = float(config.get("voice.gap_seconds", 0.3))
    timing = {
        "voice": voice,
        "gap_seconds": gap,
        "total_duration": round(
            sum(entry["duration"] for entry in entries)
            + gap * max(len(entries) - 1, 0),
            3,
        ),
        "sentences": entries,
    }
    output = out_dir / "timing.json"
    utils.write_json(output, timing)
    log.info("S4 完成: %d 句，配音总时长 %.1fs", len(entries), timing["total_duration"])
    return output
