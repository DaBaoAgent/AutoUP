<!-- README-PROMO:START -->
<p align="center">
  <img src="assets/readme/hero.webp" alt="AutoUP：纪录片解说全自动生产线" width="100%" />
</p>
<!-- README-PROMO:END -->

# AutoUP — 纪录片解说全自动生产线

从 YouTube 片源到多平台发布就绪文件夹，一条命令跑完全链路：**核验 → 下载(1080p+SRT) → 爆款文案 → 配音 → 影子匹配 → 合成剪辑 → 烧字幕+BGM → 发布信息 → 三比例封面 → 验收**。

> 由 AutoYY (DaBaoAgent/AutoYY) 迭代而来。需求基准见 `docs/requirements.md`，
> 技术选型见 `docs/research-editing-pipeline.md`（NarratoAI/VideoLingo 源码级调研结论）。

## 快速开始

```powershell
# 1. 配置参考音频(GPT-SoVITS 音色) — autoup/config.yaml → voice.gpt_sovits.voices.default
#    未配置时自动降级 edge-tts(免费, 音色固定)

# 2. 准备选题清单(每行一个 YouTube 链接)
#    D:/AutoUP/mybatch_urls.txt

# 3. 一键跑批次
python -m autoup.run --manifest D:/AutoUP/mybatch_urls.txt --batch mybatch

# 断点续跑(中断后重复同一命令即可, 已完成阶段自动跳过)
python -m autoup.run --batch mybatch

# 常用参数
python -m autoup.run --batch mybatch --only s3,s4        # 只跑文案+配音
python -m autoup.run --batch mybatch --force --only s6   # 强制重跑合成
python -m autoup.run --batch mybatch --voice default --limit 3 --set script.target_chars=4500
```

## 产出结构

```
D:/AutoUP/<批次>/
├── _核验报告.csv
└── 01-选题名/
    ├── 素材/高清源视频.mp4      # 1080p
    ├── 字幕/字幕.srt            # YouTube 英文字幕
    ├── 文案/爆款口播稿.txt      # ~4500 字中文解说
    ├── 配音/0001.wav...timing.json
    ├── edit_decision.json       # 文案↔源片时间轴匹配
    ├── 成片工程/                # 中间产物(可删)
    ├── 成片.mp4                 # 1080p30 硬字幕+BGM
    ├── 发布/国内平台.txt  海外平台.txt  封面文案.txt
    ├── 封面/封面-9x16.png 16x9 1x1
    ├── state.json               # 断点状态
    └── 验收报告.json
```

## 阶段门禁

| 门禁 | 规则 |
|---|---|
| S1 源核验 | 时长≥30min、≥720p、必须自带英文字幕(无字幕直接拒单) |
| S3 文案 | 目标字数 ±12% 验收，事实锁死字幕，去 AI 味 |
| S5 匹配 | 时间戳必须命中真实字幕块(防幻觉)、禁片头广告段、段间不重叠 |
| S9 验收 | 14 项全过才算完成 |

## 贡献者

- Dabao · 基于 AutoYY / NarratoAI(MIT) / VideoLingo(Apache-2.0) 的经验与代码思想

## License

MIT
