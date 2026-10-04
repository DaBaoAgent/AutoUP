"""OpenAI 兼容 LLM 客户端：连接复用、JSON 模式与有边界的重试。"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests

from . import config

log = logging.getLogger("autoup.llm")
_SESSION = requests.Session()


def _headers() -> dict[str, str]:
    key = str(config.get("llm.api_key", "") or "")
    if not key:
        raise RuntimeError("缺少 GLM_API_KEY（环境变量或本机配置）")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _strip_fence(text: str) -> str:
    match = re.search(r"\x60\x60\x60(?:json)?\s*(.*?)\x60\x60\x60", text, re.S | re.I)
    return (match.group(1) if match else text).strip()


def chat(
    prompt: str,
    system: str = "",
    json_mode: bool = False,
    temperature: float | None = None,
) -> str:
    base_url = str(config.get("llm.base_url", "") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("llm.base_url 未配置")

    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    body: dict[str, Any] = {
        "model": str(config.get("llm.model", "glm-4.6")),
        "messages": messages,
        "temperature": float(config.get("llm.temperature", 0.7))
        if temperature is None
        else temperature,
        "max_tokens": int(config.get("llm.max_tokens", 8192)),
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
        body["thinking"] = {"type": "disabled"}

    retries = max(int(config.get("llm.max_retries", 3)), 1)
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            response = _SESSION.post(
                f"{base_url}/chat/completions",
                headers=_headers(),
                json=body,
                timeout=300,
            )
            if response.status_code == 200:
                message = response.json()["choices"][0]["message"]
                content = (message.get("content") or "").strip()
                if not content:
                    content = (message.get("reasoning_content") or "").strip()
                if content:
                    return _strip_fence(content) if json_mode else content
                last_error = f"空内容: keys={list(message.keys())}"
            else:
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                if response.status_code < 500 and response.status_code != 429:
                    break
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            last_error = str(exc)

        if attempt < retries:
            delay = min(2 ** attempt * 2, 30)
            log.warning(
                "LLM 第 %d/%d 次失败: %s；%ds 后重试",
                attempt,
                retries,
                last_error,
                delay,
            )
            time.sleep(delay)

    raise RuntimeError(f"LLM 调用失败（尝试 {retries} 次）: {last_error}")


def chat_json(
    prompt: str,
    system: str = "",
    temperature: float | None = None,
) -> Any:
    raw = chat(prompt, system=system, json_mode=True, temperature=temperature)
    try:
        return json.loads(raw)
    except ValueError:
        cleaned = _strip_fence(raw)
        for pattern in (r"\{.*\}", r"\[.*\]"):
            match = re.search(pattern, cleaned, re.S)
            if match:
                return json.loads(match.group(0))
        raise
