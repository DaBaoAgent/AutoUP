# AutoUP content and cover rules

## Voiceover

- Output only narrator-ready Chinese prose.
- Facts must come from the subtitle window supplied to that generation section.
- Do not invent names, numbers, events, motives or causal links.
- Prefer short and medium spoken sentences with concrete verbs and nouns.
- Avoid production labels, editing instructions, generic engagement calls and formulaic AI transitions.
- Default target is controlled by `script.target_chars` and `script.tolerance`; validation enforces both lower and upper bounds.
- When the source cannot support the requested length, fail rather than padding with unsupported material.

S3 writes `script_map.json` so each generated section retains its source time range.

## Publication material

Domestic output:

```text
<title no longer than 25 characters>
#tag1 #tag2 #tag3 #tag4 #tag5
```

Rules are enforced in code: non-empty title, exactly five unique tags, no spaces inside tags, and no `#` inside model-returned tag values.

Overseas output uses an English title no longer than 90 characters plus an English description. Chinese characters in the English material fail validation.

## Covers

AutoUP generates three delivery ratios:

- 9:16 — 1080×1920
- 16:9 — 1920×1080
- 1:1 — 1080×1080

Cover main text must be exactly six Chinese characters and subtitle exactly eight. The renderer uses the bundled/configured font, golden main title, white subtitle, dark outline/shadow, and recalculates text bounds after font fitting to avoid off-center long text.

Demo images and historical covers are retained in the repository as reference/history assets; runtime code must not depend on historical cover filenames.
