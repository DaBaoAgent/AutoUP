# AutoYY 项目关键环境事实（2026-08）

内存条目已精简,完整事实存此。修改/维护 AutoYY 时先读本文件。

## 项目位置与同步

- 项目根目录：`D:\@kaifa\AutoYY`
- Git 仓库：`DaBaoAgent/AutoYY`（GitHub,HTTPS 被墙,走 SSH 443 端口）
- 本机 codex + hermes 均通过 **junction 指向**同一份源码 —— 任意一端 commit + push 即多端同步；另一台机器只 pull 即可
- 注意：junction 方案下不要用删除目录的方式重装,会破坏链接

## 文案标准

- 口播文案：4500-5500 字 / 纯中文 / 去 AI 味
- 具体标准见本技能 `references/content-style.md`（或 creative 下文案类技能）

## 已知坑

- `read_file` 对中文 txt 会误判为二进制 → 用 python 读（`open(..., encoding='utf-8')`）
- 委托子代理输出路径必须写 E 盘（曾误写 `D:\@油管二创素材` 建出空骨架需清理）
- delegation 已放宽：1800s / 150 轮
