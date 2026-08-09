"""编辑切换测试 fixtures（pytest 自动加载）

复用现有 8080 后端（不新起进程）；测试文档隔离创建/清理。
"""
import http.server
import json
import socketserver
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
API_BASE = "http://127.0.0.1:8080"

PROJ = "projects/MyKnowledge 项目知识管理平台"
TRAIN = "projects/Training 人员培训"
DOC_MAIN = f"{PROJ}/common-knowledge/test-edit-auto-main.md"
DOC_SAME = f"{PROJ}/common-knowledge/test-edit-auto-same.md"
DOC_TARGET = f"{TRAIN}/common-knowledge/test-edit-auto-target.md"
NEW_TITLE = "test-edit-auto-renamed"


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{API_BASE}{path}", method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def backend_doc(path):
    st, d = api("GET", f"/api/document/{urllib.parse.quote(path, safe='/')}")
    return (st, d) if st == 200 else (st, None)


@pytest.fixture(scope="module")
def backend_running():
    """复用现有 8080 后端；无后端则跳过"""
    try:
        urllib.request.urlopen(f"{API_BASE}/api/lock", timeout=3)
    except Exception:
        pytest.skip("需要后端在 8080 运行（myknowledge serve --root .myknowledge_test）")


@pytest.fixture(scope="module")
def static_server():
    with socketserver.TCPServer(("127.0.0.1", 0),
                                lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(FRONTEND), **kw)) as httpd:
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{port}/index.standalone.html"
        httpd.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            try:
                b = p.chromium.launch(headless=True)
            except Exception as e:
                pytest.skip(f"Browser unavailable: {e}")
        yield b
        b.close()


@pytest.fixture
def test_docs(backend_running):
    """每个测试独立创建/清理测试文档（隔离：S3/S4e rename 会改路径，不能跨测试复用）"""
    docs = {
        DOC_MAIN: ("# Auto Main 文档\n\n主文档正文段落。\n\n引用 [Target](ref:" + DOC_TARGET + ")", "主文档摘要"),
        DOC_SAME: ("# Auto Same 文档\n\n同项目目标文档正文。", "同项目摘要"),
        DOC_TARGET: ("# Auto Target 文档\n\n跨项目目标文档正文。\n\n引用 [Main](ref:" + DOC_MAIN + ")", "跨项目摘要"),
    }
    for path, (content, summary) in docs.items():
        st, _ = backend_doc(path)
        if st != 200:
            api("POST", f"/api/document/{urllib.parse.quote(path, safe='/')}",
                {"content": content, "summary": summary})
    yield docs
    # 清理：删除（含 rename 后的新名）
    for path in list(docs) + [f"{PROJ}/common-knowledge/{NEW_TITLE}.md"]:
        api("DELETE", f"/api/document/{urllib.parse.quote(path, safe='/')}")
    api("POST", "/api/trash/empty")


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.add_init_script("""
      window.__toasts = [];
      new MutationObserver(() => {
        document.querySelectorAll('.toast-container .toast').forEach(t => {
          if (!t.dataset.captured) { t.dataset.captured = '1'; window.__toasts.push(t.textContent); }
        });
      }).observe(document.documentElement, {childList: true, subtree: true});
    """)
    yield pg
    ctx.close()
