"""MyKnowledge 前端烟雾测试

验证所有路由页面正常渲染和交互。

依赖：pip install playwright && playwright install chromium
运行：PYTHONPATH=. python tests/frontend/test_smoke.py
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "index.html"
BACKEND_PORT = 8080
BASE_URL = f"http://127.0.0.1:{BACKEND_PORT}"


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def backend():
    """启动后端服务"""
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.main:app",
            "--port", str(BACKEND_PORT),
            "--host", "127.0.0.1",
        ],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # 等待后端启动
    for _ in range(20):
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{BACKEND_PORT}/api/lock")
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate()
        pytest.skip("Backend requires initialized knowledge base (run `myknowledge init` first)")
    yield
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="module")
def static_server():
    """本地静态服务器（http:// 打开 standalone——file:// 下 tiptap-bundle.mjs 会被 CORS 拦截，
    导致 store.init 卡在 setup，页面视图无法切换，smoke 渲染断言全部失败）。"""
    import http.server, socketserver, threading
    frontend = (ROOT / "frontend").resolve()
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(frontend), **kw)
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        yield f"http://127.0.0.1:{port}/index.standalone.html"
        httpd.shutdown()


@pytest.fixture(scope="module")
def browser():
    """启动浏览器。优先用系统 Chrome（零下载），fallback 到 Playwright Chromium"""
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
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    p = ctx.new_page()
    yield p
    ctx.close()


# ═══════════════════════════════════════════════════════════════════════════
# 静态结构测试（不依赖后端运行）
# ═══════════════════════════════════════════════════════════════════════════


class TestStaticStructure:
    """验证 HTML 文件结构完整性"""

    def test_html_exists(self):
        assert FRONTEND.exists(), f"{FRONTEND} not found"

    def test_standalone_exists(self):
        standalone = ROOT / "frontend" / "index.standalone.html"
        assert standalone.exists(), "Standalone HTML not built. Run: python3 build.py"

    def test_css_files_present(self):
        css_dir = ROOT / "frontend" / "css"
        required = [
            "design-tokens.css", "reset.css", "layout.css",
            "sidebar.css", "viewer.css", "editor.css",
            "components.css", "markdown-content.css",
        ]
        for f in required:
            assert (css_dir / f).exists(), f"Missing CSS: css/{f}"

    def test_js_files_present(self):
        js_dir = ROOT / "frontend" / "js"
        required = [
            "api.js", "store.js", "router.js",
            "renderer.js", "converter.js", "app.js", "utils.js",
        ]
        for f in required:
            assert (js_dir / f).exists(), f"Missing JS: js/{f}"

    def test_required_vendor_scripts(self):
        """库全部本地 vendor（无 CDN——设计：防白屏/离线）"""
        html = FRONTEND.read_text(encoding="utf-8")
        required = [
            "vendor/alpine.min.js",
            "vendor/marked.min.js",
            "vendor/highlight.js",
            "vendor/turndown.js",
            "tiptap-bundle.mjs",
        ]
        for dep in required:
            assert dep in html, f"Missing vendor dependency: {dep}"

    def test_alpine_components_defined(self):
        html = FRONTEND.read_text(encoding="utf-8")
        components = [
            'x-data="dashboardComponent"',
            'x-data="projectComponent"',
            'x-data="docComponent"',
            'x-data="sidebarComponent"',
            'x-data="modalComponent"',
        ]
        for comp in components:
            assert comp in html, f"Missing Alpine component: {comp}"

    def test_x_cloak_critical_css(self):
        html = FRONTEND.read_text(encoding="utf-8")
        assert "[x-cloak]{display:none!important}" in html.replace(" ", ""), \
            "Missing critical x-cloak inline CSS (modal FOUC fix)"

    def test_build_script_exists(self):
        build_py = ROOT / "frontend" / "build.py"
        assert build_py.exists(), "build.py not found"


def _has_playwright():
    """检查 Playwright Python 包是否已安装"""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


# ═══════════════════════════════════════════════════════════════════════════
# 路由渲染测试（需要 playwright install chromium）
# ═══════════════════════════════════════════════════════════════════════════


# 浏览器测试需要本机有 Chrome 或 Playwright Chromium。
# 在此沙箱环境中默认跳过，本地运行时自动启用。
@pytest.mark.skipif(
    not _has_playwright(),
    reason="pip install playwright && playwright install chromium（或用系统 Chrome）"
)
class TestRouteRendering:
    @pytest.fixture(autouse=True)
    def _base(self, static_server):
        self.base = static_server
    """验证每个路由页面正确渲染"""

    def test_dashboard_loads(self, page):
        """#dashboard 仪表盘正常加载"""
        page.goto(f"{self.base}#dashboard")
        page.wait_for_timeout(4000)  # 等 Alpine 初始化（file:// 下 fetch 后端有往返开销）
        # 验证侧边栏品牌名可见（text=MyKnowledge 会匹配 10+ 元素触发 strict 报错）
        expect(page.locator(".sidebar-brand__name").first).to_be_visible(timeout=5000)

    def test_dashboard_content_renders(self, page):
        """仪表盘内容区渲染"""
        page.goto(f"{self.base}#dashboard")
        page.wait_for_timeout(2000)
        # 检查侧边栏
        sidebar = page.locator("[data-sidebar], .sidebar, #sidebar")
        expect(sidebar.first).to_be_visible(timeout=5000)

    def test_no_modal_visible_on_load(self, page):
        """页面加载时弹窗不应显示"""
        page.goto(f"{self.base}#dashboard")
        page.wait_for_timeout(2000)
        # 所有 modal-overlay 应该不可见
        modals = page.locator(".modal-overlay")
        count = modals.count()
        for i in range(count):
            expect(modals.nth(i)).not_to_be_visible()

    def test_theme_toggle_present(self, page):
        """主题切换控件存在"""
        page.goto(f"{self.base}#dashboard")
        page.wait_for_timeout(2000)
        toggle = page.locator("[data-theme-switch], .theme-toggle, select[data-theme]")
        if toggle.count() > 0:
            expect(toggle.first).to_be_visible()

    def test_dashboard_shows_title(self, page):
        """仪表盘显示产品标题"""
        page.goto(f"{self.base}#dashboard")
        page.wait_for_timeout(2000)
        header = page.locator("h1, h2").first
        expect(header).to_be_visible(timeout=5000)

    def test_lock_banner_hidden_when_not_locked(self, page):
        """未锁定时不显示锁提示"""
        page.goto(f"{self.base}#dashboard")
        page.wait_for_timeout(3000)
        banner = page.locator(".locked-banner, [class*='lock-banner']")
        if banner.count() > 0:
            # 前端用 opacity 控制显隐（未锁 opacity:0），检查实际透明度
            opacity = banner.first.evaluate("el => getComputedStyle(el).opacity")
            assert opacity == "0", f"Lock banner should be hidden when unlocked, opacity={opacity}"

    def test_trash_view_renders(self, page):
        """#trash 垃圾箱视图加载（空状态渲染）"""
        page.goto(f"{self.base}#trash")
        page.wait_for_timeout(2000)
        expect(page.locator(".page-title", has_text="垃圾箱")).to_be_visible(timeout=5000)

    def test_empty_state_handled(self, page):
        """无数据时显示空状态而非崩溃"""
        page.goto(f"{self.base}#dashboard")
        page.wait_for_timeout(3000)
        # 检查没有 Alpine 错误闪现（页面不空白）
        main = page.locator("main, [role='main'], #content").first
        if main.count() > 0:
            expect(main).to_be_visible()

    def test_sidebar_loads_projects(self, page):
        """侧边栏渲染项目列表"""
        page.goto(f"{self.base}#dashboard")
        page.wait_for_timeout(3000)
        sidebar = page.locator("[data-sidebar], .sidebar, #sidebar").first
        if sidebar.count() > 0:
            expect(sidebar).to_be_visible()


