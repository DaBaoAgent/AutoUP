# AutoUP requirements

## Product position

AutoUP is a lightweight CLI pipeline that turns an approved long-form documentary source into a publish-ready narration package while keeping every intermediate artifact inspectable and rerunnable.

The project intentionally avoids WebUI, database, Redis/Celery and other infrastructure until a concrete requirement justifies them.

## Core requirements

1. Input starts from a user-provided URL manifest.
2. S1 accepts only sources meeting configured duration/resolution thresholds with an available English subtitle.
3. S2 downloads source media and the exact subtitle language selected during verification.
4. S3 narration is grounded section-by-section in the complete subtitle timeline; unsupported padding is forbidden.
5. S4 supports GPT-SoVITS and Edge TTS, selectable by voice, with fingerprint-aware cache reuse.
6. S5 maps every narration sentence to one semantically relevant, real source-video interval. Missing coverage is a hard failure.
7. S6 produces 1920×1080/30fps by default, removes source audio, overlays narration/subtitles, and optionally ducks deterministic BGM.
8. S7 generates strict domestic and overseas publication material plus exact 6/8-character cover copy.
9. S8 outputs 9:16, 16:9 and 1:1 covers.
10. S9 is the delivery gate. A full batch returns a non-zero exit code when any topic fails unless partial success was explicitly allowed.
11. Every stage stores a content/config fingerprint and elapsed time in `state.json`.
12. Machine-specific paths and secrets are never committed.

## Portability

Repository defaults use commands such as `ffmpeg` and a relative `output` directory. Users may override them with `autoup/config.local.yaml`, `AUTOUP_*` environment variables or `--set`.

## Engineering quality

- Python 3.11+
- `pyproject.toml` is the dependency/configuration source of truth.
- `uv.lock` provides reproducible dependency resolution.
- Ruff must pass.
- pytest must pass.
- Coverage must remain at or above the configured 70% gate.
- Linux full CI and Windows smoke CI must pass before delivery.

## Repository assets

Demo videos, README imagery and historical cover examples stay in the repository. They are reference/history assets; production code should not couple itself to individual historical files.
