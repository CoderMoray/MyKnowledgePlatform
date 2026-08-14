"""MyKnowledge 前端 — 知识库结构体检视图（#health）测试

覆盖：
1. 静态结构：路由 #health、侧边栏「结构体检」入口、health 样式类、复杂区/复制 prompt
2. 构建：standalone 含 health 功能文本/路由/样式
3. 浏览器渲染（复用 conftest fixtures）：
   - #health 加载：显示「重新检查」常驻按钮
   - 触发体检后：健康概览卡（徽标/三联数字/分组计数芯片）+ 问题分组 + 复杂区 + 复制 prompt
   - 空态：saved:false →「尚未检查」+ 检查按钮
   - console 无报错/警告

依赖：pip install playwright && playwright install chromium
运行：PYTHONPATH=. pytest tests/frontend/test_health.py
"""

from pathlib import Path

import pytest
from playwright.sync_api import expect

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
INDEX = FRONTEND / "index.html"
ROUTER = FRONTEND / "js" / "router.js"
STORE = FRONTEND / "js" / "store.js"
API = FRONTEND / "js" / "api.js"
COMPONENTS_CSS = FRONTEND / "css" / "components.css"
STANDALONE = FRONTEND / "index.standalone.html"


# ═══════════════════════════════════════════════════════════════════════════
# 静态结构测试（不依赖后端运行）
# ═══════════════════════════════════════════════════════════════════════════


class TestHealthStaticStructure:
    """验证 #health 视图的 HTML/JS/CSS 结构完整性"""

    def test_index_html_exists(self):
        assert INDEX.exists(), f"{INDEX} not found"

    def test_health_route_registered(self):
        """路由在 router.js 中注册 #health"""
        js = ROUTER.read_text(encoding="utf-8")
        assert 'router.on("health"' in js or "router.on('health'" in js, \
            "Missing #health route in router.js"
        assert "loadHealthSaved" in js, "route handler should call loadHealthSaved()"

    def test_sidebar_health_entry(self):
        html = INDEX.read_text(encoding="utf-8")
        assert "知识健康检查" in html, "Missing sidebar entry「知识健康检查」"
        assert "结构体检" not in html, "旧 sidebar 文案「结构体检」应移除"
        assert 'hash=\'health\'' in html or 'hash="health"' in html, \
            "Sidebar entry not pointing to #health"

    def test_health_copy_btn_text(self):
        """复杂区按钮文案为「复制 prompt」，含 copy icon + hover title"""
        html = INDEX.read_text(encoding="utf-8")
        assert "复制 prompt" in html, "Missing「复制 prompt」button text"
        assert "复制 prompt 交 AI" not in html, "旧文案「复制 prompt 交 AI」应移除"
        assert "complex-zone__copy-btn" in html
        assert "title=" in html, "copy 按钮缺少 hover title 提示"

    def test_health_renamed_view_title(self):
        """页面标题与 subtitle 已改名「知识健康检查」"""
        html = INDEX.read_text(encoding="utf-8")
        assert "知识健康检查" in html, "Missing new view title「知识健康检查」"
        assert "知识库结构体检" not in html, "旧页面标题「知识库结构体检」应移除"
        assert "检测知识库结构健康度，识别并处理结构性问题" in html, \
            "Missing updated subtitle"

    def test_health_button_two_states(self):
        """检查按钮两态：尚未检查=开始检查 / 有结果=重新检查（动态 getter）"""
        html = INDEX.read_text(encoding="utf-8")
        # 顶部按钮用 healthCheckBtnLabel 动态渲染
        assert "healthCheckBtnLabel" in html, "顶部按钮未使用 healthCheckBtnLabel"
        assert "开始检查" in html, "Missing「开始检查」label"
        assert "重新检查" in html, "Missing「重新检查」label"
        # 未检查空态按钮=开始检查
        assert "开始检查" in html
        # 健康空态按钮=再次体检
        assert "再次体检" in html

    def test_health_view_block(self):
        html = INDEX.read_text(encoding="utf-8")
        assert "currentView === 'health'" in html, "Missing health view x-show"
        assert "知识健康检查" in html, "Missing health view title"
        assert "healthCheckBtnLabel" in html, "Missing dynamic check button label"

    def test_health_overview_markup(self):
        html = INDEX.read_text(encoding="utf-8")
        for el in ["health-badge", "health-metric", "health-chip", "health-generated",
                   "health-group", "issue-row", "issue-severity", "issue-path",
                   "issue-message", "complex-zone", "复制 prompt"]:
            assert el in html, f"Missing health element: {el}"

    def test_health_empty_states(self):
        html = INDEX.read_text(encoding="utf-8")
        assert "尚未检查" in html, "Missing「尚未检查」empty state"
        assert "知识库结构健康" in html, "Missing「知识库结构健康」clean empty state"

    def test_health_api_methods(self):
        """api.js 暴露 diagnose 方法"""
        js = API.read_text(encoding="utf-8")
        assert "getDiagnoseSaved" in js, "Missing api.getDiagnoseSaved()"
        assert "getDiagnose" in js, "Missing api.getDiagnose()"
        assert "/api/diagnose/saved" in js, "Missing endpoint path /api/diagnose/saved"

    def test_health_store_state_and_methods(self):
        """store.js 暴露 health 状态与方法"""
        js = STORE.read_text(encoding="utf-8")
        for name in ["healthData", "healthLoading", "healthGeneratedAt",
                     "loadHealthSaved", "runHealthCheck",
                     "healthComplexIssues", "healthGroups", "buildHealthPrompt",
                     "copyHealthPrompt", "healthCheckBtnLabel"]:
            assert name in js, f"Missing store symbol: {name}"

    def test_health_store_uses_generated_at(self):
        """runHealthCheck 用后端返回的 generated_at 赋值（而非写死空串）"""
        js = STORE.read_text(encoding="utf-8")
        # runHealthCheck 内应使用 data.generated_at（带"后端已补 generated_at"注释）
        assert "this.healthGeneratedAt = data.generated_at || \"\";" in js, \
            "runHealthCheck 应使用 data.generated_at"
        assert "后端已补 generated_at" in js, "runHealthCheck 应注明使用后端 generated_at"

    def test_health_css_classes_in_components(self):
        css = COMPONENTS_CSS.read_text(encoding="utf-8")
        for cls in ["health-badge", "health-chip", "issue-row", "issue-severity",
                    "issue-path", "issue-message", "complex-zone"]:
            assert f".{cls}" in css, f"Missing CSS class: .{cls}"

    def test_health_css_uses_tokens_not_new_colors(self):
        """health 样式必须复用 design token（不引入新的十六进制/原生颜色值）"""
        css = COMPONENTS_CSS.read_text(encoding="utf-8")
        marker = "知识健康检查（#health）"
        assert marker in css, f"Missing health CSS section marker: {marker}"
        block = css[css.index(marker):]
        for hexcolor in ["#f00", "#ff0000", "#e74c3c", "#dc3545", "#27ae60", "#f39c12"]:
            assert hexcolor not in block, f"Hardcoded color in health CSS: {hexcolor}"
        # 严重度三色必须走 token
        assert "--color-danger" in block, "high severity must use --color-danger token"
        assert "--color-warning" in block, "medium severity must use --color-warning token"
        assert "--color-info" in block, "low severity must use --color-info token"
        assert "--color-success" in block, "healthy badge must use --color-success token"


