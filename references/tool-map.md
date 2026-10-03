# AutoUP tool map

AutoUP deliberately stays a small Python CLI rather than introducing a database, queue, WebUI or distributed worker system.

| Stage | Main implementation | External dependency |
|---|---|---|
| S1/S2 | `autoup/stages/download.py` | yt-dlp, FFmpeg |
| S3 | `autoup/stages/script.py` | OpenAI-compatible LLM |
| S4 | `autoup/stages/dub.py`, `autoup/tts/` | Edge TTS or GPT-SoVITS |
| S5 | `autoup/stages/match.py` | OpenAI-compatible LLM |
| S6 | `autoup/stages/render.py` | FFmpeg, pydub |
| S7 | `autoup/stages/publish.py` | OpenAI-compatible LLM |
| S8 | `autoup/stages/cover.py` | Pillow, FFmpeg |
| S9 | `autoup/stages/validate.py` | Pillow, ffprobe |

## Design constraints

- Source subtitles are the factual boundary for generated narration.
- LLM output is always treated as untrusted structured input and validated in Python.
- Missing semantic matches fail closed rather than receiving arbitrary footage.
- TTS cache reuse is fingerprint-based, not filename-based.
- BGM random mode is deterministic per topic.
- NVENC capability probing is cached; CPU encoding remains the portable fallback.
- Source verification can use bounded concurrency, while full topic production remains serial by default.
- Every expensive stage writes elapsed seconds to `state.json.metrics`.

## Development

```bash
uv sync --all-extras --locked
uv run ruff check autoup tests
uv run pytest --cov=autoup
```
