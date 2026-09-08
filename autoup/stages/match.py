"""S5 影子匹配: 解说句 × 原片 SRT 语义匹配 → edit_decision.json。

匹配 prompt 思想参考 NarratoAI prompts/film_tv_narration/script_matching.py (MIT)。
护栏(在 LLM 之外由代码强制):
  - 每段 start/end 必须落在某个字幕块的 [start, end+容差] 内 (防幻觉)
  - 段间不重叠、时间递增
  - 画面时长 ≥ 配音时长 - 0.5s (不足时自动向后顺延扩展)
  - 自动剔除片头/片尾/广告/预告(关键字段 LLM 提示 + 字幕关键词二次过滤)
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .. import config, llm, utils

log = logging.getLogger("autoup.s5")

BAD_KEYWORDS = re.compile(
    r"订阅|关注(我们|频道)|赞助|广告|片尾|下集预告|感谢观看|subscribe|like and", re.I)
TAIL_TOLERANCE = 1.5      # 段尾允许超出字幕块尾的秒数
MIN_PICTURE_PAD = 0.5     # 画面比配音至少多出的缓冲


def _srt_context(srt: list[dict], max_chars: int = 12000) -> str:
    """SRT → 紧凑时间轴文本(带序号), 超长截尾。"""
    lines = [f"[{i}] {utils.fmt_ts(c['start'])}-{utils.fmt_ts(c['end'])} {c['text']}"
             for i, c in enumerate(srt)]
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...(字幕过长已截断, 只使用之前的段落)"
    return text


def _prompt(srt_text: str, sentences: list[str], topic: str) -> str:
    sent_lines = "\n".join(f"{i}. {s}" for i, s in enumerate(sentences, 1))
    return f"""# 纪录片解说-画面匹配任务

## 选题
{topic}

## 解说文案(逐句编号, 必须全部使用且按顺序)
<sentences>
{sent_lines}
</sentences>

## 原片英文字幕时间轴([序号] 起-止 英文)
<subtitles>
{srt_text}
</subtitles>

## 任务
为每一句解说匹配一段原片画面(取自字幕时间轴), 输出严格 JSON:
{{"items": [{{"sentence_index": 1, "start": "0:01:23.000", "end": "0:01:29.500"}}]}}

