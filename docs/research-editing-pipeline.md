# AutoUP 剪辑合成技术选型报告（2026-09-08）

> 调研对象：GitHub 高星同类项目源码级深读。结论服务于 docs/requirements.md 第 5/6/7/8 环节（配音→影子匹配→合成剪辑→字幕/BGM）的实现选型。**本文档结论经用户确认后动工。**

## 1. 全景对比

| 项目 | ⭐ | 许可 | 活跃 | 路线 | 对 AutoUP 的价值 |
|---|---|---|---|---|---|
| MoneyPrinterTurbo | 121k | MIT | 活跃 | 素材库混剪：LLM 文案→Pexels/本地素材→moviepy 合成 | 合成流程参考，但画面来源与我们不同 |
| NarratoAI | 11k | MIT | 活跃 | **影视解说压剪**：文案↔字幕时间戳匹配→FFmpeg 逐段剪切→拼接 | ★ 主参考，问题域完全一致 |
| VideoLingo | 18k | Apache-2.0 | 活跃 | 视频翻译配音：ASR→翻译→TTS 对齐原字幕时间轴 | ★ 配音工程参考（GPT-SoVITS 集成） |
| FunClip | 6.2k | MIT | 活跃 | FunASR 转写→LLM 选段→CLI 剪切 | 无 ASR 需求（我们有官方 SRT），仅思想参考 |
| auto-editor | 5.1k | Unlicense | 活跃 | 静音检测自动剪 | 不适用（我们是内容驱动剪辑） |
| ShortGPT | 7.9k | MIT | **2025-02 停更** | 素材库自动短视频 | 不选 |
| OpenCreator(原KrillinAI) | 11.3k | **无许可** | 活跃 | 一体化创作 | 无许可不可移植代码，仅产品形态参考 |

## 2. 三强核心发现（源码级）

### NarratoAI —— 剪辑路线的直接答案
- **压剪模型**：`clip_video.py` 的 OST=0 段处理——「解说时长决定画面时长」：`end = start + TTS时长`，FFmpeg `-ss/-to` fast-seek 逐段剪切 + `-an` 去原声，与需求「纯解说压剪」完全同构。我们只需 OST=0 一种段型，比它更简单。
- **工程健壮性**：编码器 fallback 链（NVENC→AMF→QSV→libx264）、`-avoid_negative_ts make_zero`、`+faststart`——直接移植。
- **影子匹配 prompt**（`prompts/film_tv_narration/script_matching.py`）：逐句切分解说→匹配 SRT 时间戳→JSON items；关键护栏：字幕索引校验（时间戳必须命中真实字幕块，防幻觉）、禁止匹配片头/广告/预告、**估时公式「字数/5 秒」**、同视频内时间段不得重叠、长句拆多段。
- **总装一条流**（`generate_video.py:_build_ffmpeg_merge_command`）：视频+配音+BGM 三输入，BGM `-stream_loop -1` 循环 + 尾部 `afade=t=out:d=3`，`amix normalize=0`（不做自动增益，音量全靠 config），字幕 `subtitles` 滤镜 → `drawtext` → PNG overlay 三级降级。

### VideoLingo —— 配音对齐的工程细节
- **GPT-SoVITS 集成**（`tts_backend/gpt_sovits_tts.py`）：api_v2 协议 POST `127.0.0.1:9880/tts`（text/text_lang/ref_audio_path/prompt_text/speed_factor）；**服务自拉起**：探端口→`runtime\python.exe api_v2.py -c 角色.yaml`→ping 等就绪。本机 `D:\@佳康顺矩阵\@工具\GPT-SoVITS` 含 `api_v2.py`，协议直接可用。
- **参考音频三种模式**：①角色默认参考音频 ②用第 1 句克隆源 ③逐句用原片对应音频。我们用模式①+config 多音色。
- **音节估时**（`estimate_duration.py`）：中文按拼音音节×0.21s+标点停顿，预估每句配音时长，用于**配音前**的时长预算——比 NarratoAI 的「字数/5」更准。
- **音频拼接**（`_11_merge_audio.py`）：分段 wav→pydub→按时间轴插静音→合并；音量归一化后进成片。

