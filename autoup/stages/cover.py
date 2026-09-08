"""S8 封面: 源片帧 + 金黄主标题/白副标题(黑描边+投影) → 9:16 / 16:9 / 1:1 三比例。

版式标准继承 AutoYY: 特大金黄主标题+黑描边黑投影, 白色副标题约为主标题 2/3 宽,
上半区居中。默认黑体加粗; 书法字体可通过 cover.font_path 指定。
"""
from __future__ import annotations

import logging
from pathlib import Path

from .. import config, utils
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

log = logging.getLogger("autoup.s8")

SIZES = {"9x16": (1080, 1920), "16x9": (1920, 1080), "1x1": (1080, 1080)}
GOLD = (255, 201, 60)


def _load_font(size: int):
    custom = config.get("cover.font_path")
    path = Path(str(custom)) if custom else Path("C:/Windows/Fonts/simhei.ttf")
    if not path.exists():
        path = Path("C:/Windows/Fonts/msyhbd.ttc")
    return ImageFont.truetype(str(path), size)


def _draw_text_layer(w: int, main: str, sub: str) -> Image.Image:
    """透明文字层: 主标题(金黄+黑描边+投影) + 副标题(白+黑描边), 居中。"""
    layer = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # 主标题字号: 6 字占宽度 ~86%
    size = int(w * 0.86 / max(len(main), 1))
    font = _load_font(size)
    bbox = d.textbbox((0, 0), main, font=font, stroke_width=max(size // 14, 4))
    tw = bbox[2] - bbox[0]
    if tw > w * 0.92:                      # 防溢出缩字号
        size = int(size * w * 0.92 / tw)
        font = _load_font(size)
    x = (w - tw) // 2
    y = 0
    sw = max(size // 13, 5)
    # 投影
    d.text((x + size // 22, y + size // 16), main, font=font,
           fill=(0, 0, 0, 200), stroke_width=sw, stroke_fill=(0, 0, 0, 200))
    # 金黄主体 + 黑描边
    d.text((x, y), main, font=font, fill=GOLD + (255,), stroke_width=sw,
           stroke_fill=(0, 0, 0, 255))
    # 副标题: 约 2/3 宽
    ssize = int(size * 0.62 * len(main) / max(len(sub), 1) * 0.98)
    sfont = _load_font(ssize)
    sbbox = d.textbbox((0, 0), sub, font=sfont, stroke_width=max(ssize // 14, 3))
    stw = sbbox[2] - sbbox[0]
    sx = (w - stw) // 2
    sy = y + int(size * 1.28)
    ssw = max(ssize // 13, 3)
    d.text((sx + ssize // 22, sy + ssize // 16), sub, font=sfont,
           fill=(0, 0, 0, 190), stroke_width=ssw, stroke_fill=(0, 0, 0, 190))
    d.text((sx, sy), sub, font=sfont, fill=(255, 255, 255, 255),
           stroke_width=ssw, stroke_fill=(0, 0, 0, 255))
    bbox_full = layer.getbbox()
    return layer.crop(bbox_full) if bbox_full else layer


def _crop_ratio(img: Image.Image, w: int, h: int) -> Image.Image:
    ratio = w / h
    iw, ih = img.size
    if iw / ih > ratio:
        nw = int(ih * ratio)
        img = img.crop(((iw - nw) // 2, 0, (iw + nw) // 2, ih))
    else:
        nh = int(iw / ratio)
        img = img.crop((0, (ih - nh) // 2, iw, (ih + nh) // 2))
    return img.resize((w, h), Image.LANCZOS)


def _pick_frame(topic_dir: Path) -> Path:
    """取 ED 最长段中点的源片帧作为封面底图。"""
    ed = utils.read_json(topic_dir / "edit_decision.json") or {}
    items = sorted(ed.get("items", []), key=lambda i: i["end"] - i["start"], reverse=True)
    if not items:
        raise FileNotFoundError("缺少 edit_decision.json 或其中无 items")
    t = (items[0]["start"] + items[0]["end"]) / 2
    src = next((f for f in (topic_dir / "素材").iterdir()
                if f.suffix.lower() in {".mp4", ".mkv", ".webm"}), None)
    if src is None:
        raise FileNotFoundError("缺少源视频")
    out = topic_dir / "封面" / "_frame.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    p = utils.run([config.ffmpeg(), "-y", "-loglevel", "error", "-ss", t,
                   "-i", src, "-frames:v", "1", out], desc="抽封面帧")
    if p.returncode != 0 or not out.exists():
        raise RuntimeError("抽帧失败")
    return out


def run(topic_dir: Path) -> Path:
    pub = topic_dir / "发布" / "封面文案.txt"
    if not pub.exists():
        raise FileNotFoundError("缺少 封面文案.txt (先跑 S7)")
    lines = [l.strip() for l in pub.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    main, sub = (lines + ["", ""])[:2]

    frame = _pick_frame(topic_dir)
    base = Image.open(frame).convert("RGB")
    base = ImageEnhance.Brightness(base).enhance(0.82)
    base = ImageEnhance.Contrast(base).enhance(1.06)

    out_dir = topic_dir / "封面"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (w, h) in SIZES.items():
        bg = _crop_ratio(base, w, h).filter(ImageFilter.GaussianBlur(1.2))
        text_layer = _draw_text_layer(w, main, sub)
        # 文字层放上半区
        ty = int(h * (0.14 if h > w else 0.16))
        bg = bg.convert("RGBA")
        bg.alpha_composite(text_layer, ((w - text_layer.width) // 2, ty))
        out = out_dir / f"封面-{name}.png"
        bg.convert("RGB").save(out, quality=92)
        log.info("封面 %s: %s", name, out)
    return out_dir
