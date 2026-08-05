# Content and cover style

## Contents

- Voiceover objective
- Voiceover structure
- Language rules
- Prohibited patterns
- AI-flavor removal
- Publication information
- Topic covers
- Collection covers
- Cover quality control

## Voiceover objective

Write text that can be pasted directly into text-to-speech or read by a narrator. Sound like a knowledgeable friend telling a surprising true story, not a paper, editing brief, lesson plan, or AI outline.

Default target: 4,500–5,500 non-whitespace Chinese characters for a roughly 15-minute finished piece. Adjust to narration speed and requested duration. Substance has priority over length.

## Voiceover structure

- Open within 80–150 characters with danger, contradiction, scale, or a result that demands explanation.
- Establish the central question quickly.
- Move chronologically or causally; introduce one idea per paragraph.
- Renew curiosity every 500–800 characters through a concrete discovery, consequence, or reversal.
- Explain numbers by comparison when useful.
- Resolve the opening question and connect the ending to people, choices, or present-day meaning.

Do not announce structural beats. The listener should feel them, not hear their labels.

## Language rules

- Prefer short and medium sentences that are easy to say in one breath.
- Use everyday verbs and concrete nouns.
- Explain specialist terms immediately.
- Rewrite tongue-twisters, stacked modifiers, and dense abstractions.
- Use cautious wording for disputed claims.
- Keep names, dates, quantities, and causal statements consistent with checked sources.

## Prohibited patterns

Do not include:

- `【开场钩子】`, `【核心悬念】`, `【推进】`, `【结尾升华】`, or `【补充叙事】`;
- “镜头切到”“画面来到”“字幕里”等 editing directions;
- “这段视频最容易省略的一层”“回看整条因果链”“前面三条线索共同指向”等 meta-commentary;
- generic filler copied between topics;
- repeated complete paragraphs;
- unrelated systems or engineering language inserted into an animal, history, or culture topic;
- “点赞、关注、收藏、转发”等 calls to action unless explicitly requested;
- fabricated dialogue, motives, facts, numbers, or conclusions.

Do not use a fixed transition library to expand every script. When the source is thin, find another reliable source or shorten the piece.

## AI-flavor removal (去AI味)

After drafting, invoke the installed `$remove-ai-flavor` skill on the full
Chinese voiceover. Treat it as a preservation-first editorial pass: remove
only template shells and machine-polished structures while preserving facts,
numbers, names, quotes, uncertainty, chronology, target tone, and the
narrator's speaking voice. Do not invent facts, jokes, examples, dialogue, or
personal experience to make text look human.

If `$remove-ai-flavor` is unavailable, apply the fallback rules below and
report that the external skill pass was skipped. Do not silently claim that
the skill or its audit ran.

High-priority shells to remove or rewrite:

- Binary contrast shells: 「不是A，而是B」「并非A，而是B」「不在于A，而在于B」「不只是A，更是B」「与其说A，不如说B」— if A is padding, delete it and state B directly.
- Staged sequence shells: 「先A，再B」「先A，然后B」「第一步…第二步…」— keep the order only when the order changes the outcome.
- Essence claims: 「真正重要的是」「真正决定X的是」「本质上」「核心在于」「底层逻辑」— name the actual subject; replace abstract emphasis with evidence or consequence.
- Assistant route markers: 「接下来」「我们可以看到」「值得注意的是」「不可否认的是」「总的来说」「说白了」「划重点」— enter the actual content directly.
- Narrowing frames: 「这次只看…」「今天只看…」「答案很简单：」— delete the setup if the next sentence carries the meaning.
- Template punctuation and paragraph shape: repeated 「观点：解释」「概念：解释」colons, three or more parallel clauses with the same grammar, claim + explanation + summary in every paragraph, paragraphs so even that the draft looks sorted by a model. Vary paragraph weight: short beat, medium explanation, thick paragraph, short landing.
- Unmotivated ending questions: 「你觉得呢？」「是不是很震撼？」— remove them by default. Keep one specific, discussion-worthy ending question only when the user explicitly requests a Douyin comment hook.

