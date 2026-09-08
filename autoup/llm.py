"""GLM (zai/bigmodel OpenAI 兼容) 客户端: chat + JSON 模式, 带重试。

api_key 来源见 config._find_glm_key() (环境变量 GLM_API_KEY 或 Hermes .env)。
"""
from __future__ import annotations

import json
import logging
import re
import time

import requests

from . import config

log = logging.getLogger("autoup.llm")


def _headers() -> dict:
    key = str(config.get("llm.api_key", ""))
    if not key:
        raise RuntimeError("缺少 GLM_API_KEY (环境变量或 %LOCALAPPDATA%/hermes/.env)")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _strip_fence(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def chat(prompt: str, system: str = "", json_mode: bool = False,
         temperature: float | None = None) -> str:
    """单轮对话; json_mode=True 时要求输出可解析 JSON。"""
    url = str(config.get("llm.base_url")).rstrip("/") + "/chat/completions"
    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
    body = {
        "model": str(config.get("llm.model", "glm-4.6")),
        "messages": messages,
        "temperature": float(config.get("llm.temperature", 0.7))
                       if temperature is None else temperature,
        "max_tokens": 8192,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
        body["thinking"] = {"type": "disabled"}   # GLM 思考模型: JSON 输出禁用深度思考
    retries = int(config.get("llm.max_retries", 3))
    last_err: Exception | str = ""
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, headers=_headers(), json=body, timeout=300)
            if r.status_code == 200:
                msg = r.json()["choices"][0]["message"]
                content = (msg.get("content") or "").strip()
                if not content:
                    content = (msg.get("reasoning_content") or "").strip()
                if content:
                    return _strip_fence(content) if json_mode else content
                last_err = f"空内容: message keys={list(msg.keys())}"
            else:
                last_err = f"HTTP {r.status_code}: {r.text[:300]}"
        except (requests.RequestException, KeyError, ValueError) as e:
            last_err = str(e)
        log.warning("LLM 第 %d/%d 次失败: %s", attempt, retries, last_err)
        time.sleep(min(2 ** attempt * 2, 30))
    raise RuntimeError(f"LLM 调用失败(重试 {retries} 次): {last_err}")


def chat_json(prompt: str, system: str = "", temperature: float | None = None) -> dict:
    raw = chat(prompt, system=system, json_mode=True, temperature=temperature)
    try:
        return json.loads(raw)
    except ValueError:
        m = re.search(r"\{.*\}|\[.*\]", raw, re.S)
        if m:
            return json.loads(m.group(0))
        raise
