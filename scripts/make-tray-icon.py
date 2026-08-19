#!/usr/bin/env python3
"""Regenerate tray template icon (16px + 32px@2x), text 'MK' on transparent.

Template image rules (macOS):
  - Pure black strokes + transparent background
  - macOS auto-inverts to white on dark menu bar
  - Filename must end with 'Template' so macOS auto-handles dark mode

Usage:
    python3 scripts/make-tray-icon.py
Output:
    desktop/assets/trayTemplate.png       (16x16, 1x DPI)
    desktop/assets/trayTemplate@2x.png    (32x32, 2x DPI Retina)
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "desktop" / "assets"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Helvetica 优先（紧凑黑体，MK 视觉整齐）；PingFang 作为中文回退。"""
    for cand in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/PingFang.ttc",
    ]:
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render(size: int) -> Image.Image:
    """16 → 标准托盘图；32 → Retina @2x。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 字号小一档（11/22）保证 K 不触边；MK 整体视觉重心偏右，额外左移 6%
    font_size = 11 if size <= 16 else 22
    f = _font(font_size)
    txt = "MK"
    bbox = d.textbbox((0, 0), txt, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0] - size * 0.06
    y = (size - th) / 2 - bbox[1]
    d.text((x, y), txt, font=f, fill=(0, 0, 0, 255))
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    render(16).save(OUT / "trayTemplate.png")
    render(32).save(OUT / "trayTemplate@2x.png")
    print(f"✓ 已生成:\n  {OUT / 'trayTemplate.png'}\n  {OUT / 'trayTemplate@2x.png'}")


if __name__ == "__main__":
    main()