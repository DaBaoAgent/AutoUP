# AutoUP engineering comparison and design choices

AutoUP was compared with high-star projects in the same broad space, including MoneyPrinterTurbo, VideoLingo, NarratoAI and ShortGPT.

## What AutoUP borrows conceptually

- **MoneyPrinterTurbo:** automated media workflow discipline, packaging and CI ideas.
- **NarratoAI:** subtitle-driven narration/video matching and FFmpeg-first composition.
- **VideoLingo:** robust TTS/dubbing integration patterns.
- **ShortGPT:** explicit pipeline stages and modular engines.

## What AutoUP deliberately does not copy

AutoUP currently has a small, focused CLI core. It does not need a WebUI, API server, database, Redis, Celery, plugin marketplace or distributed worker layer. Those systems would increase failure surface and maintenance cost without improving the current single-machine batch goal.

## Current architecture

```text
manifest
  -> S1 verify
  -> S2 download
  -> S3 subtitle-grounded script
  -> S4 sentence TTS + timing
  -> S5 semantic source matching
  -> S6 FFmpeg render
  -> S7 publication material
  -> S8 three cover ratios
  -> S9 delivery validation
```

The important boundary is between probabilistic LLM output and deterministic Python validation. S3 retains source-window provenance; S5 retries missing semantic matches and fails closed; S7 validates formatting; S9 acts as a final contract.

## Performance strategy

Performance work is intentionally low-complexity and measurable:

- bounded concurrency for independent S1 metadata requests;
- one persistent HTTP session for LLM calls;
- cached NVENC capability detection;
- fingerprinted TTS/stage caches to avoid unnecessary recomputation;
- deterministic BGM selection for reproducible rendering;
- per-stage elapsed-time metrics in `state.json`.

A monolithic FFmpeg filter graph or distributed queue is not introduced until profiling shows that the simpler pipeline is insufficient.
