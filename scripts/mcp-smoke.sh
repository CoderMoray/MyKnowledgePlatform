#!/usr/bin/env bash
# MCP stdio 冒烟测试——验证 myknowledge 的 MCP server 能握手并优雅退出。
#
# 用途：
#   1) 构建后自动验证：build-backend.sh 在打包成功后调用它，指向 frozen 二进制。
#   2) 独立手动验证（无需打包）：直接跑，用开发环境的 python -m backend.cli mcp。
#
# 用法：
#   ./scripts/mcp-smoke.sh                    # 用 python -m backend.cli mcp（dev 路径）
#   ./scripts/mcp-smoke.sh --bin /path/to/myknowledge-backend   # 用 frozen 二进制 --mcp
#   ./scripts/mcp-smoke.sh --root /path/to/kb # 指定 KB 根（默认临时目录）
#   ./scripts/mcp-smoke.sh --timeout 5        # 无响应判定超时（秒，默认 8）
#
# 原理：
#   MCP stdio server 是阻塞长驻进程（app.run(transport="stdio") 读到 stdin EOF 才退出）。
#   冒烟流程：发 initialize → 用 select 非阻塞读响应（快速判定失败，不阻塞满时长）→
#   校验 serverInfo/MyKnowledge → close(stdin) 触发优雅退出 → wait(timeout) 兜底防挂起。
#   任一环节失败即非零退出，绝不无限挂起。
set -euo pipefail

BIN_CMD=""            # 留空 = python -m backend.cli mcp（dev 路径）
ROOT=""               # 留空 = 临时目录（避免污染真实 KB）
TIMEOUT=8
PYTHON="${PYTHON:-python3}"

while [ $# -gt 0 ]; do
  case "$1" in
    --bin) BIN_CMD="${2:-}"; shift 2 ;;
    --root) ROOT="${2:-}"; shift 2 ;;
    --timeout) TIMEOUT="${2:-8}"; shift 2 ;;
    *) echo "✗ 未知参数: ${1}（支持 --bin / --root / --timeout）" >&2; exit 1 ;;
  esac
done

# 默认用临时 KB（dev 路径也会 _auto_init），确保不触碰真实 ~/.myknowledge。
if [ -z "$ROOT" ]; then
  ROOT="$(mktemp -d)/kb"
fi

step() { echo "==> $1"; }

# 把目标 MCP server 的启动命令解析成 argv 列表传给 Python。
# --bin /path/x        → ["/path/x", "--mcp"]
# 默认（dev）          → [python, -m, backend.cli, mcp]
if [ -n "$BIN_CMD" ]; then
  ARGS_JSON="[\"$BIN_CMD\", \"--mcp\"]"
  DESC="frozen 二进制 $BIN_CMD --mcp"
else
  ARGS_JSON="[\"$PYTHON\", \"-m\", \"backend.cli\", \"mcp\"]"
  DESC="dev 路径 python -m backend.cli mcp"
fi

step "MCP stdio 冒烟（${DESC}）"
MYKNOWLEDGE_ROOT="$ROOT" "$PYTHON" - "$ARGS_JSON" "$ROOT" "$TIMEOUT" <<'PYEOF'
import json, os, select, subprocess, sys, time

argv = json.loads(sys.argv[1])   # 目标 MCP server 的 argv 列表
kb_root = sys.argv[2]            # MYKNOWLEDGE_ROOT（Python 已注入）
timeout = float(sys.argv[3])

env = dict(os.environ)
env["MYKNOWLEDGE_ROOT"] = kb_root
p = subprocess.Popen(
    argv,
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, bufsize=1, env=env,
)

req = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
       "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                  "clientInfo": {"name": "smoke", "version": "0.0.1"}}}
p.stdin.write(json.dumps(req) + "\n")
p.stdin.flush()

# 非阻塞读响应：用 select 等 stdout 可读，超时(timeout)即判失败。
# 相比固定 sleep 阻塞，失败路径能在超时一到立即返回，不会无谓等待。
deadline = time.monotonic() + timeout
line = None
while time.monotonic() < deadline:
    r, _, _ = select.select([p.stdout], [], [], 0.2)
    if r:
        line = p.stdout.readline()
        break
    if p.poll() is not None:
        # 进程已退出但没给出响应——多半身份未设置或模块缺失。
        err = p.stderr.read().strip()
        raise SystemExit(
            f"✗ MCP 冒烟失败：进程提前退出(rc={p.returncode})，无响应。\n"
            f"  stderr: {err[:400]}")
    time.sleep(0.05)

if line is None:
    p.kill()
    raise SystemExit(
        f"✗ MCP 冒烟失败：{timeout:g}s 内无 initialize 响应。"
        f"  stderr: {p.stderr.read().strip()[:400]}")

if '"serverInfo"' not in line or '"MyKnowledge"' not in line:
    p.kill()
    raise SystemExit(
        f"✗ MCP 冒烟失败：响应缺少 serverInfo/MyKnowledge。\n  {line.strip()[:200]}")

# 校验通过 → 触发优雅退出（stdio EOF）。
p.stdin.close()
try:
    p.wait(timeout=5)
except subprocess.TimeoutExpired:
    p.kill()
    raise SystemExit("✗ MCP 冒烟失败：close(stdin) 后进程未在 5s 内退出")
print(f"✓ MCP 冒烟通过：serverInfo=MyKnowledge，进程优雅退出（rc={p.returncode}）")
PYEOF
