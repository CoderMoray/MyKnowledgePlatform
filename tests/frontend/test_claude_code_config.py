"""前端验收：Claude Code 平台 MCP / Hooks / Agent 设置页开关的读写逻辑。

配套测试方案：``docs/test-plan-claude-code-config.md``。

分两层：

1. ``TestClaudeCodeConfigStatic`` —— 静态源码断言（不依赖后端 / 浏览器，总是运行）。
   钉死 store.js / api.js / index.html 里开关的双向逻辑：
     - 开关视觉态绑定 ``clientStatus(platform, kind)``（= 后端 detect 结果）；
     - 点击调 ``configureClient(plat.key, kind.key)``；
     - ``configureClient`` 按当前状态取反：开→``setClientConfig`` (POST)，
       关→``deleteClientConfig`` (DELETE)，之后 ``loadClientConfig`` 回读真实态；
     - 单写锁 ``clientConfiguring`` 防并发串扰；
     - ``guideExecute``（重新运行初始化引导）用 ``kindMeta.key`` 字符串、且只
       「确保开启」不误关已配置项 —— 见测试方案「发现的问题」#1 #2。

2. ``TestClaudeCodeToggleBrowser`` —— Playwright，全量 mock ``/api/**``（不碰真实
   ``~/.claude``、不需要 8080 后端），真跑 Alpine：验证开关 UI ↔ mock 配置态一致、
   点击发对方向的 HTTP 动词、``guideExecute`` 不误删已配置项。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "frontend" / "js" / "store.js"
API = ROOT / "frontend" / "js" / "api.js"
INDEX = ROOT / "frontend" / "index.html"


# ═══════════════════════════════════════════════════════════════════════════
#  1. 静态源码断言
# ═══════════════════════════════════════════════════════════════════════════


class TestClaudeCodeConfigStatic:
    def test_api_has_write_and_remove_methods(self) -> None:
        js = API.read_text(encoding="utf-8")
        assert "async setClientConfig(platform, kind)" in js
        assert "async deleteClientConfig(platform, kind)" in js
        assert 'method: "POST"' in js and 'method: "DELETE"' in js
        assert "/api/client-config/${encodeURIComponent(platform)}/${encodeURIComponent(kind)}" in js

    def test_configure_client_is_bidirectional_toggle(self) -> None:
        """configureClient 按当前检测态取反：开=POST 写，关=DELETE 移除。"""
        js = STORE.read_text(encoding="utf-8")
        body = js[js.index("async configureClient("):js.index("async configureClient(") + 1600]
        assert "const prev = !!this.clientConfig[platform][kind]" in body
        assert "target = !prev" in body
        assert "api.setClientConfig(platform, kind)" in body
        assert "api.deleteClientConfig(platform, kind)" in body
        # 写/移除后回读真实态（开关状态以后端 detect 为准）
        assert "await this.loadClientConfig()" in body

    def test_configure_client_single_flight_lock(self) -> None:
        js = STORE.read_text(encoding="utf-8")
        body = js[js.index("async configureClient("):js.index("async configureClient(") + 1600]
        assert "if (this.clientConfiguring) return" in body
        assert "this.clientConfiguring = { platform, kind }" in body
        assert "this.clientConfiguring = null" in body  # finally 释放

    def test_switch_visual_state_bound_to_client_status(self) -> None:
        """设置页 toggle 的开/关 class 由 clientStatus(plat.key, kind.key) 决定，
        点击调 configureClient(plat.key, kind.key)。"""
        html = INDEX.read_text(encoding="utf-8")
        assert "$store.app.clientStatus(plat.key, kind.key)" in html
        assert "$store.app.configureClient(plat.key, kind.key)" in html
        # clientStatus 直接取 detect 结果
        js = STORE.read_text(encoding="utf-8")
        cs = js[js.index("clientStatus(platform, kind) {"):]
        cs = cs[:cs.index("},")]
        assert "return cfg[platform][kind]" in cs

    def test_client_status_reads_backend_detect(self) -> None:
        """loadClientConfig 把 GET /api/client-config 的结果整体存进 clientConfig。"""
        js = STORE.read_text(encoding="utf-8")
        body = js[js.index("async loadClientConfig()"):js.index("async loadClientConfig()") + 600]
        assert "api.getClientConfig()" in body
        assert "this.clientConfig = data" in body

    def test_guide_execute_uses_kind_key_string(self) -> None:
        """回归 #1：guideExecute 必须取 kindMeta.key（字符串），不能把 {key,label,desc}
        对象直接传给 configureClient —— 否则 URL 变 /api/client-config/X/[object Object]
        → 后端 400 → 引导一个配置都写不进去。"""
        js = STORE.read_text(encoding="utf-8")
        ge = js[js.index("async guideExecute()"):js.index("async guideExecute()") + 1600]
        assert "this.platformKinds(platform)" in ge
        assert "kindMeta.key" in ge, "guideExecute 未从 platformKinds 元信息取 .key"
        assert re.search(r"configureClient\(platform,\s*kind\)", ge)
        # 不能再出现「直接 for (const kind of this.platformKinds(...)) { ... configureClient(platform, kind) }」
        assert "for (const kind of this.platformKinds(platform))" not in ge

    def test_guide_execute_only_ensures_on(self) -> None:
        """回归 #2：guideExecute 只「确保开启」，对已配置 kind 跳过——重新运行
        初始化引导不能把已有配置误关（configureClient 是双向开关）。"""
        js = STORE.read_text(encoding="utf-8")
        ge = js[js.index("async guideExecute()"):js.index("async guideExecute()") + 1600]
        assert "this.clientStatus(platform, kind) === true" in ge
        assert "continue" in ge

    def test_platform_kinds_returns_meta_objects(self) -> None:
        """platformKinds 返回 {key,label,desc} 元信息（供调用方取 .key）——
        钉住这个契约，guideExecute/guideConfigItems 才知道要 .key。"""
        js = STORE.read_text(encoding="utf-8")
        pk = js[js.index("platformKinds(platform) {"):]
        pk = pk[:pk.index("},")]
        assert "this.clientKinds.filter" in pk

    def test_claude_code_supports_all_three_kinds(self) -> None:
        js = STORE.read_text(encoding="utf-8")
        row = next(l for l in js.splitlines() if '"ClaudeCode"' in l and "kinds:" in l)
        assert '"mcp", "hooks", "agent"' in row


# ═══════════════════════════════════════════════════════════════════════════
#  2. 浏览器（全量 mock /api/**，真跑 Alpine）
# ═══════════════════════════════════════════════════════════════════════════

PLATFORMS_META = {
    "ClaudeCode": {"display": "Claude Code", "enabled": True, "order": 1,
                   "kinds": ["mcp", "hooks", "agent"]},
    "ClaudeDesktop": {"display": "Claude Desktop", "enabled": True, "order": 2,
                      "kinds": ["mcp"]},
    "CodeBuddyIDE": {"display": "CodeBuddy IDE", "enabled": True, "order": 3,
                     "kinds": ["mcp", "hooks", "agent"]},
    "WorkBuddy": {"display": "WorkBuddy", "enabled": True, "order": 4,
                  "kinds": ["mcp", "hooks", "agent"]},
    "Enchante": {"display": "Enchanté", "enabled": True, "order": 5,
                 "kinds": ["mcp", "agent"]},
    "Cursor": {"display": "Cursor", "enabled": True, "order": 6,
               "kinds": ["mcp", "hooks", "agent"]},
}


class _MockBackend:
    """内存态 AI-client 配置 + 调用记录；驱动 page.route 拦截 /api/**。"""

    def __init__(self, identity: bool = True):
        self.cfg = {
            p: {"client_installed": True, "connection": "not_connected",
                "mcp": False, "hooks": False, "agent": False}
            for p in PLATFORMS_META
        }
        self.calls: list[tuple[str, str, str]] = []  # (method, platform, kind)
        self.identity = identity

    def install(self, page) -> None:
        page.route("**/api/**", self._handle)

    def _handle(self, route) -> None:
        req = route.request
        url = req.url
        path = url.split("://", 1)[-1].split("/", 1)[-1]
        path = "/" + path.split("?", 1)[0]
        method = req.method

        if path.startswith("/api/events"):
            return route.abort()

        m = re.match(r"/api/client-config/([^/]+)/([^/]+)$", path)
        if m:
            platform, kind = m.group(1), m.group(2)
            self.calls.append((method, platform, kind))
            if method == "POST":
                if platform in self.cfg and kind in ("mcp", "hooks", "agent"):
                    self.cfg[platform][kind] = True
                    return self._json(route, {"platform": platform, "kind": kind,
                                              "status": "written", "detected": True})
                return self._json(route, {"detail": f"bad kind {kind}"}, status=400)
            if method == "DELETE":
                if platform in self.cfg and kind in ("mcp", "hooks", "agent"):
                    self.cfg[platform][kind] = False
                return self._json(route, {"platform": platform, "kind": kind,
                                          "status": "removed"})

        if path == "/api/client-config":
            return self._json(route, self.cfg)
        if path == "/api/platforms-meta":
            return self._json(route, PLATFORMS_META)
        if path == "/api/identity":
            if self.identity:
                return self._json(route, {"nickname": "Tester", "email": "t@example.com"})
            return self._json(route, {"detail": "not set"}, status=404)
        if path == "/api/config-status":
            return self._json(route, {"configured": False})
        if path == "/api/version":
            return self._json(route, {"system": "0.7.7", "kb": ""})
        if path == "/api/lock":
            return self._json(route, {"locked": False})
        if path == "/api/mcp":
            return self._json(route, {"status": "disconnected"})
        # 其它 GET 一律给空对象（store 里都有 try/catch 兜底）
        return self._json(route, {})

    @staticmethod
    def _json(route, data: dict, status: int = 200) -> None:
        route.fulfill(status=status, content_type="application/json",
                      body=json.dumps(data))


@pytest.fixture
def mock_page(browser, static_server):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    yield pg
    ctx.close()


def _open_settings(page, group: str) -> None:
    page.locator(".user-menu__trigger").click()
    page.locator(".user-menu__item", has_text="设置").click()
    page.wait_for_timeout(600)
    page.locator(".settings-nav__item", has_text=group).click()
    page.wait_for_timeout(400)


class TestClaudeCodeToggleBrowser:
    def _boot(self, page, static_server, mock: _MockBackend):
        mock.install(page)
        page.goto(f"{static_server}#dashboard")
        try:
            page.wait_for_selector(".user-menu__trigger", timeout=8000)
        except Exception:
            pytest.skip("前端未能在 mock 环境下启动（Alpine/资源加载）")

    def test_switch_reflects_backend_state(self, mock_page, static_server):
        """检验一/二/三 的 UI 侧：开关 on/off class 与 mock 的 clientConfig 一致。"""
        mock = _MockBackend()
        mock.cfg["ClaudeCode"].update(mcp=True, hooks=False, agent=True)
        self._boot(mock_page, static_server, mock)
        _open_settings(mock_page, "MCP")

        def toggle(kind_nav, plat="ClaudeCode"):
            mock_page.locator(".settings-nav__item", has_text=kind_nav).click()
            mock_page.wait_for_timeout(250)
            return mock_page.locator(
                f".settings-modal .ai-platform-row[data-platform='{plat}'][data-kind="
                f"'{ {'MCP':'mcp','Hooks':'hooks','Agents':'agent'}[kind_nav] }'] .toggle")

        cls_mcp = toggle("MCP").get_attribute("class")
        cls_hooks = toggle("Hooks").get_attribute("class")
        cls_agent = toggle("Agents").get_attribute("class")
        assert "toggle--on" in cls_mcp and "toggle--off" not in cls_mcp.replace("toggle--off-soft", "")
        assert "toggle--off" in cls_hooks
        assert "toggle--on" in cls_agent

    def test_toggle_off_sends_delete_then_on_sends_post(self, mock_page, static_server):
        """开关双向：当前为开 → 点击发 DELETE；当前为关 → 点击发 POST。回读后 class 翻转。"""
        mock = _MockBackend()
        mock.cfg["ClaudeCode"]["mcp"] = True
        self._boot(mock_page, static_server, mock)
        _open_settings(mock_page, "MCP")

        row = mock_page.locator(
            ".settings-modal .ai-platform-row[data-platform='ClaudeCode'][data-kind='mcp']")
        tog = row.locator(".toggle")
        assert "toggle--on" in tog.get_attribute("class")

        tog.click()  # 开 → 关
        mock_page.wait_for_timeout(600)
        assert ("DELETE", "ClaudeCode", "mcp") in mock.calls
        assert mock.cfg["ClaudeCode"]["mcp"] is False
        assert "toggle--off" in tog.get_attribute("class")

        mock.calls.clear()
        tog.click()  # 关 → 开
        mock_page.wait_for_timeout(600)
        assert ("POST", "ClaudeCode", "mcp") in mock.calls
        assert mock.cfg["ClaudeCode"]["mcp"] is True
        assert "toggle--on" in tog.get_attribute("class")

    def test_three_switches_independent(self, mock_page, static_server):
        """关 hooks 不影响 mcp / agent（只对 hooks 发一次 DELETE）。"""
        mock = _MockBackend()
        mock.cfg["ClaudeCode"].update(mcp=True, hooks=True, agent=True)
        self._boot(mock_page, static_server, mock)
        _open_settings(mock_page, "Hooks")

        mock_page.locator(
            ".settings-modal .ai-platform-row[data-platform='ClaudeCode'][data-kind='hooks'] .toggle"
        ).click()
        mock_page.wait_for_timeout(600)

        kinds_touched = {(mth, k) for (mth, p, k) in mock.calls if p == "ClaudeCode"}
        assert kinds_touched == {("DELETE", "hooks")}, kinds_touched
        assert mock.cfg["ClaudeCode"] == {
            "client_installed": True, "connection": "not_connected",
            "mcp": True, "hooks": False, "agent": True}

    def test_guide_reexecute_does_not_remove_configured(self, mock_page, static_server):
        """回归 #1+#2：已完整配置 ClaudeCode 时再跑 guideExecute（重新运行初始化引导），
        不得对 ClaudeCode 发任何 DELETE，也不得用非法 kind（[object Object]）。"""
        mock = _MockBackend()
        mock.cfg["ClaudeCode"].update(mcp=True, hooks=True, agent=True)
        self._boot(mock_page, static_server, mock)

        mock_page.evaluate(
            """async () => {
                const s = Alpine.store('app');
                s.clientConfig = JSON.parse(JSON.stringify({
                  ClaudeCode: { client_installed: true, connection: 'not_connected',
                                mcp: true, hooks: true, agent: true } }));
                s.guideSelected = ['ClaudeCode'];
                await s.guideExecute();
            }"""
        )
        mock_page.wait_for_timeout(300)

        cc_calls = [(m, k) for (m, p, k) in mock.calls if p == "ClaudeCode"]
        assert all(m != "DELETE" for (m, k) in cc_calls), f"引导误发 DELETE: {cc_calls}"
        assert all(k in ("mcp", "hooks", "agent") for (m, k) in cc_calls), \
            f"引导用了非法 kind: {cc_calls}"
        assert mock.cfg["ClaudeCode"]["mcp"] and mock.cfg["ClaudeCode"]["hooks"] \
            and mock.cfg["ClaudeCode"]["agent"]

    def test_guide_execute_writes_all_three_when_unconfigured(self, mock_page, static_server):
        """回归 #1 正向：全未配置时 guideExecute 应把 mcp/hooks/agent 三个都 POST 写入。"""
        mock = _MockBackend()
        self._boot(mock_page, static_server, mock)

        mock_page.evaluate(
            """async () => {
                const s = Alpine.store('app');
                s.clientConfig = JSON.parse(JSON.stringify({
                  ClaudeCode: { client_installed: true, connection: 'not_connected',
                                mcp: false, hooks: false, agent: false } }));
                s.guideSelected = ['ClaudeCode'];
                await s.guideExecute();
            }"""
        )
        mock_page.wait_for_timeout(300)

        posts = sorted(k for (m, p, k) in mock.calls if p == "ClaudeCode" and m == "POST")
        assert posts == ["agent", "hooks", "mcp"], f"引导写入不全: {mock.calls}"
        assert mock.cfg["ClaudeCode"]["mcp"] and mock.cfg["ClaudeCode"]["hooks"] \
            and mock.cfg["ClaudeCode"]["agent"]
