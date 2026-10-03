"""配置加载：仓库默认配置 + 可选本机覆盖，提供点路径访问。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "autoup" / "config.yaml"
_LOCAL_CONFIG_PATH = _REPO_ROOT / "autoup" / "config.local.yaml"
_cfg_cache: dict[str, Any] | None = None


def repo_root() -> Path:
    return _REPO_ROOT


def reset_cache() -> None:
    """清空配置缓存，主要用于测试和运行期切换配置。"""
    global _cfg_cache
    _cfg_cache = None


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置根节点必须是 mapping: {path}")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _set_dotted(data: dict[str, Any], dotted: str, value: Any) -> None:
    node = data
    parts = dotted.split(".")
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def load() -> dict[str, Any]:
    global _cfg_cache
    if _cfg_cache is not None:
        return _cfg_cache

    cfg = _read_yaml(_CONFIG_PATH)
    local_path = Path(os.environ.get("AUTOUP_CONFIG", "")).expanduser() if os.environ.get("AUTOUP_CONFIG") else _LOCAL_CONFIG_PATH
    if local_path.exists():
        _deep_merge(cfg, _read_yaml(local_path))

    env_map = {
        "AUTOUP_FFMPEG": "paths.ffmpeg",
        "AUTOUP_FFPROBE": "paths.ffprobe",
        "AUTOUP_OUTPUT_ROOT": "paths.output_root",
        "AUTOUP_GPT_SOVITS_ROOT": "paths.gpt_sovits_root",
        "AUTOUP_LLM_BASE_URL": "llm.base_url",
        "AUTOUP_LLM_MODEL": "llm.model",
    }
    for env_name, dotted in env_map.items():
        value = os.environ.get(env_name)
        if value:
            _set_dotted(cfg, dotted, value)

    cfg.setdefault("llm", {})
    if not cfg["llm"].get("api_key"):
        cfg["llm"]["api_key"] = _find_glm_key()

    _cfg_cache = cfg
    return cfg


def _find_glm_key() -> str:
    """GLM key：环境变量优先，兼容 Hermes 的本机 .env。"""
    for name in ("GLM_API_KEY", "ZHIPUAI_API_KEY"):
        key = os.environ.get(name, "").strip()
        if key:
            return key

    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return ""
    env_file = Path(local_appdata) / "hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("GLM_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def get(dotted: str, default: Any = None) -> Any:
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
    raw = Path(str(get("paths.output_root", "output"))).expanduser()
    path = raw if raw.is_absolute() else _REPO_ROOT / raw
    path.mkdir(parents=True, exist_ok=True)
    return path
