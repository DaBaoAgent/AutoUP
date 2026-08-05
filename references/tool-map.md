# End-to-end workflow and tool map

## Contents

- Operating principles
- Complete stage map
- Supporting skills
- Local tools and resources

## Operating principles

- Inspect first, mutate only the requested scope, and validate before reporting completion.
- Use current web checks for volatile YouTube metadata and record the verification date.
- Ask for explicit authorization before browser cookies, copyrighted downloads, package installation, proxy use, overwriting approved assets, or external publishing.
- Keep raw source facts separate from editorial inference.
- Resume from verified artifacts instead of restarting a batch.

## Complete stage map

| Stage | Main action | Tools | Supporting skills | Output or gate |
|---|---|---|---|---|
| 0. Scope and inventory | Resolve roots, requested stages, counts, formats, permissions, and existing files | PowerShell, `rg`, task plan | AutoYY | Confirmed scope with no accidental overwrite |
| 1. Performance audit | Read every platform screenshot, transcribe visible metrics, deduplicate overlap, normalize topics | Image viewer, visual OCR, filesystem search; spreadsheet tooling for tables | Spreadsheets when aggregation is substantial | Audited raw records and platform/topic summary |
| 2. Topic planning | Extract winning audience promises; allocate 70% proven, 20% adjacent, 10% experiments; score candidates | Structured analysis, spreadsheet formulas or scripts | AutoYY, Spreadsheets when useful | Topics scoring 20/25 or a documented exception |
| 3. Source research | Find direct YouTube videos, verify duration, views, resolution, subtitles, match, channel, date, and rights note | Web search/open, browser inspection, metadata-only `yt-dlp` checks | In-app Browser; Chrome only for explicitly authorized signed-in state | Verified 30+ minute source rows |
| 4. Report and manifest | Translate titles, write the topic report, and create the UTF-8 download manifest | File editing, CSV tooling | AutoYY, Spreadsheets for large manifests | Approved report and manifest |
| 5. Authorized download | Plan, download, merge HD media, select subtitles, normalize filenames, and resume partials | PowerShell, `scripts/download_from_manifest.ps1`, `yt-dlp`, `ffmpeg` | Chrome only when cookies are explicitly authorized | One playable HD source and one SRT per topic, or a blocked reason |
| 6. Voiceover writing | Read the full transcript, build a factual narrative, then run a preservation-first de-AI pass | Filesystem text reading, reliable web sources for needed context, `$remove-ai-flavor`, its optional `audit_ai_flavor.py` | AutoYY, Remove AI Flavor | Pure 4,500–5,500-character voiceover with no production labels, filler, or unresolved AI-template shells |
| 7. Publication information | Write or recursively refresh a factual Douyin-style title and five tags | File editing, PowerShell for safe bulk rewrites, `scripts/validate_publication_info.py`, `rg` for legacy fields | AutoYY | Exactly two lines; title ≤25 characters; exactly five hashtags |
| 8. Cover production | Create matching 3:4 and 4:3 topic covers or 1:1 and 4:3 collection covers | Image generation, image viewer, dimension inspection, approved assets | Imagegen | Exact Chinese text, approved typography, correct ratios |
| 9. Package validation | Check media, subtitles, scripts, publication files, covers, ratios, duplicates, and zero-byte files | `scripts/validate_deliverables.py`, `scripts/validate_publication_info.py`, manual visual review | AutoYY | Complete/incomplete/blocked counts |
| 10. Handoff and resume | Report output paths, manifest, exceptions, and safe restart point | Filesystem inventory and logs | AutoYY | Traceable handoff without redoing completed work |

## Supporting skills

- **AutoYY:** Orchestrate the entire documentary workflow and enforce stage gates.
- **Remove AI Flavor:** Preserve facts and authorial voice while removing template sentence shells, assistant route markers, over-even paragraph structures, and generic engagement endings from Chinese voiceovers.
- **Imagegen:** Generate or edit raster covers from approved 3:4, 4:3, and collection references.
- **Spreadsheets:** Consolidate screenshot metrics, calculate medians/outliers, score topics, and manage large manifests.
- **In-app Browser:** Inspect public pages and visible YouTube metadata.
- **Chrome control:** Use existing signed-in state only when necessary and explicitly authorized.
- **Skill creator:** Update AutoYY itself, add reusable resources, and validate the skill package.

## Local tools and resources

- **PowerShell:** Inventory Windows folders, perform exact-path batch operations, run download and validation scripts.
- **`rg`:** Find files and detect legacy publication fields or prohibited script phrases.
- **Web search/open:** Verify current source links, public views, availability, and official facts.
- **`yt-dlp`:** Inspect formats and download authorized source media and subtitles.
- **`ffmpeg`:** Merge video/audio and normalize playable outputs.
- **`scripts/download_from_manifest.ps1`:** Execute resumable downloads from the approved manifest.
- **`scripts/validate_publication_info.py`:** Recursively validate strict two-line publication metadata.
- **`scripts/validate_deliverables.py`:** Validate complete topic packages.
- **`remove-ai-flavor/scripts/audit_ai_flavor.py`:** Flag enumerable Chinese AI-writing shells after the editorial pass; use it as a regression aid, not a substitute for human review.
- **Approved cover assets:** Lock typography, colors, outlines, shadows, spacing, and aspect-ratio identity.
