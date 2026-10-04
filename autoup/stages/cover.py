"""S8 封面：源片帧 + 6/8字标题，输出 9:16 / 16:9 / 1:1。"""
from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .. import config, utils

log = logging.getLogger("autoup.s8")

SIZES = {"9x16": (1080, 1920), "16x9": (1920, 1080), "1x1": (1080, 1080)}
GOLD = (255, 201, 60)


def _resolve_font() -> Path:
    raw = config.get("cover.font_path")
    if raw:
        path = Path(str(raw)).expanduser()
        if not path.is_absolute():
            path = config.repo_root() / path
        if path.exists():
            return path
    bundled = config.repo_root() / "assets" / "fonts" / "05_江西拙楷.ttf"
    if bundled.exists():
        return bundled
    raise FileNotFoundError("找不到封面字体，请配置 cover.font_path")


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_resolve_font()), max(size, 10))


def _measure(draw: ImageDraw.ImageDraw, text: str, font, stroke_width: int) -> tuple[int, int, tuple]:
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox


def _fit_font(draw: ImageDraw.ImageDraw, text: str, initial_size: int, max_width: int):
    size = max(initial_size, 10)
    while size > 20:
        font = _load_font(size)
        stroke = max(size // 14, 4)
        width, _, _ = _measure(draw, text, font, stroke)
        if width <= max_width:
            return size, font
        size = max(int(size * 0.94), size - 2)
    return size, _load_font(size)


def _draw_text_layer(width: int, main: str, sub: str) -> Image.Image:
    layer = Image.new("RGBA", (width, width), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    initial = int(width * 0.86 / max(len(main), 1))
    size, font = _fit_font(draw, main, initial, int(width * 0.92))
    stroke = max(size // 13, 5)
    main_width, _, _ = _measure(draw, main, font, stroke)
    x = (width - main_width) // 2
    y = 0

    draw.text(
        (x + size // 22, y + size // 16),
        main,
        font=font,
        fill=(0, 0, 0, 200),
        stroke_width=stroke,
        stroke_fill=(0, 0, 0, 200),
    )
    draw.text(
        (x, y),
        main,
        font=font,
        fill=GOLD + (255,),
        stroke_width=stroke,
        stroke_fill=(0, 0, 0, 255),
    )

    sub_initial = int(size * 0.62 * len(main) / max(len(sub), 1) * 0.98)
    sub_size, sub_font = _fit_font(draw, sub, sub_initial, int(width * 0.72))
    sub_stroke = max(sub_size // 13, 3)
    sub_width, _, _ = _measure(draw, sub, sub_font, sub_stroke)
    sub_x = (width - sub_width) // 2
    sub_y = y + int(size * 1.28)
    draw.text(
        (sub_x + sub_size // 22, sub_y + sub_size // 16),
        sub,
        font=sub_font,
        fill=(0, 0, 0, 190),
        stroke_width=sub_stroke,
        stroke_fill=(0, 0, 0, 190),
    )
    draw.text(
        (sub_x, sub_y),
        sub,
        font=sub_font,
        fill=(255, 255, 255, 255),
        stroke_width=sub_stroke,
        stroke_fill=(0, 0, 0, 255),
    )
    bounds = layer.getbbox()
    return layer.crop(bounds) if bounds else layer


def _crop_ratio(image: Image.Image, width: int, height: int) -> Image.Image:
    ratio = width / height
    image_width, image_height = image.size
    if image_width / image_height > ratio:
        new_width = int(image_height * ratio)
        image = image.crop(
            ((image_width - new_width) // 2, 0, (image_width + new_width) // 2, image_height)
        )
    else:
        new_height = int(image_width / ratio)
        image = image.crop(
            (0, (image_height - new_height) // 2, image_width, (image_height + new_height) // 2)
        )
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _pick_frame(topic_dir: Path) -> Path:
    edit = utils.read_json(topic_dir / "edit_decision.json") or {}
    items = sorted(
        edit.get("items", []),
        key=lambda item: item["end"] - item["start"],
        reverse=True,
    )
    if not items:
        raise FileNotFoundError("edit_decision.json 无有效画面段")
    timestamp = (items[0]["start"] + items[0]["end"]) / 2
    material = topic_dir / "素材"
    source = next(
        (
            file
            for file in material.iterdir()
            if file.suffix.lower() in {".mp4", ".mkv", ".webm"}
        ),
        None,
    ) if material.exists() else None
    if source is None:
        raise FileNotFoundError("缺少源视频")

    output = topic_dir / "封面" / "_frame.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = utils.run(
        [
            config.ffmpeg(),
            "-y",
            "-loglevel",
            "error",
            "-ss",
            timestamp,
            "-i",
            source,
            "-frames:v",
            "1",
            output,
        ],
        desc="抽封面帧",
    )
    if proc.returncode != 0 or not output.exists():
        raise RuntimeError("抽封面帧失败")
    return output


def run(topic_dir: Path) -> Path:
    copy_path = topic_dir / "发布" / "封面文案.txt"
    if not copy_path.exists():
        raise FileNotFoundError("缺少 封面文案.txt（先跑 S7）")
    lines = [
        line.strip()
        for line in copy_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if len(lines) < 2:
        raise ValueError("封面文案必须包含主标题和副标题两行")
    main, sub = lines[:2]
    if len(main) != 6 or len(sub) != 8:
        raise ValueError(f"封面标题长度必须 6/8 字，当前 {len(main)}/{len(sub)}")

    frame = _pick_frame(topic_dir)
    with Image.open(frame) as source:
        base = source.convert("RGB")
    base = ImageEnhance.Brightness(base).enhance(0.82)
    base = ImageEnhance.Contrast(base).enhance(1.06)

    output_dir = topic_dir / "封面"
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, (width, height) in SIZES.items():
        background = _crop_ratio(base, width, height).filter(ImageFilter.GaussianBlur(1.2))
        text_layer = _draw_text_layer(width, main, sub)
        top = int(height * (0.14 if height > width else 0.16))
        background = background.convert("RGBA")
        background.alpha_composite(
            text_layer,
            ((width - text_layer.width) // 2, top),
        )
        output = output_dir / f"封面-{name}.png"
        background.convert("RGB").save(output, format="PNG", optimize=True)
        log.info("封面 %s: %s", name, output)
    return output_dir
