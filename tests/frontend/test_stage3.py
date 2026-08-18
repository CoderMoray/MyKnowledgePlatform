"""MyKnowledge 前端 — 阶段三：引导页三步向导 + 配置 modal（5 平级导航 + 5 态开关）测试

覆盖：
1. 静态结构：api.js client-config 方法；store.js 阶段三状态/方法；
   index.html 引导向导（guide-steps 3 步）+ 配置 modal（settings-nav 5 平级：
   账号/通用/MCP/Hooks/Agents，分组页内 5 态 toggle 表达配置状态）
2. 构建：standalone 含阶段三功能文本/样式
3. 浏览器渲染（复用 conftest fixtures）：
   - user-menu「设置」打开配置 modal；左导航 5 平级切换
   - 账号卡保存；通用卡双层主题；MCP/Hooks/Agents 页平台状态 + 5 态开关
   - 引导页三步向导（Step1 身份 → Step2 AI 协作 → Step3 完成）
   - console 无报错/警告

注意：浏览器测试只 GET 检测 + 打开 modal 渲染，不实际 POST 写入
（避免污染用户全局 ~/.claude / ~/.codebuddy 配置）。

依赖：pip install playwright && playwright install chromium
运行：PYTHONPATH=. pytest tests/frontend/test_stage3.py
"""

from pathlib import Path

from playwright.sync_api import expect

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
INDEX = FRONTEND / "index.html"
API = FRONTEND / "js" / "api.js"
STORE = FRONTEND / "js" / "store.js"
MODAL = FRONTEND / "js" / "components" / "modal.js"
COMPONENTS_CSS = FRONTEND / "css" / "components.css"
STANDALONE = FRONTEND / "index.standalone.html"


# ═══════════════════════════════════════════════════════════════════════════
# 静态结构测试（不依赖后端运行）
# ═══════════════════════════════════════════════════════════════════════════


