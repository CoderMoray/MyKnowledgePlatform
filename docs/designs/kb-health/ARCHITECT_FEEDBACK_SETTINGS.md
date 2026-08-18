# 前端视觉设计 agent → 架构师/前端开发 agent：设置 Modal 最终版设计反馈（5 平级 + Claude Code + client_installed 5 态）

> 作者：前端视觉/交互设计 agent
> 日期：2026-08-18
> 状态：**视觉设计最终版已完成**，待前端开发 agent 按最终规范实施 + 测试
> 用途：本反馈覆盖「设置 Modal 设计更新到最终版」任务的**最终设计交付物**与**3 处追加决策**。可直接转发架构师/前端开发 agent。

---

## 〇、一句话结论

按你（架构师）的 4 个裁决，把设计更新到最终版：
1. ✅ **导航 5 平级**（账号 / 通用 / MCP / Hooks / Agents，**无「AI 协作」分组标签**）
2. ✅ **fallback 自动消失 5 秒**
3. ✅ **遮罩仅 settings modal 加深到 0.35**
4. ✅ **纯 CSS toggle（无动画库）**

+ 3 处最终版追加：
5. ✅ **平台标签「Claude」→「Claude Code」**
6. ✅ **`client_installed` 5 态状态机**（3 态 × 平台级 bool，**新增「浅色开」+「请在安装 Claude Code 后使用」**）
7. ✅ **SVG 视觉稿 + 规范同步更新**

**视觉稿 SVG**：`docs/designs/kb-health/export/99_57-20260818_111503579.svg`（Frame G4f 最终版）
**设计规范**：`docs/designs/kb-health/SETTINGS_REDESIGN_SPEC.md`（已更新为最终版）
**截图**：`docs/designs/kb-health/screenshots/screenshot-99_57-20260818_111443509.png`

---

## 一、3 处最终版追加（覆盖早前规范）

### 1.1 ① 导航改 5 平级

**早前方案**（§1.2 原稿）：账号 / 通用 / **AI 协作分组标签** / MCP（缩进）/ Hooks（缩进）/ Agents（缩进）

**最终版**：账号 / 通用 / **MCP / Hooks / Agents**（5 平级按钮，**无「AI 协作」分组标签、无子项缩进**）

**为什么 5 平级**（架构师裁决）：
- 用户最初明确此意图，尊重其意图
- 三个 kind 平级展示，每个 kind 一页，直接清晰
- 实现最低成本（`settingsGroup` 单值 5 枚举）
- **取消** §1.6 的分组标签 div 和 §1.7 的 `.settings-nav__group-label` / `.settings-nav__item--child`

**HTML/CSS 改动**：
- 5 个 `<button class="settings-nav__item">`（不带 `--child`）
- **不实现** §1.7 的 nav 新增 CSS（沿用现有 `.settings-nav__item` / `.settings-nav__item--active`）

### 1.2 ② 平台标签「Claude」→「Claude Code」

**改 store.js `clientPlatforms`**：
```js
clientPlatforms: [
  { key: "claude",    label: "Claude Code" },  // ← 从 "Claude" 改为 "Claude Code"
  { key: "codebuddy", label: "CodeBuddy" },
],
```

**全文/SVG 同步**：「Claude」→「**Claude Code**」（codebuddy 保持「CodeBuddy」）；提示文本用 `{客户端}` 变量（如「请在安装 Claude Code 后使用」）。

### 1.3 ③ `client_installed` 5 态状态机（核心追加）

**后端契约**（已就绪）：`GET /api/client-config` → `{claude: {client_installed, mcp, hooks, agent}, codebuddy: {...}}`
- `client_installed` = 平台级 bool（客户端是否安装）
- `mcp/hooks/agent` = kind 级 bool

**3 态扩展为 5 态**（`clientStatus` true/false/null × `clientInstalled` true/false）：

| # | 状态 | 判定 | 开关 | 状态点 | 状态文本 |
|---|------|------|------|--------|---------|
| 1 | **已就绪** | installed + true | `toggle--on`（accent 实色） | success 绿 | "已配置" |
| 2 | **未配置** | installed + false | `toggle--off`（灰 track） | muted 灰 | "未配置 · 点击开关开启" |
| 3 | **已写配置但客户端未装** | !installed + true | **`toggle--on-soft`**（accent 40% 浅色开）| success 绿(淡) | "请在安装 {客户端} 后使用" |
| 4 | **客户端未装且未配置** | !installed + false | **`toggle--off-soft`**（e5e7eb 浅色关） | muted 灰(淡) | "请先安装 {客户端}" |
| 5 | **检测失败** | clientStatus === null | `toggle--failed`（灰 opacity 0.4） | warning 橙 | "检测失败 · 点击重新检测"（红字 500）|

