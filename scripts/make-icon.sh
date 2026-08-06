#!/usr/bin/env bash
# 生成 app 图标：desktop/assets/icon.svg → desktop/assets/icon.icns
# 依赖 macOS 内置的 qlmanage / sips / iconutil（无需额外安装）
set -euo pipefail
cd "$(dirname "$0")/../desktop"

mkdir -p assets
SRC="assets/icon.svg"
[ -f "$SRC" ] || { echo "缺少 $SRC"; exit 1; }

TMP="$(mktemp -d)"
ICONSET="$TMP/icon.iconset"
mkdir -p "$ICONSET"

echo "==> 渲染 1024x1024 PNG（QuickLook）"
qlmanage -t -s 1024 -o "$TMP" "$SRC" >/dev/null 2>&1
[ -f "$TMP/icon.svg.png" ] || { echo "✗ qlmanage 渲染失败"; exit 1; }
cp "$TMP/icon.svg.png" "$TMP/icon-1024.png"

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
