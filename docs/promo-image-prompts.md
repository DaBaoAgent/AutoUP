# AutoUP GitHub 推广图 · 文生图提示词（2026-09-08）

> 用法：即梦/通义万相用中文提示词；Midjourney/SD 用英文提示词。
> ⚠️ 文生图模型渲染中文长文案不可靠：每张图都设计了"文字留白区"，生成后用封面引擎
> （`python -m autoup.stages.font_preview` 同款江西拙楷）或任意修图工具叠加真实文字。
> 英文单词 "AutoUP" 可以让模型直接渲染（成功率较高）。

---

## 图 1 · 仓库主视觉 Hero（横幅 3:1 或 16:9，放 README 顶部）

**画面概念**：深海纪录片氛围 + 金色书法主视觉，一句话传达"纪录片 × AI 自动化"。

### 中文提示词（即梦）
> 电影级纪录片海报风格，深蓝色的深海场景，一艘二战时期的货轮剪影缓缓沉入海底，
> 一束金色光柱从海面穿透而下照亮沉船，海水中悬浮着微尘颗粒，画面上方三分之一留出深色负空间
> 用于放置标题文字，画面下方是起伏的海床轮廓。整体色调深蓝与金黄对比，质感如 BBC 纪录片剧照，
> 光影戏剧性，超高清细节，电影感构图。画面上方负空间中央放置金色毛笔书法大字 "AutoUP"，
> 字体为粗犷的手写毛笔楷书，带黑色描边和柔和投影，字号巨大，是该画面的视觉中心。

### 英文提示词（Midjourney/SD）
> cinematic documentary poster style, deep blue ocean scene, silhouette of a WWII cargo
> ship sinking into the abyss, a single golden light beam piercing down from the surface
> illuminating the wreck, floating particles in seawater, dark negative space in the top
> third of the frame for title text, seabed silhouette at the bottom, deep blue and gold
> color contrast, BBC documentary still quality, dramatic lighting, ultra detailed,
> cinematic composition --ar 3:1 --v 6
> （后期叠加：金色江西拙楷 "AutoUP" + 小字 "纪录片解说全自动生产线"）

### 负面提示词
> 文字模糊, 多余乱码文字, 水印, 卡通, 低对比, 过曝, 人物面部特写
> blurry text, gibberish text, watermark, cartoon, low contrast, overexposed

---

## 图 2 · 全自动流水线 Pipeline（16:9，放"核心特性"章节前）

**画面概念**：等距插画风格的"AI 内容工厂"——一条发光流水线把"链接"变成"成片"。

### 中文提示词（即梦）
> 等距视角（isometric）3D 插画，一条横贯画面的未来感工厂流水线，深蓝夜色工作台背景，
> 流水线从左到右依次排列九个发光工位：一个下载箭头图标、一张文稿纸、一个声波麦克风、
> 一把电影剪辑刀、一张金色封面卡片、一组发布火箭，每个工位由细金色光轨串联，
> 传送带上有一个小小的视频播放器方块正在被"装配"，零件悬浮，微弱金色粒子光效，
> 色彩以深蓝底 + 橙金高光为主，干净现代，渐变背景，科技感插画，细节丰富，无文字。

### 英文提示词
> isometric 3D illustration of a futuristic content factory assembly line spanning the
> frame, nine glowing workstations left to right: download arrow, script paper, microphone
> with sound wave, film editing blade, golden cover card, publishing rocket, connected by
> thin golden light trails, a tiny video player cube being assembled on the conveyor belt,
> floating parts, subtle gold particle effects, deep navy background with orange-gold
> highlights, clean modern tech infographic style, rich detail, no text --ar 16:9 --v 6
> （后期叠加：每个工位下方标注小字 下载/文案/配音/匹配/剪辑/封面/发布）

### 负面提示词
> 真实照片, 文字标签, 乱码, 杂乱线缆, 恐怖机械, 过暗
> photorealistic, text labels, gibberish, messy cables, dark horror machinery, too dark

---

## 图 3 · 一条命令出成片 One Command（16:9，放"快速开始"章节后）

**画面概念**：暗色终端窗口 + 一条命令 + 产出文件夹——程序员/工具党最吃这一套。

### 中文提示词（即梦）
> 暗房氛围的程序员工作桌俯拍场景，中央是一台显示巨型终端窗口的显示器，终端为深色半透明
> 毛玻璃质感，里面是一行发亮的绿色命令行文字和一个闪烁光标，屏幕发出柔和的冷光照亮桌面，
> 键盘右侧放着一杯冒热气的咖啡，显示器旁边悬浮三张微微发光的视频封面卡片（竖版、横版、
> 方形各一张，卡片上是海战纪录片画面和金色毛笔字标题的模糊意象），背景深蓝黑色调，
> 带轻微金色景深光斑，电影感浅景深，超高质量，画面中不要出现任何可读文字。

### 英文提示词
> overhead shot of a programmer's desk in a dark room, a large monitor displaying a giant
> terminal window with dark frosted-glass texture, one glowing green command line and a
> blinking cursor, soft cool screen light illuminating the desk, a steaming coffee cup by
> the keyboard, three floating glowing video cover cards beside the monitor (portrait,
> landscape, square) hinting naval documentary covers with golden calligraphy, deep navy
> black palette, soft golden bokeh, cinematic shallow depth of field, ultra quality,
> no readable text on screen --ar 16:9 --v 6
> （后期叠加：终端里写上真实命令 `python -m autoup.run --manifest urls.txt --batch 第一批`，
> 用江西拙楷在卡片上叠 "一键出片"）

### 负面提示词
> 可读文字, 乱码字符, 亮白屏幕, 白天, 杂乱桌面, 人物
> readable text, gibberish characters, bright white screen, daylight, messy desk, people

---

## 出图后处理建议

1. **叠字**：中文标题一律用 `assets/fonts/05_江西拙楷.ttf` 叠加（金黄 #FFC93C + 黑描边 + 投影），
   与自动封面完全同一套视觉语言；可复用 `autoup/stages/cover.py::_draw_text_layer`。
2. **尺寸**：GitHub README 顶部横幅建议 1500×500（3:1）；章节插图 1280×720（16:9）。
3. **压缩**：上传前转 WebP（原 AutoYY 的 assets/readme 就是这个格式），单张控制在 300KB 内。