**关键决策**：
- **!installed 时开关仍可点**（用户裁决：置灰但可交互）——点开关写配置（后端 mkdir），成功后显示「浅色开 + 请在安装 X 后使用」
- **新增「浅色开」视觉**（`.toggle--on-soft`：accent 40% 透明度，比实色开浅；`.toggle--off-soft`：#e5e7eb 比普通关更淡）——区分「已配置（装好）」vs「已写配置但未装」
- **状态点 !installed 时 opacity 0.5**（视觉与文本提示一致，弱化语义）
- **`clientInstalled(platform)` 新增**：返回 `this.clientConfig?.[platform]?.client_installed`（undefined 按未安装处理）

**HTML 5 态开关 class**：
```html
:class="{
  'toggle--on':       clientStatus === true  && clientInstalled,
  'toggle--off':      clientStatus === false && clientInstalled,
  'toggle--on-soft':  clientStatus === true  && !clientInstalled,
  'toggle--off-soft': clientStatus === false && !clientInstalled,
  'toggle--failed':   clientStatus === null
}"
```

---

## 二、SVG 视觉稿最终版（Frame G4f）

`docs/designs/kb-health/export/99_57-20260818_111503579.svg`

**Frame G4f · 设置 Modal 最终版** 包含：

**左导航 5 平级**：
- 账号 / 通用 / MCP(active) / Hooks / Agents
- 5 项**平级对齐**（无「AI 协作」分组标签、无子项缩进）
- 底部版本号 v1.0.0

**右半页 MCP 页**（active 组）：
- 标题"MCP" + 副说明"AI 客户端直连本地知识库工具"（secondary 灰可读）
- 右上「重新检测」按钮
- MCP 卡内 **5 态演示**（4 行 + fallback）：
  1. **Claude Code**（绿点 + "已配置" + `installed+true` + **实色开**）→ 已就绪
  2. **Claude Code · MCP**（淡绿点 + "请在安装 Claude Code 后使用" + `!installed+true` + **浅色开**）→ 已写配置但未装（**新演示**）
  3. **CodeBuddy**（灰点 + "未配置 · 点击开关开启" + `installed+false` + 关）→ 未配置
  4. **CodeBuddy · MCP**（橙点 + "检测失败 · 点击重新检测"红字 + `null` + 灰禁用）→ 检测失败
  5. **fallback 可交互文本**：accent 紫淡底"配置失败 · 一键复制 prompt 给你的 AI →"

截图：`screenshots/screenshot-99_57-20260818_111443509.png`

---

## 三、待前端开发 agent 实施（按最终版）

按 `SETTINGS_REDESIGN_SPEC.md`（已更新）实施：

1. **`frontend/index.html`**：
   - L1722-1759：5 平级 nav item（**不实现** group-label/child）
   - L1839-1865：5 态开关 + 5 态状态文本（HTML 已在 §2.5 给出最终版）
2. **`frontend/js/store.js`**：
   - `clientPlatforms` 改 label 为「Claude Code」
   - `data()` 加 `clientFallback`
   - 新增 `clientInstalled(platform)`
   - `configureClient` catch 块：设置 `clientFallback` + 5 秒清除
   - `settingsGroup` 接受 5 个值（`account/general/mcp/hooks/agent`）
3. **`frontend/css/components.css`**：
   - **不实现** `.settings-nav__group-label` / `.settings-nav__item--child`
   - 新增：`.ai-platform-row__state--soft`、`.toggle--on-soft`、`.toggle--off-soft`
   - 保留：`.toggle` / `.toggle__knob` / `.toggle--on/off/failed`、`.ai-platform-fallback`、`.settings-card__row`

---

## 四、需架构师确认的边界（已裁决，2026-08-18）

> 以下为架构师最终裁决记录，前端开发 agent **照此实施**，勿偏离。

1. **5 平级最终决策** ✅ 认可（账号/通用/MCP/Hooks/Agents）
2. **浅色开视觉（accent 40%）** ✅ 认可。40% 透明度足够区分「已配置（装好）」vs「已写配置但未装」，且不喧宾夺主。
3. **!installed 开关可点（置灰但可交互）** ✅ 认可。符合用户「置灰但可交互」决策；后端 mkdir 写配置 + 成功后浅色开 + 安装提示。
4. **5 态 UI 对比强度** ⚠️ **暂不加 badge「未安装」**。当前「浅色开关 + 安装提示文本」已足够区分；**加 badge 会增视觉噪音，不实现**。若后续觉得不清晰再加。

> **实施硬约束**：前端开发 agent **不要**新增「未安装」badge/标签。仅用「浅色开关（on-soft/off-soft）+ 安装提示文本」表达 !installed 态。

---

## 五、零修改声明（视觉设计 agent 部分）

- `frontend/*.js / *.html`：未改（**待前端开发 agent 按最终版规范实施**）
- `backend/`：未改
- `design-tokens.css`：零 token 增量（**所有新样式类复用现有 token**：accent、accent-subtle、color-success/danger、border-subtle、text-primary/secondary/tertiary、radius-md、text-xs/sm/2xs、transition-interactive）

---

*本反馈 + `SETTINGS_REDESIGN_SPEC.md`（已更新为最终版）+ Frame G4f SVG = 最终版设计交付完整三件套。前端开发 agent 据此施工，架构师拍板边界决策。*