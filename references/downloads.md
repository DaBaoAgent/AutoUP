# AutoUP authorized download workflow

Only process media the user is authorized to download and reuse. AutoUP does not bypass DRM, paywalls, private-video access, geographic restrictions or account security.

## S1 verification

`yt-dlp` metadata inspection records:

- source URL and video ID;
- title/channel;
- duration and highest available height;
- exact selected English subtitle language;
- whether that subtitle is manual or automatic.

The batch verifier can use bounded concurrency via `download.verify_workers`.

## S2 download

The exact subtitle language selected in S1 is passed into S2. Video download is capped by `download.max_height`.

If the resulting container is not MP4, AutoUP uses FFmpeg to remux with stream copy. If stream copy cannot produce a valid MP4, it transcodes. It never changes a `.webm` or `.mkv` extension to `.mp4` without a real container conversion.

Subtitles are normalized to `字幕/字幕.srt`. If a download leaves VTT only, FFmpeg conversion is used as a bounded fallback.

## Local settings

Use `autoup/config.local.yaml`, environment variables or `--set` for local FFmpeg paths, proxies and output locations. Do not commit browser cookies, API keys or machine-specific paths.
