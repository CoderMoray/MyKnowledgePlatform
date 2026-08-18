# AI 客户端配置页「连接检测」状态设计规范

> 作者：前端视觉/交互设计 agent
> 日期：2026-08-18
> 用途：本规范为「AI 客户端配置页增加连接检测状态展示」任务的设计权威。前端开发 agent 据此实施。
> 前置：与现有「配置检测」（configured 5 态开关，`SETTINGS_REDESIGN_SPEC.md` + `frontend/index.html:1877-1911`）**协调共存，不冲突**。

---

## 〇、TL;DR

在设置 Modal 的 **MCP 卡**内，为每个平台行新增**平台级连接态展示**（`connection` 四态：not_connected / connected / inactive / lost），与现有**配置态 5 态开关****双维度并排**：

```
[配置态dot] Claude Code  [配置文本]  [toggle]  │  [连接态dot] [连接文本] ●tooltip
```

- **配置态**（左）：kind 粒度，现有 5 态开关（已落地，不动）
- **连接态**（右）：平台粒度，`connection` 四态（dot + 文本 + tooltip）
- **双 dot 区分**：配置态 dot = 实心 8px；连接态 dot = **带白描边 10px 圆环**（色盲可辨识 + 视觉分离）
- **tooltip**：纯 CSS hover 气泡（不引 JS 库）

---

## 一、四状态视觉定义（connection）

### 1.1 状态判定与语义

| 状态 | 后端值 | 语义 |
|------|--------|------|
| 未连接 | `not_connected` | 该平台从未连接过 MyKnowledge |
| 已连接 | `connected` | 平台近期正在使用 MyKnowledge 的 MCP，可正常调用知识库工具 |
| 未激活 | `inactive` | 平台较长时间未调用 MCP，可能空闲或已停用 |
| 已断联 | `lost` | 已判定断联（平台退出或 MCP 被关闭） |

### 1.2 dot 视觉（色值引用 design-tokens）

| 状态 | dot 颜色 | token | 描边 | 形状 |
|------|----------|-------|------|------|
| 未连接 | 灰 | `var(--text-muted)` | 无 | 10px 圆 + 白描边 |
| 已连接 | 绿 | `var(--color-success)` | 无 | 10px 圆 + 白描边 |
| 未激活 | 黄 | `var(--color-warning)` | 无 | 10px 圆 + 白描边 |
| 已断联 | 红 | `var(--color-danger)` | 无 | 10px 圆 + 白描边 |

**尺寸**：10px（比配置态 dot 8px 大），**带 1.5px 白描边**（`box-shadow: 0 0 0 1.5px var(--card-glass-bg)`）→ 在浅色/卡片背景上清晰，且**与配置态实心 8px 点视觉区分**。

**色盲可辨识**：dot 颜色 + 状态文本**双重表达**；不依赖单色。黄(未激活)与绿(已连接)对红绿色盲用户通过文本区分。

### 1.3 状态文本（行内，紧邻 dot）

| 状态 | 文案 | 颜色 |
|------|------|------|
| 未连接 | `未连接` | `--text-muted` |
| 已连接 | `已连接` | `--color-success` |
| 未激活 | `未激活` | `--color-warning` |
| 已断联 | `已断联` | `--color-danger` |

> 文本 + dot 双重表达，色盲友好。文案简短（tooltip 承载完整解释）。

---

## 二、tooltip（hover 一句话气泡）

### 2.1 触发

- 悬停**连接态 dot** 或 **连接文本**（`hover`）时显示
- **touch 触屏**：`hover` 失效 → 用 **`focus`**（点击 dot 聚焦显示）+ 提供**可点查看**（或读屏朗读 title）

### 2.2 四状态 tooltip 文案

| 状态 | tooltip 文案 |
|------|-------------|
| 未连接 | 该平台从未连接过 MyKnowledge，配置后在此显示实时连接状态 |
| 已连接 | 平台近期正在使用 MyKnowledge 的 MCP，可正常调用知识库工具 |
| 未激活 | 平台较长时间未调用 MCP，可能处于空闲或已停用；到平台使用一次 MyKnowledge 即可确认 |
| 已断联 | 已判定断联（可能平台退出或 MCP 被关闭）；请到该平台重新使用一次 MyKnowledge 以重新激活 |

### 2.3 tooltip 视觉（纯 CSS）

