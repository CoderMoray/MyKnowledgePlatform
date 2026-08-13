"""h11 共享冲突回归监测（HTTP/1.1 keep-alive + 分块传输）。

背景（见 ADR：projects/MyKnowledge 项目知识管理平台/common-knowledge/fastapi依赖升级架构决策.md
「⚠️ 显式风险登记：h11 共享冲突」一节）：

引入 httpx2 后环境并存两套 HTTP 底层，h11 版本要求互斥：
  - httpx  → httpcore(1.0.5)  → 要求 h11<0.15,>=0.13
  - httpx2 → httpcore2(2.10)  → 要求 h11>=0.16
h11 是 HTTP/1.1 协议实现，httpcore 与 h11 的版本耦合非随意——当前真实请求路径未触发，
不代表所有路径（keep-alive / 分块传输 / 异常处理）都安全。

本文件的职责【监测，不是解决冲突】：
- 用真实 HTTP/1.1 网络栈（httpx 真实客户端连 uvicorn 真实 server，走 httpcore→h11）
  与 TestClient（走 httpx2→httpcore2→h11）两条路径覆盖 keep-alive 与分块/大响应体。
- 固定当前基线：若未来升级 h11 / httpcore / httpx 任一库，或某路径触发冲突，
  本文件跑红即暴露——届时须优先排查 h11 共享冲突（见 ADR）。
- 不 pin h11、不卸载 httpx2（架构师已定决策，保留 httpx2 正视冲突）。

注意：本测试起真实 uvicorn server，加载 websockets 库时会产生 `websockets.legacy`
弃用警告——那是 uvicorn/websockets 库自身的启动噪音，与 h11 冲突无关。为不污染全量
strict 门禁（`-W error::DeprecationWarning`），抑制这两类已知噪音警告。
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

from backend.storage import Storage

# 抑制 uvicorn 起真实 server 时 websockets 库的启动弃用警告（库噪音，非 h11 冲突）
pytestmark = pytest.mark.filterwarnings(
    "ignore:websockets.legacy is deprecated:DeprecationWarning",
    "ignore:websockets.server.WebSocketServerProtocol is deprecated:DeprecationWarning",
)


# ══════════════════════════════════════════════════════════════
#  helpers
# ══════════════════════════════════════════════════════════════

def _free_port() -> int:
    """Return an available TCP port on 127.0.0.1 (bind-and-release)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


_CHUNKED_PROBE_PATH = "/api/_h11_chunked_probe"


def _mount_chunked_probe() -> None:
    """Insert a streaming chunked endpoint into backend.main.app.

    Must insert BEFORE the trailing StaticFiles Mount (frontend, path=""),
    otherwise the catch-all Mount matches first and 404s. FastAPI's ``@app.get``
    appends to the route list end (after the Mount), so use ``routes.insert``.
    """
    import backend.main as _bm
    from fastapi.responses import StreamingResponse
    from fastapi.routing import APIRoute

    def _probe():
        def _gen():
            for i in range(100):
                yield f"chunk-{i}-" + ("x" * 500)
        return StreamingResponse(_gen(), media_type="text/plain")

    route = APIRoute(_CHUNKED_PROBE_PATH, _probe, methods=["GET"])
    routes = _bm.app.router.routes
    mount_idx = next(
        (i for i, r in enumerate(routes) if type(r).__name__ == "Mount"),
        len(routes),
    )
    routes.insert(mount_idx, route)


def _unmount_chunked_probe() -> None:
    import backend.main as _bm
    _bm.app.router.routes = [
        r for r in _bm.app.router.routes
        if getattr(r, "path", None) != _CHUNKED_PROBE_PATH
    ]


def _make_storage(tmp_kb_root: Path, gen) -> tuple[Storage, object]:
    storage = Storage(kb_root=tmp_kb_root)
    return storage, gen


# ══════════════════════════════════════════════════════════════
#  fixtures
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def _patched_backend(tmp_kb_root: Path, monkeypatch):
    """Patch backend.main.get_storage to a temp KB + return (storage, app)."""
    import backend.main
    from backend.readme_generator import ReadmeGenerator

    storage = Storage(kb_root=tmp_kb_root)
    template = tmp_kb_root / "_templates" / "readme.md"
    if not template.exists():
        template.parent.mkdir(parents=True, exist_ok=True)
        template.write_text("# {name}\n\n{summary}")
    gen = ReadmeGenerator(storage=storage, template_path=template)

    def _test_storage():
        return storage, gen

    orig = backend.main.get_storage
    monkeypatch.setattr(backend.main, "get_storage", _test_storage)
    yield storage


