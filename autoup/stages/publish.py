"""S7 发布信息：生成后严格校验，不合格则修复重试，最终 fail-closed。"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .. import config, llm, utils

log = logging.getLogger("autoup.s7")

SYSTEM = "你是短视频发布运营编辑，只能基于给定解说词事实，严格按 JSON 格式输出。"


def _prompt(topic: str, script_text: str) -> str:
    body = script_text[:2500]
    return f"""纪录片选题: {topic}

解说词节选:
<script>
{body}
</script>

输出严格 JSON:
{{
  "cn_title": "国内平台标题，最多25字符，不含#",
  "cn_tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
  "en_title": "英文标题，最多90字符",
  "en_description": "英文描述2-4句，末尾3个英文hashtag",
  "cover_main": "恰好6个汉字",
  "cover_sub": "恰好8个汉字"
}}

硬规则:
1. 所有事实必须来自解说词，禁止夸大或新增事实。
2. cn_title 必须非空且 <=25字符；cn_tags 恰好5个，每个标签不含空格和#。
3. en_title 必须非空且 <=90字符；英文标题和描述不得出现中文字符。
4. cover_main 必须恰好6个汉字，cover_sub 必须恰好8个汉字。
5. 只输出 JSON。"""


def _validate(data: dict) -> list[str]:
    problems: list[str] = []
    cn_title = str(data.get("cn_title", "")).strip()
    tags = data.get("cn_tags", [])
    en_title = str(data.get("en_title", "")).strip()
    en_description = str(data.get("en_description", "")).strip()
    cover_main = str(data.get("cover_main", "")).strip()
    cover_sub = str(data.get("cover_sub", "")).strip()

    if not cn_title or len(cn_title) > 25 or "#" in cn_title:
        problems.append("国内标题必须非空、≤25字符且不含#")
    if not isinstance(tags, list) or len(tags) != 5:
        problems.append("国内标签必须恰好5个")
    else:
        normalized = [str(tag).strip() for tag in tags]
        if any(not tag or "#" in tag or re.search(r"\s", tag) for tag in normalized):
            problems.append("每个国内标签必须非空且不含空格/#")
        if len(set(normalized)) != 5:
            problems.append("国内标签不能重复")

    if not en_title or len(en_title) > 90:
        problems.append("英文标题必须非空且≤90字符")
    if re.search(r"[\u4e00-\u9fff]", en_title + en_description):
        problems.append("英文标题/描述不得包含中文")
    if not en_description:
        problems.append("英文描述不能为空")
    if not re.fullmatch(r"[\u4e00-\u9fff]{6}", cover_main):
        problems.append("封面主标题必须恰好6个汉字")
    if not re.fullmatch(r"[\u4e00-\u9fff]{8}", cover_sub):
        problems.append("封面副标题必须恰好8个汉字")
    return problems


def run(topic_dir: Path) -> Path:
    script_path = topic_dir / "文案" / "爆款口播稿.txt"
    if not script_path.exists():
        raise FileNotFoundError(f"缺少文案: {script_path}")
    script_text = script_path.read_text(encoding="utf-8-sig")
    data = llm.chat_json(
        _prompt(topic_dir.name, script_text),
        system=SYSTEM,
        temperature=0.6,
    )
    if not isinstance(data, dict):
        raise ValueError("S7 LLM 返回的不是 JSON object")

    attempts = max(int(config.get("publish.repair_attempts", 2)), 0)
    problems = _validate(data)
    for attempt in range(attempts):
        if not problems:
            break
        log.warning("S7 格式修复第 %d/%d 轮: %s", attempt + 1, attempts, problems)
        fixed = llm.chat_json(
            "只修复格式和长度，不新增任何事实。\n"
            + "问题: "
            + "; ".join(problems)
            + "\n原 JSON:\n"
            + json.dumps(data, ensure_ascii=False),
            system=SYSTEM,
            temperature=0.25,
        )
        if not isinstance(fixed, dict):
            continue
        data = {**data, **fixed}
        problems = _validate(data)

    if problems:
        raise ValueError("S7 发布信息验收失败: " + "; ".join(problems))

    publish_dir = topic_dir / "发布"
    publish_dir.mkdir(parents=True, exist_ok=True)
    tags = [str(tag).strip().lstrip("#") for tag in data["cn_tags"]]
    (publish_dir / "国内平台.txt").write_text(
        str(data["cn_title"]).strip()
        + "\n"
        + " ".join(f"#{tag}" for tag in tags)
        + "\n",
        encoding="utf-8",
    )
    (publish_dir / "海外平台.txt").write_text(
        str(data["en_title"]).strip()
        + "\n\n"
        + str(data["en_description"]).strip()
        + "\n",
        encoding="utf-8",
    )
    (publish_dir / "封面文案.txt").write_text(
        str(data["cover_main"]).strip()
        + "\n"
        + str(data["cover_sub"]).strip()
        + "\n",
        encoding="utf-8",
    )
    utils.write_json(publish_dir / "发布信息.json", {"data": data, "problems": []})
    log.info("S7 完成")
    return publish_dir
