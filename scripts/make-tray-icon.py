#!/usr/bin/env python3
"""Regenerate tray template icon (16px + 32px@2x) — rounded-rect badge + MK knockout.

Design (定稿 2026-08-19):
  - 圆角矩形徽章（填满画布约 95%），角半径约 22%
  - "MK" 镂空：矩形是实心，文字区域透明（knockout）
  - 黑色 + 透明底 = macOS template 图规则，菜单栏深色模式自动反白
    （用户看到的效果：浅色菜单栏=黑徽章白字，深色菜单栏=白徽章黑字）

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

    # ── 1. 黑色圆角矩形徽章（占画布 ~95%，居中）──────────
    pad = max(1, size // 16)          # 16px→1px 边距；32px→2px
    rx = max(2, round(size * 0.22))   # 角半径 22%
    rect_box = [pad, pad, size - pad, size - pad]
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    bd.rounded_rectangle(rect_box, radius=rx, fill=(0, 0, 0, 255))

    # ── 2. "MK" 文字 mask → 从徽章上镂空 ────────────────
    # 文字尺寸相对徽章：16px 徽章内文字 ~9px；32px 内 ~19px
    font_size = max(7, round(size * 0.56))
    f = _font(font_size)
    txt = "MK"
    measure = ImageDraw.Draw(img)
    tb = measure.textbbox((0, 0), txt, font=f)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    # 徽章内居中（以 badge 内区域为基准）；MK 视觉重心偏右，微左移
    cx = (rect_box[0] + rect_box[2]) / 2
    cy = (rect_box[1] + rect_box[3]) / 2
    x = cx - tw / 2 - tb[0] - size * 0.03
    y = cy - th / 2 - tb[1]

    # 文字 mask（白色文字 → 用 R 通道作 mask）
    txt_layer = Image.new("L", (size, size), 0)
    td = ImageDraw.Draw(txt_layer)
    td.text((x, y), txt, font=f, fill=255)
    # 用 mask 擦除徽章：badge 在文字处变透明
    badge.putalpha(Image.composite(Image.new("L", (size, size), 0), badge.getchannel("A"), txt_layer))

    img.paste(badge, (0, 0), badge)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    render(16).save(OUT / "trayTemplate.png")
    render(32).save(OUT / "trayTemplate@2x.png")
    print(f"✓ 已生成:\n  {OUT / 'trayTemplate.png'}\n  {OUT / 'trayTemplate@2x.png'}")


if __name__ == "__main__":
    main()