| 属性 | 值 |
|------|-----|
| 位置 | **dot/文本上方 8px**（`bottom: calc(100% + 8px)`），水平对齐（`transform: translateX(-50%)` 居中于目标），箭头朝下 |
| 背景 | `--bg-tertiary`（深灰，`#ebebeb`）或实心 `#111827` + 白字（高对比）|
| 文字颜色 | 白（`#fff`）on 深底 |
| 字号 | `--text-2xs`（10px） |
| 圆角 | `--radius-sm`（4px） |
| padding | 6px 10px |
| 箭头 | 底部 6px 三角（`::before` 三角形，指向目标） |
| 阴影 | `--shadow-card` |
| 延迟 | `transition-delay: 200ms`（防误触闪烁） |
| z-index | 高于 modal（`z-index: 20`） |

**实现**：`.connection-tip` 包裹 dot+文本，`:hover` / `:focus` 时显示子 `.connection-tip__bubble`。**纯 CSS，不引 JS 库**。同时给连接元素加 `aria-label` / `title`（读屏 + 触屏 fallback）。

---

## 三、与现有「配置检测 5 态开关」的协调（核心组合规则）

### 3.1 双维度并存（不冲突）

| 维度 | 粒度 | 位置 | 视觉 |
|------|------|------|------|
| **配置态**（现有） | kind 级（mcp/hooks/agent） | 行左 | 8px 实心 dot + 配置文本 + toggle |
| **连接态**（新增） | **平台级**（connection） | 行右（toggle 右侧）| 10px 描边 dot + 连接文本 + tooltip |

### 3.2 为什么连接态放「平台行右」

- **connection 是平台级**（后端每平台返回一个 connection），而配置态是 kind 级（同一平台有 mcp/hooks/agent 三行）
- 若放某 kind 行内会**重复 3 次**（每 kind 显示同平台连接态）
- **连接态仅在 MCP 卡展示**（MCP 是"平台直连知识库"的实时通道，有连接概念；hooks/agent 是静态文件配置，无连接）
- 放**平台行右（toggle 右侧）**：平台粒度对齐，不拥挤

> **注意**：连接态与**平台**绑定，仅 MCP 卡每平台一行显示一次；Hooks/Agents 卡**不显示连接态**（静态配置）。

### 3.3 连接态与配置态 dot 的视觉分离

- **配置态 dot**：8px 实心（现有 `.status-indicator__dot`），表达"是否配置好"
- **连接态 dot**：10px + 白描边（新 `.connection-dot`），表达"实时连接"
- **间距**：两 dot 组间用 `margin-left: 16px` 分隔，或用 `│` 竖分隔线（`--border-subtle`）

### 3.4 连接态是否影响 toggle 可交互

**不影响 toggle 的可交互性**。toggle 只由配置态（clientStatus + clientInstalled）决定（现有逻辑不动）。
连接态是**只读展示**，不改变 toggle 状态。

**组合语义**（配置态 × 连接态，供前端参考，非强制）：
- 配置开 + 已连接：`已配置 · 已连接`（正常使用中）
- 配置开 + 未激活：`已配置 · 未激活`（配了但空闲）
- 配置开 + 已断联：`已配置 · 已断联`（配了但 MCP 关了，建议重新激活）
- 配置开 + 未连接：`已配置 · 未连接`（配了但从未连上）
- 配置关 + 任意连接：**installed 时显示真实 connection**（见 §3.5，不再置灰）

> 详细组合矩阵见 §3.5。

### 3.5 配置态 × 连接态组合矩阵（前端判定参考）

> **置灰规则（架构师修订，2026-08-18）**：连接态置灰**仅当 `!installed`**；**installed 的平台（无论 configured on/off/null）直接显示真实 connection**。
> 原因：部分平台（如 Enchante）配置检测恒 False（deeplink 无配置文件）但 connection 有效，若按"配置未就绪→置灰"会误置灰使其连接检测失效。

| 判定依据 | 连接态呈现 | 行内示例 |
|----------|-----------|----------|
| `!installed`（无论 configured）| **置灰**（opacity 0.4 + 文本"未连接"）+ 配置文本"请先安装 {客户端}" | `请先安装 Claude Code  │  ⊙未连接(灰)` |
| `installed` + 已配置(on) + connected | **真实 connection**：绿"已连接" | `已配置  │  ●已连接(绿)` |
| `installed` + 已配置(on) + inactive | **真实 connection**：黄"未激活" | `已配置  │  ●未激活(黄)` |
| `installed` + 已配置(on) + lost | **真实 connection**：红"已断联" | `已配置  │  ●已断联(红)` |
| `installed` + 已配置(on) + not_connected | **真实 connection**：灰"未连接" | `已配置  │  ●未连接(灰)` |
| `installed` + 未配置(off) + 任意 | **真实 connection**（显示实际四态）| `未配置  │  ●已连接(绿)` |
| `installed` + 检测失败(null) + 任意 | **真实 connection**（显示实际四态）+ 配置文本"检测失败" | `检测失败  │  ●已连接(绿)` |