class TestStage3StaticStructure:
    """验证阶段三引导页 + 配置 modal 的 HTML/JS/CSS 结构完整性"""

    def test_api_client_config_methods(self):
        """api.js 暴露 client-config 方法（get 检测 / set 写 / delete 移除）"""
        js = API.read_text(encoding="utf-8")
        assert "getClientConfig" in js, "Missing api.getClientConfig()"
        assert "setClientConfig" in js, "Missing api.setClientConfig(platform, kind)"
        assert "deleteClientConfig" in js, "Missing api.deleteClientConfig(platform, kind)"
        assert 'method: "DELETE"' in js, "Missing DELETE request (remove client config)"
        assert "/api/client-config" in js, "Missing /api/client-config endpoint"
        assert "getClientConfigDeeplink" in js, "Missing api.getClientConfigDeeplink()"
        assert "/deeplink" in js, "Missing deeplink endpoint (Enchante MCP)"

    def test_store_stage3_state_and_methods(self):
        """store.js 暴露阶段三状态与方法"""
        js = STORE.read_text(encoding="utf-8")
        for name in ["clientConfig", "settingsGroup", "guideStep", "clientConfiguring",
                     "clientPlatforms", "clientKinds", "loadClientConfig",
                     "configureClient", "copyClientPrompt", "openSettings",
                     "rerunGuide", "isClientConfiguring", "clientStatus",
                     "guideConfigItems", "guideSummary", "deleteClientConfig",
                     "connectionValue", "connectionClass", "connectionLabel",
                     "connectionTooltip", "clientInstalled",
                     "refreshClientConfigIfStale",
                     "usesDeeplink", "generateEnchanteDeeplink", "deeplinkBusy"]:
            assert name in js, f"Missing store symbol: {name}"

    def test_store_platforms_match_backend(self):
        """平台列表与后端 client_config.PLATFORMS 严格一致（PascalCase 平台标识符）：
        ClaudeCode / ClaudeDesktop(MCP-only) / CodeBuddyIDE / WorkBuddy / Enchante；
        标签定稿 Claude Code / CodeBuddy IDE / Enchanté；kinds 数组与后端 platforms.json 一致"""
        js = STORE.read_text(encoding="utf-8")
        for key in ["ClaudeCode", "ClaudeDesktop", "CodeBuddyIDE", "WorkBuddy", "Enchante"]:
            assert f'key: "{key}"' in js, f"Missing platform key: {key}"
        # 平台标签定稿（Claude Code（CLI）/ CodeBuddy IDE（IDE）/ Enchanté）
        assert "Claude Code" in js, "Missing Claude Code platform label"
        assert "CodeBuddy IDE" in js, "Missing CodeBuddy IDE platform label"
        assert "WorkBuddy" in js, "Missing WorkBuddy platform label"
        assert "Enchanté" in js, "Missing Enchante platform label"
        # kinds 数组（替代 mcpOnly 二值）：ClaudeDesktop 仅 mcp、Enchante mcp+agent、其余 mcp+hooks+agent
        assert "kinds: [\"mcp\", \"hooks\", \"agent\"]" in js, "Missing 3-kind platform kinds array"
        assert "kinds: [\"mcp\"]" in js, "Missing ClaudeDesktop kinds (mcp only)"
        assert "kinds: [\"mcp\", \"agent\"]" in js, "Missing Enchante kinds (mcp+agent)"
        assert "mcpOnly" not in js, "mcpOnly 二值已移除，应改用 kinds 数组"
        # 不应出现 cursor 平台（后端未实现，前端不硬编码）
        assert "cursor" not in js, "cursor 平台不应存在（后端 PLATFORMS 未含 cursor）"

    def test_store_kind_filter_upgrade(self):
        """kind 过滤升级：platformsForKind/platformKinds 按每平台 kinds 数组过滤（与后端 platforms.json 一致）：
        Enchante 出现在 MCP + Agent，Hooks 不出现；现有 4 平台分组不回归"""
        js = STORE.read_text(encoding="utf-8")
        # usesDeeplink 判定（当前仅 Enchante MCP）
        assert 'return platform === "Enchante" && kind === "mcp"' in js, "Missing usesDeeplink Enchante-MCP rule"
        # deeplink 流程 + 状态
        assert "generateEnchanteDeeplink" in js, "Missing generateEnchanteDeeplink"
        assert "deeplinkBusy" in js, "Missing deeplinkBusy state"
        # 过滤实现：kinds 数组而非 mcpOnly 二值
        assert "kinds.includes(kindKey)" in js, "platformsForKind 应按 kinds 数组过滤"
        assert "p.kinds.includes(kindKey)" in js, "platformsForKind 过滤应基于 p.kinds"
        assert "Array.isArray(p.kinds)" in js, "platformsForKind 应防御非数组 kinds"

    def test_modal_stage3_methods(self):
        """modal.js 暴露向导与配置 modal 逻辑"""
        js = MODAL.read_text(encoding="utf-8")
        for name in ["guideNext", "guidePrev", "settingsNav",
                     "saveSettingsIdentity", "configureAi", "copyAiPrompt"]:
            assert name in js, f"Missing modal method: {name}"

    def test_index_settings_entry(self):
        """user-menu 含「设置」入口，点击 openSettings()"""
        html = INDEX.read_text(encoding="utf-8")
        assert "openSettings()" in html, "Missing openSettings entry in user-menu"
        assert "设置" in html, "Missing「设置」menu item"

    def test_index_guide_wizard(self):
        """引导页为三步向导：guide-steps + Step1 身份 / Step2 AI 协作 / Step3 完成"""
        html = INDEX.read_text(encoding="utf-8")
        assert "guide-steps" in html, "Missing guide-steps (3-step indicator)"
        assert "guideStep === 1" in html, "Missing Step1 身份"
        assert "guideStep === 2" in html, "Missing Step2 AI 协作"
        assert "guideStep === 3" in html, "Missing Step3 完成"
        assert "guideNext" in html, "Missing guideNext()"
        assert "guidePrev" in html, "Missing guidePrev()"
        assert "初始化 AI 协作" in html, "Missing Step2 title「初始化 AI 协作」"
        assert "初始化完成" in html, "Missing Step3 title「初始化完成」"
        assert "开始使用" in html, "Missing「开始使用」button"

    def test_index_settings_modal_markup(self):
        """配置 modal：settings-nav 5 平级 + settings-body 分组页 + 5 态开关"""
        html = INDEX.read_text(encoding="utf-8")
        assert "settings-nav" in html, "Missing settings-nav (left navigation)"
        assert "settingsGroup === 'account'" in html, "Missing account group"
        assert "settingsGroup === 'general'" in html, "Missing general group"
        assert "settingsGroup === 'mcp'" in html, "Missing MCP group"
        assert "settingsGroup === 'hooks'" in html, "Missing Hooks group"
        assert "settingsGroup === 'agent'" in html, "Missing Agents group"
        assert "settings-card" in html, "Missing settings-card"
        # 账号卡
        assert "saveSettingsIdentity" in html, "Missing account save"
        # 通用卡：双层主题 + 重新引导（一行排布）+ 关于
        assert "designTheme" in html, "Missing designTheme picker"
        assert "showColorMode" in html, "Missing color-mode segmented (双层主题)"
        assert "rerunGuide" in html, "Missing rerun guide button"
        assert "settings-card__row" in html, "Missing guide card row layout"
        assert "systemVersion" in html, "Missing about version"
        # MCP/Hooks/Agents 分组页：平台行 + 5 态开关 + fallback + 重新检测
        assert "ai-platform-row" in html, "Missing ai-platform-row"
        assert "toggle--failed" in html, "Missing 5-state toggle (failed)"
        assert "clientInstalled" in html, "Missing clientInstalled (5 态状态机)"
        assert "clientFallback" in html, "Missing clientFallback (fallback 可交互文本)"
        assert "重新检测" in html, "Missing 重新检测 button"
        # 连接态（MCP 卡平台行右，平台级四态）：仅 MCP 卡展示（kind.key === 'mcp'）
        assert "ai-platform-row__connection" in html, "Missing connection area"
        assert "connection-tip" in html, "Missing connection-tip (dot+text+tooltip)"
        assert "connectionClass" in html, "Missing connectionClass (连接态样式类)"
        assert "connectionLabel" in html, "Missing connectionLabel (连接态文本)"
        assert "connectionTooltip" in html, "Missing connectionTooltip (四态文案)"
        # Enchante MCP：单按钮「生成专属链接」不走 toggle（usesDeeplink 条件渲染）
        assert "usesDeeplink" in html, "Missing usesDeeplink (Enchante MCP deeplink 判定)"
        assert "生成专属链接" in html, "Missing「生成专属链接」button (Enchante MCP)"
        assert "generateEnchanteDeeplink" in html, "Missing generateEnchanteDeeplink handler"
        assert "kind.key === 'mcp'" in html, "连接态应仅在 MCP 卡展示 (x-show kind.key === 'mcp')"
        # 平台标签经 plat.label 动态渲染（"Claude Code" 断言在 store 平台测试中）
        # 引导页仍保留 configure/copy（Step2 兜底）
        assert "configureAi" in html, "Missing configureAi (guide Step2)"
        assert "copyAiPrompt" in html, "Missing copyAiPrompt (复制 prompt 兜底)"

    def test_stage3_css_classes(self):
        """阶段三新增样式类在 components.css"""
        css = COMPONENTS_CSS.read_text(encoding="utf-8")
        for cls in ["guide-steps", "guide-steps__dot", "guide-steps__dot--active",
                    "guide-steps__dot--done", "guide-steps__line",
                    "ai-config-item", "ai-config-item__status", "ai-config-item__actions",
                    "settings-nav", "settings-nav__item", "settings-nav__item--active",
                    "settings-modal", "settings-body", "settings-card",
                    "theme-picker", "color-mode-seg", "ai-platform-row",
                    "ai-platform-row__name", "ai-platform-row__state",
                    "toggle", "toggle--on-soft", "toggle--off-soft", "toggle--failed",
                    "ai-platform-fallback", "settings-card__row",
                    "ai-platform-row__connection", "connection-tip",
                    "connection-dot", "connection-dot--not_connected",
                    "connection-dot--connected", "connection-dot--inactive",
                    "connection-dot--lost", "connection-dot--disabled",
                    "connection-text", "connection-text--not_connected",
                    "connection-text--connected", "connection-text--inactive",
                    "connection-text--lost", "connection-text--disabled",
                    "connection-tip__bubble",
                    "btn--deeplink"]:
            assert f".{cls}" in css, f"Missing CSS class: .{cls}"

    def test_stage3_css_toggle_knob_slides(self):
        """toggle__knob 有 transform 过渡：knob 滑动动画（0.42s = 0.06s × 7）"""
        css = COMPONENTS_CSS.read_text(encoding="utf-8")
        marker = ".toggle__knob {"
        assert marker in css, "Missing .toggle__knob rule"
        seg = css[css.index(marker):]
        seg = seg[:seg.index("}") + 1]  # 截断到规则块结束
        assert "transform" in seg, "toggle__knob 缺少 transform 过渡（knob 无滑动动画）"
        assert "0.42s" in seg, "knob 滑动时长应为 0.06s 整数倍（0.42s = 0.06 × 7）"

    def test_stage3_css_uses_tokens_not_new_colors(self):
        """阶段三样式必须复用 design token（不引入硬编码十六进制颜色）"""
        css = COMPONENTS_CSS.read_text(encoding="utf-8")
        marker = "阶段三 · 引导页三步向导 + 配置 modal（5 平级左导航 + 分组页 5 态开关）"
        assert marker in css, f"Missing stage3 CSS section marker: {marker}"
        block = css[css.index(marker):]
        for hexcolor in ["#f00", "#ff0000", "#e74c3c", "#dc3545", "#27ae60", "#f39c12"]:
            assert hexcolor not in block, f"Hardcoded color in stage3 CSS: {hexcolor}"
        # 语义色必须走 token
        assert "--color-success" in block, "success must use --color-success token"
        assert "--accent" in block, "active nav must use --accent token"
        assert "--card-glass-bg" in block, "settings-card must use --card-glass-bg token"
        # 不应引用不存在的 --border-color
        assert "--border-color" not in block, "must not use non-existent --border-color token"


