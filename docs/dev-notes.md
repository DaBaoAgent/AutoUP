# AutoUP development notes

## Current invariants

- S3 partitions the complete SRT by progress; no section is generated without a source subtitle window.
- S4 reuses sentence audio only when the text/voice/config/reference-audio fingerprint matches.
- S5 requires one semantic picture segment per narration sentence. Missing matches are retried; unresolved sentences fail instead of receiving arbitrary free footage.
- S6 refuses to render an incomplete S5 decision.
- S7 validates and repairs structured publication data, then fails closed if constraints still do not pass.
- S9 validates both lower and upper script length, TTS fingerprints, complete non-overlapping mapping, final video properties, publication formats and exact cover dimensions.
- Stage fingerprints invalidate stale checkpoints automatically.
- `state.json.metrics` records stage elapsed seconds for performance analysis.

## Known platform details

- yt-dlp/FFmpeg may need explicit local paths on Windows; use `autoup/config.local.yaml` instead of editing repository defaults.
- yt-dlp curl can fail with a CA path containing non-ASCII characters; S1/S2 copies the CA bundle to a temporary ASCII path when required.
- FFmpeg ASS filters on Windows are run from the work directory with relative paths to avoid drive-letter escaping issues.
- GPT-SoVITS is optional. If its configured voice is unavailable, the pipeline can fall back to Edge TTS.
- BGM selection in `random` mode is deterministic from the topic name for reproducible reruns.

## Quality commands

```bash
uv sync --all-extras --locked
uv run python -m compileall -q autoup tests
uv run ruff check autoup tests
uv run pytest -q --cov=autoup --cov-report=term-missing
```

CI runs full quality gates on Linux and a Windows smoke suite.