## 规则
1. 每句解说对应一段或多段连续画面; 按解说顺序输出 items。
2. 画面内容必须与解说句语义对应(事件/人物/场景/物件)。
3. 禁止匹配: 片头品牌动画、片尾致谢/订阅、广告、预告。字幕出现 subscribe/广告/预告类字样的时间段不得使用。
4. 画面时长要接近该句解说时长(中文约 0.21 秒/字), 可略长不可明显偏短。
5. 同一段画面只能被一句解说使用, items 之间时间不得重叠, 且必须时间递增。
6. 一句解说过长时可拆成多段连续画面(同一 sentence_index 出现多次)。
7. start/end 必须来自上面字幕时间轴的真实时间(可对齐到其间的任意点), 严禁编造不存在的时刻。
"""


def _parse_ts(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _validate_and_fix(items: list[dict], srt: list[dict],
                      sentences: list[str]) -> tuple[list[dict], list[str]]:
    """护栏校验 + 自动修复; 返回 (合法段列表, 问题说明列表)。"""
    problems: list[str] = []
    out: list[dict] = []
    last_end = -1.0
    video_end = srt[-1]["end"] if srt else 0.0
    # 字幕块边界索引: (块start, 块end+TOLERANCE)
    bounds = [(c["start"], c["end"] + TAIL_TOLERANCE) for c in srt]

    def clamp_to_srt(t: float) -> float | None:
        """时刻必须落在任一字幕块附近(±5s), 否则视为幻觉。"""
        for bs, be in bounds:
            if bs - 5.0 <= t <= be + 5.0:
                return min(max(t, bs), be)
        return None

    for it in items:
        try:
            si = int(it.get("sentence_index", 0))
            st, en = _parse_ts(str(it["start"])), _parse_ts(str(it["end"]))
        except (KeyError, TypeError, ValueError):
            problems.append(f"丢弃无法解析的段: {it}")
            continue
        if not (1 <= si <= len(sentences)):
            problems.append(f"句序号越界: {it}")
            continue
        cst = clamp_to_srt(st)
        if cst is None:
            problems.append(f"start 落在字幕空隙(疑似幻觉): {it['start']}")
            continue
        cen = clamp_to_srt(max(en, cst + 0.5))
        if cen is None:
            cen = min(cst + 5.0, video_end)
        st, en = min(cst, cen), max(cst, cen)
        if en > video_end:
            en = video_end
        if st <= last_end + 0.01:
            st = last_end + 0.05
            if en - st < 0.5:
                problems.append(f"段与前段重叠过多被丢弃: {it}")
                continue
            en = max(en, st + 0.5)
        # 画面时长须覆盖该句配音
        need = _sentence_need(sentences[si - 1])
        if en - st < need - 1.0:
            en = min(st + need, video_end)   # 顺延扩展
        if en <= st:
            problems.append(f"画面段无效: {it}")
            continue
        out.append({"sentence_index": si, "start": round(st, 3), "end": round(en, 3)})
        last_end = en
    return out, problems


def _sentence_need(sentence: str) -> float:
    """该句解说的配音时长需求(估时 + 句间间隙)。"""
    gap = float(config.get("voice.gap_seconds", 0.3))
    return utils.estimate_duration(sentence) + gap


def _filter_bad(srt: list[dict], items: list[dict]) -> list[dict]:
    """命中广告/片尾关键词的字幕块所在时间段直接弃用。"""
    bad_ranges = [(c["start"], c["end"]) for c in srt if BAD_KEYWORDS.search(c["text"])]
    if not bad_ranges:
        return items

    def overlap(a: dict) -> bool:
        return any(a["start"] < be and a["end"] > bs for bs, be in bad_ranges)

    kept = [a for a in items if not overlap(a)]
    if len(kept) != len(items):
        log.warning("广告/片尾过滤: %d 段被剔除", len(items) - len(kept))
    return kept


def run(topic_dir: Path) -> Path:
    srt_path = next((topic_dir / "字幕").glob("*.srt"), None) \
        if (topic_dir / "字幕").exists() else None
    timing = utils.read_json(topic_dir / "配音" / "timing.json")
    if srt_path is None:
        raise FileNotFoundError(f"缺少字幕: {topic_dir}/字幕/*.srt")
    if not timing:
        raise FileNotFoundError("缺少 timing.json (先跑 S4 配音)")

    sentences = [s["text"] for s in timing["sentences"]]
    srt = utils.parse_srt(srt_path)
    topic = topic_dir.name
    srt_text = _srt_context(srt)

    data = llm.chat_json(_prompt(srt_text, sentences, topic),
                         system="你是一位懂纪录片叙事节奏的剪辑师, 严格输出 JSON。",
                         temperature=0.3)
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError(f"LLM 返回结构异常: {str(data)[:200]}")

    # 按句覆盖检查: 缺句则补近似段(顺延上一段尾)
    fixed, problems = _validate_and_fix(items, srt, sentences)
    fixed = _filter_bad(srt, fixed)
    missing = sorted(set(range(1, len(sentences) + 1)) - {it["sentence_index"] for it in fixed})
    if missing:
        problems.append(f"未覆盖解说句: {missing}")
        fixed = _fill_missing(fixed, sentences, srt, missing)

    covered = sorted({it["sentence_index"] for it in fixed})
    ed = {
        "topic": topic,
        "source_srt": srt_path.name,
        "items": fixed,
        "uncovered_sentences": missing,
        "problems": problems,
        "total_picture_duration": round(sum(it["end"] - it["start"] for it in fixed), 3),
    }
    out = topic_dir / "edit_decision.json"
    utils.write_json(out, ed)
    log.info("匹配完成: %d 段画面 / %d 句解说, 覆盖 %d 句, 画面总时长 %.0fs",
             len(fixed), len(sentences), len(covered), ed["total_picture_duration"])
    if problems:
        log.warning("匹配问题(已尽力修复): %s", "; ".join(problems[:6]))
    return out


def _fill_missing(items: list[dict], sentences: list[str], srt: list[dict],
                  missing: list[int]) -> list[dict]:
    """未覆盖句: 在其相邻已覆盖段之间就近取字幕块补齐, 实在无处安放则放弃并记录。"""
    if not items:
        return items
    bounds = [c for c in srt]
    result = list(items)
    used = [(it["start"], it["end"]) for it in items]

    def free_slots() -> list[tuple[float, float]]:
        slots, prev = [], 0.0
        for st, en in sorted(used):
            if st - prev > 1.0:
                slots.append((prev, st))
            prev = en
        if bounds and bounds[-1]["end"] - prev > 1.0:
            slots.append((prev, bounds[-1]["end"]))
        return slots

    for si in missing:
        need = _sentence_need(sentences[si - 1])
        placed = False
        for bs, be in free_slots():
            if be - bs >= need:
                result.append({"sentence_index": si, "start": round(bs, 3),
                               "end": round(bs + need, 3)})
                used.append((bs, bs + need))
                placed = True
                break
        if not placed:
            log.warning("第 %d 句无处安放画面, 将用上一段画面延续", si)
    return sorted(result, key=lambda x: x["start"])
