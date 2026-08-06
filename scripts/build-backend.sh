#!/usr/bin/env bash
# 打包 MyKnowledge 后端为单个可执行文件（供 Electron 壳 spawn）
#
# 用法：
#   ./scripts/build-backend.sh                # 用 python3
#   PYTHON=/path/to/python ./scripts/build-backend.sh
#
# 产物：dist-backend/myknowledge-backend（PyInstaller onefile）
# 前端静态资源（frontend/）一并打入，运行时从 sys._MEIPASS/frontend 定位。
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
OUT_DIR="dist-backend"

echo "==> 1/3 前端构建（生成 index.standalone.html + 资源版本号）"
"${PYTHON}" frontend/build.py

echo "==> 2/3 PyInstaller 打包后端"
rm -rf build "${OUT_DIR}"
# 注意：默认 onedir 模式（不传 --onefile）——onedir 免去每次启动解包，
# 后端就绪时间从 ~10s 降到 ~2s，对 Electron 冷启动体验影响巨大。
"${PYTHON}" -m PyInstaller \
  --name myknowledge-backend \
  --collect-all uvicorn \
  --collect-all pydantic \
  --collect-all mcp \
  --collect-submodules yaml \
  --collect-submodules git \
  --collect-submodules aiosqlite \
  --collect-submodules multipart \
  --collect-submodules fastapi \
  --collect-submodules starlette \
  --add-data "frontend:frontend" \
  --distpath "${OUT_DIR}" \
  --workpath build \
  --clean \
  --noconfirm \
  backend/desktop_server.py

chmod +x "${OUT_DIR}/myknowledge-backend/myknowledge-backend"

echo "==> 3/3 完成"
echo "    后端: ${OUT_DIR}/myknowledge-backend/myknowledge-backend"
echo "    冒烟测试: ${OUT_DIR}/myknowledge-backend/myknowledge-backend --port 8099"
