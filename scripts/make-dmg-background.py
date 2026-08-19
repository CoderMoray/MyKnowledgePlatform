#!/usr/bin/env python3
"""Generate the DMG installer background (600x400 + 1200x800 Retina).

Design (定稿 2026-08-19):
  - Pure-white corners (光晕径向渐变 alpha，不外溢 → 四角纯白)
  - Two overlapping soft indigo glows → "流动" 淡蓝紫氛围
  - White arrow pointing left→right (App icon → Applications folder)
  - Title + subtitle + version tag

NOTE: 背景图**不画 App 图标 / 文件夹图标** —— 它们由 electron-builder 的
``dmg.contents`` 坐标在对应位置放**真实图标**（.icns）。背景只承担：
渐变 + 箭头 + 文字。图标中心锚点在 (150, 170) 与 (450, 170)，
与 electron-builder.yml 的 dmg.contents 保持一致。

Usage:
    python3 scripts/make-dmg-background.py
Output:
    desktop/assets/dmg-background.png      (600x400)
    desktop/assets/dmg-background@2x.png   (1200x800)
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "desktop" / "assets"

# 图标锚点（electron-builder dmg.contents 同款坐标，仅用于排版参考）
APP_ICON_CENTER = (150, 170)   # 左：App 图标
FOLDER_CENTER = (450, 170)     # 右：Applications 快捷方式


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for cand in [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]:
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _add_glow(img: Image.Image, cx: int, cy: int, r: int,
              col: tuple[int, int, int], peak: int, blur: int) -> Image.Image:
    """叠加一个径向渐变 alpha 光晕（中心浓→外缘 0），模糊后自然衰减。"""
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for rr in range(r, 0, -1):
        a = int(peak * (1 - rr / r))
        gd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col + (a,))
    glow = glow.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(img.convert("RGBA"), glow)


def _arrow(d: ImageDraw.ImageDraw, x1: int, y: int, x2: int,
           width: int, color: tuple[int, int, int, int], head: float = 0.9) -> None:
    d.line([(x1, y), (x2, y)], fill=color, width=width)
    d.polygon([(x2, y - width * 1.4), (x2 + width * 2.4, y), (x2, y + width * 1.4)], fill=color)


def render(scale: int) -> Image.Image:
    """scale=1 → 600x400；scale=2 → 1200x800。坐标全部按 scale 放大。"""
    W, H = 600 * scale, 400 * scale
    S = scale

    img = Image.new("RGB", (W, H), (0xFF, 0xFF, 0xFF))

    # 光晕：对角线排布（左上 + 右下），半径更小 + blur 更弱 → 两个分明光球，
    # 不再糊在一起。中心更靠角，让中部留出图标/箭头的干净呼吸区。
    img = _add_glow(img, 140 * S, 110 * S, 200 * S, (129, 140, 248), 215, 40 * S)
    img = _add_glow(img, 460 * S, 300 * S, 210 * S, (99, 102, 241), 200, 40 * S)
    d = ImageDraw.Draw(img)

    # 箭头：白色 + 柔光阴影（与定稿图一致）
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    _arrow(sd, 215 * S, 170 * S, 385 * S, 6 * S, (0, 0, 0, 90), head=0.9)
    shadow = shadow.filter(ImageFilter.GaussianBlur(4 * S))
    img = Image.alpha_composite(img, shadow)
    d = ImageDraw.Draw(img)
    _arrow(d, 212 * S, 168 * S, 388 * S, 5 * S, (255, 255, 255, 255), head=0.9)

    # 标题区（顶部）
    f_title = _font(22 * S)
    d.text((W / 2, 52 * S), "MyKnowledge", font=f_title, fill=(0x11, 0x18, 0x27), anchor="mm")
    f_sub = _font(13 * S)
    d.text((W / 2, 88 * S), "拖拽到 Applications 文件夹完成安装", font=f_sub,
           fill=(0x6B, 0x72, 0x80), anchor="mm")
    # 版本号/slogan：移到图标行下方（y=245）—— DMG Finder 窗口实际尺寸
    # 不固定，贴底会被截；放在图标下方既安全又符合"图标-标签"的 Finder 习惯。
    f_tag = _font(11 * S)
    d.text((W / 2, 245 * S), "v0.7.6 · Local-first Knowledge Platform", font=f_tag,
           fill=(0x6B, 0x72, 0x80), anchor="mm")

    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    render(1).save(OUT / "dmg-background.png")
    render(2).save(OUT / "dmg-background@2x.png")
    print(f"✓ 已生成:\n  {OUT / 'dmg-background.png'}\n  {OUT / 'dmg-background@2x.png'}")


if __name__ == "__main__":
    main()