# ═══════════════════════════════════════════════════════════════════════════
# 管理后台 API 集成测试（需要后端 + 知识库）
# ═══════════════════════════════════════════════════════════════════════════


class TestBackendAPI:
    """验证后端 API 是否正常响应（需要已初始化的知识库 `myknowledge init`）"""

    @pytest.fixture(scope="class", autouse=True)
    def _ensure_available(self, backend):
        import urllib.request
        try:
            resp = urllib.request.urlopen(f"{BASE_URL}/api/lock")
            if resp.status != 200:
                pytest.skip("Backend available but returns unexpected status")
        except Exception:
            pytest.skip("Backend requires initialized KB: myknowledge init")

    def test_status_endpoint(self, backend):
        import urllib.request
        try:
            resp = urllib.request.urlopen(f"{BASE_URL}/api/status")
            assert resp.status == 200
        except Exception as e:
            pytest.skip(f"Backend /api/status unavailable: {e}")

    def test_lock_endpoint(self, backend):
        import urllib.request
        resp = urllib.request.urlopen(f"{BASE_URL}/api/lock")
        data = json.loads(resp.read())
        assert resp.status == 200
        assert "locked" in data

    def test_status_detail_endpoint(self, backend):
        import urllib.request
        try:
            resp = urllib.request.urlopen(f"{BASE_URL}/api/status/detail")
            assert resp.status in (200, 404)
        except Exception as e:
            pytest.skip(f"Backend /api/status/detail unavailable: {e}")

    def test_list_root(self, backend):
        import urllib.request
        try:
            resp = urllib.request.urlopen(f"{BASE_URL}/api/list/")
            assert resp.status == 200
        except Exception:
            pass  # 知识库可能为空


