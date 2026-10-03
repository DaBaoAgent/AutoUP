"""S5 画面匹配：按解说进度分窗口匹配，缺句必须二次修复，禁止随机空闲画面兜底。"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .. import config, llm, utils

log = logging.getLogger("autoup.s5")

BAD_KEYWORDS = re.compile(
    r"订阅|关注(我们|频道)|赞助|广告|片尾|下集预告|感谢观看|subscribe|like and",
    re.I,
)
TAIL_TOLERANCE = 1.5


def _srt_context(cues: list[dict], max_chars: int) -> str:
    lines = [
        f"[{index}] {utils.fmt_ts(cue['start'])}-{utils.fmt_ts(cue['end'])} {cue['text']}"
        for index, cue in enumerate(cues)
    ]
    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    center = len(text) // 2
    return "...(窗口前部省略)\n" + text[max(0, center - half) : center + half] + "\n...(窗口后部省略)"


def _window_cues(
    srt: list[dict],
    start_fraction: float,
    end_fraction: float,
    overlap_ratio: float,
) -> list[dict]:
    if not srt:
        return []
    source_start = srt[0]["start"]
    source_end = srt[-1]["end"]
    duration = max(source_end - source_start, 1.0)
    span = max(end_fraction - start_fraction, 0.01)
    margin = span * max(overlap_ratio, 0.0)
    left = max(0.0, start_fraction - margin)
    right = min(1.0, end_fraction + margin)
    window_start = source_start + duration * left
    window_end = source_start + duration * right
    selected = [
        cue for cue in srt if cue["end"] >= window_start and cue["start"] <= window_end
    ]
    return selected or srt


def _prompt(cues_text: str, sentences: list[dict], topic: str, *, repair: bool = False) -> str:
    sentence_lines = "\n".join(
        f"{item['index']}. {item['text']}" for item in sentences
    )
    task = (
        "这是缺失句修复任务。只返回这些句子的匹配结果。"
        if repair
        else "这是本批次的画面匹配任务。"
    )
    return f"""# 纪录片解说-画面匹配

选题: {topic}
{task}

解说句（使用这里给出的全局 sentence_index）:
<sentences>
{sentence_lines}
</sentences>

当前允许使用的原片字幕时间窗口:
<subtitles>
{cues_text}
</subtitles>

输出严格 JSON:
{{"items": [{{"sentence_index": 1, "start": "0:01:23.000", "end": "0:01:29.500"}}]}}

