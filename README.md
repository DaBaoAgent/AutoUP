<div align="center">

<img src="assets/readme/hero-20260912.webp" alt="AutoUP：从片源到发布就绪的纪录片视频流水线" width="100%" />

# AutoUP

### 给一份 YouTube 片源清单，自动产出纪录片解说成片

核验片源 → 下载高清素材 → 生成中文口播 → 配音 → 影子匹配 → 自动剪辑 → 字幕+BGM → 发布资料 → 三比例封面 → 验收

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-required-007808?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![License](https://img.shields.io/badge/license-MIT-2ea44f.svg)](LICENSE)

**本地运行 · 中间产物留档 · 失败可续跑 · 交付前自动验收**

</div>

> AutoUP 是面向纪录片解说创作者的本地化内容生产流水线。它负责把片源、字幕、文案、配音、画面和发布资料串成一条可复跑的生产线；最终发布动作仍由你在对应平台完成。

## 你会得到什么

输入一个 URL 清单：

```text
https://www.youtube.com/watch?v=...
https://www.youtube.com/watch?v=...
```

运行一条命令：

```bash
python -m autoup.run --manifest urls.txt --batch 20260911-A
```

每个通过验收的选题都会留下完整交付包：

```text
01-大西洋海战/
├── 成片.mp4              # 1080p 成片：硬字幕 + BGM + 配音
├── 封面/                  # 9:16 / 16:9 / 1:1
├── 发布/                  # 国内与海外平台发布资料
├── 素材/ 字幕/ 文案/ 配音/  # 可检查、可替换、可从中间阶段重跑
├── edit_decision.json     # 逐句画面匹配结果
├── state.json             # 断点状态
└── 验收报告.json           # 交付前检查结果
```

## 先看成片

以下 Demo 都是 AutoUP 流程产出的成片：

<table>
  <tr>
    <th>二战纪录片</th>
    <th>监狱纪录片</th>
    <th>自然纪录片</th>
  </tr>
  <tr>
    <td align="center">
      <video controls playsinline preload="metadata" width="100%" poster="assets/demos/poster-ww2.webp">
        <source src="assets/demos/demo-ww2.mp4" type="video/mp4" />
      </video>
    </td>
    <td align="center">
      <video controls playsinline preload="metadata" width="100%" poster="assets/demos/poster-prison.webp">
        <source src="assets/demos/demo-prison.mp4" type="video/mp4" />
      </video>
    </td>
    <td align="center">
      <video controls playsinline preload="metadata" width="100%" poster="assets/demos/poster-nature.webp">
        <source src="assets/demos/demo-nature.mp4" type="video/mp4" />
      </video>
    </td>
  </tr>
  <tr>
    <td align="center">点击播放按钮观看</td>
    <td align="center">点击播放按钮观看</td>
    <td align="center">点击播放按钮观看</td>
  </tr>
</table>

## 为什么是 AutoUP

### 一条流水线，但每一步都能检查

<img src="assets/readme/pipeline-20260912.webp" alt="AutoUP 六个核心阶段：素材、文案、配音、匹配、剪辑、交付" width="100%" />

- **片源先核验**：时长、最高分辨率、英文字幕不达标就拒单，避免下载后才发现无法生产。
- **文案以字幕为事实边界**：基于原片字幕生成中文解说，降低人名、数字和事件被凭空补写的风险。
- **影子匹配而不是随机拼接**：逐句将解说与原片字幕时间轴关联，再生成可审查的剪辑决策。
- **音画按实测时长对齐**：每句配音单独落盘，`timing.json` 记录真实时长，方便断点续跑和排查。
- **一次准备三种画幅**：横版、竖版、方版封面同时生成，适配不同发布场景。
- **验收报告作为门禁**：分辨率、时长、音轨、字幕、配音、发布资料和封面逐项检查。

### 它不是什么

- 不是一键生成后无法修改的黑盒 SaaS。
- 不是替你绕过平台规则或自动规避版权的工具。
- 不是剪辑软件的完整替代品：复杂创意剪辑仍建议在专业软件中做最后调整。

## 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/DaBaoAgent/AutoUP.git
cd AutoUP
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate
pip install -r requirements.txt
```

准备 **Python 3.11+**、**FFmpeg/ffprobe**，并确认它们可以被程序找到。首次使用前，打开 [`autoup/config.yaml`](autoup/config.yaml)，按本机环境调整路径和参数。

### 2. 配置模型 Key

文案和画面匹配需要一个兼容 OpenAI 格式的模型服务。默认配置为智谱，也可以修改 `llm.base_url` 和 `llm.model`：

```powershell
$env:GLM_API_KEY = "你的 API Key"
```

不想配置 GPT-SoVITS 时，可切换为免费的 Edge TTS：

```bash
python -m autoup.run --manifest urls.txt --batch demo --set voice.engine=edge_tts
```

### 3. 开始生产

```bash
# 完整流水线
python -m autoup.run --manifest urls.txt --batch 20260911-A

# 只重跑某些阶段
python -m autoup.run --batch 20260911-A --only s4,s5,s6

# 强制重跑指定阶段
python -m autoup.run --batch 20260911-A --only s8 --force

# 只处理前两个通过核验的选题
python -m autoup.run --manifest urls.txt --batch smoke --limit 2
```

同一批次再次运行时会读取 `state.json`。阶段状态和关键产物都会被核对，文件被删掉或不完整时会自动重新执行该阶段。

## 生产流程

```mermaid
flowchart LR
  A[URL 清单] --> B[S1 片源核验]
  B -->|通过| C[S2 下载视频与字幕]
  C --> D[S3 中文口播]
  D --> E[S4 逐句配音]
  E --> F[S5 影子匹配]
  F --> G[S6 渲染成片]
  G --> H[S7 发布资料]
  H --> I[S8 三比例封面]
  I --> J[S9 自动验收]
```

<img src="assets/readme/one-command-20260912.webp" alt="一条命令从输入到视频交付包" width="100%" />

## 配置重点

所有默认值集中在 [`autoup/config.yaml`](autoup/config.yaml)：

| 配置 | 作用 |
|---|---|
| `paths` | FFmpeg、GPT-SoVITS、输出目录 |
| `video` | 成片分辨率、帧率、编码器和质量 |
| `voice` | GPT-SoVITS / Edge TTS、音色、语速和停顿 |
| `subtitle` | 字体、字号、颜色和单行字数 |
| `script` | 文案目标字数、容差和分段长度 |
| `download` | 最低时长、最低分辨率、下载上限和代理 |

运行时可用 `--set key=value` 做单次覆盖，不会写回配置文件。

## 目录与文档

- [`docs/requirements.md`](docs/requirements.md)：产品规则与验收标准
- [`docs/research-editing-pipeline.md`](docs/research-editing-pipeline.md)：剪辑策略与技术选型
- [`docs/dev-notes.md`](docs/dev-notes.md)：开发记录与已知问题
- [`autoup/config.yaml`](autoup/config.yaml)：唯一配置事实来源

## 适用边界与合规

请只处理你有权使用的片源、字幕、音乐和字体，并遵守所在地法律法规以及 YouTube、抖音、快手、Bilibili、视频号、TikTok、X 等平台的服务条款。AutoUP 不提供版权授权，也不保证第三方平台内容可以被下载、改编或发布。

## 路线图

- [x] 片源核验、下载、字幕和断点续跑
- [x] AI 文案、双 TTS 引擎、逐句音频 timing
- [x] 字幕驱动的影子匹配与 FFmpeg 渲染
- [x] 国内/海外发布资料与三比例封面
- [x] 交付前自动验收
- [ ] 更丰富的本地素材输入与镜头策略
- [ ] 可视化任务面板与失败阶段重试
- [ ] 更多字幕语言和可插拔 TTS 引擎

## 贡献与许可

欢迎提交 Issue、改进文档或发起 Pull Request。使用前请先阅读 [`SKILL.md`](SKILL.md) 与项目文档。

本项目采用 [MIT License](LICENSE)。

<div align="center">

如果 AutoUP 帮你省下了剪辑时间，欢迎点一个 ⭐，也欢迎把真实问题反馈回来。

Made with ❤️ by Dabao

</div>