@pytest.fixture
def long_doc(_patched_backend: Storage) -> str:
    """A long document to exercise chunked / large-body transfer."""
    storage = _patched_backend
    # ~200KB body so uvicorn streams it in multiple writes (chunked path)
    body = "# 长文档\n\n" + ("h11 分块传输监测内容行\n" * 20000)
    storage.write_document("common-knowledge/long.md", {"summary": "long"}, body, auto_id=False)
    return body


@pytest.fixture
def real_http_client(_patched_backend, long_doc):
    """Run a real uvicorn server on a free port and return httpx.Client.

    httpx.Client hits a real HTTP/1.1 socket → httpcore → h11, which is the
    network stack whose shared-h11 conflict we monitor.
    """
    import httpx
    import uvicorn
    from backend.main import app

    # 挂一个流式分块端点，必须在 uvicorn 启动前（启动后路由已固定，动态加不生效）
    _mount_chunked_probe()
    try:
        port = _free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        base = f"http://127.0.0.1:{port}"
        client = httpx.Client(base_url=base, timeout=20)
        try:
            # wait until responsive
            for _ in range(200):
                try:
                    r = client.get("/api/version")
                    if r.status_code == 200:
                        break
                except Exception:
                    time.sleep(0.05)
            yield client
        finally:
            client.close()
            server.should_exit = True
            thread.join(timeout=5)
    finally:
        _unmount_chunked_probe()


@pytest.fixture
def test_client(_patched_backend):
    """TestClient(app) — starlette testclient uses httpx2 → httpcore2 → h11."""
    from fastapi.testclient import TestClient
    from backend.main import app

    # 挂流式分块端点（TestClient 每请求实时读 app 路由）
    _mount_chunked_probe()
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        _unmount_chunked_probe()


# ══════════════════════════════════════════════════════════════
#  监测用例（h11 共享冲突）
# ══════════════════════════════════════════════════════════════

class TestH11KeepAlive:
    """HTTP/1.1 keep-alive: repeated requests reuse the connection."""

    def test_real_client_keepalive_repeated_requests(self, real_http_client) -> None:
        """httpx 真实客户端（httpcore→h11）连续多次请求复用连接，全 200。"""
        statuses = [real_http_client.get("/api/version").status_code for _ in range(10)]
        assert statuses == [200] * 10, f"keep-alive 复用连接应全部 200: {statuses}"
        # 响应内容完整可解析
        r = real_http_client.get("/api/version")
        assert "system" in r.json()

    def test_testclient_keepalive_repeated_requests(self, test_client) -> None:
        """TestClient（httpx2→httpcore2→h11）连续多次请求全 200。"""
        statuses = [test_client.get("/api/version").status_code for _ in range(10)]
        assert statuses == [200] * 10, f"keep-alive 复用连接应全部 200: {statuses}"


class TestH11ChunkedLargeBody:
    """HTTP/1.1 分块传输 / 大响应体完整性。"""

    def test_real_client_large_body_integrity(self, real_http_client, long_doc) -> None:
        """httpx 真实客户端读长文档（大响应体走分块），状态码 + 内容完整。"""
        r = real_http_client.get("/api/document/common-knowledge/long.md")
        assert r.status_code == 200
        data = r.json()
        assert data["content"] == long_doc, "大响应体内容完整（分块传输无丢失/截断）"

    def test_testclient_large_body_integrity(self, test_client, long_doc) -> None:
        """TestClient（httpx2 侧）读长文档，状态码 + 内容完整。"""
        r = test_client.get("/api/document/common-knowledge/long.md")
        assert r.status_code == 200
        data = r.json()
        assert data["content"] == long_doc, "大响应体内容完整"

    def test_real_client_chunked_stream(self, real_http_client) -> None:
        """httpx 真实客户端走 StreamingResponse（transfer-encoding: chunked）分块路径。

        分块传输只在响应无 Content-Length（流式输出）时发生，h11 需逐 chunk 聚合。
        验证状态码 + 分块聚合后的内容完整性——这是 h11 分块路径的直接监测。
        """
        r = real_http_client.get("/api/_h11_chunked_probe")
        assert r.status_code == 200
        assert r.headers.get("transfer-encoding", "").lower() == "chunked", \
            "流式响应应走 chunked transfer-encoding"
        expected = "".join(f"chunk-{i}-" + ("x" * 500) for i in range(100))
        assert r.content.decode() == expected, "分块传输聚合后内容完整"

    def test_testclient_chunked_stream(self, test_client) -> None:
        """TestClient（httpx2→httpcore2→h11）分块路径：流式响应聚合完整。"""
        r = test_client.get("/api/_h11_chunked_probe")
        assert r.status_code == 200
        expected = "".join(f"chunk-{i}-" + ("x" * 500) for i in range(100))
        assert r.content.decode() == expected, "分块传输聚合后内容完整"
