---
name: autoyy
description: Plan, produce, refresh, and validate documentary-explainer content packages from performance screenshots, topic research, and long-form source videos. Use when Codex needs to analyze multi-platform creator data; identify repeatable documentary topics; search and verify 30+ minute YouTube sources; prepare a download manifest; download authorized HD video and subtitles; write and humanize Chinese voiceover scripts; create or recursively bulk-refresh Douyin-ready publication metadata; generate photorealistic topic or collection covers; resume an interrupted batch; or audit whether every topic folder is complete.
---

# Produce Documentary Content

Build a traceable pipeline from creator data to one ready-to-edit folder per documentary topic. Keep facts tied to subtitles or reliable sources, preserve source metadata, and validate every deliverable before reporting completion.

Use `D:\自动剪辑` as the default working root. If the user does not provide a project directory, create a dedicated project subdirectory such as `D:\自动剪辑\AutoYY-YYYYMMDD-项目名`. Inspect but never reorganize, rename, or overwrite unrelated files already present in the working root.

## Start

1. Determine which stages the user requested: performance audit, topic planning, source research, authorized downloads, text production, cover generation, full pipeline, resume, or audit.
2. Record configurable inputs instead of hardcoding prior values: input data, topic count, project directory under the default working root, target platforms, duration, resolution, subtitle languages, script length and tone, and cover mode.
3. Use a task plan for multi-topic or full-pipeline work. Resume from verified files rather than restarting.
4. Ask only for decisions that materially change the result or permission scope. Never assume authorization to use browser cookies, download copyrighted media, bypass access controls, overwrite approved assets, or publish externally.

## Route to supporting skills and tools

- Read `references/tool-map.md` when planning a full pipeline or when the user asks which tools and skills are used at each stage.
- Read every supplied screenshot. Use visual inspection and OCR; use the spreadsheet skill when consolidating or analyzing tabular records.
- Browse the web for current YouTube links, view counts, availability, duration, quality, and recommendations. Treat all volatile metrics as dated observations.
- Use Chrome control only when the user explicitly needs signed-in browser state. Use `--cookies-from-browser` only after explicit authorization.
- Use the image-generation skill for all raster cover generation and edits. Load the relevant master cover from `assets/` as a style reference.
- Use the installed `$remove-ai-flavor` skill as the required second editorial pass for every newly generated or substantially rewritten Chinese voiceover. If it is unavailable, use the fallback rules in `references/content-style.md` and report that the external pass was skipped.
- Use `scripts/download_from_manifest.ps1` for repeatable Windows batch downloads.
- Use `scripts/validate_publication_info.py` to recursively audit publication files, including topic folders nested under archive directories such as `@已发`.
- Use `scripts/validate_deliverables.py` for the final folder audit.

## Workflow

### 1. Audit published performance

Read all visible records, not just top performers. Preserve platform, date, canonical topic, displayed title, views/reads, impressions, likes, comments, duration, and screenshot source when available.

Normalize title variants into a canonical topic without altering raw values. Deduplicate overlapping screenshots and cross-platform reposts before aggregation. Calculate platform medians, outliers, and cross-platform topic totals. Identify the repeatable audience promise behind each winner, such as extreme risk plus giant engineering, war relic plus salvage, counterintuitive animal behavior, or closed institutions. Do not infer missing metrics.

### 2. Generate and score candidate topics

Allocate a batch by default as 70% proven themes, 20% adjacent extensions, and 10% experiments. Score each candidate from 0–5 on:

1. danger or conflict;
2. visual density;
3. counterintuitive insight;
4. numeric scale;
5. source quality and usable rights.

Prioritize candidates scoring at least 20/25. Lower the score when the source only partially matches the planned angle.

### 3. Research and verify long sources

For every candidate, verify a direct watch URL and capture:

- Chinese topic and translated Chinese video title;
- original title, channel, URL, upload date;
- duration, current view count, highest available resolution;
- original language and subtitle availability;
- match grade: exact, high, adjacent, or reject;
- copyright/license note and verification date.

Default filters are duration at least 30 minutes and resolution at least 720p; prefer 1080p or 4K. Never fabricate view counts or quality. Reject inaccessible, misleading, synthetic, compilation-only, or weakly matched sources.

Write approved rows to a UTF-8 CSV manifest using `assets/topic-manifest-template.csv`.

### 4. Create the topic report

Lead with evidence from the user's performance data. For each proposed topic include its validated audience promise, source link and dated metadata, translated source title, likely hook, intended platforms, match grade, and licensing caveat. Separate verified facts from editorial inference.

### 5. Download authorized media and subtitles

Read `references/downloads.md` before downloading. Create one Chinese-named subdirectory per topic. Use the manifest and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/download_from_manifest.ps1 `
  -Manifest <manifest.csv> `
  -OutputRoot <output-root>
