# 前端视觉设计 agent → MyKnowledge 架构师：「连接检测状态」设计反馈

> 作者：前端视觉/交互设计 agent
> 日期：2026-08-18
> 用途：本反馈覆盖「AI 客户端配置页增加连接检测状态展示」任务的**设计交付物**与**关键决策**。可直接转发架构师。

---

## 〇、一句话结论

按你（架构师）的设计需求，产出**连接态四态 + tooltip + 与配置态协调**的完整设计规范与视觉稿：
- **四态**：not_connected 灰 / connected 绿 / inactive 黄 / lost 红
- **位置**：MCP 卡内每平台行**右侧**（toggle 之后），平台级 connection
- **与配置态协调**：双 dot 双维度——配置 8px 实心（左）+ 连接 10px **白描边**（右），竖分隔线
- **tooltip**：纯 CSS hover/focus 气泡（200ms 延迟，深底白字高对比 + 箭头）
- **零 design-token 增量**，与现有 5 态开关**共存不冲突**

**设计三件套**（存 `docs/designs/连接状态-ai-client/`）：
- `SPEC.md`（190 行，语义规范）
- `export/101_5-20260818_163709501.svg`（Frame H · MCP 卡 · 5 平台连接态视觉稿）
- `screenshots/screenshot-101_5-*.png`（人审参考）

---

## 一、范围与边界（明确）

| 项 | 状态 |
|---|---|
| **只做视觉/交互设计** | ✅（不写 HTML/JS 实现，那由前端开发 agent 执行） |
| **不改后端** | ✅（connection 字段由后端新增，前端只消费） |
| **不改连接检测阈值/机制** | ✅（架构已定，只呈现状态） |
| **不改现有配置态视觉** | ✅（配置态 5 态开关已落地于 `index.html:1877-1911`，不重做） |
| **零 design-token 增量** | ✅（全复用现有 token：--color-success/warning/danger、--text-muted、--card-glass-bg、--border-subtle、--radius-sm、--text-2xs/xs、--shadow-card、--transition-interactive） |

---

## 二、关键设计决策

### 2.1 连接态放在「MCP 卡内平台行右」

**为什么不是放 Hooks/Agent 卡**：
- connection 是**平台级**实时连接通道；MCP 正是「平台直连知识库」的实时通道
- hooks/agent 是静态文件配置，**无连接概念**
- 后端每平台返回一个 connection（平台级），kind 级无 connection

**为什么放行右**（toggle 之后）：
- 配置态（kind 级，行左）+ 连接态（平台级，行右）**双维度并排**
- 中间竖分隔线视觉分组
- 不重复：每个 kind 行（mcp/hooks/agent）都有配置态，但连接态只在 MCP 卡平台行显示一次

### 2.2 双 dot 视觉区分（防色盲 + 防冲突）

| 维度 | dot 视觉 | 表达 |
|------|----------|------|
| **配置态**（现有） | 8px **实心**圆 | 是否配置好（5 态） |
| **连接态**（新增） | 10px **带 1.5px 白描边**圆 | 实时连接（四态） |

**白描边**用 `box-shadow: 0 0 0 1.5px var(--card-glass-bg)`：在浅色卡片背景上清晰，且**视觉与配置态实心点形成对比**。

**色盲可辨识**：dot 颜色 + 状态文本**双重表达**（已连接/未激活/已断联/未连接 文本跟随颜色），不依赖单色。

**色彩冲突处理**：
- 配置态已配置 = success 绿（现有）
- 连接态 connected = success 绿（新）
- **冲突？**：不会——因为两者**位置分离**（左实心 8px vs 右描边 10px），且语义不同（"配好" vs "已连"）。同时 connected 绿文本 + 配置态"已配置"文本共存，表达"已配置 + 已连接"复合语义。

### 2.3 tooltip 设计（纯 CSS，无 JS 库）

| 属性 | 规范 |
|------|------|
| 触发 | `:hover` / `:focus`（触屏 tabindex=0 focus） |
| 文案 | 四态各一句（见 SPEC §2.2） |
| 位置 | 元素下方 8px，水平居中（`transform: translateX(-50%)`） |
| 视觉 | 深底（`#111827`）+ 白字 + `--text-2xs`（10px）+ `--radius-sm`（4px）圆角 + 底部 6px 三角箭头 + `--shadow-card` |
| 延迟 | `transition-delay: 200ms`（防误触） |
| z-index | 20（高于 modal） |
| 触屏 fallback | `title` + `aria-label`（读屏）+ `focus` 显示 |

