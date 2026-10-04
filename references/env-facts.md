# AutoUP 环境约定

AutoUP 不绑定任何开发者电脑路径。仓库提交的 `autoup/config.yaml` 只包含可移植默认值。

## 配置优先级

1. `autoup/config.yaml`：仓库默认值；
2. `autoup/config.local.yaml`：本机覆盖，已加入 `.gitignore`；
3. `AUTOUP_*` 环境变量；
4. 命令行 `--set key=value`：仅本次运行覆盖。

可从 `autoup/config.example.yaml` 复制一份本机配置。

## 必要环境

- Python 3.11+
- FFmpeg / ffprobe
- 一个 OpenAI 兼容的 LLM API；默认配置使用 GLM
- Edge TTS 可直接作为免费 TTS；GPT-SoVITS 为可选本地引擎

API Key 使用环境变量，例如 `GLM_API_KEY`，不要提交到仓库。

## 开发与验收

依赖与工具统一由 `pyproject.toml` + `uv.lock` 管理。CI 在 Linux 做完整 lint/test/coverage，在 Windows 做安装和核心 smoke test。
