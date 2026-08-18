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

step() {  # step <序号> <总数> <标题>
  echo "==> $1/$2 $3"
}

tick() {  # 单行进度条：<当前> <总数>
  local done=$(( $1 * 100 / $2 ))
  printf "\r    ["
  for (( i=0; i<50; i++ )); do
    if (( i < done / 2 )); then printf "#"; else printf "."; fi
  done
  printf "] %3d%%" "$done"
}

step 1 3 "前端构建（生成 index.standalone.html + 资源版本号）"
T0=$(date +%s)
"${PYTHON}" frontend/build.py
echo "    ✓ 前端构建完成 ($(( $(date +%s) - T0 ))s)"

step 2 3 "PyInstaller 打包后端（含前端静态资源，约 60-90s）"
rm -rf build "${OUT_DIR}"
# 注意：默认 onedir 模式（不传 --onefile）——onedir 免去每次启动解包，
# 后端就绪时间从 ~10s 降到 ~2s，对 Electron 冷启动体验影响巨大。
T1=$(date +%s)
# 实时抓 PyInstaller 进度行，换算成 0-100% 进度条。
# 按构建里程碑估算权重：分析(10%) → 生成 PYZ(20%) → 收集依赖(35%) →
# 打包 EXE(25%) → 生成 COLLECT(10%)，完成后置 100%。
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
  --add-data "frontend/index.standalone.html:frontend" \
  --add-data "frontend/index.html:frontend" \
  --add-data "frontend/js:frontend/js" \
  --add-data "frontend/css:frontend/css" \
  --add-data "frontend/vendor:frontend/vendor" \
  --add-data "frontend/tiptap-bundle.mjs:frontend" \
  --add-data "backend/hooks_forward.py:backend" \
  --add-data "backend/templates:backend/templates" \
  --exclude-module matplotlib \
  --exclude-module PIL \
  --exclude-module lxml \
  --exclude-module jedi \
  --exclude-module numpy \
  --exclude-module gevent \
  --exclude-module pandas \
  --exclude-module scipy \
  --exclude-module IPython \
  --exclude-module pytest \
  --exclude-module tkinter \
  --strip \
  --distpath "${OUT_DIR}" \
  --workpath build \
  --clean \
  --noconfirm \
  backend/desktop_server.py \
  2>&1 | awk '
    function pct(kind) {
      # 按构建里程碑返回 0-100 进度
      if      (kind ~ /ANALYZING|Processing/) return 10;
      else if (kind ~ /Building PYZ/)          return 30;
      else if (kind ~ /checking COLLECT|Building COLLECT/) return 85;
      else if (kind ~ /Building EXE/)          return 65;
      else if (kind ~ /Building PKG/)          return 55;
      else return -1;   # 其他 INFO 行不更新
    }
    {
      # 打印原始日志（可被上层 tail 读取）
      print
      # 只对含 "Building" / "checking COLLECT" / "Analyzing" 的关键行推进进度条
      if ($0 ~ /(Building|checking COLLECT|Analyzing|Appending PKG|completed successfully|Building PKG)/) {
        last = pct($0)
        if (last >= 0) { current = last }
      }
      if ($0 ~ /completed successfully/) {
        printf "\r    [%s] %3d%%  \n", "##################################################", 100
      } else if (current > 0) {
        bars = current * 50 / 100
        line = "    ["
        for (i = 0; i < 50; i++) line = line (i < bars ? "#" : ".")
        line = line "] " current "%"
        printf "\r%s", line
      }
    }'
echo "    ✓ PyInstaller 完成 ($(( $(date +%s) - T1 ))s)"

chmod +x "${OUT_DIR}/myknowledge-backend/myknowledge-backend"

step 3 3 "完成"
echo "    后端: ${OUT_DIR}/myknowledge-backend/myknowledge-backend"
echo "    冒烟测试: ${OUT_DIR}/myknowledge-backend/myknowledge-backend --port 8099"
