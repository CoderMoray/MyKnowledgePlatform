#!/usr/bin/env python3
"""Regenerate tray template icon (16px + 32px@2x) — Bold M 字形.

Design (定稿 2026-08-19, design spec: docs/designs/tray-icon-2026-08-19/SPEC.md):
  - 16×16 viewport 内手工描 Bold M 字根（Helvetica Bold 几何）
  - 纯黑 + alpha 通道（macOS template image 协议约束）
  - macOS 菜单栏浅色 = 黑图标；深色 = 自动反色为白图标
  - 文件名必须以 'Template' 结尾，macOS 自动按菜单栏深浅反色

像素栅格（@1x 单位）：viewBox="0 0 16 16"
  - 左竖 / 右竖：x ∈ [1.0, 3.6] / [12.4, 15.0]，y 满 1→15（87.5% 高）
  - 中央 V 顶 / 谷：(8, 7.6) → (8, 11.6)（纵向 25% H）
  - 字形边界：x ∈ [1, 15], y ∈ [1, 15]，周围留 1px 安全边距

为何不用「主图标 icon.svg 降采样」：
    旧版是 512×512 圆角矩形 + 渐变背景降采样到 16，16px 下 M 笔画只剩
    1–2px；@2x 只是简单放大没做 Retina hint。本方案直接在 16 像素栅格
    上重新描线，22pt 菜单栏物理尺寸下远看仍能辨。

依赖：rsvg-convert (librsvg)。macOS 上 `brew install librsvg`，
或：`brew install --cask xquartz && rsvg-convert` 已自带 Cairo/Pango。

Usage:
    python3 scripts/make-tray-icon.py
Output:
    desktop/assets/trayTemplate.png       (16x16, 1x DPI)
    desktop/assets/trayTemplate@2x.png    (32x32, 2x DPI Retina)
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "desktop" / "assets"

# ── 设计 SVG 源头（viewBox=16，1x 像素栅格）──────────────────────
# 坐标含义详见模块 docstring + SPEC §1.2/§1.3。
SVG_PATH = "M1 15 L1 1 L4.5 1 L8 7.6 L11.5 1 L15 1 L15 15 L12.4 15 L12.4 5.6 L9 11.6 L7 11.6 L3.6 5.6 L3.6 15 Z"

SVG_1X = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"'
    f' viewBox="0 0 16 16"><path d="{SVG_PATH}" fill="#000"/></svg>'
)
SVG_2X = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"'
    f' viewBox="0 0 16 16"><path d="{SVG_PATH}" fill="#000"/></svg>'
)


def _render(svg_str: str, out_size: int, dst: Path) -> None:
    """用 rsvg-convert 把 SVG 栅格化成 PNG @ 指定尺寸。"""
    if shutil.which("rsvg-convert") is None:  # pragma: no cover
        raise SystemExit(
            "rsvg-convert 未找到。\n"
            "安装：brew install librsvg\n"
            "或：apt-get install librsvg2-bin"
        )
    # 用 stdin 传 SVG，避免落临时文件
    proc = subprocess.run(
        ["rsvg-convert", "-w", str(out_size), "-h", str(out_size), "-f", "png", "-"],
        input=svg_str.encode("utf-8"),
        check=True,
        capture_output=True,
    )
    dst.write_bytes(proc.stdout)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _render(SVG_1X, 16, OUT / "trayTemplate.png")
    _render(SVG_2X, 32, OUT / "trayTemplate@2x.png")
    print(
        "✓ 已生成 (Bold M · 方案 A 定稿):\n"
        f"  {OUT / 'trayTemplate.png'}      (16x16, 1x DPI)\n"
        f"  {OUT / 'trayTemplate@2x.png'}   (32x32, 2x DPI Retina)\n"
        "\n"
        "设计源: docs/designs/tray-icon-2026-08-19/export/trayTemplate-v2-source.svg\n"
        "规格:   docs/designs/tray-icon-2026-08-19/SPEC.md"
    )


if __name__ == "__main__":
    main()
