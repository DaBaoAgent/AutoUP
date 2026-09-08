# 开发备忘(坑与修复)

- yt-dlp curl 后端加载不了中文路径下的 certifi (curl:77) → download._fix_curl_ca() 已修
- yt-dlp 合并格式需要 ffmpeg 在 PATH → download._ensure_ffmpeg_on_path()
- ffmpeg ass 滤镜参数含盘符冒号会被截断 → cwd=成片工程 用相对路径 subs.ass
- pydub 动态 which() 找 ffmpeg → utils.ensure_pydub_ffmpeg() 前置 PATH
- GLM-4.6 思考模型 JSON 模式 content 为空(在 reasoning_content) → llm.py 已带 thinking disabled + 兜底
- yt-dlp 中途死会留 .vtt → download.py 有 vtt→srt 兜底; 多语言 srt 优先取 .en
- 本机 GPT-SoVITS 用 .venv/Scripts/python.exe (非官方 runtime/python.exe), api_v2 起服务后首次合成前有预热延迟
- edge_tts 实测语速 ~0.25s/字: 4500 字 ≈ 19 分钟成片; 要压 15 分钟调 script.target_chars 或 voice 语速
- S6 时间轴: 每句末尾段多剪 gap_seconds 当句间停顿画面; 未匹配句延续末段画面
- 冒烟: python -m autoup.run --batch _smoke_e2e --set download.max_height=360 --set script.target_chars=300 (续跑)
- assets/bgm 是 CC-BY (Kevin MacLeod), 发布必须带 CREDITS.txt 里的署名
