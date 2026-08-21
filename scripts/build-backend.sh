#!/usr/bin/env bash
# 打包 MyKnowledge 后端为单个可执行文件（供 Electron 壳 spawn）
#
# 用法：
#   ./scripts/build-backend.sh                              # 默认（全平台）
#   ./scripts/build-backend.sh --enterprise Acme            # 企业定制
#   PYTHON=/path/to/python ./scripts/build-backend.sh
#
# --enterprise <name>：读取 desktop/enterprises/<name>.json，在打包期把
# enabled/display 覆盖合并进 platforms.json，产物只含该企业启用的平台。
# 不传则保持默认（platforms.json 原样，全平台）。
#
# 产物：dist-backend/myknowledge-backend（PyInstaller onefile）
# 前端静态资源（frontend/）一并打入，运行时从 sys._MEIPASS/frontend 定位。
set -euo pipefail
cd "$(dirname "$0")/.."

# ── 参数解析 ────────────────────────────────────────────────────────────
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

# 企业配置：合并到临时 AiClientConfig 目录（不污染源 platforms.json）
ENTERPRISE_DIR=""
if [ -n "$ENTERPRISE" ]; then
  ENTERPRISE_FILE="desktop/enterprises/${ENTERPRISE}.json"
  if [ ! -f "$ENTERPRISE_FILE" ]; then
    echo "✗ 企业配置不存在: $ENTERPRISE_FILE" >&2
    echo "  可用配置: $(ls desktop/enterprises/*.json 2>/dev/null | xargs -n1 basename | tr '\n' ' ')" >&2
    exit 1
  fi
  echo "  ✓ 企业定制: ${ENTERPRISE}（${ENTERPRISE_FILE}）"
  ENTERPRISE_DIR="$(mktemp -d)"
  trap 'rm -rf "$ENTERPRISE_DIR"' EXIT
fi

# Python 智能探测：显式 PYTHON 优先；否则优先当前 PATH 的 python3，
# 但若它没有 PyInstaller（如 npm run 子进程解析到 macOS 系统 python），
# 自动回退到 conda base / 常见 conda 路径，避免 "No module named PyInstaller"。
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if command -v python3 >/dev/null 2>&1 && python3 -c "import PyInstaller" >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
  else
    # 候选：conda base（CONDA_PREFIX）→ 当前 shell 的 conda exe → 常见安装路径
    for cand in \
      "${CONDA_PREFIX:-}/bin/python3" \
      "$(command -v conda >/dev/null 2>&1 && dirname "$(dirname "$(command -v conda)")")/bin/python3" \
      "/opt/homebrew/Caskroom/miniconda/base/bin/python3" \
      "$HOME/miniconda3/bin/python3" \
      "$HOME/miniforge3/bin/python3"; do
      if [ -n "$cand" ] && [ -x "$cand" ] && "$cand" -c "import PyInstaller" >/dev/null 2>&1; then
        PYTHON="$cand"
        break
      fi
    done
    if [ -z "$PYTHON" ]; then
      echo "✗ 未找到带 PyInstaller 的 Python。请安装: pip install pyinstaller，或显式 PYTHON=/path/to/python" >&2
      exit 1
    fi
    echo "  ✓ PATH 的 python3 无 PyInstaller，自动使用: $PYTHON"
  fi
fi
echo "  ✓ 使用 Python: $PYTHON ($("$PYTHON" --version 2>&1))"
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

# ── 企业配置合并（仅 --enterprise 时）────────────────────────────────
AICLIENT_SRC="backend/AiClientConfig"
if [ -n "$ENTERPRISE" ]; then
  step 2 4 "合并企业配置 → 临时 AiClientConfig"
  AICLIENT_SRC="${ENTERPRISE_DIR}/AiClientConfig"
  "${PYTHON}" -c "
import json, shutil
from pathlib import Path
src = Path('backend/AiClientConfig')
dst = Path('${ENTERPRISE_DIR}/AiClientConfig')
shutil.copytree(src, dst)
base = json.loads((dst / 'platforms.json').read_text(encoding='utf-8'))
ent = json.loads(Path('${ENTERPRISE_FILE}').read_text(encoding='utf-8'))
overrides = ent.get('platforms', {})
platforms = base.get('platforms', {})
unknown = [k for k in overrides if k not in platforms]
if unknown:
    raise SystemExit(f'✗ 企业配置含未知平台: {\", \".join(unknown)}（仅支持: {\", \".join(platforms)}）')
# default_disabled=true → 未列出的平台默认禁用（只启用显式列出的）；
# 缺省 false → 未列出的沿用 platforms.json 默认（向后兼容）。
default_disabled = bool(ent.get('default_disabled', False))
for key, ov in overrides.items():
    if 'enabled' in ov:
        platforms[key]['enabled'] = bool(ov['enabled'])
    elif default_disabled:
        platforms[key]['enabled'] = True  # 显式列出即启用
    if 'display' in ov and ov['display']:
        platforms[key]['display'] = ov['display']
    if 'order' in ov:
        platforms[key]['order'] = ov['order']
if default_disabled:
    # 未显式列出的平台全部禁用
    for key in platforms:
        if key not in overrides:
            platforms[key]['enabled'] = False
(dst / 'platforms.json').write_text(json.dumps(base, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
enabled = [k for k, v in platforms.items() if v.get('enabled', True)]
print(f'  ✓ 启用平台: {\", \".join(enabled)}')
" || exit 1
fi

step 3 4 "PyInstaller 打包后端（含前端静态资源，约 60-90s）"
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
  --add-data "${AICLIENT_SRC}:backend/AiClientConfig" \
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

# ── MCP stdio 冒烟（自动执行）─────────────────────────────────────────
# 唯一能在真实 frozen 二进制上验证 --mcp 生效的地方（单测只能 mock sys.frozen，
# 而 PyInstaller 静态追踪 / datas 打包只有真跑产物才能暴露）。逻辑在
# scripts/mcp-smoke.sh（可独立手动运行，无需打包）；此处指向 frozen 二进制。
# MCP stdio server 是阻塞长驻进程，冒烟脚本用 select 非阻塞读 + close(stdin)
# 优雅退出 + wait(timeout) 兜底，保证不挂起。
step 4 4 "MCP stdio 冒烟（--mcp 自动验证）"
bash scripts/mcp-smoke.sh --bin "${OUT_DIR}/myknowledge-backend/myknowledge-backend"
if [ $? -ne 0 ]; then
  echo "    MCP 冒烟失败（见上方错误）。" >&2
  exit 1
fi

step 4 4 "完成"
echo "    后端: ${BIN}"
echo "    手动冒烟: ${BIN} --port 8099"
if [ -n "$ENTERPRISE" ]; then
  echo "    企业定制: $ENTERPRISE"
fi