Pass sequence:

1. Scan structure, voice, sentence shells, wording, and ending in that order.
2. Repair locally when possible. Rewrite a whole paragraph only when its shape causes the AI flavor.
3. If the installed skill package includes the auditor, run:

   ```powershell
   python <remove-ai-flavor-skill-root>\scripts\audit_ai_flavor.py <draft.txt> --fail-on-review
   ```

4. Resolve blocker findings with context-aware edits, rerun the audit, then manually check factual fidelity, paragraph rhythm, and speakability. A clean audit is not proof that the writing is good.

Quality gate before finalizing: no obvious binary-contrast / staged-sequence /
essence-claim shell remains unless a quoted speaker justifies it; paragraph
weights are uneven; sentence lengths vary; the text reads like a person
telling a story, not a template being filled. The final file contains only
narrator-ready prose, preserves every supported claim, and passes the auditor
without unresolved blockers when the auditor is available.

Keep versioned drafts during revision. After the approved text has been promoted to `爆款口播稿.txt`, read it back and confirm it is non-empty and still passes the factual, length, speakability, and AI-flavor checks. Then delete superseded voiceover files in that topic directory, including `爆款钩子文案.txt` and versioned `爆款口播稿-*` drafts. Keep the drafts when promotion or validation fails. Do not treat subtitles, research notes, publication information, or unrelated text documents as disposable drafts.

## Publication information

Use exactly:

```text
<title of at most 25 characters>
#标签1 #标签2 #标签3 #标签4 #标签5
```

Write exactly two non-empty lines. Do not add `标题：`, `爆款标题：`, `标签：`, section headings, blank lines, emoji, publishing advice, platform notes, cover copy, or interaction prompts.

Count every Chinese character, digit, Latin letter, punctuation mark, and space toward the 25-character title limit. The title should follow Douyin's high-click logic while remaining factual: build an information gap with a checked number, contrast, consequence, or concise question. Prefer a concrete causal question or measurable scale over a proper noun alone. Never fabricate or exaggerate beyond the source.

Put exactly five space-separated, topic-specific hashtags on the second line.

## Topic covers

Use `assets/topic-cover-3x4-approved.png` and `assets/topic-cover-4x3-approved.png` as the approved style references.

- Ratios: 3:4 portrait and 4:3 landscape.
- Background: photorealistic documentary image tied to the exact topic.
- Type: rough handwritten Chinese brush lettering with strong contrast.
- Main title: exactly six Chinese characters, one line.
- Subtitle: exactly eight Chinese characters, one line.
- Placement: upper half.
- Width: subtitle about two-thirds the main-title width.
- Main-title treatment: extra-large vivid golden-yellow brush calligraphy, thin crisp black outline, and strong soft black drop shadow; nearly span the available safe width.
- Subtitle treatment: medium-large white brush calligraphy, thin crisp black outline, and strong soft black drop shadow; center directly below the main title.
- Keep both lines visually centered with clear spacing and safe margins; do not crop a stroke.
- No extra text, English, logo, watermark, or decorative badge.

## Collection covers

Use `assets/collection-cover-1x1.png` and `assets/collection-cover-4x3.png` as style references.

- Ratios: 1:1 and 4:3.
- Background: one iconic photorealistic scene expressing the collection.
- Title: exact four-character collection name, one centered line.
- Type: warm antique-gold rough brush calligraphy with a subtle dark shadow.
- No subtitle or other text.

## Cover quality control

1. Visually read every Chinese character.
2. Confirm no unwanted words or pseudo-text.
3. Measure pixel dimensions and aspect ratio.
4. Confirm the scene is realistic and topic-relevant.
5. Compare both variants for consistent identity.
6. Save drafts with versioned names; promote only approved files to final names.
