"""S3 文案: SRT → 中文解说词(分段生成, 字数验收, 补写循环)。

文风规则吸收 AutoYY references/content-style.md 与 vendor/blader-humanizer 精髓:
纯口播、事实锁死字幕、去 AI 味、无生产标签。
注: 按实测 edge_tts 语速约 0.25s/字, 4500 字 ≈ 19 分钟配音; 想压 15 分钟可调低
script.target_chars 或提高 voice.gpt_sovits.speed_factor / edge 语速。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .. import config, llm, utils
from .dub import SCRIPT_NAME

log = logging.getLogger("autoup.s3")

SYSTEM = (
    "你是一位顶级中文纪录片解说文案作者, 为历史/工程/灾难类纪录片写抖音横版长视频口播稿。"
    "你只输出解说词正文, 不输出任何标题、标注、括号说明或制作备注。"
)

RULES = """写作铁律:
1. 事实完全来自给定字幕内容, 严禁编造字幕中不存在的人名/数字/事件; 可以做合理的语言润色和因果串联, 不能新增事实。
2. 纯口语播稿: 短句、主谓宾清晰、数字读法友好(1943 → 一九四三年)、术语要随口解释。
3. 开头 3 句必须强钩子(悬念/反差/巨大数字), 中段层层推进, 结尾收束有余味, 不要"关注我"类互动话术。
4. 去 AI 味: 不用"首先/其次/总之/值得一提的是/不难发现/随着…的发展"模板词; 不用排比堆砌; 句长长短交错。
5. 直接输出解说词正文, 禁止任何小标题、序号、旁注、"(画面: xxx)"类提示。"""


def _srt_text(path: Path, max_chars: int = 24000) -> str:
    cues = utils.parse_srt(path)
    text = "\n".join(f"[{utils.fmt_ts(c['start'])}] {c['text']}" for c in cues)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…(字幕过长已截断)"
    return text


def _count(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def _section_prompt(srt_text: str, topic: str, target: int, prev_tail: str,
                    part: int, total_parts: int) -> str:
    head = (f"纪录片选题: {topic}\n\n原片字幕(英文, 带时间轴):\n<srt>\n{srt_text}\n</srt>\n\n"
            if part == 1 else "")
    prev = f"上一段结尾(必须无缝衔接, 不要重复其内容):\n…{prev_tail}\n\n" if prev_tail else ""
    task = (f"这是全文的第 {part}/{total_parts} 段。"
            f"{'写出开篇钩子并切入主题。' if part == 1 else '承接上文继续推进。'}"
            f"{'写出收束全文的结尾。' if part == total_parts else '在段落中间的自然处停笔。'}")
    return f"""{head}{prev}{task}

{RULES}

本段目标约 {target} 个汉字(允许 ±15%)。只输出本段解说词正文。"""


def run(topic_dir: Path) -> Path:
    srt_path = next((topic_dir / "字幕").glob("*.srt"), None) \
        if (topic_dir / "字幕").exists() else None
    if srt_path is None:
        raise FileNotFoundError(f"缺少字幕: {topic_dir}/字幕/*.srt")

    target = int(config.get("script.target_chars", 4500))
    tolerance = float(config.get("script.tolerance", 0.12))
    seg_size = int(config.get("script.section_chars", 850))
    total_parts = max(1, round(target / seg_size))
    srt_text = _srt_text(srt_path)
    topic = topic_dir.name

    out_dir = topic_dir / "文案"
    out_dir.mkdir(parents=True, exist_ok=True)
    draft = out_dir / f"爆款口播稿-draft.txt"

    parts: list[str] = []
    for p in range(1, total_parts + 1):
        prev_tail = parts[-1][-120:] if parts else ""
        text = llm.chat(_section_prompt(srt_text, topic, seg_size, prev_tail, p, total_parts),
                        system=SYSTEM, temperature=0.75).strip()
        text = re.sub(r"^(好的|以下是|【|\[).*?\n+", "", text)  # 防寒暄头
        parts.append(text)
        draft.write_text("\n\n".join(parts), encoding="utf-8")
        log.info("第 %d/%d 段完成, 累计 %d 字", p, total_parts, _count("".join(parts)))

    full = "\n\n".join(parts)
    lo, hi = int(target * (1 - tolerance)), int(target * (1 + tolerance))
    cnt = _count(full)
    # 补写循环(最多 3 轮, 每轮最多 2 段)
    rounds = 0
    while cnt < lo and rounds < 3:
        rounds += 1
        need = min(seg_size, lo - cnt + 100)
        prev_tail = full[-120:]
        add = llm.chat(_section_prompt(srt_text, topic, need, prev_tail,
                                       len(parts) + 1, len(parts) + 1),
                       system=SYSTEM, temperature=0.75).strip()
        parts.append(add)
        full = "\n\n".join(parts)
        cnt = _count(full)
        log.info("补写 %d 字, 现 %d 字", _count(add), cnt)
    if cnt > hi:
        # 截到最后一个句号且不低于下限
        cut = full
        while _count(cut) > hi:
            idx = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"))
            if idx <= 0:
                break
            cut = cut[:idx + 1]
        if _count(cut) >= lo:
            full = cut
        log.warning("文案超上限, 截至约 %d 字(如需更长请调高 script.target_chars)", _count(full))

    # 清洗: 合并多余空行, 去生产标签
    full = re.sub(r"\n{3,}", "\n\n", full).strip()
    final = out_dir / SCRIPT_NAME
    final.write_text(full, encoding="utf-8")
    if draft.exists() and final.exists():
        draft.unlink()

    est = utils.estimate_duration(full)
    log.info("文案完成: %d 字, 预估配音 %.0fs (%.1f 分钟)", _count(full), est, est / 60)
    if not (lo <= _count(full) <= hi):
        log.warning("字数 %d 不在 [%d, %d], 请人工复核", _count(full), lo, hi)
    return final
