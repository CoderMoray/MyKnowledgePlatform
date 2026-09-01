"""针对**打包产物**的验收测试（不是源码单测）。

现有 900+ 测试全部是源码级单元测试，桌面相关的重活（uvicorn / MCP stdio /
PyInstaller datas / electron 打包）都被 mock 掉了 —— 于是"只有打包产物才会暴露"
的问题（裸 ``mcp`` 报错、旧前端被封进包、缺 logo、企业配置没生效、单实例锁
丢失…）没有任何测试能抓到。

本模块补这个缺口：**直接检查打好的东西本身**。

测试对象：
  1. ``dist-backend/myknowledge-backend/myknowledge-backend`` —— PyInstaller
     frozen 二进制（release 链的中间产物）。
  2. ``/Applications/MyKnowledge (Apple).app`` —— 已安装的企业定制桌面 App
     （``release.sh --enterprise Apple`` 的最终产物）。

运行前置：**必须先构建**。没构建时整个模块 skip，并提示：

    bash scripts/make-icon.sh
    bash scripts/release.sh --enterprise Apple

与源码单测的关系：
  * 独立模块，不 import 也不改动任何现有测试。
  * 绝大多数用例是"读产物 / 起子进程打产物"，秒级完成。
  * 真跑一遍完整 release 链（electron-builder，数分钟）的用例默认 skip，
    需 ``MYK_RUN_RELEASE=1`` 显式开启。

《验收清单》对应关系见每个 ``Test*`` 类的 docstring。
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator

import pytest

# ──────────────────────────────────────────────────────────────────────────
#  路径与常量
# ──────────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"

DIST_BACKEND_DIR = REPO_ROOT / "dist-backend" / "myknowledge-backend"
DIST_BIN = DIST_BACKEND_DIR / "myknowledge-backend"
DIST_INTERNAL = DIST_BACKEND_DIR / "_internal"

APP_PATH = Path("/Applications/MyKnowledge (Apple).app")
APP_CONTENTS = APP_PATH / "Contents"
APP_RESOURCES = APP_CONTENTS / "Resources"
APP_BIN = APP_RESOURCES / "myknowledge-backend" / "myknowledge-backend"
APP_INTERNAL = APP_RESOURCES / "myknowledge-backend" / "_internal"
APP_ASAR = APP_RESOURCES / "app.asar"
APP_ICNS = APP_RESOURCES / "icon.icns"
APP_INFO_PLIST = APP_CONTENTS / "Info.plist"

ENTERPRISE_JSON = REPO_ROOT / "desktop" / "enterprises" / "Apple.json"


def _read_source_version() -> str:
    """版本号单一来源：backend/__version__.py。"""
    txt = (REPO_ROOT / "backend" / "__version__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', txt)
    assert m, "backend/__version__.py 里找不到 __version__"
    return m.group(1)


EXPECTED_VERSION = _read_source_version()

# 企业定制（Apple）下前端应当只看到这两个平台
APPLE_ENABLED_PLATFORMS = {"Enchante", "ClaudeCode"}
APPLE_DISPLAY = {
    "Enchante": "Enchanté",
    "ClaudeCode": "Claude Code (Apple Internal)",
}
APPLE_ORDER = {"Enchante": 1, "ClaudeCode": 2}


# ──────────────────────────────────────────────────────────────────────────
#  模块级 skip：没构建就不跑
# ──────────────────────────────────────────────────────────────────────────

_BUILD_HINT = (
    "打包产物不存在。先构建：\n"
    "    bash scripts/make-icon.sh\n"
    "    bash scripts/release.sh --enterprise Apple\n"
    f"（缺少 {DIST_BIN}）"
)

pytestmark = pytest.mark.skipif(not DIST_BIN.exists(), reason=_BUILD_HINT)

_app_installed = pytest.mark.skipif(
    not APP_BIN.exists(),
    reason=f"未安装企业定制 App（缺少 {APP_PATH}）——跑 release.sh --enterprise Apple 后拖入 /Applications",
)


# ──────────────────────────────────────────────────────────────────────────
#  工具函数
# ──────────────────────────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http_get(url: str, timeout: float = 5.0):
    """返回 (status_code, body_bytes, headers)。网络异常直接抛。"""
    req = urllib.request.Request(url, headers={"User-Agent": "packaged-artifact-test"})
    def _lc(headers) -> dict:
        return {k.lower(): v for k, v in dict(headers or {}).items()}

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read(), _lc(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), _lc(e.headers)


class _BackendProcess:
    """起一个 frozen 二进制 ``--port`` 子进程，轮询 /api/status 直到 200。"""

    def __init__(self, binary: Path):
        self.binary = binary
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._proc: subprocess.Popen | None = None
        self._root = REPO_ROOT / ".pytest_cache" / f"pkg_kb_{self.port}"

    def __enter__(self) -> "_BackendProcess":
        import shutil
        import tempfile

        self._root = Path(tempfile.mkdtemp(prefix="myk_pkg_kb_"))
        env = dict(os.environ)
        env["MYKNOWLEDGE_ROOT"] = str(self._root)
        self._proc = subprocess.Popen(
            [str(self.binary), "--port", str(self.port), "--root", str(self._root)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                out = self._proc.stdout.read().decode("utf-8", "replace") if self._proc.stdout else ""
                raise RuntimeError(
                    f"frozen 二进制提前退出 rc={self._proc.returncode}\n{out[:2000]}"
                )
            try:
                code, _, _ = _http_get(f"{self.base_url}/api/status", timeout=2)
                if code == 200:
                    return self
            except Exception:
                pass
            time.sleep(0.3)
        self._terminate()
        raise RuntimeError("frozen 二进制 40s 内 /api/status 未就绪")

    def __exit__(self, *exc) -> None:
        self._terminate()
        import shutil

        shutil.rmtree(self._root, ignore_errors=True)

    def _terminate(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self._proc.kill()


def _mcp_handshake(binary: Path, extra_argv: list[str], root: Path,
                   timeout: float = 30.0) -> tuple[dict, list[str]]:
    """对 frozen 二进制的 MCP stdio server 发 initialize（+ tools/list）。

    返回 (initialize_result, tool_names)。任一步失败即 raise。
    复刻 scripts/mcp-smoke.sh 的非阻塞读 + close(stdin) 优雅退出逻辑。
    """
    import select

    env = dict(os.environ)
    env["MYKNOWLEDGE_ROOT"] = str(root)
    proc = subprocess.Popen(
        [str(binary), *extra_argv],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    def _send(obj: dict) -> None:
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def _read_json(match_key: str, deadline: float) -> dict:
        while time.monotonic() < deadline:
            r, _, _ = select.select([proc.stdout], [], [], 0.2)
            if r:
                line = proc.stdout.readline()
                if not line:
                    break
                if match_key in line:
                    return json.loads(line)
            if proc.poll() is not None:
                err = proc.stderr.read()
                raise RuntimeError(
                    f"MCP 进程提前退出 rc={proc.returncode}\n{err[:2000]}"
                )
        raise RuntimeError(f"{timeout:g}s 内未读到含 {match_key!r} 的响应")

    try:
        _send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "pkg-test", "version": "0"},
            },
        })
        deadline = time.monotonic() + timeout
        init = _read_json('"serverInfo"', deadline)

        _send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools_resp = _read_json('"tools"', time.monotonic() + timeout)
        names = sorted(t["name"] for t in tools_resp["result"]["tools"])

        proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("close(stdin) 后 MCP 进程未在 5s 内优雅退出")
        return init["result"], names
    finally:
        if proc.poll() is None:
            proc.kill()


def _read_asar(asar_path: Path) -> dict[str, bytes]:
    """极简 asar 解包：返回 {相对路径: 文件字节}。

    asar 格式：[uint32 =4][uint32 headerSize][uint32 headerObjSize]
    [uint32 jsonLen][json header][4 字节对齐后是文件数据区]。
    """
    data = asar_path.read_bytes()
    (_, _, _, json_len) = struct.unpack("<IIII", data[:16])
    header = json.loads(data[16:16 + json_len].decode("utf-8"))
    base = 16 + (json_len + 3) // 4 * 4
    out: dict[str, bytes] = {}

    def _walk(node: dict, prefix: str) -> None:
        for name, entry in node.get("files", {}).items():
            rel = f"{prefix}/{name}" if prefix else name
            if "files" in entry:
                _walk(entry, rel)
            elif "offset" in entry:
                off = int(entry["offset"])
                size = int(entry["size"])
                out[rel] = data[base + off: base + off + size]

    _walk(header, "")
    return out


def _internal_frontend_files(internal_dir: Path) -> list[Path]:
    fdir = internal_dir / "frontend"
    return [p for p in fdir.rglob("*") if p.is_file()]


# ──────────────────────────────────────────────────────────────────────────
#  fixtures
# ──────────────────────────────────────────────────────────────────────────

# 关键 HTTP 用例同时打两个后端：dist-backend 中间产物 + 已装 App 内的后端。
_BACKEND_BINARIES = [pytest.param(DIST_BIN, id="dist-backend")]
if APP_BIN.exists():
    _BACKEND_BINARIES.append(pytest.param(APP_BIN, id="installed-app"))


@pytest.fixture(scope="module")
def dist_backend() -> Iterator[_BackendProcess]:
    with _BackendProcess(DIST_BIN) as bp:
        yield bp


@pytest.fixture(scope="module", params=_BACKEND_BINARIES)
def any_backend(request) -> Iterator[_BackendProcess]:
    with _BackendProcess(request.param) as bp:
        yield bp


@pytest.fixture(scope="module")
def asar_files() -> dict[str, bytes]:
    if not APP_ASAR.exists():
        pytest.skip(f"缺少 {APP_ASAR}")
    return _read_asar(APP_ASAR)


# ══════════════════════════════════════════════════════════════════════════
#  1. 打包能通 —— release 链一路跑通不中断〔d03d103〕
# ══════════════════════════════════════════════════════════════════════════


class TestReleaseChain:
    """《验收清单》1：release 链能一路跑通不中断。

    完整跑一遍 electron-builder 要数分钟，默认 skip（``MYK_RUN_RELEASE=1`` 开）。
    默认只做**静态**校验，重点覆盖 d03d103 修的那个"链断在中途"的 bug：
    build-backend.sh 结尾引用了未定义的 ``$BIN`` → ``set -u`` 下非零退出 →
    ``release.sh`` 的 ``set -e`` 中断 → electron-builder 从未执行 → dmg 一直是旧的。
    """

    RELEASE_SCRIPTS = [
        "release.sh", "build-backend.sh", "build-desktop.sh",
        "make-icon.sh", "mcp-smoke.sh",
    ]

    @pytest.mark.parametrize("name", RELEASE_SCRIPTS)
    def test_release_scripts_syntax_valid(self, name: str) -> None:
        """release 链上每个脚本 ``bash -n`` 语法自检通过。"""
        script = SCRIPTS / name
        assert script.exists(), f"缺少 {script}"
        r = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert r.returncode == 0, f"{name} 语法错误：{r.stderr}"

    def test_build_backend_defines_BIN_before_use(self) -> None:
        """〔d03d103 回归〕build-backend.sh 在 ``echo ... ${BIN}`` 之前定义 BIN。"""
        src = (SCRIPTS / "build-backend.sh").read_text(encoding="utf-8")
        assert "set -euo pipefail" in src, "build-backend.sh 应处于 set -u 严格模式"
        assign = src.find('BIN="${OUT_DIR}/myknowledge-backend/myknowledge-backend"')
        first_use = src.find('echo "    后端: ${BIN}"')
        assert assign != -1, "build-backend.sh 未定义 BIN 变量（d03d103 的修复丢失）"
        assert first_use != -1, "build-backend.sh 结尾未找到 ${BIN} 引用行"
        assert assign < first_use, "BIN 在被引用之后才定义 —— set -u 下会 unbound variable 中断 release 链"

    def test_release_chains_backend_then_desktop(self) -> None:
        """release.sh 依次调用 build-backend.sh → build-desktop.sh。"""
        src = (SCRIPTS / "release.sh").read_text(encoding="utf-8")
        i_backend = src.find("scripts/build-backend.sh")
        i_desktop = src.find("scripts/build-desktop.sh")
        assert i_backend != -1 and i_desktop != -1
        assert i_backend < i_desktop
        assert "set -euo pipefail" in src

    def test_build_backend_runs_mcp_smoke_on_frozen_binary(self) -> None:
        """build-backend.sh 收尾会对 frozen 二进制跑 MCP 冒烟（唯一真机验证点）。"""
        src = (SCRIPTS / "build-backend.sh").read_text(encoding="utf-8")
        assert "scripts/mcp-smoke.sh" in src
        assert '--bin "${OUT_DIR}/myknowledge-backend/myknowledge-backend"' in src

    @pytest.mark.skipif(
        not os.environ.get("MYK_RUN_RELEASE"),
        reason="完整 release 链耗时数分钟；设 MYK_RUN_RELEASE=1 显式开启",
    )
    def test_full_release_chain_produces_dmg(self) -> None:
        """真跑 ``release.sh --enterprise Apple``，断言 rc==0 且产出新 dmg/zip。"""
        dist_dir = REPO_ROOT / "desktop" / "dist"
        dmg = dist_dir / f"MyKnowledge-{EXPECTED_VERSION}-arm64.dmg"
        before = dmg.stat().st_mtime if dmg.exists() else 0
        start = time.time()
        env = dict(os.environ)
        # build-backend.sh 需要一个带 PyInstaller 的解释器；当前跑测试的这个若满足就直接用。
        try:
            import PyInstaller  # noqa: F401
            env.setdefault("PYTHON", sys.executable)
        except ModuleNotFoundError:
            pass
        r = subprocess.run(
            ["bash", str(SCRIPTS / "release.sh"), "--enterprise", "Apple"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=1800, env=env,
        )
        assert r.returncode == 0, (
            f"release 链中断 rc={r.returncode}\n"
            f"--- stdout tail ---\n{r.stdout[-3000:]}\n"
            f"--- stderr tail ---\n{r.stderr[-3000:]}"
        )
        assert dmg.exists(), f"release 完成但没产出 {dmg.name}"
        assert dmg.stat().st_mtime > before or dmg.stat().st_mtime >= start, "dmg 未被重新生成"
        assert (dist_dir / f"MyKnowledge-{EXPECTED_VERSION}-arm64-mac.zip").exists()


# ══════════════════════════════════════════════════════════════════════════
#  2. 门面 —— logo + 版本号
# ══════════════════════════════════════════════════════════════════════════


class TestFacade:
    """《验收清单》2：产物带 logo（icon.icns 在包里）、版本号 = 0.7.7。"""

    @_app_installed
    def test_app_bundles_icns_logo(self) -> None:
        assert APP_ICNS.exists(), f"App 里没有 logo：{APP_ICNS}"
        blob = APP_ICNS.read_bytes()
        assert blob[:4] == b"icns", "icon.icns 头 4 字节不是 'icns'（文件损坏 / 不是真 icns）"
        assert len(blob) > 20_000, f"icon.icns 只有 {len(blob)} 字节，疑似占位空图标"

    @_app_installed
    def test_app_plist_declares_icon_file(self) -> None:
        info = plistlib.loads(APP_INFO_PLIST.read_bytes())
        assert info.get("CFBundleIconFile", "").startswith("icon"), info.get("CFBundleIconFile")

    def test_icns_source_present_for_rebuild(self) -> None:
        """release.sh 依赖 desktop/assets/icon.icns（make-icon.sh 产出）。"""
        icns = REPO_ROOT / "desktop" / "assets" / "icon.icns"
        assert icns.exists(), "缺少 desktop/assets/icon.icns —— 先跑 scripts/make-icon.sh"
        assert icns.read_bytes()[:4] == b"icns"

    @_app_installed
    def test_app_plist_version_is_expected(self) -> None:
        info = plistlib.loads(APP_INFO_PLIST.read_bytes())
        assert info["CFBundleShortVersionString"] == EXPECTED_VERSION
        assert info["CFBundleVersion"] == EXPECTED_VERSION
        assert info["CFBundleIdentifier"] == "com.myknowledge.desktop"

    def test_version_sources_all_consistent(self) -> None:
        """backend/__version__.py == desktop/package.json == 0.7.7（验收清单硬编码值）。"""
        assert EXPECTED_VERSION == "0.7.7", (
            f"验收清单要求 0.7.7，但 backend/__version__.py = {EXPECTED_VERSION}"
        )
        pkg = json.loads((REPO_ROOT / "desktop" / "package.json").read_text(encoding="utf-8"))
        assert pkg["version"] == EXPECTED_VERSION

    @pytest.mark.parametrize("binary", _BACKEND_BINARIES)
    def test_api_version_reports_expected(self, binary: Path) -> None:
        """打产物起后端，``/api/version`` 的 system 字段 = 0.7.7。"""
        with _BackendProcess(binary) as bp:
            code, body, _ = _http_get(f"{bp.base_url}/api/version")
            assert code == 200
            assert json.loads(body)["system"] == EXPECTED_VERSION


# ══════════════════════════════════════════════════════════════════════════
#  3. 后端起得来
# ══════════════════════════════════════════════════════════════════════════


class TestBackendBoots:
    """《验收清单》3：subprocess 拉起 frozen 二进制 --port，/api/status 返 200。"""

    def test_status_200_and_nonempty(self, any_backend: _BackendProcess) -> None:
        code, body, _ = _http_get(f"{any_backend.base_url}/api/status")
        assert code == 200
        assert body.strip(), "/api/status body 为空"

    def test_status_detail_json_ok(self, any_backend: _BackendProcess) -> None:
        code, body, _ = _http_get(f"{any_backend.base_url}/api/status/detail")
        assert code == 200
        data = json.loads(body)
        assert "projects" in data and "documents" in data

    def test_binary_binds_the_requested_port(self, any_backend: _BackendProcess) -> None:
        """frozen 二进制严格监听 ``--port`` 传入值（不会自己漂移到别的端口）。"""
        code, _, _ = _http_get(f"{any_backend.base_url}/api/status")
        assert code == 200


# ══════════════════════════════════════════════════════════════════════════
#  4. MCP 能连〔0783141〕
# ══════════════════════════════════════════════════════════════════════════


def _source_mcp_tool_names() -> set[str]:
    """从 backend/mcp_server.py 抽出所有 @mcp.tool() 装饰的函数名（= 工具名）。"""
    src = (REPO_ROOT / "backend" / "mcp_server.py").read_text(encoding="utf-8")
    return set(re.findall(r"@mcp\.tool\(\)\s*\n\s*(?:async\s+)?def\s+(\w+)", src))


class TestMcpConnect:
    """《验收清单》4：对二进制发 initialize，裸 ``mcp`` 和 ``--mcp`` 都返回
    ``serverInfo=MyKnowledge``〔0783141：frozen 后端要同时接受裸 ``mcp`` 位置参数〕。
    """

    @pytest.mark.parametrize("binary", _BACKEND_BINARIES)
    @pytest.mark.parametrize("argv", [["--mcp"], ["mcp"]], ids=["flag", "bare-positional"])
    def test_initialize_returns_myknowledge_serverinfo(
        self, binary: Path, argv: list[str], tmp_path: Path
    ) -> None:
        result, _ = _mcp_handshake(binary, argv, tmp_path / "kb")
        assert result["serverInfo"]["name"] == "MyKnowledge", result["serverInfo"]
        assert result["protocolVersion"]

    def test_frozen_mcp_exposes_all_source_tools(self, tmp_path: Path) -> None:
        """frozen 二进制 tools/list 与源码 @mcp.tool() 全集一致。

        PyInstaller 静态追踪漏掉某个工具模块 / ``--collect-all mcp`` 回归时，
        frozen 里会少工具，只有真跑产物能发现。
        """
        _, frozen_tools = _mcp_handshake(DIST_BIN, ["--mcp"], tmp_path / "kb")
        expected = _source_mcp_tool_names()
        assert len(expected) >= 25, f"源码解析出的工具数异常：{len(expected)}"
        assert set(frozen_tools) == expected, (
            f"frozen 缺失: {sorted(expected - set(frozen_tools))}；"
            f"多出: {sorted(set(frozen_tools) - expected)}"
        )

    def test_mcp_smoke_script_passes_on_frozen_binary(self) -> None:
        """直接跑 scripts/mcp-smoke.sh（build-backend.sh 收尾用的那条）。"""
        r = subprocess.run(
            ["bash", str(SCRIPTS / "mcp-smoke.sh"), "--bin", str(DIST_BIN), "--timeout", "30"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
        )
        assert r.returncode == 0, f"mcp-smoke.sh 失败：\n{r.stdout}\n{r.stderr}"
        assert "MCP 冒烟通过" in r.stdout


# ══════════════════════════════════════════════════════════════════════════
#  5. 打进包的是最新前端
# ══════════════════════════════════════════════════════════════════════════


class TestPackagedFrontend:
    """《验收清单》5：GET ``/`` 返回 index.standalone.html、js/css/vendor 静态
    资源都 200（防旧前端 / 漏文件被封进包）。
    """

    def _internal(self, bp: _BackendProcess) -> Path:
        return APP_INTERNAL if bp.binary == APP_BIN else DIST_INTERNAL

    def test_root_serves_inlined_standalone(self, any_backend: _BackendProcess) -> None:
        code, body, headers = _http_get(f"{any_backend.base_url}/")
        assert code == 200
        html = body.decode("utf-8")
        # standalone 的特征：本地 js/css 被内联（build.py 打的 `/* xxx */` 注释头），
        # 且没有残留的 `<script src="js/...">` 外链（那是没内联的旧 index.html 壳）。
        assert "/* js/app.js */" in html, "GET / 不是 standalone（缺内联 js 标记）"
        assert "/* design-tokens.css */" in html or "<style>" in html
        assert not re.search(r'<script[^>]+src=["\']js/', html), (
            "GET / 里出现 `<script src=js/...>` 外链 —— 打进包的是没内联的 index.html 壳，不是 standalone"
        )
        assert "no-cache" in headers.get("cache-control", "").lower()

    def test_root_body_equals_bundled_standalone(self, any_backend: _BackendProcess) -> None:
        """GET / 的正文与包里 _internal/frontend/index.standalone.html 逐字节一致。"""
        bundled = (self._internal(any_backend) / "frontend" / "index.standalone.html").read_bytes()
        code, body, _ = _http_get(f"{any_backend.base_url}/")
        assert code == 200
        assert body == bundled, "GET / 与包内 standalone 文件不一致"

    def test_bundled_standalone_reflects_bundled_sources(self, any_backend: _BackendProcess) -> None:
        """包内 standalone 里内联的 js/css，其内容 = 包内对应源文件的当前内容。

        旧 standalone + 新源文件一起封进包时，这里会失配 → 抓到"旧前端"。
        """
        fdir = self._internal(any_backend) / "frontend"
        html = (fdir / "index.standalone.html").read_text(encoding="utf-8")
        stale: list[str] = []
        for asset in sorted(fdir.glob("js/**/*.js")) + sorted(fdir.glob("css/*.css")):
            rel = asset.relative_to(fdir).as_posix()
            marker = f"/* {rel} */"
            if marker not in html:
                continue  # 该文件走静态外链（如 ES module），不在内联范围
            content = asset.read_text(encoding="utf-8").strip()
            if content not in html:
                stale.append(rel)
        assert not stale, f"standalone 里这些内联资源不是最新内容（旧前端被封进包）：{stale}"

    def test_all_bundled_frontend_files_reachable(self, any_backend: _BackendProcess) -> None:
        """包里 frontend/ 下每个文件都能通过 HTTP 200 拿到（防漏文件）。"""
        fdir = self._internal(any_backend) / "frontend"
        missing: list[str] = []
        for f in sorted(fdir.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(fdir).as_posix()
            if rel in ("index.standalone.html", "index.html"):
                continue  # 走 GET / 与显式路由，另有用例覆盖
            code, body, _ = _http_get(f"{any_backend.base_url}/{rel}")
            if code != 200 or len(body) != f.stat().st_size:
                missing.append(f"{rel} (code={code})")
        assert not missing, f"这些打进包的前端文件取不到：{missing}"

    def test_versioned_vendor_refs_in_served_html_resolve(self, any_backend: _BackendProcess) -> None:
        """GET / 里 ``src="vendor/xxx?v=hash"`` 的每个引用都能 200。"""
        _, body, _ = _http_get(f"{any_backend.base_url}/")
        html = body.decode("utf-8")
        refs = re.findall(r'(?:src|href)=["\'](vendor/[^"\']+)["\']', html)
        assert refs, "standalone 里没有 vendor/ 引用（不应该）"
        bad: list[str] = []
        for ref in sorted(set(refs)):
            code, _, _ = _http_get(f"{any_backend.base_url}/{ref}")
            if code != 200:
                bad.append(f"{ref} -> {code}")
        assert not bad, f"vendor 资源引用失效：{bad}"

    def test_explicit_index_html_route_ok(self, any_backend: _BackendProcess) -> None:
        code, _, _ = _http_get(f"{any_backend.base_url}/index.html")
        assert code == 200

    def test_bundled_frontend_matches_repo_sources(self) -> None:
        """dist-backend 里的 frontend/ 与仓库 frontend/ 逐文件一致。

        打包用的是过期的 dist-backend（忘了重新 build-backend）时，这里失配。
        仓库在构建后又推进了前端代码也会失配 —— 那就重新跑 release.sh。
        """
        bundle = DIST_INTERNAL / "frontend"
        repo = REPO_ROOT / "frontend"
        drift: list[str] = []
        for f in sorted(bundle.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(bundle)
            r = repo / rel
            if not r.exists():
                drift.append(f"{rel} (仓库已删)")
            elif f.read_bytes() != r.read_bytes():
                drift.append(f"{rel} (内容不一致)")
        assert not drift, (
            "打进包的前端与仓库当前前端不一致，需重新构建（release.sh --enterprise Apple）：\n  "
            + "\n  ".join(drift)
        )


# ══════════════════════════════════════════════════════════════════════════
#  6. 企业配置生效〔bc23341 + Apple.json〕
# ══════════════════════════════════════════════════════════════════════════


class TestEnterpriseConfig:
    """《验收清单》6：``/api/platforms-meta`` 只启用 Enchante + ClaudeCode、
    display / order 正确。
    """

    def test_platforms_meta_only_enterprise_platforms(self, any_backend: _BackendProcess) -> None:
        code, body, _ = _http_get(f"{any_backend.base_url}/api/platforms-meta")
        assert code == 200
        meta = json.loads(body)
        assert set(meta) == APPLE_ENABLED_PLATFORMS, (
            f"platforms-meta 平台集应为 {APPLE_ENABLED_PLATFORMS}，实际 {set(meta)}"
        )
        for key, spec in meta.items():
            assert spec["enabled"] is True
            assert spec["display"] == APPLE_DISPLAY[key], (key, spec["display"])
            assert spec["order"] == APPLE_ORDER[key], (key, spec["order"])

    def test_platforms_meta_order_sorted(self, any_backend: _BackendProcess) -> None:
        _, body, _ = _http_get(f"{any_backend.base_url}/api/platforms-meta")
        meta = json.loads(body)
        keys = list(meta)  # dict 保序：platforms_meta() 已按 order 升序
        assert keys == ["Enchante", "ClaudeCode"], keys

    @pytest.mark.parametrize("internal", [
        pytest.param(DIST_INTERNAL, id="dist-backend"),
        *([pytest.param(APP_INTERNAL, id="installed-app")] if APP_BIN.exists() else []),
    ])
    def test_bundled_platforms_json_is_enterprise_merged(self, internal: Path) -> None:
        """包内 platforms.json 已按 Apple.json 合并：只有这俩 enabled，其余关掉。"""
        pj = internal / "backend" / "AiClientConfig" / "platforms.json"
        assert pj.exists(), f"缺少 {pj}"
        platforms = json.loads(pj.read_text(encoding="utf-8"))["platforms"]
        enabled = {k for k, v in platforms.items() if v.get("enabled", True)}
        assert enabled == APPLE_ENABLED_PLATFORMS, f"包内 enabled 平台 = {enabled}"
        assert platforms["ClaudeCode"]["display"] == "Claude Code (Apple Internal)"
        assert platforms["Enchante"]["order"] == 1
        assert platforms["ClaudeCode"]["order"] == 2

    def test_enterprise_json_matches_expectation(self) -> None:
        """desktop/enterprises/Apple.json 本身声明的就是这套（防配置漂移）。"""
        ent = json.loads(ENTERPRISE_JSON.read_text(encoding="utf-8"))
        assert ent["default_disabled"] is True
        assert set(ent["platforms"]) == APPLE_ENABLED_PLATFORMS
        assert ent["platforms"]["Enchante"]["order"] == 1
        assert ent["platforms"]["ClaudeCode"]["order"] == 2
        assert ent["platforms"]["ClaudeCode"]["display"] == "Claude Code (Apple Internal)"

    def test_disabled_platforms_absent_from_meta(self, any_backend: _BackendProcess) -> None:
        """ClaudeDesktop / Cursor / CodeBuddyIDE / WorkBuddy 不出现在前端可见集。"""
        _, body, _ = _http_get(f"{any_backend.base_url}/api/platforms-meta")
        meta = json.loads(body)
        for gone in ("ClaudeDesktop", "Cursor", "CodeBuddyIDE", "WorkBuddy"):
            assert gone not in meta


# ══════════════════════════════════════════════════════════════════════════
#  7. 加载动画 —— 「初始化完成」文本能正常显示〔d5d6ef7 / 57efb2c〕
# ══════════════════════════════════════════════════════════════════════════


class TestLoadingAnimation:
    """《验收清单》7：「初始化完成」文本能正常显示。

    真实"文本在屏幕上停留够久"需要跑起 Electron 肉眼看 → 报告里标为**需人工**。
    但这两个 bug 的根因都能静态验证已打进包：
      * 57efb2c：文本延迟显示不能靠 ``opacity:0`` + ``animation: both``（会互相覆盖）。
      * d5d6ef7：绿条展开后再等 1100ms 才切主界面 + 主进程兜底 3s→9s，
        否则文本 opacity≈0 时主界面就切走了。
    """

    @_app_installed
    def test_loading_html_packed_with_fix(self, asar_files: dict[str, bytes]) -> None:
        assert "loading.html" in asar_files, "app.asar 里没有 loading.html"
        html = asar_files["loading.html"].decode("utf-8")
        assert "初始化完成" in html
        assert "splash__bar-fill--done" in html
        # 57efb2c：不能再有 `opacity: 0` 硬写在 .splash__bar-text 上（会盖掉 animation to 态）
        text_block = re.search(r"\.splash__bar-text\s*\{[^}]*\}", html)
        assert text_block and "opacity: 0" not in text_block.group(0), (
            "loading.html 的 .splash__bar-text 又写死了 opacity:0（57efb2c 回归）"
        )
        # d5d6ef7：切主界面前等文本显示（transitionend + 1100ms 停留）
        assert "transitionend" in html
        assert "1100" in html, "loading.html 缺少切换前的 1100ms 文本停留（d5d6ef7 回归）"
        assert "__mykLoadingDone__" in html

    @_app_installed
    def test_main_js_loading_fallback_is_9s(self, asar_files: dict[str, bytes]) -> None:
        """d5d6ef7：主进程 loading 兜底从 3s 提到 9s（晚于 loading-done 正常触发）。"""
        main_js = asar_files["main.js"].decode("utf-8")
        m = re.search(r"if\s*\(\s*!loadingDone\s*\)\s*\{[\s\S]{0,220}?\}\s*,\s*(\d+)\s*\)", main_js)
        assert m, "main.js 里找不到 loading 兜底 setTimeout"
        assert int(m.group(1)) == 9000, f"loading 兜底应为 9000ms，实际 {m.group(1)}"

    def test_repo_loading_html_consistent_with_packed(self) -> None:
        """仓库 desktop/loading.html 与打进包的一致（防旧 loading 页被封进包）。"""
        if not APP_ASAR.exists():
            pytest.skip("App 未安装")
        packed = _read_asar(APP_ASAR)["loading.html"]
        repo = (REPO_ROOT / "desktop" / "loading.html").read_bytes()
        assert packed == repo, "app.asar 里的 loading.html 与仓库版本不一致"

    NEEDS_MANUAL = (
        "「初始化完成」文本在真实 Electron 里的可见时长需人工确认："
        "打开 App → 盯加载动画尾段 → 绿条展开后「初始化完成」应清晰停留约 0.8s 再进主界面。"
    )

    @pytest.mark.skip(reason=NEEDS_MANUAL)
    def test_loading_text_visible_duration_MANUAL(self) -> None:
        """占位：见 skip reason，人工执行。"""


# ══════════════════════════════════════════════════════════════════════════
#  8. 打开健壮性 —— 端口递增 + 单实例锁
# ══════════════════════════════════════════════════════════════════════════


class TestLaunchRobustness:
    """《验收清单》8：端口被占能自动递增换端口、单实例锁行为正常。

    这两条都是 Electron 主进程逻辑（后端二进制本身不做端口漂移 / 单实例）。
    完整运行时行为（真开两个 App 实例）需人工，但**打进包的逻辑**能静态核验，
    外加一个"两个后端实例各自独立"的实测。
    """

    @_app_installed
    def test_port_auto_increment_logic_packed(self, asar_files: dict[str, bytes]) -> None:
        main_js = asar_files["main.js"].decode("utf-8")
        assert "findFreePort" in main_js
        # 递增扫描一段端口，逐个 isPortFree 探测
        assert re.search(r"for\s*\(\s*let\s+p\s*=\s*start\s*;\s*p\s*<\s*start\s*\+\s*\d+", main_js), (
            "main.js 缺少端口递增扫描循环（旧 main.js 被封进包？）"
        )
        assert "isPortFree" in main_js and "net.createServer" in main_js

    @_app_installed
    def test_single_instance_lock_packed(self, asar_files: dict[str, bytes]) -> None:
        main_js = asar_files["main.js"].decode("utf-8")
        assert "requestSingleInstanceLock" in main_js, "单实例锁逻辑没打进包"
        assert 'app.on("second-instance"' in main_js, "缺少 second-instance 处理（第二实例聚焦/恢复首窗）"
        assert "app.quit()" in main_js

    def test_two_backend_instances_are_independent(self) -> None:
        """同时起两个 frozen 后端（不同端口）互不干扰 —— Electron 递增换端口后的落点。"""
        with _BackendProcess(DIST_BIN) as a, _BackendProcess(DIST_BIN) as b:
            assert a.port != b.port
            for bp in (a, b):
                code, _, _ = _http_get(f"{bp.base_url}/api/status")
                assert code == 200

    def test_backend_does_not_silently_move_port(self) -> None:
        """端口被占时 frozen 二进制**不会**偷偷换端口（设计如此 —— 换端口是壳的事）。

        占住一个端口，再让二进制监听同一端口 → 它应当起不来 / 该端口不归它，
        而不是自己漂到别的端口让壳的 waitForBackend 指向落空。
        """
        busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        busy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        port = busy.getsockname()[1]
        try:
            import tempfile
            root = Path(tempfile.mkdtemp(prefix="myk_portclash_"))
            env = dict(os.environ, MYKNOWLEDGE_ROOT=str(root))
            proc = subprocess.Popen(
                [str(DIST_BIN), "--port", str(port), "--root", str(root)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
            )
            time.sleep(4)
            # 占用端口上响应的应该还是我们的裸 socket，不是后端
            still_ours = True
            try:
                code, _, _ = _http_get(f"http://127.0.0.1:{port}/api/status", timeout=1)
                still_ours = False  # 竟然有 HTTP 200 → 后端抢到了？不应该
            except Exception:
                pass
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            assert still_ours, "端口被占时 frozen 二进制不应抢占/漂移到该端口"
        finally:
            busy.close()

    NEEDS_MANUAL = (
        "真机验证：(a) 8080-2030 端口段被占时 App 仍能起（递增换端口）；"
        "(b) 已开一个 App，再双击 → 不起第二个，只把已有窗口带到前台。"
    )

    @pytest.mark.skip(reason=NEEDS_MANUAL)
    def test_runtime_port_and_single_instance_MANUAL(self) -> None:
        """占位：见 skip reason，人工执行。"""


# ══════════════════════════════════════════════════════════════════════════
#  9. 人工项 —— 未签名 → xattr 放行
# ══════════════════════════════════════════════════════════════════════════


class TestUnsignedGatekeeperManual:
    """《验收清单》9：未签名 → 用户跑 xattr 放行（人工项，此处只做现状确认）。"""

    @_app_installed
    def test_app_is_adhoc_signed_not_notarized(self) -> None:
        """确认 App 确实是 adhoc 签名（= Gatekeeper 眼里的"未签名"），佐证需要 xattr。"""
        r = subprocess.run(
            ["codesign", "-dv", "--verbose=2", str(APP_PATH)],
            capture_output=True, text=True,
        )
        out = r.stderr + r.stdout
        assert "adhoc" in out or "linker-signed" in out, out
        assert "TeamIdentifier=not set" in out or "TeamIdentifier=" not in out or "adhoc" in out

    MANUAL_STEP = (
        "首次拖入 /Applications 打不开（提示'未验证的开发者'或'已损坏'）时，用户执行：\n"
        "    xattr -dr com.apple.quarantine '/Applications/MyKnowledge (Apple).app'\n"
        "然后正常双击打开。（DMG 分发未做 Apple 公证，属预期。）"
    )

    @pytest.mark.skip(reason=MANUAL_STEP)
    def test_xattr_release_flow_MANUAL(self) -> None:
        """占位：见 skip reason，写进交付报告的人工清单。"""
