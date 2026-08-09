#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为每个选题目录生成《封面提示词-即梦.txt》（两段纯提示词：3:4竖版 + 4:3横版）。

用法:
  python scripts/gen_jimeng_cover_prompts.py <root> [--csv <csv>] [--dry-run]

CSV 列(表头): 目录名,主标题,副标题,竖版画面,横版画面
  - 目录名: 与 root 下子目录名精确匹配，决定提示词文件写到哪个目录
  - 主标题: 6 字（金黄色粗毛笔大字）
  - 副标题: 8 字（白色毛笔字）
  - 竖版画面 / 横版画面: 该比例的画面描述（不含文字排版部分，脚本自动拼接）

CSV 模板: assets/jimeng-cover-template.csv
输出: 每个匹配目录下 封面提示词-即梦.txt，只含两段提示词，段落间空一行。
"""
import argparse
import csv
import os
import sys

HEAD_3X4 = "电影级写实纪录片封面，3:4竖版构图。画面："
HEAD_4X3 = "电影级写实纪录片封面，4:3横版构图。画面："

TEXT_3X4 = (
    "画面正上方约三分之一处居中排列两行书法大字，文字醒目、笔画清晰、无变形无错字："
    "第一行主标题「{m}」——特大号金黄色粗毛笔书法字，刚劲有力，黑色细描边，柔和黑色投影，几乎横贯版面宽度；"
    "第二行副标题「{s}」——中号白色毛笔书法字，与主标题同风格描边和投影，宽度约为主标题三分之二，紧贴主标题下方居中。"
    "文字有安全边距，笔画不裁切。除这两行文字外画面无其他文字、无英文、无logo、无水印。"
    "背景高清写实、细节丰富、景深自然，纪录片封面质感，主体突出，构图平衡，色彩高级。"
)

TEXT_4X3 = (
    "画面上部居中排列两行书法大字，文字醒目、笔画清晰、无变形无错字："
    "第一行主标题「{m}」——特大号金黄色粗毛笔书法字，刚劲有力，黑色细描边，柔和黑色投影，几乎横贯版面宽度；"
    "第二行副标题「{s}」——中号白色毛笔书法字，与主标题同风格描边和投影，宽度约为主标题三分之二，紧贴主标题下方居中。"
    "文字有安全边距，笔画不裁切。除这两行文字外画面无其他文字、无英文、无logo、无水印。"
    "背景高清写实、细节丰富、景深自然，纪录片封面质感，主体突出，构图平衡，色彩高级。"
)


def build_3x4(main: str, sub: str, scene: str) -> str:
    return HEAD_3X4 + scene + TEXT_3X4.format(m=main, s=sub)


def build_4x3(main: str, sub: str, scene: str) -> str:
    return HEAD_4X3 + scene + TEXT_4X3.format(m=main, s=sub)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成即梦封面提示词文件")
    ap.add_argument("root", help="选题根目录（含各 <NN-中文选题>/ 子目录）")
    ap.add_argument("--csv", default="jimeng-cover-input.csv",
                    help="输入 CSV 路径（默认 ./jimeng-cover-input.csv）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将生成的配对，不写文件")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        print(f"错误: root 目录不存在: {args.root}", file=sys.stderr)
        return 1
    if not os.path.isfile(args.csv):
        print(f"错误: CSV 不存在: {args.csv}", file=sys.stderr)
        return 1

    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("错误: CSV 无数据行", file=sys.stderr)
        return 1

    done, skipped, missing = 0, 0, []
    for i, row in enumerate(rows, start=2):
        name = (row.get("目录名") or "").strip()
        main6 = (row.get("主标题") or "").strip()
        sub8 = (row.get("副标题") or "").strip()
        scene_v = (row.get("竖版画面") or "").strip()
        scene_h = (row.get("横版画面") or "").strip()
        if not (name and main6 and sub8 and scene_v and scene_h):
            print(f"跳过 第{i}行: 字段不全", file=sys.stderr)
            skipped += 1
            continue
        if len(main6) != 6:
            print(f"警告 第{i}行「{name}」主标题应为6字, 实际{len(main6)}字: {main6}", file=sys.stderr)
        if len(sub8) != 8:
            print(f"警告 第{i}行「{name}」副标题应为8字, 实际{len(sub8)}字: {sub8}", file=sys.stderr)

        target = os.path.join(args.root, name)
        if not os.path.isdir(target):
            missing.append(name)
            print(f"跳过 第{i}行: 目录不存在 {target}", file=sys.stderr)
            skipped += 1
            continue

        # 已有封面 → 跳过。自主判断：目录中图片文件（png/jpg/jpeg/webp/bmp/gif）数量 >= 2
        # 即视为已有两张封面（文件名可能为 封面-3比4 / 封面-4比3 / 封面 / cover 等任意命名）
        import glob as _glob
        _IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
        cover_files = [p for p in _glob.glob(os.path.join(target, "*"))
                       if os.path.splitext(p)[1].lower() in _IMG_EXTS]
        if len(cover_files) >= 2:
            names = ", ".join(os.path.basename(p) for p in sorted(cover_files))
            print(f"跳过 第{i}行: 已有 {len(cover_files)} 张封面图 ({names}) → {os.path.basename(target)}", file=sys.stderr)
            skipped += 1
            continue

        content = build_3x4(main6, sub8, scene_v) + "\n\n" + build_4x3(main6, sub8, scene_h)
        out = os.path.join(target, "封面提示词-即梦.txt")
        if args.dry_run:
            print(f"[dry-run] 将写入 {out} ({len(content)}字符)")
        else:
            with open(out, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"已写入 {out} ({len(content)}字符)")
        done += 1

    print(f"\n完成: 生成 {done} 个, 跳过 {skipped} 个")
    if missing:
        print(f"未找到目录: {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