```

Prefer manual English subtitles, then automatic English, then another available language. Keep the original URL and metadata in the manifest. Do not defeat DRM, paywalls, regional access controls, or platform security.

### 6. Write the Chinese voiceover

Read the full subtitle or transcript before drafting. Use subtitles as the narrative backbone and reliable sources only for necessary context. Read `references/content-style.md` for the complete specification.

Default requirements:

- pure spoken Chinese with no production labels;
- approximately 4,500–5,500 non-whitespace Chinese characters unless the user sets another target;
- light, conversational popular-science tone;
- a strong opening hook, steady reveals, and a meaningful ending;
- short, speakable sentences with technical terms explained simply;
- no invented facts, unrelated filler, duplicated paragraphs, template transitions, or calls to follow/share.

After drafting:

1. Keep the first draft under a versioned filename; do not promote it to `爆款口播稿.txt` yet.
2. Invoke `$remove-ai-flavor` on the full draft as Chinese documentary voiceover. Preserve facts, numbers, names, quotes, uncertainty, chronology, tone, and the user's target length. Prefer local sentence or paragraph repairs over a wholesale rewrite.
3. When the installed skill package exposes `scripts/audit_ai_flavor.py`, run it with `--fail-on-review`. Treat its result as a regression signal, then manually review context instead of deleting every flagged phrase blindly.
4. Recheck factual consistency against the subtitle/transcript, spoken rhythm, opening hook, ending, and character count. Promote only the cleaned narrator-ready text to `爆款口播稿.txt`; do not include edit notes or an audit report in the script.
5. Read back and validate the promoted `爆款口播稿.txt`. Only after it exists, is non-empty, and passes the final checks, delete superseded voiceover copies in the same topic directory, including `爆款钩子文案.txt` and versioned `爆款口播稿-*` drafts. Leave only `爆款口播稿.txt` as the script deliverable. If validation fails, retain the drafts for repair. Never delete subtitles, source notes, publication information, or unrelated text files.

Remove padding-based binary contrasts, ceremonial sequencing, abstract essence claims, assistant route markers, repeated template colons, over-even paragraph shapes, and generic engagement questions. Keep a contrast, sequence, or question when it carries necessary facts, causality, quoted speech, or a user-requested specific comment hook.

Do not pad to length. If the source cannot support the requested duration, state the evidence gap and propose supplemental sources.

### 7. Create publication information

Write `发布信息.txt` as:

```text
<one accurate curiosity-driven title of at most 25 characters>
#标签1 #标签2 #标签3 #标签4 #标签5
```

Use exactly two non-empty lines with no field labels, blank lines, emoji, publishing advice, platform notes, or extra copy. Count every Chinese character, digit, Latin letter, punctuation mark, and space toward the 25-character title limit. Use Douyin-style information gaps built from a factual number, contrast, consequence, or question, but do not exaggerate beyond the source. Use exactly five topic-specific hashtags on the second line.

For a bulk refresh:

1. Recursively find every existing `发布信息.txt`; include nested archive folders and do not create a file in a container-only directory.
2. Read each topic folder name and its existing publication text. Preserve the topic and any accurate, specific tags; rewrite only what is needed.
3. Produce a unique title for each topic. Do not reuse one template across the batch.
4. Overwrite only `发布信息.txt` after confirming the discovered file count equals the planned update count. Do not touch video, subtitles, voiceover, or covers.
5. Run `python scripts/validate_publication_info.py <root>` and scan for legacy fields such as `爆款标题：`, `匹配标签：`, `发布建议：`, and `版权提醒：`.

### 8. Generate covers

Read the cover section in `references/content-style.md` and use the relevant style-reference asset.

- Topic-cover mode: create 3:4 and 4:3 photorealistic covers. Put a six-character main title and eight-character subtitle in the upper half, each on one line; make the subtitle about two-thirds the width of the main title.
- Collection-cover mode: create 1:1 and 4:3 photorealistic covers. Put the exact four-character collection name on one centered line with no subtitle.

For topic covers, match the approved reference typography precisely: an extra-large vivid golden-yellow rough brush-calligraphy main title with a thin black outline and strong soft black shadow, followed by a medium-large white rough brush-calligraphy subtitle with the same black outline and shadow. Center both lines in the upper half, keep the subtitle about two-thirds the main-title width, and leave safe margins around every character. Use high contrast and no extra text, logo, or watermark. Inspect every generated image for exact Chinese text and actual pixel ratio before saving.

### 9. Validate and hand off

Expected topic directory:

```text
<NN-中文选题>/
├── 高清源视频.<mp4|mkv|webm>
├── 字幕.srt
├── 发布信息.txt
├── 爆款口播稿.txt
├── 封面-3比4.<png|jpg>
└── 封面-4比3.<png|jpg>
```

Run:

```powershell
python scripts/validate_deliverables.py <output-root>
```

Do not report success until deterministic validation and manual checks agree. Report completed, incomplete, and blocked topics separately.

## Resume and overwrite rules

- Treat existing user files as authoritative unless they are known outputs of the current run.
- Skip complete video and subtitle files.
- Never replace an approved script or cover without explicit instruction.
- Keep logs and manifest state so a stopped batch can continue.
- Use versioned filenames while drafting; after a verified promotion, remove superseded voiceover copies and retain only the final standard filename.

## Resources

- Read `references/workflow-spec.md` for manifest fields, stage gates, and acceptance checks.
- Read `references/tool-map.md` for the end-to-end stage, tool, supporting-skill, and output map.
- Read `references/content-style.md` before writing scripts, publication information, or covers.
- Read `references/downloads.md` before media retrieval or cookie/proxy troubleshooting.
- Use `assets/topic-manifest-template.csv` as the batch manifest schema.
- Use `assets/topic-cover-3x4-approved.png` and `assets/topic-cover-4x3-approved.png` for the approved topic-cover typography, scale, color, outline, shadow, and layout.
- Use `assets/collection-cover-1x1.png` and `assets/collection-cover-4x3.png` for collection-cover style.
- Use `scripts/download_from_manifest.ps1` for downloading.
- Use `scripts/validate_publication_info.py` for recursive two-line publication metadata validation.
- Use `scripts/validate_deliverables.py` for deterministic acceptance checks.