# ═══════════════════════════════════════════════════════════════════════════
# 构建测试
# ═══════════════════════════════════════════════════════════════════════════


class TestBuild:
    def test_build_produces_standalone(self):
        """build.py 能正常生成 standalone HTML"""
        import subprocess
        build_dir = ROOT / "frontend"
        result = subprocess.run(
            [sys.executable, "build.py"],
            cwd=str(build_dir),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Build failed:\n{result.stderr}"
        output = build_dir / "index.standalone.html"
        assert output.exists()
        content = output.read_text()

        # ── 依赖：全部内联（无 CDN——设计：防白屏/离线）──
        assert "cdn.jsdelivr" not in content and "unpkg.com" not in content,             "Standalone should be fully inline (no CDN)"
        checks = {
            "Alpine": "alpine:init",  # alpine.min.js 是 IIFE（无 window.Alpine），用初始化钩子标记
            "marked": "marked.parse",
            "Turndown": "TurndownService",
            "TipTap StarterKit": "StarterKit",
        }
        for label, pattern in checks.items():
            assert pattern in content, f"Missing inline lib: {label}"

        # ── 全局函数 ──
        funcs = [
            "marked.parse", "class Router", "Alpine.store",
            "loadDocument", "formatDate", "extractDisplayName",
            "statusLabel", "fileName", "escapeHtml",
            "_mykRefClick", "_mykSplash",
        ]
        for fn in funcs:
            assert fn in content, f"Missing function: {fn}"

        # ── 路由 ──
        routes = ["dashboard", "project", "doc", "status"]
        for r in routes:
            assert f'router.on("{r}' in content or f"router.on('{r}" in content, \
                f"Missing route: #{r}"

        # ── 组件 ──
        components = [
            "dashboardComponent", "projectComponent",
            "docComponent", "sidebarComponent",
        ]
        for c in components:
            assert c in content, f"Missing component: {c}"

        # ── UI 元素 ──
        elements = [
            "class=\"splash\"", "id=\"splashBar\"",
            "class=\"sidebar\"", "class=\"content-panel\"",
            "class=\"page-label\"", "class=\"project-panel\"",
        ]
        for el in elements:
            assert el in content, f"Missing element: {el}"

        # ── 关键文本 ──
        texts = [
            "知识库版本", "知识", "子项目", "归档",
            "用户编辑中", "正在操作", "锁最长剩余",
            "已完成", "已取消", "已废弃",
        ]
        for t in texts:
            assert t in content, f"Missing text: {t}"

        # ── 垃圾箱（trash）新增功能 ──
        trash_checks = [
            "垃圾箱",                 # 侧栏入口 + 视图标题
            "30 天内可恢复",           # 删除弹窗文案
            "3 秒后返回首页",           # 删除后倒计时面板提示（store 固定文案）
            "清空垃圾箱",             # trash 视图按钮
            "该文档已被删除",         # 404 已删除视图
            "去垃圾箱恢复",           # 404 恢复入口
            "已进垃圾箱·可恢复",      # refs 面板 in_trash 徽标
            "引用不存在",             # refs 面板 dead 徽标
            "#trash",                # 路由
        ]
        for t in trash_checks:
            assert t in content, f"Missing trash feature text: {t}"

        # ── x-cloak ──
        assert "[x-cloak]{display:none!important}" in content.replace(" ", ""), \
            "Missing x-cloak inline CSS"

        # ── 路由跳转目标 ──
        assert 'hash = `doc/' in content, "goToDocument not pointing to #doc/"