**简化判定（前端实现）**：
```js
// 连接态置灰判定：仅 !installed 置灰；installed 平台显示真实 connection
function connectionDisabled(platform) {
  return !clientInstalled(platform);  // undefined 按未安装 → 置灰
}
// 连接态视觉：installed 且非 disabled 时，用真实 connection 四态；disabled 时灰+未连接
```

> **核心**：`installed` 是连接态是否置灰的**唯一依据**；`configured（on/off/null）` 不参与置灰，仅决定配置文本与 toggle。

---

## 四、多平台并存布局

### 4.1 平台列表

ClaudeCode / ClaudeDesktop / CodeBuddyIDE / WorkBuddy（及未来 Enchante）。

> 现有 `clientPlatforms`（`store.js:1301`）当前为 claude/codebuddy（label：Claude Code / CodeBuddy）。**本次连接态设计需支持未来扩展**到上述 4+ 平台。前端开发 agent 在扩展 `clientPlatforms` 时，连接态自动适配。

### 4.2 行布局（不拥挤）

每平台一行（MCP 卡内），宽度约 500px（卡内可用）：

```
[dot][Claude Code][已配置][toggle]  │  [⊙][已连接]
```

- 左：配置态（dot + 名 + 配置文本 + toggle）占约 60%
- 右：连接态（dot + 连接文本 + tooltip）占约 40%，右对齐
- **行高**：36-40px（与现有 `.ai-platform-row` 一致）
- **连接文本较短**（未连接/已连接/未激活/已断联），不挤占 toggle
- 4 平台同列表时：每行高度不变，垂直滚动（卡内 max-height + overflow-y）

### 4.3 响应式

- 平台行 flex 布局；卡窄时连接态文本可省略为仅 dot（`@media` 或 `min-width` 隐藏文本），tooltip 保留完整语义

---

## 五、无障碍 / 边界

| 项 | 处理 |
|----|------|
| **色盲可辨识** | dot 颜色 + 状态文本双重表达；黄/绿不依赖单色 |
| **hover 触屏替代** | 连接元素加 `title` / `aria-label`；`focus` 也触发 tooltip |
| **读屏** | 连接态行加 `role="status"` / `aria-live="polite"`（状态变化时播报） |
| **键盘** | 连接态 dot 可 `tabindex="0"` + `focus` 显示 tooltip |
| **低对比** | tooltip 深底白字高对比；连接 dot 带白描边 |
| **不影响现有** | 不改配置态 5 态开关、不改 toggle 可交互、不改其他页面 |

---

## 六、新增样式类（components.css）

```css
/* 连接态容器（包裹 dot + 文本，用于 tooltip hover 定位） */
.connection-tip {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: help;
}
/* 连接态 dot：10px + 白描边（区分配置态实心 8px） */
.connection-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  box-shadow: 0 0 0 1.5px var(--card-glass-bg);
  flex-shrink: 0;
}
.connection-dot--not_connected { background: var(--text-muted); }
.connection-dot--connected     { background: var(--color-success); }
.connection-dot--inactive      { background: var(--color-warning); }
.connection-dot--lost          { background: var(--color-danger); }
.connection-dot--disabled      { background: var(--text-muted); opacity: 0.4; }  /* 仅 !installed 置灰（架构师修订）*/

/* 连接态文本 */
.connection-text { font-size: var(--text-xs); white-space: nowrap; }
.connection-text--not_connected { color: var(--text-muted); }
.connection-text--connected     { color: var(--color-success); }
.connection-text--inactive      { color: var(--color-warning); }
.connection-text--lost          { color: var(--color-danger); }
.connection-text--disabled      { color: var(--text-muted); opacity: 0.4; }

/* 连接态与配置态分隔 */
.ai-platform-row__connection {
  margin-left: 16px;
  padding-left: 16px;
  border-left: 1px solid var(--border-subtle);
}

/* tooltip 气泡（纯 CSS hover/focus） */
.connection-tip__bubble {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  width: max-content;
  max-width: 260px;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  background: #111827;
  color: #fff;
  font-size: var(--text-2xs);
  line-height: 1.5;
  text-align: left;
  box-shadow: var(--shadow-card);
  opacity: 0;
  visibility: hidden;
  transition: opacity var(--transition-interactive), visibility var(--transition-interactive);
  transition-delay: 200ms;
  z-index: 20;
  pointer-events: none;
}
.connection-tip:hover .connection-tip__bubble,
.connection-tip:focus .connection-tip__bubble {
  opacity: 1;
  visibility: visible;
}
/* 箭头：指向目标的小三角 */
.connection-tip__bubble::after {
  content: "";
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-top-color: #111827;
}
```