### 2.4 配置态 × 连接态组合矩阵

| 配置态 | 连接态 | 行内呈现 |
|--------|--------|----------|
| 已配置 + connected | "已配置 · 已连接"（正常使用中） |
| 已配置 + inactive | "已配置 · 未激活"（配了但空闲） |
| 已配置 + lost | "已配置 · 已断联"（配了但 MCP 关闭） |
| 已配置 + not_connected | "已配置 · 未连接"（配了但从未连上） |
| 未配置 / 检测失败 / !installed | **连接态置灰**（opacity 0.4 + 文本"未连接"），避免与配置态语义混淆 |

**关键**：连接态**不影响 toggle 可交互**（toggle 只由配置态决定，现有逻辑不动）。

---

## 三、产物清单（本机绝对路径）

- **设计规范**：`docs/designs/连接状态-ai-client/SPEC.md`（190 行）
- **视觉稿 SVG**：`docs/designs/连接状态-ai-client/export/101_5-20260818_163709501.svg`（Frame H · MCP 卡）
- **人审截图**：
  - `screenshots/screenshot-101_5-*.png`（MCP 卡整体 · 5 平台连接态 + 图例）
  - `screenshots/screenshot-101_8-*.png`（行 1 局部 · ClaudeCode 已连接 + tooltip 箭头）

---

## 四、需架构师确认的决策

1. **连接态位置**（MCP 卡内平台行右）：
   - **我的决策**：仅 MCP 卡（因 connection 是平台级实时连接，hooks/agent 无连接概念）
   - **替代方案 A**：三个 kind 卡都显示连接态（每平台重复 3 次，不推荐）
   - **替代方案 B**：独立「连接状态」分组（顶部统一展示，无 toggle）
   - **请定夺我的决策是否符合预期**

2. **双 dot 视觉区分**（8px 实心 vs 10px 描边）：
   - 足够区分吗？色盲用户能辨识？
   - 是否需要更明显（如加 label "配置"/"连接"）

3. **tooltip 文案**（四态各一句，见 SPEC §2.2）：
   - 文案是否需要调整
   - 触屏 fallback（`title` + `aria-label`）是否够

4. **配置未就绪时连接态置灰**（架构师已修订，2026-08-18）：
   - **置灰仅当 `!installed`**；`installed`（无论 configured on/off/null）**直接显示真实 connection**
   - 原因：Enchante 配置检测恒 False（deeplink 无配置文件）但 connection 有效，原规则会误置灰使其连接检测失效
   - 已同步 SPEC §3.5 组合矩阵 + §六 CSS 注释 + §七 connectionClass 判定

5. **平台列表**（任务提到 ClaudeCode/ClaudeDesktop/CodeBuddyIDE/WorkBuddy/Enchante）：
   - 当前 `clientPlatforms` 只有 claude/codebuddy
   - 前端开发 agent 需扩展 `clientPlatforms`，连接态设计**已支持未来扩展**

---

## 五、待前端开发 agent 实施

按 SPEC §六/§七 实施：

1. **`frontend/index.html` L1877**：MCP 卡平台行右侧新增 `.ai-platform-row__connection` 区
2. **`frontend/js/store.js`**：
   - 新增 `connectionClass(platform)` / `connectionLabel(platform)` / `connectionTooltip(platform)`
   - 数据源：`this.clientConfig?.[platform]?.connection`（后端新增）
3. **`frontend/css/components.css`**：新增 `.connection-tip` / `.connection-dot` / `.connection-text` / `.connection-tip__bubble` 等（见 SPEC §六）
4. **不动** `frontend/index.html` L1660 那个 ai-platform-row（其他平台的，不是 MCP 卡；也非本次任务范围）

---

## 六、零修改声明

- `frontend/*.js / *.html`：未改（**待前端开发 agent 按 SPEC 实施**）
- `backend/`：未改
- `design-tokens.css`：零 token 增量

---

*本反馈 + SPEC.md + Frame H SVG = 连接检测状态设计交付完整三件套。前端开发 agent 据此施工，架构师拍板决策点（§四）。*
