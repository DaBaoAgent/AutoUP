#!/usr/bin/env python3
"""Build deterministic 3:4 and 4:3 topic covers from local source videos.

The tool keeps exact Chinese cover text by rendering it locally after selecting
a representative documentary frame from each topic video. Existing finished
covers are skipped unless --force is supplied.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageStat


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}
PROMPT_NAME = "封面提示词-即梦.txt"

MISSING_TEXT = {
    "27-哈尔登监狱：全球最奢华监狱": ("奢华挪威监狱", "囚犯住进森林别墅"),
    "33-最凶残狱友": ("最凶狱友实录", "与杀人犯同室生存"),
    "35-死囚比利·特雷西": ("死囚最后岁月", "比利特雷西等行刑"),
    "43-美国ADX超级监狱内幕": ("地下超级监狱", "二十三小时独囚禁"),
    "45-美国最臭名昭著死囚区": ("死囚区的噩梦", "囚犯每天等待死亡"),
    "47-拥挤暴力的世界监狱": ("塞爆世界监狱", "拥挤暴力天天上演"),
    "50-萨尔瓦多黑帮大监狱": ("黑帮巨型牢笼", "四万人塞进大监狱"),
    "58-红洋葱超级监狱": ("红洋葱活地狱", "最高戒备终身独囚"),
    "78-美国最危险监狱群": ("危险监狱帝国", "全美重刑犯都在此"),
}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--ffmpeg", type=Path, required=True)
    ap.add_argument("--title-font", type=Path, required=True)
    ap.add_argument("--subtitle-font", type=Path, required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--background-override", type=Path)
    ap.add_argument("--background-override-dir", default="")
    ap.add_argument("--background-dir", type=Path)
    return ap.parse_args()


def cover_text(folder: Path) -> tuple[str, str]:
    prompt = folder / PROMPT_NAME
    if prompt.exists():
        text = prompt.read_text(encoding="utf-8")
        main = re.search(r"主标题[「“\"]([^」”\"]+)[」”\"]", text)
        sub = re.search(r"副标题[「“\"]([^」”\"]+)[」”\"]", text)
        if main and sub:
            return main.group(1), sub.group(1)
    if folder.name in MISSING_TEXT:
        return MISSING_TEXT[folder.name]
    raise ValueError(f"missing cover text: {folder}")


def duration_seconds(ffmpeg: Path, video: Path) -> float:
    proc = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-i", str(video)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not match:
        raise RuntimeError(f"cannot read duration: {video}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def frame_score(path: Path) -> float:
    image = Image.open(path).convert("RGB").resize((320, 180))
    gray = ImageOps.grayscale(image)
    stat = ImageStat.Stat(gray)
    mean = stat.mean[0]
    contrast = stat.stddev[0]
    entropy = gray.entropy()
    edge = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0]
    exposure_penalty = abs(mean - 112) * 0.20
    black_penalty = max(0, 42 - mean) * 1.8
    white_penalty = max(0, mean - 215) * 1.8
    return contrast * 1.7 + entropy * 7.0 + edge * 1.2 - exposure_penalty - black_penalty - white_penalty


def extract_best_frame(ffmpeg: Path, video: Path, temp_dir: Path) -> Image.Image:
    duration = duration_seconds(ffmpeg, video)
    candidates: list[tuple[float, Path]] = []
    for index, fraction in enumerate((0.14, 0.26, 0.38, 0.50, 0.62, 0.74, 0.86)):
        output = temp_dir / f"frame-{index}.jpg"
        timestamp = max(1.0, min(duration - 1.0, duration * fraction))
        cmd = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-ss", f"{timestamp:.3f}",
            "-i", str(video), "-frames:v", "1", "-vf", "scale=1920:-2", "-q:v", "2",
            "-y", str(output),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        candidates.append((frame_score(output), output))
    _, best = max(candidates, key=lambda item: item[0])
    with Image.open(best) as image:
        return image.convert("RGB").copy()


def fit_background(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.48))
    image = ImageEnhance.Color(image).enhance(0.82)
    image = ImageEnhance.Contrast(image).enhance(1.18)
    image = ImageEnhance.Sharpness(image).enhance(1.12)
    cool = Image.new("RGB", size, (19, 42, 61))
    image = Image.blend(image, cool, 0.12)

    # Darken the title area while retaining enough scene detail.
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    alpha = Image.new("L", (1, size[1]), 0)
    pixels = alpha.load()
    height = size[1]
    for y in range(height):
        t = y / height
        top = max(0.0, 1.0 - t / 0.52)
        bottom = max(0.0, (t - 0.82) / 0.18)
        value = int(125 * top * top + 28 * bottom)
        pixels[0, y] = min(170, value)
    alpha = alpha.resize(size)
    overlay.putalpha(alpha)
    return Image.alpha_composite(image.convert("RGBA"), overlay)


def fitted_font(font_path: Path, text: str, max_width: int, start_size: int) -> ImageFont.FreeTypeFont:
    size = start_size
    probe = Image.new("L", (8, 8))
    draw = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(probe)
    while size >= 36:
        font = ImageFont.truetype(str(font_path), size)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=max(1, size // 70))
        if box[2] - box[0] <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(str(font_path), size)


def centered_text(
    image: Image.Image,
    text: str,
    y: int,
    font_path: Path,
    font_size: int,
    max_width: int,
    fill: tuple[int, int, int, int],
    stroke: int,
    shadow_blur: int,
    shadow_offset: int,
) -> int:
    from PIL import ImageDraw

    font = fitted_font(font_path, text, max_width, font_size)
    probe = ImageDraw.Draw(image)
    box = probe.textbbox((0, 0), text, font=font, stroke_width=stroke)
    width = box[2] - box[0]
    height = box[3] - box[1]
    x = (image.width - width) // 2 - box[0]
    baseline_y = y - box[1]

    shadow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow_layer)
    sd.text(
        (x + shadow_offset, baseline_y + shadow_offset), text, font=font,
        fill=(0, 0, 0, 235), stroke_width=stroke + 2, stroke_fill=(0, 0, 0, 245),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(shadow_blur))
    image.alpha_composite(shadow_layer)

    draw = ImageDraw.Draw(image)
    draw.text(
        (x, baseline_y), text, font=font, fill=fill,
        stroke_width=stroke, stroke_fill=(8, 8, 8, 255),
    )
    return y + height


def build_cover(source: Image.Image, size: tuple[int, int], main: str, sub: str, title_font: Path, subtitle_font: Path) -> Image.Image:
    image = fit_background(source, size)
    width, height = size
    main_top = int(height * 0.055)
    main_bottom = centered_text(
        image, main, main_top, title_font, int(height * 0.155), int(width * 0.92),
        (255, 205, 0, 255), max(3, width // 360), max(6, width // 150), max(6, width // 180),
    )
    sub_top = main_bottom + int(height * 0.025)
    centered_text(
        image, sub, sub_top, subtitle_font, int(height * 0.075), int(width * 0.70),
        (248, 248, 248, 255), max(2, width // 500), max(5, width // 210), max(4, width // 240),
    )
    return image.convert("RGB")


def choose_video(folder: Path) -> Path:
    videos = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
    if not videos:
        raise FileNotFoundError(f"no source video: {folder}")
    return max(videos, key=lambda p: p.stat().st_size)


def main() -> int:
    args = parse_args()
    folders = sorted((p for p in args.root.iterdir() if p.is_dir()), key=lambda p: p.name)
    if args.limit:
        folders = folders[: args.limit]

    completed = 0
    skipped = 0
    failed: list[tuple[str, str]] = []
    for index, folder in enumerate(folders, 1):
        portrait = folder / "封面-3比4.png"
        landscape = folder / "封面-4比3.png"
        if not args.force and portrait.exists() and landscape.exists():
            print(f"[{index}/{len(folders)}] SKIP {folder.name}")
            skipped += 1
            continue
        try:
            main_text, sub_text = cover_text(folder)
            if len(main_text) != 6 or len(sub_text) != 8:
                raise ValueError(f"title lengths are {len(main_text)}+{len(sub_text)}, expected 6+8")
            cached_background = args.background_dir / f"{folder.name}.png" if args.background_dir else None
            if cached_background and cached_background.exists():
                with Image.open(cached_background) as image:
                    source = image.convert("RGB").copy()
            elif args.background_override and folder.name == args.background_override_dir:
                with Image.open(args.background_override) as image:
                    source = image.convert("RGB").copy()
            else:
                video = choose_video(folder)
                with tempfile.TemporaryDirectory(prefix="autoyy-cover-") as temp:
                    source = extract_best_frame(args.ffmpeg, video, Path(temp))

            p_img = build_cover(source, (1200, 1600), main_text, sub_text, args.title_font, args.subtitle_font)
            l_img = build_cover(source, (1600, 1200), main_text, sub_text, args.title_font, args.subtitle_font)
            p_img.save(portrait, format="PNG", optimize=True)
            l_img.save(landscape, format="PNG", optimize=True)
            completed += 1
            print(f"[{index}/{len(folders)}] OK   {folder.name} | {main_text} / {sub_text}")
        except Exception as exc:  # keep the batch resumable
            failed.append((folder.name, str(exc)))
            print(f"[{index}/{len(folders)}] FAIL {folder.name}: {exc}", file=sys.stderr)

    print(f"completed={completed} skipped={skipped} failed={len(failed)}")
    for name, reason in failed:
        print(f"FAILED\t{name}\t{reason}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
