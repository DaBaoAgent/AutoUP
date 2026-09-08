"""GPT-SoVITS api_v2 客户端 + 服务自拉起。

协议与服务管理参考 VideoLingo core/tts_backend/gpt_sovits_tts.py (Apache-2.0),
按本机部署形态 (D:/@佳康顺矩阵/@工具/GPT-SoVITS, api_v2.py, runtime/python.exe) 适配。
"""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

import requests

from .. import config

log = logging.getLogger("autoup.tts.gptsovits")


def _alive(url: str) -> bool:
    try:
        return requests.get(url, timeout=2).status_code == 200
    except requests.RequestException:
        return False


def _find_python(root: Path) -> Path | None:
    """官方整合包为 runtime/python.exe; 本机布局可能是 .venv/Scripts/python.exe。"""
    for cand in (root / "runtime" / "python.exe",
                 root / ".venv" / "Scripts" / "python.exe"):
        if cand.exists():
            return cand
    return None


def ensure_server() -> bool:
    """确保 GPT-SoVITS api_v2 就绪; 未运行则后台拉起并轮询等待。"""
    ping = str(config.get("voice.gpt_sovits.ping"))
    if _alive(ping):
        return True
    root = Path(str(config.get("paths.gpt_sovits_root", "")))
    api = root / "api_v2.py"
    py = _find_python(root)
    if not api.exists() or py is None:
        log.error("GPT-SoVITS 目录不完整: %s (需要 api_v2.py 与 python 解释器)", root)
        return False
    cmd = [str(py), str(api), "-a", "127.0.0.1", "-p", "9880"]
    cfg_yaml = config.get("voice.gpt_sovits.config_yaml")
    if cfg_yaml:
        cmd += ["-c", str(cfg_yaml)]
    log.info("启动 GPT-SoVITS api_v2 (首次约 1 分钟)...")
    subprocess.Popen(
        cmd,
        cwd=str(root),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    timeout = int(config.get("voice.gpt_sovits.startup_timeout", 180))
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(5)
        if _alive(ping):
            log.info("GPT-SoVITS 就绪 (等待 %.0fs)", time.time() - t0)
            return True
    log.error("GPT-SoVITS %ds 内未就绪", timeout)
    return False


def synth(text: str, out_path: Path, voice: str = "default") -> bool:
    """合成一句中文语音; voice 为 config.voice.gpt_sovits.voices 的键。"""
    vcfg = config.get(f"voice.gpt_sovits.voices.{voice}") or {}
    ref = vcfg.get("ref_audio_path")
    prompt = vcfg.get("prompt_text", "")
    if not ref or not Path(str(ref)).exists():
        log.error("音色 %r 参考音频无效: %r", voice, ref)
        return False
    payload = {
        "text": text,
        "text_lang": config.get("voice.gpt_sovits.text_lang", "zh"),
        "ref_audio_path": str(ref),
        "prompt_lang": config.get("voice.gpt_sovits.prompt_lang", "zh"),
        "prompt_text": prompt,
        "speed_factor": float(config.get("voice.gpt_sovits.speed_factor", 1.0)),
    }
    try:
        r = requests.post(str(config.get("voice.gpt_sovits.api")), json=payload, timeout=120)
    except requests.RequestException as e:
        log.error("GPT-SoVITS 请求失败: %s", e)
        return False
    if r.status_code == 200 and r.content[:4] == b"RIFF":
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(r.content)
        return True
    log.error("GPT-SoVITS 返回异常: %s %s", r.status_code, r.content[:120])
    return False
