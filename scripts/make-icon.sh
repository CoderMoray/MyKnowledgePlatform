#!/usr/bin/env bash
# 生成 app 图标：desktop/assets/icon.svg → desktop/assets/icon.icns
#
# 渲染器优先级：
#   1. rsvg-convert  — 保留 SVG 透明背景（推荐，否则 Dock 图标四角出现白块）
#   2. qlmanage      — macOS 自带回退（会把透明角渲染成不透明白色，会触发校验告警）
# 后续步骤用 macOS 内置 sips + iconutil，无需额外安装。
set -euo pipefail
cd "$(dirname "$0")/../desktop"

mkdir -p assets
SRC="assets/icon.svg"
[ -f "$SRC" ] || { echo "缺少 $SRC"; exit 1; }

TMP="$(mktemp -d)"
ICONSET="$TMP/icon.iconset"
mkdir -p "$ICONSET"

echo "==> 渲染 1024x1024 PNG"
RENDERER=""
if command -v rsvg-convert >/dev/null 2>&1; then
  rsvg-convert -w 1024 -h 1024 "$SRC" -o "$TMP/icon-1024.png"
  RENDERER="rsvg-convert"
else
  qlmanage -t -s 1024 -o "$TMP" "$SRC" >/dev/null 2>&1
  cp "$TMP/icon.svg.png" "$TMP/icon-1024.png"
  RENDERER="qlmanage (fallback)"
fi
echo "    渲染器: ${RENDERER}"

# 校验四角透明（macOS 图标必须带 alpha，否则 Dock/Launchpad 出现白角）
if python3 -c "import PIL" >/dev/null 2>&1; then
  python3 - "$TMP/icon-1024.png" <<'PY'
import sys
from PIL import Image
img = Image.open(sys.argv[1]).convert("RGBA")
w, h = img.size
for x, y in [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]:
    px = img.getpixel((x, y))
    if px[3] != 0:
        sys.exit(f"✗ 图标四角非透明 RGBA={px}，请安装 rsvg-convert 后重跑")
print("    ✓ 四角透明")
PY
else
  echo "    ! 未安装 Pillow，跳过四角透明校验"
fi

echo "==> 生成标准尺寸集"
sips -z 16 16   "$TMP/icon-1024.png" --out "$ICONSET/icon_16x16.png" >/dev/null
sips -z 32 32   "$TMP/icon-1024.png" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
sips -z 32 32   "$TMP/icon-1024.png" --out "$ICONSET/icon_32x32.png" >/dev/null
sips -z 64 64   "$TMP/icon-1024.png" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
sips -z 128 128 "$TMP/icon-1024.png" --out "$ICONSET/icon_128x128.png" >/dev/null
sips -z 256 256 "$TMP/icon-1024.png" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "$TMP/icon-1024.png" --out "$ICONSET/icon_256x256.png" >/dev/null
sips -z 512 512 "$TMP/icon-1024.png" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$TMP/icon-1024.png" --out "$ICONSET/icon_512x512.png" >/dev/null
cp "$TMP/icon-1024.png" "$ICONSET/icon_512x512@2x.png"

echo "==> 生成 icns"
iconutil -c icns "$ICONSET" -o assets/icon.icns
rm -rf "$TMP"
echo "OK  assets/icon.icns"