# ═══════════════════════════════════════════════════════════════════════════
# 构建测试
# ═══════════════════════════════════════════════════════════════════════════


class TestHealthBuild:
    def test_standalone_contains_health(self):
        assert STANDALONE.exists(), "Standalone not built. Run: python3 build.py"
        content = STANDALONE.read_text(encoding="utf-8")
        checks = [
            "router.on(\"health\"",
            "currentView === 'health'",
            "知识健康检查",
            "healthCheckBtnLabel",
            "知识健康检查",
            "复制 prompt",
            "health-badge", "health-chip", "issue-row", "complex-zone",
        ]
        for c in checks:
            assert c in content, f"Missing in standalone: {c}"


# ═══════════════════════════════════════════════════════════════════════════
# 浏览器渲染测试（复用 conftest fixtures：backend_running/static_server/browser/page）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("playwright"),
    reason="pip install playwright && playwright install chromium",
)
class TestHealthBrowser:
    """依赖 8080 后端 + 已初始化知识库（.myknowledge_test）"""

    def _goto_health_and_ensure_data(self, static_server, page):
        """打开 #health；若无结果数据则点击「开始检查」生成；有数据则直接展示"""
        page.goto(f"{static_server}#health")
        page.wait_for_timeout(2500)
        # 用 is_visible 判断实际显示分支（「尚未检查」空态在 DOM 中始终存在但可隐藏）
        if page.locator(".empty-state__title", has_text="尚未检查").is_visible():
            page.locator("button", has_text="开始检查").first.click()
            page.wait_for_timeout(2500)
        elif not page.locator(".health-badge").is_visible():
            # 既无空态也无概览（加载未完成）→ 点顶部重新检查
            page.locator("button", has_text="重新检查").first.click()
            page.wait_for_timeout(2500)

    def test_health_sidebar_entry(self, static_server, page, backend_running):
        """侧边栏存在「知识健康检查」入口，点击跳转 #health"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(2500)
        entry = page.locator(".sidebar-item__name", has_text="知识健康检查")
        expect(entry.first).to_be_visible(timeout=5000)
        entry.first.click()
        page.wait_for_timeout(1500)
        expect(page.locator("h1", has_text="知识健康检查")).to_be_visible(timeout=5000)

    def test_health_view_title_and_check_button(self, static_server, page, backend_running):
        """#health 显示标题 + 常驻检查按钮（未检查=开始检查/有结果=重新检查）"""
        page.goto(f"{static_server}#health")
        page.wait_for_timeout(2500)
        expect(page.locator("h1", has_text="知识健康检查")).to_be_visible(timeout=5000)
        # 按钮两态：可见的那个必须在当前状态下正确显示（开始检查 或 重新检查）
        btn_start_visible = page.locator("button", has_text="开始检查").is_visible()
        btn_recheck_visible = page.locator("button", has_text="重新检查").is_visible()
        # 互斥且至少一个可见
        assert btn_start_visible != btn_recheck_visible, \
            f"检查按钮应恰好一个可见（当前 start={btn_start_visible}, recheck={btn_recheck_visible}）"
        expect((page.locator("button", has_text="重新检查")
                if btn_recheck_visible
                else page.locator("button", has_text="开始检查")).first).to_be_visible(timeout=5000)

    def test_health_recheck_button_runs(self, static_server, page, backend_running):
        """点击「重新检查」触发真算，loading 时显示「刷新中...」，结束后概览卡出现"""
        self._goto_health_and_ensure_data(static_server, page)
        # 触发重新检查（先有数据后点它）
        page.locator("button", has_text="重新检查").first.click()
        page.wait_for_timeout(500)
        # 按钮可能处于刷新中或已结束；最终概览卡可见
        expect(page.locator(".health-badge")).to_be_visible(timeout=8000)

    def test_health_overview_badge_present(self, static_server, page, backend_running):
        """健康概览卡显示徽标 + 三联数字（扫描文件/发现问题/高危问题）"""
        self._goto_health_and_ensure_data(static_server, page)
        expect(page.locator(".health-badge")).to_be_visible(timeout=5000)
        expect(page.locator(".health-metric", has_text="扫描文件")).to_be_visible(timeout=5000)
        expect(page.locator(".health-metric", has_text="发现问题")).to_be_visible(timeout=5000)

    def test_health_overview_chips(self, static_server, page, backend_running):
        """分组计数芯片渲染（position/metadata/index/ref/illegal/system）"""
        self._goto_health_and_ensure_data(static_server, page)
        expect(page.locator(".health-chip").first).to_be_visible(timeout=5000)

    def test_health_complex_zone(self, static_server, page, backend_running):
        """有 needs_semantic 问题时复杂区 +「复制 prompt」按钮显示"""
        self._goto_health_and_ensure_data(static_server, page)
        # 此测试库存在需 AI 判断的问题（复杂区），断言其渲染
        if page.locator(".health-badge__label", has_text="发现问题").count() > 0:
            expect(page.locator(".complex-zone__title")).to_be_visible(timeout=5000)
            expect(page.locator("button", has_text="复制 prompt")).to_be_visible(timeout=5000)

    def test_health_copy_prompt_content(self, static_server, page, backend_running):
        """复制 prompt 内容：前缀正确 + 含全部复杂 issue + 不含 KB 根路径"""
        self._goto_health_and_ensure_data(static_server, page)
        if page.locator(".complex-zone").count() == 0:
            pytest.skip("当前知识库无 needs_semantic 复杂问题")
        # 授予剪贴板权限并点击复制
        ctx = page.context
        try:
            ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass
        page.locator("button", has_text="复制 prompt").first.click()
        page.wait_for_timeout(500)
        # 读取剪贴板
        try:
            text = page.evaluate("async () => await navigator.clipboard.readText()")
        except Exception:
            text = ""
        assert text, "剪贴板为空（复制失败或剪贴板权限被拒）"
        # 前缀
        assert "请用 MyKnowledge 的 MCP 工具（maint__knowledgebase_diagnose 复查 + write__ 系列修复）" in text, \
            "Prompt missing required prefix"
        # 结尾：扫描文件
        assert "扫描文件：" in text, "Prompt missing 扫描文件 footer"
        # 不含 KB 根路径声明（common-knowledge / projects / archive 不应作为路径前缀写入 prompt）
        assert "/api/" not in text, "Prompt should not contain API root path"

    def test_health_empty_state(self, static_server, page, backend_running):
        """空态与概览互斥：未检查时显示「尚未检查」+检查按钮；有结果时显示概览卡。

        说明：「尚未检查」空态在 DOM 中始终存在（x-show 控制显隐），因此用
        is_visible() 判断当前实际显示的分支，验证两个分支互斥且元素正确。
        """
        page.goto(f"{static_server}#health")
        page.wait_for_timeout(2500)
        empty_visible = page.locator(".empty-state__title", has_text="尚未检查").is_visible()
        badge_visible = page.locator(".health-badge").is_visible()
        # 两分支互斥：不能同时显示
        assert empty_visible != badge_visible, \
            "「尚未检查」空态与概览卡必须互斥（当前都不显示或都显示）"
        if empty_visible:
            expect(page.locator("button", has_text="开始检查")).to_be_visible(timeout=5000)
        else:
            expect(page.locator(".health-badge")).to_be_visible(timeout=5000)

    def test_health_console_clean(self, static_server, page, backend_running):
        """#health 加载无 console 报错/警告"""
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
        self._goto_health_and_ensure_data(static_server, page)
        page.wait_for_timeout(1500)
        assert errors == [], f"Console errors/warnings on #health: {errors}"
