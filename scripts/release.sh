#!/usr/bin/env bash
# 一键打包 MyKnowledge macOS 桌面 App（dmg + zip）
#
# 用法：
#   bash scripts/release.sh                    # 默认（全平台）
#   bash scripts/release.sh --enterprise Acme  # 企业定制（desktop/enterprises/Acme.json）
#
# 流程：前端构建 → 后端 PyInstaller（合并企业配置）→ electron-builder 打包
# 产物：desktop/dist/MyKnowledge-<ver>-arm64.dmg / .zip（及 blockmap）
set -euo pipefail
cd "$(dirname "$0")/.."

ENTERPRISE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --enterprise)
      ENTERPRISE="${2:-}"
      if [ -z "$ENTERPRISE" ]; then
        echo "✗ --enterprise 需要一个企业名（desktop/enterprises/<name>.json）" >&2
        exit 1
      fi
      shift 2
      ;;
    *)
      echo "✗ 未知参数: $1（仅支持 --enterprise <name>）" >&2
      exit 1
      ;;
  esac
done

echo "=============================================="
echo " MyKnowledge 桌面打包"
if [ -n "$ENTERPRISE" ]; then
  echo " 企业: $ENTERPRISE（desktop/enterprises/${ENTERPRISE}.json）"
else
  echo " 企业: 默认（全平台）"
fi
echo "=============================================="

# 1. 后端（含前端构建 + 可选企业配置合并）
if [ -n "$ENTERPRISE" ]; then
  bash scripts/build-backend.sh --enterprise "$ENTERPRISE"
else
  bash scripts/build-backend.sh
fi

# 2. electron-builder 打包
bash scripts/build-desktop.sh

echo "=============================================="
echo " 完成 ✅"
echo " 产物目录: desktop/dist/"
echo "=============================================="
