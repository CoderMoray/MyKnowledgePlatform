#!/usr/bin/env bash
# 打包 MyKnowledge macOS 桌面 App（electron-builder）— 带步骤进度展示
#
# 用法：
#   cd desktop && npm run build:app     （推荐）
#   或直接 bash scripts/build-desktop.sh
#
# 产物：desktop/dist/MyKnowledge-<ver>-arm64.dmg / -x64.dmg（及 .zip）
# 前置：dist-backend/ 已存在（先跑 npm run build:backend / scripts/build-backend.sh）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/desktop"

step() { printf "==> %s/%s %s\n" "$1" "$2" "$3"; }

TOTAL=4

# ── 1. 前置检查 ────────────────────────────────────────────
step 1 "$TOTAL" "前置检查：dist-backend 后端二进制"
BACKEND="$ROOT/dist-backend/myknowledge-backend/myknowledge-backend"
if [ ! -x "$BACKEND" ]; then
  echo "  ✗ 缺少后端二进制：$BACKEND" >&2
  echo "    请先执行: npm run build:backend（scripts/build-backend.sh，约 60-90s）" >&2
  exit 1
fi
echo "  ✓ dist-backend 就绪"

# ── 2. 依赖 ────────────────────────────────────────────────
step 2 "$TOTAL" "electron-builder 依赖（electron 二进制 / 工具链，有缓存则秒过）"

# ── 3. 打包（日志实时转发 + 抓关键行映射进度）────────────
step 3 "$TOTAL" "打包 dmg + zip（electron-builder）"
T3=$(date +%s)
ELECTRON_MIRROR="${ELECTRON_MIRROR:-https://npmmirror.com/mirrors/electron/}" \
ELECTRON_BUILDER_BINARIES_MIRROR="${ELECTRON_BUILDER_BINARIES_MIRROR:-https://npmmirror.com/mirrors/electron-builder-binaries/}" \
  npx electron-builder --mac 2>&1 | awk '
    function bar(p) {
      n = int(p / 2);
      s = "    [";
      for (i = 0; i < 50; i++) s = s (i < n ? "#" : ".");
      return s "] " p "%";
    }
    /Downloading/ { if (pct < 30) pct = 30; printf "\r%s\n", bar(pct); print; next }
    /building macOS zip|building.*\.zip/ { if (pct < 55) pct = 55; printf "\r%s\n", bar(pct); }
    /building.*\.dmg|DMG/ { if (pct < 80) pct = 80; printf "\r%s\n", bar(pct); }
    /build.*completed|completed successfully/ { pct = 100; printf "\r%s\n", bar(pct); }
    { print }
  '
ELAPSED=$(( $(date +%s) - T3 ))

# ── 4. 完成 ────────────────────────────────────────────────
step 4 "$TOTAL" "完成（打包耗时 ${ELAPSED}s）"
if ls -lh "$ROOT"/desktop/dist/*.dmg "$ROOT"/desktop/dist/*.zip >/dev/null 2>&1; then
  ls -lh "$ROOT"/desktop/dist/*.dmg "$ROOT"/desktop/dist/*.zip
else
  echo "  （desktop/dist/ 未找到产物，请检查上方 electron-builder 输出）" >&2
  exit 1
fi
echo "  ✓ 打包完成"