**无 design-token 增量**：全复用 `--text-muted` / `--color-success/warning/danger` / `--card-glass-bg` / `--border-subtle` / `--radius-sm` / `--text-2xs` / `--text-xs` / `--shadow-card` / `--transition-interactive`。

---

## 七、HTML 结构参考（MCP 卡平台行，供前端开发 agent）

```html
<!-- 现有配置态行（index.html:1877 之后，行右追加连接态） -->
<div class="ai-platform-row" :data-platform="plat.key" :data-kind="'mcp'">
  <!-- 左：配置态（现有，不动） -->
  <span class="status-indicator__dot" :class="...现有5态..."></span>
  <span class="ai-platform-row__name" x-text="plat.label"></span>
  <span class="ai-platform-row__state" :class="...现有5态..." x-text="..."></span>
  <button class="toggle" :class="...现有5态..." :disabled="..." @click="...">...</button>

  <!-- 右：连接态（新增） -->
  <div class="ai-platform-row__connection">
    <div class="connection-tip" tabindex="0"
         :title="$store.app.connectionTooltip(plat.key)"
         :aria-label="$store.app.connectionTooltip(plat.key)">
      <span class="connection-dot"
            :class="'connection-dot--' + ($store.app.connectionClass(plat.key))"></span>
      <span class="connection-text"
            :class="'connection-text--' + ($store.app.connectionClass(plat.key))"
            x-text="$store.app.connectionLabel(plat.key)"></span>
      <div class="connection-tip__bubble" x-text="$store.app.connectionTooltip(plat.key)"></div>
    </div>
  </div>
</div>
```

> 前端开发 agent 需在 store.js 加：
> - `connectionClass(platform)`：返回 `not_connected/connected/inactive/lost/disabled`。**判定**：`!clientInstalled(platform)` → `disabled`（置灰）；否则返回真实 connection 四态。
> - `connectionLabel(platform)`：返回 `未连接/已连接/未激活/已断联/未连接`（disabled 时返回"未连接"）
> - `connectionTooltip(platform)`：返回 §2.2 四态文案（disabled 时返回"该平台客户端未安装"或 §2.2 not_connected 文案）
> - `connection` 数据源：`this.clientConfig?.[platform]?.connection`（后端新增）
>
> **置灰判定唯一依据 = `clientInstalled(platform)`**；`configured`（on/off/null）不参与连接态置灰。

---

## 八、验收对照

| 验收点 | 验证 |
|--------|------|
| 四状态 dot 颜色正确 | 未连接灰 / 已连接绿 / 未激活黄 / 已断联红 |
| 状态文本正确 | 四态 + 置灰"未连接" |
| 与 5 态开关协调 | 配置态左 + 连接态右，双 dot 视觉区分，toggle 不受连接态影响 |
| tooltip 显示 | hover/focus 显示一句话气泡，箭头指向，200ms 延迟 |
| 多平台不拥挤 | 4 平台垂直排列，行高一致，可滚动 |
| 色盲可辨识 | dot 颜色 + 文本双重表达 |
| 触屏替代 | title / aria-label / focus 触发 |
| 构建通过 | `python3 frontend/build.py` |
| 后端回归 | `pytest tests/ --ignore=tests/frontend -q` |

---

## 九、零 token 增量 + 边界

- **零 design-token 增量**：全复用现有 token（见 §6）
- **不动后端**：`connection` 字段由后端新增，前端只消费
- **不改现有配置态视觉**：只新增连接态，不重做
- **不改其他页面**：仅设置 Modal MCP 卡平台行

---

*本规范与 `SETTINGS_REDESIGN_SPEC.md`（配置态 5 态）并存：配置态规范定义 toggle 5 态；本规范定义连接态四态 + 与配置态组合规则。两者共同构成 AI 客户端配置页完整状态体系。*
