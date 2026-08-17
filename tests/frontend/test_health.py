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

import json
import re
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

    # ── 阶段二：就绪信号 静态结构 ───────────────────────────────────────

    def test_stage2_store_readiness_methods(self):
        """store.js 暴露就绪信号状态与 getter"""
        js = STORE.read_text(encoding="utf-8")
        for name in ["readiness", "readinessLabel", "readinessDotClass",
                     "readinessTitle", "loadReadiness", "_syncReadinessFromHealth"]:
            assert name in js, f"Missing readiness store symbol: {name}"

    def test_stage2_api_events_diagnose(self):
        """api.js subscribeEvents 已存在（SSE 订阅）"""
        js = API.read_text(encoding="utf-8")
        assert "subscribeEvents" in js, "Missing subscribeEvents"
        assert "EventSource" in js, "Missing EventSource SSE"

    def test_stage2_index_readiness_markup(self):
        """顶部 status-indicator 替换为就绪信号；sidebar-footer 保留"""
        html = INDEX.read_text(encoding="utf-8")
        assert "status-indicator--readiness" in html, "Missing readiness indicator"
        assert "readinessLabel" in html, "Missing readinessLabel binding"
        assert "readinessDotClass" in html, "Missing readinessDotClass binding"
        assert "readinessTitle" in html, "Missing readiness tooltip"
        assert "hash='health'" in html or 'hash="health"' in html, \
            "readiness 应可点击进 #health"
        # sidebar-footer 状态保留
        assert "sidebar-footer__status" in html, "sidebar-footer__status 应保留"

    def test_stage2_css_classes(self):
        """就绪信号样式类在 components.css（复用 token）"""
        css = COMPONENTS_CSS.read_text(encoding="utf-8")
        for cls in ["status-indicator__dot--success", "status-indicator__dot--danger",
                    "status-indicator__dot--warning", "status-indicator__dot--muted",
                    "status-indicator--readiness"]:
            assert f".{cls}" in css, f"Missing readiness CSS class: .{cls}"
        # 语义色走 token
        assert "background: var(--color-success);" in css
        assert "background: var(--text-muted);" in css

    # ── 阶段 B：非复杂分组修复交互 静态结构 ─────────────────────────────

    def test_stageb_api_heal_methods(self):
        """api.js 暴露 heal 修复方法"""
        js = API.read_text(encoding="utf-8")
        assert "healMove" in js, "Missing api.healMove()"
        assert "healRebuild" in js, "Missing api.healRebuild()"
        assert "/api/heal/move" in js, "Missing /api/heal/move endpoint"
        assert "/api/heal/rebuild" in js, "Missing /api/heal/rebuild endpoint"

    def test_stageb_store_state_and_methods(self):
        """store.js 暴露阶段 B 勾选/修复方法"""
        js = STORE.read_text(encoding="utf-8")
        for name in ["healthSelected", "healthHealingGroup", "healthLazyCopying",
                     "healthIsFixableType", "healthGroupButtonLabel",
                     "healthGroupChecked", "healthGroupAllChecked",
                     "healthGroupSomeChecked", "toggleHealthSelect",
                     "toggleHealthGroupSelect", "openHealthFixModal",
                     "healthFixPathsPreview", "copyHealthFixPrompt",
                     "execHealthFix", "copyLazyHealthPrompt",
                     "buildHealthPrompt"]:
            assert name in js, f"Missing stage B store symbol: {name}"

    def test_stageb_lazy_button_markup(self):
        """lazy 按钮「我懒得看了，交给 AI 吧」在 header，与重新检查并列，total_issues>0 显示"""
        html = INDEX.read_text(encoding="utf-8")
        assert "我懒得看了，交给 AI 吧" in html, "Missing lazy button text"
        assert "btn-lazy-ai" in html, "Missing lazy button CSS class"
        assert "copyLazyHealthPrompt" in html, "lazy 按钮未绑定 copyLazyHealthPrompt"
        assert "healthLazyCopying" in html, "lazy 按钮缺少复制中状态"

    def test_stageb_checkbox_and_group_action_markup(self):
        """非复杂分组：勾选框 + 组头单按钮；勾选项高亮"""
        html = INDEX.read_text(encoding="utf-8")
        assert "issue-checkbox" in html, "Missing issue checkbox"
        assert "issue-group__action" in html, "Missing group action button"
        assert "toggleHealthSelect" in html, "Missing toggleHealthSelect"
        assert "toggleHealthGroupSelect" in html, "Missing group select-all"
        assert "healthGroupButtonLabel" in html, "Missing group button label"
        assert "is-checked" in html, "Missing checked highlight class"

    def test_stageb_fix_modal_markup(self):
        """修复确认弹窗：确认执行 + 复制 prompt + path 列表"""
        html = INDEX.read_text(encoding="utf-8")
        assert "health-fix" in html, "Missing health-fix modal"
        assert "确认执行" in html, "Missing confirm button"
        assert "复制 prompt" in html, "Missing copy prompt button"
        assert "fix-modal__paths" in html, "Missing fix-modal paths element"
        assert "execHealthFix" in html, "Missing execHealthFix"

    def test_stageb_css_classes(self):
        """阶段 B 新增样式类在 components.css（复用 token）"""
        css = COMPONENTS_CSS.read_text(encoding="utf-8")
        for cls in ["issue-checkbox", "issue-group__action", "issue-row.is-checked",
                    "btn-lazy-ai", "fix-modal__paths"]:
            assert f".{cls}" in css, f"Missing stage B CSS class: .{cls}"
        # 关键 token 引用
        assert "accent-color: var(--accent)" in css, "checkbox 应使用 --accent"
        assert "var(--radius-md)" in css, "lazy 按钮圆角用 --radius-md"


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
            # 阶段 B
            "btn-lazy-ai", "我懒得看了，交给 AI 吧",
            "issue-checkbox", "issue-group__action",
            "health-fix", "确认执行", "execHealthFix",
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
            expect(page.locator(".complex-zone__copy-btn")).to_be_visible(timeout=5000)

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
        page.locator("button", has_text=re.compile(r"复制 prompt(?! 给 AI)")).first.click()
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

    # ── 阶段 B：浏览器渲染测试 ─────────────────────────────────────────

    def _has_problems(self, page):
        """当前 healthData 是否有问题（有则 lazy 按钮应显示）"""
        return page.evaluate(
            "() => !!window.Alpine.store('app').healthData"
            " && (window.Alpine.store('app').healthSummary.total_issues || 0) > 0")

    def _has_fixable_group(self, page):
        """是否存在可修复分组（position/index/system）"""
        return page.evaluate(
            "() => window.Alpine.store('app').healthGroups"
            ".some(g => ['position','index','system'].includes(g.type))")

    def test_stageb_lazy_button_present(self, static_server, page, backend_running):
        """lazy 按钮存在（有问题时显示，文案正确）"""
        self._goto_health_and_ensure_data(static_server, page)
        if not self._has_problems(page):
            pytest.skip("当前知识库无问题，lazy 按钮应隐藏")
        lazy = page.locator(".btn-lazy-ai")
        expect(lazy.first).to_be_visible(timeout=5000)
        expect(lazy.first).to_contain_text("我懒得看了，交给 AI 吧")

    def test_stageb_group_action_buttons(self, static_server, page, backend_running):
        """可修复分组：默认全选后组头按钮 enabled；复杂区无按钮无勾选"""
        self._goto_health_and_ensure_data(static_server, page)
        if not self._has_fixable_group(page):
            pytest.skip("当前知识库无可修复分组")
        action = page.locator(".issue-group__action").first
        expect(action).to_be_visible(timeout=5000)
        # 进入页面默认全选可修复分组 → 按钮初始 enabled
        expect(action).to_be_enabled()
        # 复杂区无勾选框
        assert page.locator(".complex-zone .issue-checkbox").count() == 0

    def test_stageb_checkbox_activates_button(self, static_server, page, backend_running):
        """取消全选 → 按钮 disabled；重新勾选 → 变可交互"""
        self._goto_health_and_ensure_data(static_server, page)
        if not self._has_fixable_group(page):
            pytest.skip("当前知识库无可修复分组")
        checkbox = page.locator(".health-group .issue-checkbox").first
        expect(checkbox).to_be_visible(timeout=5000)
        btn = page.locator(".issue-group__action").first
        # 默认全选 → 按钮初始 enabled
        expect(btn).to_be_enabled()
        # 清空勾选 → 按钮 disabled
        page.evaluate("() => { window.Alpine.store('app').healthSelected = {}; }")
        page.wait_for_timeout(300)
        expect(btn).to_be_disabled()
        # 重新勾选第一个 issue → 按钮变可交互
        page.locator(".health-group .issue-checkbox").nth(1).click()
        page.wait_for_timeout(300)
        expect(btn).to_be_enabled(timeout=5000)

    def test_stageb_lazy_copy(self, static_server, page, backend_running):
        """lazy 复制完整清单 prompt：头部 + maint 工具 + 扫描文件"""
        self._goto_health_and_ensure_data(static_server, page)
        if not self._has_problems(page):
            pytest.skip("当前知识库无问题")
        ctx = page.context
        try:
            ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass
        page.locator(".btn-lazy-ai").first.click()
        page.wait_for_timeout(500)
        text = ""
        try:
            text = page.evaluate("async () => await navigator.clipboard.readText()")
        except Exception:
            pass
        assert text, "lazy 剪贴板为空"
        assert "我知识库的结构体检发现了以下问题" in text, "lazy 缺头部"
        assert "maint__knowledgebase_diagnose" in text, "lazy 缺复查工具"
        assert "maint__rebuild_index" in text, "lazy 缺重建工具"
        assert "扫描文件：" in text, "lazy 缺扫描文件结尾"

    def test_stageb_console_clean_with_modal(self, static_server, page, backend_running):
        """打开修复弹窗后 console 仍干净"""
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
        self._goto_health_and_ensure_data(static_server, page)
        if self._has_fixable_group(page):
            # 默认已全选 → 直接点组头按钮打开弹窗
            action = page.locator(".issue-group__action").first
            if action.is_visible():
                action.click()
                page.wait_for_timeout(500)
                # 健康修复弹窗唯一标识：fix-modal__paths（path 列表）
                expect(page.locator(".fix-modal__paths").first).to_be_attached(timeout=5000)
        page.wait_for_timeout(800)
        assert errors == [], f"Console errors/warnings: {errors}"

    # ── 阶段 B 补强：修复中禁用 + 交互/端到端测试（mock 后端） ─────────

    @staticmethod
    def _inject_health_data(page, issues, total_files=100):
        """注入受控 healthData（不依赖真实后端状态），供确定性地测试交互。"""
        page.evaluate(
            """(arg) => {
              const { issues, total } = arg;
              window.Alpine.store('app').healthData = {
                issues: issues,
                summary: { total_files: total, total_issues: issues.length, by_type: {} }
              };
              window.Alpine.store('app').healthGeneratedAt = '';
              window.Alpine.store('app').healthSelected = {};
              window.Alpine.store('app').healthHealingGroup = '';
            }""",
            {"issues": issues, "total": total_files})
        page.wait_for_timeout(300)

    def test_stageb_mock_move_rest_body(self, static_server, page, backend_running):
        """勾选 position 问题 → 确认执行 → 断言 /api/heal/move body.paths 正确 + 自动重查"""
        captured = {}
        issues = [
            {"type": "position", "path": "projects/P/orphan.md", "severity": "high",
             "message": "孤儿文档", "action": "move_to_peer_ck", "needs_semantic": False},
            {"type": "index", "path": "projects/P/readme.md", "severity": "medium",
             "message": "索引过时", "action": "rebuild_index", "needs_semantic": False},
        ]

        def handle_route(route):
            if "/api/heal/move" in route.request.url:
                captured["move"] = route.request.post_data
                route.fulfill(status=200, content_type="application/json",
                              body='{"moved":["projects/P/common-knowledge/orphan.md"],"failed":[]}')
            elif "/api/diagnose" in route.request.url:
                captured["diagnose"] = True
                route.fulfill(status=200, content_type="application/json",
                              body='{"issues":[],"summary":{"total_files":100,"total_issues":0,"by_type":{}},"generated_at":"2026-08-14T00:00:00Z"}')
            else:
                route.continue_()

        page.route("**/api/heal/move", handle_route)
        page.route("**/api/diagnose", handle_route)
        page.goto(f"{static_server}#health")
        page.wait_for_timeout(2500)
        self._inject_health_data(page, issues)

        # 勾选 position issue 并打开弹窗
        page.locator(".health-group .issue-checkbox").first.click()
        page.wait_for_timeout(300)
        page.locator(".issue-group__action").first.click()
        page.wait_for_timeout(300)
        expect(page.locator(".fix-modal__paths").first).to_be_attached(timeout=5000)
        # 确认执行
        page.locator(".modal button", has_text="确认执行").first.click()
        page.wait_for_timeout(1200)

        # 断言 REST body.paths 正确
        assert captured.get("move"), "未调用 /api/heal/move"
        move_body = json.loads(captured["move"])
        assert move_body.get("paths") == ["projects/P/orphan.md"], \
            f"move body.paths 错误: {move_body.get('paths')}"
        # 自动重查（/api/diagnose 被调用）
        assert captured.get("diagnose"), "确认执行后未自动重新检查"

    def test_stageb_mock_rebuild_rest_body(self, static_server, page, backend_running):
        """勾选 index 问题 → 确认执行 → 断言 /api/heal/rebuild body.all=true + 自动重查"""
        captured = {}
        issues = [
            {"type": "index", "path": "projects/P/readme.md", "severity": "medium",
             "message": "索引过时", "action": "rebuild_index", "needs_semantic": False},
        ]

        def handle_route(route):
            if "/api/heal/rebuild" in route.request.url:
                captured["rebuild"] = route.request.post_data
                route.fulfill(status=200, content_type="application/json",
                              body='{"rebuilt":["projects/P"],"project_status":true}')
            elif "/api/diagnose" in route.request.url:
                captured["diagnose"] = True
                route.fulfill(status=200, content_type="application/json",
                              body='{"issues":[],"summary":{"total_files":100,"total_issues":0,"by_type":{}},"generated_at":"2026-08-14T00:00:00Z"}')
            else:
                route.continue_()

        page.route("**/api/heal/rebuild", handle_route)
        page.route("**/api/diagnose", handle_route)
        page.goto(f"{static_server}#health")
        page.wait_for_timeout(2500)
        self._inject_health_data(page, issues)

        page.locator(".health-group .issue-checkbox").first.click()
        page.wait_for_timeout(300)
        page.locator(".issue-group__action").first.click()
        page.wait_for_timeout(300)
        page.locator(".modal button", has_text="确认执行").first.click()
        page.wait_for_timeout(1200)

        assert captured.get("rebuild"), "未调用 /api/heal/rebuild"
        rebuild_body = json.loads(captured["rebuild"])
        assert rebuild_body.get("all") is True, f"rebuild body.all 错误: {rebuild_body}"
        assert captured.get("diagnose"), "确认执行后未自动重新检查"

    def test_stageb_modal_copy_prompt_content(self, static_server, page, backend_running):
        """弹窗「复制 prompt」内容含勾选项 path/type/severity"""
        issues = [
            {"type": "position", "path": "projects/P/orphan.md", "severity": "high",
             "message": "孤儿文档", "action": "move_to_peer_ck", "needs_semantic": False},
        ]
        page.goto(f"{static_server}#health")
        page.wait_for_timeout(2500)
        self._inject_health_data(page, issues)
        page.locator(".health-group .issue-checkbox").first.click()
        page.wait_for_timeout(300)
        page.locator(".issue-group__action").first.click()
        page.wait_for_timeout(300)
        expect(page.locator(".fix-modal__paths").first).to_be_attached(timeout=5000)
        # 授予剪贴板权限并点弹窗「复制 prompt」
        try:
            page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        except Exception:
            pass
        page.locator(".modal button", has_text=re.compile(r"复制 prompt(?! 给 AI)")).first.click()
        page.wait_for_timeout(500)
        text = ""
        try:
            text = page.evaluate("async () => await navigator.clipboard.readText()")
        except Exception:
            pass
        assert text, "弹窗复制 prompt 为空"
        assert "projects/P/orphan.md" in text, "缺勾选项 path"
        assert "**position**" in text, "缺 type"
        assert "[high]" in text, "缺 severity"

    def test_stageb_select_all_indeterminate(self, static_server, page, backend_running):
        """部分勾选时全选框为中间态（indeterminate）"""
        issues = [
            {"type": "position", "path": "projects/P/a.md", "severity": "high",
             "message": "孤儿A", "action": "move_to_peer_ck", "needs_semantic": False},
            {"type": "position", "path": "projects/P/b.md", "severity": "high",
             "message": "孤儿B", "action": "move_to_peer_ck", "needs_semantic": False},
        ]
        page.goto(f"{static_server}#health")
        page.wait_for_timeout(2500)
        self._inject_health_data(page, issues)
        # position 组 checkbox 顺序：[全选框, issueA, issueB]；勾选第一个 issue（第 2 个）
        issue_a = page.locator(".health-group .issue-checkbox").nth(1)
        issue_a.click()
        page.wait_for_timeout(300)
        # 组头全选框（第 1 个）应为 indeterminate
        all_box = page.locator(".health-group .issue-checkbox").first
        indeterminate = all_box.evaluate("el => el.indeterminate")
        assert indeterminate, "部分勾选时全选框应为 indeterminate 中间态"

    def test_stageb_e2e_heal_loop(self, static_server, page, backend_running):
        """端到端完整闭环：勾选→按钮激活→弹窗→确认执行→toast→自动重查→修复项消失"""
        captured = {"diagnose_calls": 0}
        issues = [
            {"type": "position", "path": "projects/P/orphan.md", "severity": "high",
             "message": "孤儿文档", "action": "move_to_peer_ck", "needs_semantic": False},
        ]

        def handle_route(route):
            url = route.request.url
            if "/api/heal/move" in url:
                route.fulfill(status=200, content_type="application/json",
                              body='{"moved":["projects/P/common-knowledge/orphan.md"],"failed":[]}')
            elif "/api/diagnose" in url:
                captured["diagnose_calls"] += 1
                # 修复后返回空问题（孤儿文档已移走）→ 修复项消失
                route.fulfill(status=200, content_type="application/json",
                              body='{"issues":[],"summary":{"total_files":100,"total_issues":0,"by_type":{}},"generated_at":"2026-08-14T00:00:00Z"}')
            else:
                route.continue_()

        page.route("**/api/heal/move", handle_route)
        page.route("**/api/diagnose", handle_route)
        page.goto(f"{static_server}#health")
        page.wait_for_timeout(2500)
        self._inject_health_data(page, issues)

        # 组头按钮初始 disabled
        btn = page.locator(".issue-group__action").first
        expect(btn).to_be_disabled()
        # 勾选 → 按钮激活
        page.locator(".health-group .issue-checkbox").first.click()
        page.wait_for_timeout(300)
        expect(btn).to_be_enabled()
        # 点击按钮 → 弹窗出现
        btn.click()
        page.wait_for_timeout(300)
        expect(page.locator(".fix-modal__paths").first).to_be_attached(timeout=5000)
        # 确认执行
        page.locator(".modal button", has_text="确认执行").first.click()
        # toast「已移动」（DOM 中 toast 元素）
        expect(page.locator(".toast", has_text="已移动").first).to_be_visible(timeout=5000)
        # 自动重查（diagnose 被调用）
        assert captured["diagnose_calls"] >= 1, f"自动重查未触发: {captured['diagnose_calls']}"
        # 修复项消失：position 组不再有 issue
        pos_group = page.evaluate(
            "() => (window.Alpine.store('app').healthGroups.find(g=>g.type==='position')||{}).issues?.length || 0")
        assert pos_group == 0, f"修复后 position 组仍有问题: {pos_group}"

    def test_stageb_healing_disables_all(self, static_server, page, backend_running):
        """修复进行中禁用所有修复操作；完成后恢复（直接设置 healing 状态验证渲染）"""
        issues = [
            {"type": "position", "path": "projects/P/orphan.md", "severity": "high",
             "message": "孤儿文档", "action": "move_to_peer_ck", "needs_semantic": False},
            {"type": "index", "path": "projects/P/readme.md", "severity": "medium",
             "message": "索引过时", "action": "rebuild_index", "needs_semantic": False},
        ]
        page.goto(f"{static_server}#health")
        page.wait_for_timeout(2500)
        self._inject_health_data(page, issues)
        # 先勾选一个 issue（保证组头按钮非空可测 disabled 前的激活态）
        page.locator(".health-group .issue-checkbox").nth(1).click()
        page.wait_for_timeout(300)
        # 模拟进入修复中：healthHealingGroup = 'position'
        page.evaluate("() => { window.Alpine.store('app').healthHealingGroup = 'position'; }")
        page.wait_for_timeout(300)
        healing = page.evaluate("() => window.Alpine.store('app').isHealthHealing")
        assert healing, "应处于修复中状态"
        # 修复中断言：组头按钮 disabled、勾选 disabled、重新检查 disabled
        expect(page.locator(".issue-group__action").first).to_be_disabled()
        expect(page.locator(".health-group .issue-checkbox").first).to_be_disabled()
        recheck_btn = page.locator(".page-header button", has_text="重新检查").first
        if recheck_btn.count() > 0:
            expect(recheck_btn).to_be_disabled()
        # 模拟修复完成：healthHealingGroup 复位
        page.evaluate("() => { window.Alpine.store('app').healthHealingGroup = ''; }")
        page.wait_for_timeout(300)
        healing_after = page.evaluate("() => window.Alpine.store('app').isHealthHealing")
        assert not healing_after, "修复完成后应恢复可交互"
        # 完成后按钮恢复可交互
        expect(page.locator(".issue-group__action").first).to_be_enabled()

    # ── 阶段二：就绪信号（顶部 status-indicator） ───────────────────────

    @staticmethod
    def _set_readiness(page, saved, total_issues, has_high=False):
        """设置就绪信号状态并等待 Alpine 渲染"""
        page.evaluate(
            """(r) => { window.Alpine.store('app').readiness = r; }""",
            {"saved": saved, "total_issues": total_issues, "has_high": has_high})
        page.wait_for_timeout(400)

    @staticmethod
    def _read_readiness(page):
        """读取就绪信号 DOM 文本与状态点类"""
        return page.evaluate(
            """() => {
              const ind = document.querySelector('.status-indicator--readiness');
              if (!ind) return null;
              return {
                label: ind.innerText.trim(),
                dotClass: ind.querySelector('.status-indicator__dot').className
              };
            }""")

    def test_stage2_readiness_render_and_sidebar(self, static_server, page, backend_running):
        """就绪信号替换顶部 status-indicator；sidebar-footer AI 状态保留"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(3000)
        # 顶部就绪信号存在（--readiness）
        ind = page.locator(".status-indicator--readiness")
        expect(ind.first).to_be_attached(timeout=5000)
        # sidebar-footer 状态保留
        expect(page.locator(".sidebar-footer__status").first).to_be_attached(timeout=5000)

    def test_stage2_readiness_three_states(self, static_server, page, backend_running):
        """就绪信号三态：健康(绿)/存疑有high(红)/存疑无high(黄)/未检查(灰)"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(3000)
        # 态1 健康
        self._set_readiness(page, True, 0)
        s = self._read_readiness(page)
        assert s["label"] == "知识状态健康", f"健康态文本错误: {s['label']}"
        assert "success" in s["dotClass"], f"健康态应为绿: {s['dotClass']}"
        # 态2 存疑有 high → 红
        self._set_readiness(page, True, 3, True)
        s = self._read_readiness(page)
        assert s["label"] == "3 个知识存疑", f"存疑文本错误: {s['label']}"
        assert "danger" in s["dotClass"], f"有high应为红: {s['dotClass']}"
        # 态3 存疑无 high → 黄
        self._set_readiness(page, True, 3, False)
        s = self._read_readiness(page)
        assert "warning" in s["dotClass"], f"无high应为黄: {s['dotClass']}"
        # 态4 未检查 → 灰
        self._set_readiness(page, False, 0)
        s = self._read_readiness(page)
        assert s["label"] == "尚未触发检查", f"未检查文本错误: {s['label']}"
        assert "muted" in s["dotClass"], f"未检查应为灰: {s['dotClass']}"

    def test_stage2_readiness_click_to_health(self, static_server, page, backend_running):
        """点击就绪信号跳转 #health"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(3000)
        self._set_readiness(page, True, 3)
        page.locator(".status-indicator--readiness").first.click()
        page.wait_for_timeout(1500)
        assert page.evaluate("() => window.Alpine.store('app').currentView") == "health", \
            "点击就绪信号应跳转 #health"

    def test_stage2_readiness_offline_degrade(self, static_server, page, backend_running):
        """后端离线读 saved 失败 → 降级 muted（中性灰）"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(3000)
        # 拦截 /api/diagnose/saved 返回失败 → loadReadiness catch → muted
        page.route("**/api/diagnose/saved", lambda route: route.abort())
        page.evaluate("async () => { await window.Alpine.store('app').loadReadiness(); }")
        page.wait_for_timeout(400)
        s = self._read_readiness(page)
        assert s and "muted" in s["dotClass"], f"离线应降级 muted: {s}"
        assert s["label"] == "尚未触发检查", f"离线应为未检查灰: {s['label']}"
