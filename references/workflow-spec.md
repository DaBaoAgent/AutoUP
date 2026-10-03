# AutoUP workflow specification

## S1-S9 stage gates

| Stage | Input | Output | Hard gate |
|---|---|---|---|
| S1 source verify | URL manifest | verification CSV | duration, resolution and English subtitle availability pass |
| S2 download | approved URL | source video + `字幕/字幕.srt` | real playable video and selected subtitle exist |
| S3 script | SRT | `文案/爆款口播稿.txt` + `script_map.json` | every generated section is grounded in its subtitle window and target length passes |
| S4 dub | script | sentence WAVs + `timing.json` | every sentence audio exists and carries an input fingerprint |
| S5 match | SRT + timing | `edit_decision.json` | one semantic picture segment per sentence, all covered, chronological, non-overlapping |
| S6 render | source + timing + edit decision | `成片.mp4` | complete S5 mapping required; video/audio/subtitle render succeeds |
| S7 publication | script | CN/EN publication files + cover copy | strict format validation passes; otherwise fail closed |
| S8 cover | source + edit decision + cover copy | 9:16 / 16:9 / 1:1 PNGs | exact 6/8-character cover copy and exact pixel dimensions |
| S9 validate | all outputs | `验收报告.json` | every delivery contract passes |

## Resume semantics

`state.json` stores each stage status, input fingerprint, completion time, failure detail and measured stage duration. A stage is reusable only when:

- its status is `done`;
- required artifacts still exist;
- the current input/config fingerprint equals the stored fingerprint.

Changing an upstream file, model setting, voice, rendering config or other stage dependency invalidates the affected stage automatically. This avoids silently reusing stale outputs.

## Partial execution

`--only s3,s4,...` runs exactly the selected stages. S9 is not implicitly forced for a partial rerun. A full run includes S1-S9.

A batch exits non-zero if any selected topic fails, unless `--allow-partial` is explicitly supplied.

## Topic output

```text
<batch>/<NN-topic>/
├── 素材/高清源视频.mp4
├── 字幕/字幕.srt
├── 文案/爆款口播稿.txt
├── 文案/script_map.json
├── 配音/*.wav
├── 配音/timing.json
├── edit_decision.json
├── 成片工程/
├── 成片.mp4
├── 发布/
│   ├── 国内平台.txt
│   ├── 海外平台.txt
│   ├── 封面文案.txt
│   └── 发布信息.json
├── 封面/
│   ├── 封面-9x16.png
│   ├── 封面-16x9.png
│   └── 封面-1x1.png
├── state.json
└── 验收报告.json
```