### MoneyPrinterTurbo —— 不走 moviepy 的理由
- MPT 用 moviepy 做合成（内存加载全部片段、8-15min 1080p 重编码慢、Windows 易 codec 坑——它自己都写了 codec fallback）。**结论：AutoUP 全程 FFmpeg 命令流，不引入 moviepy**，与 NarratoAI 同路线但更彻底（无 OST=1/2 混合段型，无需逐段重编码两次）。
- 可借鉴：BGM 曲库管理、`get_audio_duration` 多来源兜底、断点状态机思想。

## 3. AutoUP 合成管线设计（推荐架构）

```
SRT+文案 → [S4 配音] 逐句 TTS(实测时长) → timing.json(每句: 音频文件/起始/时长)
              ↓ GPT-SoVITS 自拉起(9880) → 失败/超时自动切 edge-tts
        → [S5 影子匹配] 文案句 ×SRT 语义匹配(LLM) + 时长约束 → edit_decision.json
              护栏：时间戳必须命中字幕块/禁片头广告段/段间不重叠/画面时长≥配音时长
        → [S6 合成] 全 FFmpeg：
              ① 逐段剪切(-ss/-to, 去原声) → segments/*.mp4
              ② concat demuxer 拼接 → picture.mp4
              ③ 配音轨：分段 wav 按累积时间轴 adelay+amix(或 pydub 拼接)
              ④ BGM: -stream_loop 循环 + volume(config) + sidechaincompress 随解说闪避 + 尾部 afade
              ⑤ 字幕: subtitles 滤镜+ASS force_style(描边白字/底部偏上, 参数在 config)
              ⑥ 一次重编码出片: libx264/NVENC(自动探测) crf18 1080p30 + faststart
```

**代码移植清单**（MIT/Apache 兼容，vendor 目录注明出处）：
| 来源 | 移植内容 | 许可 |
|---|---|---|
| VideoLingo | gpt_sovits 集成、音节估时、音频拼接 | Apache-2.0 |
| NarratoAI | FFmpeg 剪切/编码器 fallback/总装命令/匹配 prompt 思想 | MIT |
| MPT | BGM 管理、时长兜底 | MIT |

**模块划分**：`autoup/{config.yaml, run.py(状态机断点续传), stages/s1~s9}`，产出 `D:\AutoUP\<批次>\<选题>\{源视频, 字幕, 文案, segments/, timing.json, edit_decision.json, 成片.mp4, 发布信息, 封面×3, state.json}`。每阶段产物落盘，state.json 记录断点。

**文案阶段新增约束**（S3 与 S4/S6 联动）：4500-5500 字 → 按 0.21s/音节预算 ≈ 13-15min 成片，文案生成时 LLM 拿到目标时长反馈，避免成片超 15min。

## 4. 需要确认的决策点

| # | 决策点 | 推荐 | 备选 |
|---|---|---|---|
| 1 | 影子匹配质量路线 | 一期纯 LLM 文本匹配（SRT 语义+时长约束，快/零额外成本），预留视觉复核接口 | 一期就叠加视觉帧复核（AutoDSJ 模式，慢且耗 API） |
| 2 | 编码器 | 自动探测 NVENC→libx264 fallback（NarratoAI 链） | 固定 libx264 |
| 3 | 配音句间间隙 | 保留 0.2-0.4s 自然停顿（画面同步多剪对应时长） | 全部零间隙拼接 |
| 4 | BGM 曲库 | Pixabay 免版权直链拉 20-30 首入 `assets/bgm/` | 用户提供曲库路径 |

## 5. 工作量预估（确认后）

- S4-S6 核心（配音+匹配+合成）：3-5 个工作日
- S7/S8 改造（发布信息两类+封面三比例）+ S1/S2 改造 + run.py 状态机：2-3 个工作日
- 全链路联调 + 首条真实选题端到端验收：1-2 个工作日