规则:
1. 每一句必须且只对应一段连续画面，sentence_index 必须与上面的全局编号一致。
2. 按句子顺序选择时间递增、互不重叠的真实画面。
3. start 必须落在给定字幕窗口附近，end 可向后延长以覆盖配音时长。
4. 禁止片头品牌动画、订阅/广告、片尾致谢和预告。
5. 内容必须与该解说句语义对应；找不到合适画面时不要编造时间。"""


def _parse_ts(value: str) -> float:
    parts = [float(part) for part in value.strip().replace(",", ".").split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _clamp_start(value: float, srt: list[dict]) -> float | None:
    for cue in srt:
        left = cue["start"] - 5.0
        right = cue["end"] + TAIL_TOLERANCE + 5.0
        if left <= value <= right:
            return max(cue["start"], min(value, cue["end"] + TAIL_TOLERANCE))
    return None


def _filter_bad(srt: list[dict], items: list[dict]) -> list[dict]:
    bad_ranges = [
        (cue["start"], cue["end"]) for cue in srt if BAD_KEYWORDS.search(cue["text"])
    ]
    if not bad_ranges:
        return items

    def overlaps(item: dict) -> bool:
        return any(item["start"] < end and item["end"] > start for start, end in bad_ranges)

    return [item for item in items if not overlaps(item)]


def _validate_and_fix(
    raw_items: list[dict],
    srt: list[dict],
    sentences: list[dict],
) -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    by_index = {int(item["index"]): item for item in sentences}
    parsed: list[dict] = []

    for raw in raw_items:
        try:
            sentence_index = int(raw.get("sentence_index", 0))
            start = _parse_ts(str(raw["start"]))
            end = _parse_ts(str(raw["end"]))
        except (KeyError, TypeError, ValueError):
            problems.append(f"丢弃无法解析的段: {str(raw)[:120]}")
            continue
        if sentence_index not in by_index:
            problems.append(f"句序号越界: {sentence_index}")
            continue
        parsed.append(
            {"sentence_index": sentence_index, "start": start, "end": end}
        )

    parsed.sort(key=lambda item: (item["sentence_index"], item["start"]))
    output: list[dict] = []
    seen: set[int] = set()
    last_end = -1.0
    video_end = srt[-1]["end"] if srt else 0.0
    gap = float(config.get("voice.gap_seconds", 0.3))

    for item in parsed:
        sentence_index = item["sentence_index"]
        if sentence_index in seen:
            problems.append(f"第 {sentence_index} 句返回多个片段，仅保留首个")
            continue

        start = _clamp_start(item["start"], srt)
        if start is None:
            problems.append(f"第 {sentence_index} 句 start 不在真实字幕附近")
            continue
        start = max(start, last_end + 0.05 if last_end >= 0 else start)
        minimum = float(by_index[sentence_index].get("duration", 0)) + gap
        end = max(float(item["end"]), start + max(minimum, 0.5))
        end = min(end, video_end)
        if end - start < max(minimum - 0.5, 0.4):
            problems.append(f"第 {sentence_index} 句画面时长不足")
            continue

        fixed = {
            "sentence_index": sentence_index,
            "start": round(start, 3),
            "end": round(end, 3),
        }
        output.append(fixed)
        seen.add(sentence_index)
        last_end = end

    return output, problems


def _call_match(
    topic: str,
    srt: list[dict],
    sentences: list[dict],
    total_sentences: int,
    *,
    repair: bool,
) -> list[dict]:
    first_index = int(sentences[0]["index"])
    last_index = int(sentences[-1]["index"])
    start_fraction = max((first_index - 1) / max(total_sentences, 1), 0.0)
    end_fraction = min(last_index / max(total_sentences, 1), 1.0)
    cues = _window_cues(
        srt,
        start_fraction,
        end_fraction,
        float(config.get("match.window_overlap", 0.15)),
    )
    context = _srt_context(cues, int(config.get("match.max_context_chars", 14000)))
    data = llm.chat_json(
        _prompt(context, sentences, topic, repair=repair),
        system="你是纪录片剪辑师，只能使用给定的真实字幕时间窗口，严格输出 JSON。",
        temperature=0.25 if repair else 0.3,
    )
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError(f"LLM 返回结构异常: {str(data)[:200]}")
    return items


def run(topic_dir: Path) -> Path:
    subtitle_dir = topic_dir / "字幕"
    srt_path = next(subtitle_dir.glob("*.srt"), None) if subtitle_dir.exists() else None
    timing = utils.read_json(topic_dir / "配音" / "timing.json")
    if srt_path is None:
        raise FileNotFoundError(f"缺少字幕: {subtitle_dir}/*.srt")
    if not timing or not timing.get("sentences"):
        raise FileNotFoundError("缺少有效 timing.json（先跑 S4）")

    sentences = timing["sentences"]
    srt = utils.parse_srt(srt_path)
    if not srt:
        raise ValueError("SRT 无有效字幕块")

    batch_size = max(int(config.get("match.batch_sentences", 6)), 1)
    topic = topic_dir.name
    raw_items: list[dict] = []
    for offset in range(0, len(sentences), batch_size):
        batch = sentences[offset : offset + batch_size]
        raw_items.extend(_call_match(topic, srt, batch, len(sentences), repair=False))
        log.info(
            "S5 匹配批次 %d-%d/%d",
            batch[0]["index"],
            batch[-1]["index"],
            len(sentences),
        )

    fixed, problems = _validate_and_fix(raw_items, srt, sentences)
    fixed = _filter_bad(srt, fixed)

    repair_attempts = max(int(config.get("match.repair_attempts", 2)), 0)
    repairs_used = 0
    for attempt in range(repair_attempts):
        covered = {item["sentence_index"] for item in fixed}
        missing = [
            sentence for sentence in sentences if int(sentence["index"]) not in covered
        ]
        if not missing:
            break
        repairs_used = attempt + 1
        log.warning("S5 第 %d 轮修复，缺失 %d 句", repairs_used, len(missing))
        repair_raw: list[dict] = []
        for offset in range(0, len(missing), batch_size):
            batch = missing[offset : offset + batch_size]
            repair_raw.extend(_call_match(topic, srt, batch, len(sentences), repair=True))
        raw_items.extend(repair_raw)
        fixed, new_problems = _validate_and_fix(raw_items, srt, sentences)
        problems.extend(new_problems)
        fixed = _filter_bad(srt, fixed)

    covered = {item["sentence_index"] for item in fixed}
    missing_indexes = [
        int(sentence["index"])
        for sentence in sentences
        if int(sentence["index"]) not in covered
    ]
    if missing_indexes:
        raise RuntimeError(
            "S5 语义匹配验收失败，仍有未覆盖句，拒绝随机补画面: "
            + ",".join(map(str, missing_indexes[:20]))
        )

    expected_indexes = {int(sentence["index"]) for sentence in sentences}
    if covered != expected_indexes or len(fixed) != len(sentences):
        raise RuntimeError("S5 覆盖集合异常，未达到一语句一画面的硬门槛")

    edit = {
        "topic": topic,
        "source_srt": srt_path.name,
        "items": fixed,
        "uncovered_sentences": [],
        "problems": problems[-50:],
        "repair_rounds": repairs_used,
        "total_picture_duration": round(
            sum(item["end"] - item["start"] for item in fixed),
            3,
        ),
    }
    output = topic_dir / "edit_decision.json"
    utils.write_json(output, edit)
    log.info("S5 完成: %d 句全部覆盖，%d 轮修复", len(sentences), repairs_used)
    return output
