---
name: autoup
description: Run, resume, diagnose and validate the AutoUP documentary-narration S1-S9 pipeline.
---

# AutoUP

Use this repository as a lightweight CLI pipeline. Do not revive legacy AutoYY paths or deleted helper scripts.

## Pipeline

1. S1 verifies URL duration, resolution and English subtitle availability.
2. S2 downloads/remuxes source video and normalizes the selected subtitle to SRT.
3. S3 generates narration from the complete subtitle timeline in factual windows.
4. S4 creates per-sentence TTS with fingerprint-aware cache reuse.
5. S5 semantically maps every narration sentence to real source footage.
6. S6 renders picture, narration, ASS subtitles and optional BGM.
7. S7 generates validated domestic/overseas publication material and cover copy.
8. S8 creates 9:16, 16:9 and 1:1 covers.
9. S9 validates the complete delivery contract.

Never claim completion when the requested stage or S9 gate failed.

## Setup

Use Python 3.11+, FFmpeg/ffprobe and uv.

```bash
uv sync --all-extras --locked
```

Repository defaults live in `autoup/config.yaml`. For a machine-specific setup copy `autoup/config.example.yaml` to `autoup/config.local.yaml`; that local file is ignored by Git. Keep API keys in environment variables.

## Run

```bash
python -m autoup.run --manifest urls.txt --batch demo
python -m autoup.run --batch demo --only s4,s5,s6
python -m autoup.run --batch demo --only s8 --force
```

`--only` means exactly those stages. `--allow-partial` is the explicit opt-out from a non-zero batch exit code when some topics fail.

## Resume rules

Use `state.json`; do not infer completion from filenames alone. A completed stage is reusable only if its artifacts exist and its stored input fingerprint matches the current files/config. Stage elapsed times are stored under `metrics`.

## Hard quality rules

- Never generate a script section without a subtitle fact window.
- Never fabricate a missing S5 match by assigning an unrelated free time slot.
- Never reuse TTS solely because a numbered WAV already exists.
- Never rename another video container to `.mp4` without a real remux/transcode.
- Never accept malformed publication data after repair attempts are exhausted.
- Never bypass S9 for a full delivery.
- Preserve Demo and historical cover assets in this repository.

## Development

```bash
uv run python -m compileall -q autoup tests
uv run ruff check autoup tests
uv run pytest -q --cov=autoup --cov-report=term-missing
```

CI must pass on Linux quality gates and Windows smoke tests.