# ═══════════════════════════════════════════════════════════════════════════
# 构建测试
# ═══════════════════════════════════════════════════════════════════════════


class TestStage3Build:
    def test_standalone_contains_stage3(self):
        assert STANDALONE.exists(), "Standalone not built. Run: python3 build.py"
        content = STANDALONE.read_text(encoding="utf-8")
        checks = [
            "getClientConfig", "setClientConfig", "deleteClientConfig", "clientConfig",
            "guide-steps", "初始化 AI 协作", "初始化完成",
            "settings-nav", "settings-card", "ai-platform-row",
            "复制 prompt 给 AI", "saveSettingsIdentity", "configureAi",
            "Claude Code", "toggle--failed", "重新检测", "clientInstalled",
            "connectionClass", "connectionLabel", "connectionTooltip",
            "connection-tip", "connection-dot",
        ]
        for c in checks:
            assert c in content, f"Standalone missing stage3 content: {c}"


# ═══════════════════════════════════════════════════════════════════════════
# 浏览器渲染测试（复用 conftest fixtures：backend_running/static_server/browser/page）
# ═══════════════════════════════════════════════════════════════════════════


class TestStage3Browser:
    """浏览器渲染验证。只 GET 检测 + 渲染，不实际 POST 写入用户全局配置。"""

    def _open_settings(self, page):
        """打开 user-menu 下拉并点击「设置」"""
        page.locator(".user-menu__trigger").click()
        page.locator(".user-menu__item", has_text="设置").click()
        page.wait_for_timeout(800)

    def test_settings_modal_opens(self, static_server, page, backend_running):
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(2500)
        self._open_settings(page)
        expect(page.locator(".settings-modal")).to_be_visible(timeout=5000)
        # 左侧 5 平级导航 + 账号卡默认显示
        expect(page.locator(".settings-nav__item", has_text="账号")).to_be_visible(timeout=3000)
        expect(page.locator(".settings-nav__item", has_text="通用")).to_be_visible(timeout=3000)
        expect(page.locator(".settings-nav__item", has_text="MCP")).to_be_visible(timeout=3000)
        expect(page.locator(".settings-nav__item", has_text="Hooks")).to_be_visible(timeout=3000)
        expect(page.locator(".settings-nav__item", has_text="Agents")).to_be_visible(timeout=3000)
        expect(page.locator(".settings-card", has_text="头像与名称")).to_be_visible(timeout=3000)

    def test_settings_nav_switch_groups(self, static_server, page, backend_running):
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(2500)
        self._open_settings(page)
        # 切到「通用」
        page.locator(".settings-nav__item", has_text="通用").click()
        page.wait_for_timeout(300)
        expect(page.locator(".settings-card", has_text="外观")).to_be_visible(timeout=3000)
        expect(page.locator(".settings-card", has_text="重新运行初始化引导")).to_be_visible(timeout=3000)
        expect(page.locator(".settings-card", has_text="关于")).to_be_visible(timeout=3000)
        # 切到「MCP」：MCP 服务状态卡 + 平台行 toggle
        page.locator(".settings-nav__item", has_text="MCP").click()
        page.wait_for_timeout(300)
        expect(page.locator(".settings-card", has_text="MCP 服务状态")).to_be_visible(timeout=3000)
        expect(page.locator(".ai-platform-row").first).to_be_visible(timeout=3000)
        expect(page.locator(".toggle").first).to_be_visible(timeout=3000)
        # 切到「Hooks」
        page.locator(".settings-nav__item", has_text="Hooks").click()
        page.wait_for_timeout(300)
        expect(page.locator(".settings-card", has_text="Hooks 服务状态")).to_be_visible(timeout=3000)
        # 切到「Agents」（页面标题为 Agent 服务状态）
        page.locator(".settings-nav__item", has_text="Agents").click()
        page.wait_for_timeout(300)
        expect(page.locator(".settings-card", has_text="Agent 服务状态")).to_be_visible(timeout=3000)

    def test_toggle_knob_slides_with_transform(self, static_server, page, backend_running):
        """knob 滑动动画真实生效：computed transition-property 含 transform、
        时长 0.42s（0.06s × 7）。只读不写，不触达用户全局配置。"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(2500)
        self._open_settings(page)
        page.locator(".settings-nav__item", has_text="MCP").click()
        page.wait_for_timeout(300)
        expect(page.locator(".toggle__knob").first).to_be_visible(timeout=3000)
        props = page.locator(".toggle__knob").first.evaluate(
            "el => getComputedStyle(el).transitionProperty")
        assert "transform" in props, f"knob transition-property 缺 transform: {props}"
        dur = page.locator(".toggle__knob").first.evaluate(
            "el => getComputedStyle(el).transitionDuration")
        assert "0.42" in dur, f"knob transition-duration 应为 0.42s: {dur}"

    def test_settings_mcp_connection_ui(self, static_server, page, backend_running):
        """连接态 UI：MCP 卡平台行右显示 10px dot + 文本 + tooltip（仅 MCP 卡）；
        置灰仅 !installed（ClaudeCode 未安装 → disabled）；Hooks/Agents 页不显示连接态。
        只读不写，不触达用户全局配置。"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(2500)
        self._open_settings(page)
        # MCP 页：连接态区可见（每平台一行，platformsForKind('mcp') = 4 平台）
        page.locator(".settings-nav__item", has_text="MCP").click()
        page.wait_for_timeout(300)
        expect(page.locator(".ai-platform-row__connection").first).to_be_visible(timeout=3000)
        expect(page.locator(".connection-tip").first).to_be_visible(timeout=3000)
        expect(page.locator(".connection-dot").first).to_be_visible(timeout=3000)
        # 连接文本非空（未连接/已连接/未激活/已断联 之一）
        texts = page.locator(".connection-text").all_inner_texts()
        assert texts and all(t.strip() for t in texts), f"连接文本不应为空: {texts}"
        # 置灰仅 !installed：所有平台行 dot class 必须属于连接态类；未装平台（disabled）与
        # 已装平台（真实四态）并存——未安装的 ClaudeCode/ClaudeDesktop → disabled，已安装
        # 的 CodeBuddyIDE/WorkBuddy → 非 disabled（显示真实 connection）
        dot_classes = page.locator(".connection-dot").evaluate_all(
            "els => els.map(e => e.className)")
        valid = ["not_connected", "connected", "inactive", "lost", "disabled"]
        for cls in dot_classes:
            assert any(f"connection-dot--{s}" in cls for s in valid), f"连接态 dot 类非法: {cls}"
        assert any("connection-dot--disabled" in c for c in dot_classes), \
            f"应有未安装平台置灰(disabled): {dot_classes}"
        assert any("connection-dot--disabled" not in c for c in dot_classes), \
            f"已安装平台应显示真实 connection（非 disabled）: {dot_classes}"
        # Hooks 页：连接态不显示（x-show kind.key === 'mcp' 隐藏）
        page.locator(".settings-nav__item", has_text="Hooks").click()
        page.wait_for_timeout(300)
        expect(page.locator(".ai-platform-row__connection").first).not_to_be_visible(timeout=3000)
        # 回到 MCP 页连接态恢复可见（x-show 切换正常）
        page.locator(".settings-nav__item", has_text="MCP").click()
        page.wait_for_timeout(300)
        expect(page.locator(".ai-platform-row__connection").first).to_be_visible(timeout=3000)

    def test_enchante_grouping_and_deeplink(self, static_server, page, backend_running):
        """Enchante 分组归属 + MCP 卡 deeplink 按钮（kind 过滤升级回归）：
        Enchante 出现在 MCP + Agent 分组（MCP 行=生成专属链接按钮、Agent 行=toggle），Hooks 分组不出现；
        连接态对 Enchante 正常显示。"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(2500)
        # 打开设置 → MCP
        page.click(".user-menu__trigger")
        page.wait_for_timeout(200)
        page.locator(".user-menu__item", has_text="设置").click()
        page.wait_for_timeout(800)
        page.locator(".settings-nav__item", has_text="MCP").click()
        page.wait_for_timeout(400)
        # MCP 分组：Enchante 行存在，且显示 deeplink 按钮（无 toggle）
        enchante_mcp = page.locator(".ai-platform-row[data-platform='Enchante'][data-kind='mcp']")
        expect(enchante_mcp).to_be_visible(timeout=3000)
        expect(enchante_mcp.locator(".btn--deeplink")).to_be_visible(timeout=3000)
        expect(enchante_mcp.locator(".toggle")).not_to_be_visible(timeout=3000)
        # MCP 分组：现有 4 平台仍显示 toggle（不回归）
        for plat in ["ClaudeCode", "ClaudeDesktop", "CodeBuddyIDE", "WorkBuddy"]:
            row = page.locator(f".ai-platform-row[data-platform='{plat}'][data-kind='mcp']")
            expect(row).to_be_visible(timeout=3000)
            expect(row.locator(".toggle")).to_be_visible(timeout=3000)
        # Enchante MCP 行连接态正常显示（connection 字段含 Enchante）
        expect(enchante_mcp.locator(".connection-tip")).to_be_visible(timeout=3000)
        # Agent 分组：Enchante 行存在且为普通 toggle（write_kind agent 写 SKILL.md）
        page.locator(".settings-nav__item", has_text="Agents").click()
        page.wait_for_timeout(400)
        enchante_agent = page.locator(".ai-platform-row[data-platform='Enchante'][data-kind='agent']")
        expect(enchante_agent).to_be_visible(timeout=3000)
        expect(enchante_agent.locator(".toggle")).to_be_visible(timeout=3000)
        expect(enchante_agent.locator(".btn--deeplink")).not_to_be_visible(timeout=3000)
        # Hooks 分组：Enchante 不出现（kinds=["mcp","agent"] 无 hooks）。
        # 注意 settings 三卡（MCP/Hooks/Agents）均在 DOM，x-show 切显隐——故断言 Hooks 卡内无 Enchante 行，
        # 且所有 Enchante 行（MCP/Agents 卡里的）当前均不可见
        page.locator(".settings-nav__item", has_text="Hooks").click()
        page.wait_for_timeout(400)
        hooks_card = page.locator(".settings-card", has_text="Hooks 服务状态")
        expect(hooks_card.locator(".ai-platform-row[data-platform='Enchante']")).to_have_count(0)
        enchante_rows = page.locator(".ai-platform-row[data-platform='Enchante']")
        expect(enchante_rows.first).not_to_be_visible(timeout=3000)
        # 现有平台在 Hooks 分组仍显示（不回归）
        expect(page.locator(".ai-platform-row[data-platform='CodeBuddyIDE'][data-kind='hooks']")).to_be_visible(timeout=3000)
        expect(page.locator(".ai-platform-row[data-platform='ClaudeCode'][data-kind='hooks']")).to_be_visible(timeout=3000)
        expect(page.locator(".ai-platform-row[data-platform='WorkBuddy'][data-kind='hooks']")).to_be_visible(timeout=3000)
        # ClaudeDesktop 仅 MCP：Hooks 卡内不出现（kinds=["mcp"]）
        expect(hooks_card.locator(".ai-platform-row[data-platform='ClaudeDesktop']")).to_have_count(0)

    def test_guide_wizard_three_steps(self, static_server, page, backend_running):
        """引导页三步向导：从配置 modal「重新运行初始化引导」进入，Step1→Step2→Step3"""
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(2500)
        # 通过配置 modal 通用卡「重新运行初始化引导」进入（身份已设置时唯一入口）
        self._open_settings(page)
        page.locator(".settings-nav__item", has_text="通用").click()
        page.wait_for_timeout(300)
        page.locator("button", has_text="重新运行初始化引导").click()
        page.wait_for_timeout(800)
        # Step1 身份（重新引导后身份已有值，直接可下一步）
        setup = page.locator(".modal--setup")
        expect(setup).to_be_visible(timeout=5000)
        expect(page.locator(".modal--setup", has_text="设置你的昵称和邮箱")).to_be_visible(timeout=5000)
        setup.locator("input[placeholder='如：张三']").fill("测试用户")
        setup.locator("input[placeholder='如：zhangsan@example.com']").fill("test@example.com")
        setup.locator("button", has_text="下一步").first.click()
        page.wait_for_timeout(800)
        expect(page.locator(".modal--setup", has_text="初始化 AI 协作")).to_be_visible(timeout=5000)
        expect(page.locator(".ai-config-item").first).to_be_visible(timeout=3000)
        # 进入 Step3（Step2 的「下一步」在 DOM 中位于 Step1 之后，用 .last）
        page.locator(".modal--setup button", has_text="下一步").last.click()
        page.wait_for_timeout(800)
        expect(page.locator(".modal--setup", has_text="初始化完成")).to_be_visible(timeout=5000)
        expect(page.locator(".modal--setup", has_text="开始使用")).to_be_visible(timeout=3000)

    def test_console_clean(self, static_server, page, backend_running):
        """配置 modal 打开 + 分组切换后 console 无前端 JS 报错。

        用 console error 断言（与现有 test_health 一致），过滤两类环境性错误：
        1. "Failed to load resource" — 资源/网络 404（如 8080 后端旧进程未加载
           /api/client-config 时，属后端版本环境问题，非前端 JS 错误）
        注：不用 pageerror——conftest 的 toast 捕获 init_script 与 tiptap 编辑器
        初始化时序冲突会产生既有 pageerror（stash 掉阶段三改动后依然存在），
        与本次功能无关。"""
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(f"{static_server}#dashboard")
        page.wait_for_timeout(2500)
        self._open_settings(page)
        for g in ["通用", "MCP", "Hooks", "Agents", "账号"]:
            page.locator(".settings-nav__item", has_text=g).click()
            page.wait_for_timeout(200)
        real = [e for e in errors if "Failed to load resource" not in e]
        assert not real, f"Console JS errors: {real}"
