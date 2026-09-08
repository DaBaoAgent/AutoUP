"""渲染 10 字体封面选型预览图: 同一文案逐字体渲染主/副标题样张。

用法: python -m autoup.stages.font_preview [主标题] [副标题]
输出: assets/fonts/字体选型预览.png (每行一个字体: 名称+金黄主标+白副标, 带黑描边投影)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
OUT = FONT_DIR / "字体选型预览.png"
GOLD = (255, 201, 60)
W = 1600
ROW = 340


def _text_img(text: str, font_path: Path, size: int, fill, stroke_ratio: float) -> Image.Image:
    font = ImageFont.truetype(str(font_path), size)
    sw = max(int(size * stroke_ratio), 4)
    d0 = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    bbox = d0.textbbox((0, 0), text, font=font, stroke_width=sw)
    img = Image.new("RGBA", (bbox[2] - bbox[0] + 40, bbox[3] - bbox[1] + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x, y = 20 - bbox[0], 20 - bbox[1]
    d.text((x + size // 20, y + size // 14), text, font=font, fill=(0, 0, 0, 200),
           stroke_width=sw, stroke_fill=(0, 0, 0, 200))
    d.text((x, y), text, font=font, fill=fill, stroke_width=sw, stroke_fill=(0, 0, 0, 255))
    return img


def run(main: str = "深海沉船探秘", sub: str = "沉睡百年的宝藏秘密") -> Path:
    fonts = sorted(FONT_DIR.glob("[0-9][0-9]_*.ttf"))
    if not fonts:
        raise SystemExit(f"未找到字体: {FONT_DIR}")
    H = 120 + ROW * len(fonts) + 40
    canvas = Image.new("RGB", (W, H), (24, 26, 32))
    d = ImageDraw.Draw(canvas)
    title_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 44)
    d.text((30, 30), "AutoUP 封面字体选型（主标题 6 字样张 / 副标题 8 字样张）",
           font=title_font, fill=(240, 240, 240))

    name_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 26)
    for i, fp in enumerate(fonts):
        y0 = 120 + i * ROW
        d.line([(30, y0), (W - 30, y0)], fill=(70, 74, 84), width=2)
        label = fp.stem.replace("_", " · ")
        d.text((30, y0 + 18), label, font=name_font, fill=(150, 200, 255))
        # 主标题: 金黄 特大(对标封面 0.86/6字 ≈ 230px @1600 宽)
        mi = _text_img(main, fp, 150, GOLD + (255,), 0.09)
        canvas.paste(mi, (40, y0 + 55), mi)
        # 副标题: 白 中大
        si = _text_img(sub, fp, 84, (255, 255, 255, 255), 0.09)
        canvas.paste(si, (W - si.width - 60, y0 + 210), si)
    canvas.save(OUT)
    print(OUT)
    return OUT


if __name__ == "__main__":
    run(*sys.argv[1:3])
