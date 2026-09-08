"""配置加载: config.yaml 为唯一事实来源, 提供点路径访问。"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_cfg_cache: dict | None = None


def repo_root() -> Path:
    return _REPO_ROOT


def load() -> dict:
    global _cfg_cache
    if _cfg_cache is None:
        path = _REPO_ROOT / "autoup" / "config.yaml"
        with open(path, encoding="utf-8") as f:
            _cfg_cache = yaml.safe_load(f) or {}
        _cfg_cache.setdefault("llm", {})
        if _cfg_cache["llm"].get("api_key") in (None, ""):
            _cfg_cache["llm"]["api_key"] = _find_glm_key()
    return _cfg_cache


def _find_glm_key() -> str:
    """GLM key: 环境变量优先, 其次 Hermes 的 .env。"""
    key = os.environ.get("GLM_API_KEY", "").strip()
    if key:
        return key
    env_file = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("GLM_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def get(dotted: str, default=None):
    node: object = load()
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def ffmpeg() -> str:
    return str(get("paths.ffmpeg", "ffmpeg"))


def ffprobe() -> str:
    return str(get("paths.ffprobe", "ffprobe"))


def output_root() -> Path:
    p = Path(str(get("paths.output_root", "D:/AutoUP")))
    p.mkdir(parents=True, exist_ok=True)
    return p
