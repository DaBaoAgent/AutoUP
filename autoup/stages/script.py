"""S3 文案：完整字幕按时间顺序分块生成，所有段落都受对应字幕事实约束。"""
from __future__ import annotations

import logging
import math
import re
from pathlib import Path

from .. import config, llm, utils
from .dub import SCRIPT_NAME

log = logging.getLogger("autoup.s3")

SYSTEM = (
    "你是一位专业中文纪录片解说文案作者。"
    "你只输出可直接配音的正文，不输出标题、序号、括号备注或制作标签。"
)

RULES = """写作铁律:
1. 事实只能来自当前提供的字幕窗口，严禁新增字幕中不存在的人名、数字、事件和因果。
2. 纯口播：短句优先，主谓宾清楚，术语随口解释，数字适合中文配音。
3. 开头要迅速进入冲突/悬念；中段按时间与因果推进；最后一段自然收束。
4. 禁用模板化 AI 套话：首先、其次、总之、值得一提的是、不难发现、随着……的发展。
5. 不写镜头说明、生产提示、互动求赞、关注或转发话术。"""


def _count(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def _chunk_cues(cues: list[dict], parts: int) -> list[list[dict]]:
    if not cues:
        return []
    count = min(max(parts, 1), len(cues))
    chunks: list[list[dict]] = []
    total = len(cues)
    for index in range(count):
        start = round(index * total / count)
        end = round((index + 1) * total / count)
        chunk = cues[start:end]
        if chunk:
            chunks.append(chunk)
    return chunks


def _format_cues(cues: list[dict]) -> str:
    return "\n".join(
        f"[{utils.fmt_ts(cue['start'])}-{utils.fmt_ts(cue['end'])}] {cue['text']}"
        for cue in cues
    )


def _section_prompt(
    source_text: str,
    topic: str,
    target: int,
    prev_tail: str,
    part: int,
    total_parts: int,
    *,
    supplement: bool = False,
) -> str:
    previous = (
        f"\n上一段结尾，仅用于衔接，禁止重复：\n…{prev_tail}\n"
        if prev_tail
        else ""
    )
    if supplement:
        task = (
            "这是补充段。只从当前字幕窗口挑选前文尚未明确写过的事实细节，"
            "自然接到全文末尾；不要重复已有内容，不得新增事实。"
        )
    else:
        task = (
            f"这是全文第 {part}/{total_parts} 段。"
            f"{'写强钩子并进入主题。' if part == 1 else '承接上文继续推进。'}"
            f"{'自然收束全文。' if part == total_parts else '在自然叙事节点停笔。'}"
        )
    return f"""纪录片选题: {topic}

当前可用的原片字幕事实窗口:
<srt>
{source_text}
</srt>
{previous}
任务:
{task}

{RULES}

本段目标约 {target} 个汉字，允许约 ±15%。只输出正文。"""


def _clean_generated(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^(好的|以下是|正文如下|【[^】]+】)\s*[:：]?\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _trim_to_limit(text: str, limit: int) -> str:
    best_end: int | None = None
    for match in re.finditer(r"[。！？]", text):
        if _count(text[: match.end()]) <= limit:
            best_end = match.end()
        else:
            break
    if best_end:
        return text[:best_end].strip()

    visible = 0
    output: list[str] = []
    for char in text:
        if not char.isspace():
            visible += 1
        if visible > limit:
            break
        output.append(char)
    return "".join(output).rstrip("，、；： ") + "。"


def run(topic_dir: Path) -> Path:
    subtitle_dir = topic_dir / "字幕"
    srt_path = next(subtitle_dir.glob("*.srt"), None) if subtitle_dir.exists() else None
    if srt_path is None:
        raise FileNotFoundError(f"缺少字幕: {subtitle_dir}/*.srt")

    cues = utils.parse_srt(srt_path)
    if not cues:
        raise ValueError(f"字幕无法解析或为空: {srt_path}")

    target = int(config.get("script.target_chars", 4500))
    tolerance = float(config.get("script.tolerance", 0.12))
    section_chars = max(int(config.get("script.section_chars", 850)), 200)
    total_parts = max(1, math.ceil(target / section_chars))
    chunks = _chunk_cues(cues, total_parts)
    per_target = max(200, math.ceil(target / max(len(chunks), 1)))
    topic = topic_dir.name

    out_dir = topic_dir / "文案"
    out_dir.mkdir(parents=True, exist_ok=True)
    draft = out_dir / "爆款口播稿-draft.txt"
    map_path = out_dir / "script_map.json"

    parts: list[str] = []
    mapping: list[dict] = []
    for index, chunk in enumerate(chunks, 1):
        previous = parts[-1][-160:] if parts else ""
        generated = _clean_generated(
            llm.chat(
                _section_prompt(
                    _format_cues(chunk),
                    topic,
                    per_target,
                    previous,
                    index,
                    len(chunks),
                ),
                system=SYSTEM,
                temperature=0.75,
            )
        )
        if _count(generated) < 80:
            raise RuntimeError(f"S3 第 {index} 段生成过短: {_count(generated)} 字")
        parts.append(generated)
        mapping.append(
            {
                "part": index,
                "source_start": chunk[0]["start"],
                "source_end": chunk[-1]["end"],
                "text_chars": _count(generated),
            }
        )
        draft.write_text("\n\n".join(parts), encoding="utf-8")
        utils.write_json(map_path, {"parts": mapping})
        log.info("S3 第 %d/%d 段完成，累计 %d 字", index, len(chunks), _count("".join(parts)))

    full = "\n\n".join(parts)
    lower = int(target * (1 - tolerance))
    upper = int(target * (1 + tolerance))
    supplement_rounds = max(int(config.get("script.supplement_rounds", 2)), 0)

    for round_index in range(supplement_rounds):
        if _count(full) >= lower:
            break
        chunk = chunks[round_index % len(chunks)]
        need = min(per_target, lower - _count(full) + 120)
        generated = _clean_generated(
            llm.chat(
                _section_prompt(
                    _format_cues(chunk),
                    topic,
                    need,
                    full[-180:],
                    len(parts) + 1,
                    len(parts) + 1,
                    supplement=True,
                ),
                system=SYSTEM,
                temperature=0.65,
            )
        )
        if _count(generated) >= 60:
            parts.append(generated)
            mapping.append(
                {
                    "part": len(parts),
                    "source_start": chunk[0]["start"],
                    "source_end": chunk[-1]["end"],
                    "text_chars": _count(generated),
                    "supplement": True,
                }
            )
            full = "\n\n".join(parts)

    if _count(full) > upper:
        full = _trim_to_limit(full, upper)

    final_count = _count(full)
    if not lower <= final_count <= upper:
        raise RuntimeError(
            f"S3 字数验收失败: {final_count}，要求 {lower}-{upper}；拒绝用不受事实约束的内容硬补"
        )

    final = out_dir / SCRIPT_NAME
    final.write_text(full.strip(), encoding="utf-8")
    utils.write_json(
        map_path,
        {
            "source": srt_path.name,
            "target_chars": target,
            "final_chars": final_count,
            "parts": mapping,
        },
    )
    if draft.exists():
        draft.unlink()

    estimated = utils.estimate_duration(full)
    log.info("S3 完成: %d 字，预估配音 %.1f 分钟", final_count, estimated / 60)
    return final
