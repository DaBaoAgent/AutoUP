"""S7 发布信息: 文案 → 国内平台(≤25字标题+5标签) / 海外平台(英文标题+描述) / 封面文案(6字主+8字副)。"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .. import llm, utils

log = logging.getLogger("autoup.s7")

SYSTEM = ("你是短视频发布运营专家, 熟悉抖音/YouTube 标题生态, 严格按要求格式输出 JSON。")


def _prompt(topic: str, script_text: str) -> str:
    body = script_text[:1800]
    return f"""纪录片选题: {topic}

解说词(节选):
<script>
{body}
</script>

基于解说词中真实出现的事实, 生成发布素材, 输出严格 JSON:
{{
 "cn_title": "国内平台标题, 最多25个字符(每个汉字/字母/数字/标点都算1字符), 信息差钩子, 基于真实数字/反差/后果",
 "cn_tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
 "en_title": "YouTube 风格英文标题, ≤90 字符, curiosity-driven",
 "en_description": "英文描述, 2-4 句, 概括视频内容, 末尾附 3 个英文 hashtag",
 "cover_main": "封面主标题, 恰好6个汉字",
 "cover_sub": "封面副标题, 恰好8个汉字"
}}

要求:
1. cn_title 严格 ≤25 字符且不含 # 号; cn_tags 恰好 5 个, 每个不含空格, 贴合选题垂类。
2. en_title/en_description 只用英文字符。
3. cover_main/cover_sub 必须恰好 6/8 个汉字, 来自选题最有冲击力的点, 不与 cn_title 完全相同。
4. 所有内容必须能在解说词中找到事实依据, 禁止夸大编造。
"""


def _validate(data: dict) -> list[str]:
    problems = []
    t = data.get("cn_title", "")
    if len(t) > 25:
        problems.append(f"国内标题 {len(t)} 字符超 25")
    tags = data.get("cn_tags", [])
    if len(tags) != 5:
        problems.append(f"标签数 {len(tags)} != 5")
    if not re.fullmatch(r"[\u4e00-\u9fff]{6}", data.get("cover_main", "")):
        problems.append("封面主标题不是 6 个汉字")
    if not re.fullmatch(r"[\u4e00-\u9fff]{8}", data.get("cover_sub", "")):
        problems.append("封面副标题不是 8 个汉字")
    return problems


def run(topic_dir: Path) -> Path:
    script_path = topic_dir / "文案" / "爆款口播稿.txt"
    if not script_path.exists():
        raise FileNotFoundError(f"缺少文案: {script_path}")
    text = script_path.read_text(encoding="utf-8-sig")
    data = llm.chat_json(_prompt(topic_dir.name, text), system=SYSTEM, temperature=0.6)

    problems = _validate(data)
    if problems:
        # 一次修复重试
        log.warning("格式问题 %s, 重试修复", problems)
        fix = llm.chat_json(
            "修复以下 JSON 使其满足要求: " + "; ".join(problems) +
            "\n原 JSON:\n" + json.dumps(data, ensure_ascii=False), system=SYSTEM, temperature=0.3)
        data = {**data, **fix}
        problems = _validate(data)
    # 硬兜底: 封面主/副标题超长时直接截断(保证 S8 排版规范)
    cm = re.sub(r"[^\u4e00-\u9fff]", "", data.get("cover_main", ""))
    cs = re.sub(r"[^\u4e00-\u9fff]", "", data.get("cover_sub", ""))
    if len(cm) > 6:
        data["cover_main"], problems = cm[:6], problems + ["主标题硬截断为6字"]
    if len(cs) > 8:
        data["cover_sub"], problems = cs[:8], problems + ["副标题硬截断为8字"]

    pub = topic_dir / "发布"
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "国内平台.txt").write_text(
        data.get("cn_title", "") + "\n" +
        " ".join(f"#{t.lstrip('#')}" for t in data.get("cn_tags", [])) + "\n", encoding="utf-8")
    (pub / "海外平台.txt").write_text(
        data.get("en_title", "") + "\n\n" + data.get("en_description", "") + "\n", encoding="utf-8")
    (pub / "封面文案.txt").write_text(
        data.get("cover_main", "") + "\n" + data.get("cover_sub", "") + "\n", encoding="utf-8")
    utils.write_json(pub / "发布信息.json", {"data": data, "problems": problems})
    log.info("发布信息完成%s", "" if not problems else f"(仍有问题: {problems})")
    return pub
