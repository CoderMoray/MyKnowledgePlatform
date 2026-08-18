# 引导页重设计设计规范（3 步改结构）

> 作者：前端视觉/交互设计 agent
> 日期：2026-08-18
> 用途：本规范为「引导页重设计（3 步改结构）」任务的设计权威。前端开发 agent 据此实施。
> 前置：与现有设置 Modal（5 平级导航 / 5 态开关 / ai-platform-row）**风格协调**；不改设置 Modal 结构。

---

## 〇、TL;DR

引导向导从「3 步（身份 / AI 协作全列表 / 完成）」改为「**4 页 3 步结构**」：

```
Step 1  身份（4 字段全必填 + 校验）
Step 2  ┌ 2.1 平台多选（6 平台开关，未安装禁用，至少选 1）
        └ 2.2 执行 + 结论（进度条 ≥0.36s → 按平台结论）
Step 3  完成（✓ 延续现有）
```

**动画规范（重点）**：步骤间过渡 = 淡入 + 位移/缩放，时长 **≥0.36s 且为 0.06 整数倍**（0.36/0.42/0.48/0.54/0.60s）；2.2 执行进度条也 ≥0.36s。

---

## 一、Step 1 身份（4 字段全必填）

### 1.1 字段定义

| # | 字段 | 对应身份/配置 | 必填 | 校验 | 占位示例 |
|---|------|--------------|------|------|---------|
| 1 | 昵称 | nickname | ✅ | 非空 | 如：张三 |
| 2 | 邮箱 | email | ✅ | **邮箱格式**（`isValidEmail`） | 如：zhangsan@example.com |
| 3 | 企业名称 | `KNOWLEDGE_SHARE_CODE` | ✅ | **非空 + 格式**（见 §1.2） | 如：Acme 科技 |
| 4 | 组织代码 | `SHARE_MAP` | ✅ | **非空 + 格式**（见 §1.2） | 如：acme-share |

### 1.2 校验规则

- **邮箱**：复用现有 `isValidEmail`（正则校验格式）
- **企业名称（KNOWLEDGE_SHARE_CODE）**：非空；格式建议 `[A-Za-z0-9_-]{2,32}`（字母/数字/下划线/连字符，2-32 位）——**具体格式以后端 `GET /api/config-status` 返回的 schema 为准**（前端按后端定义校验）
- **组织代码（SHARE_MAP）**：非空；格式同上或按后端定义

> 4 字段全必填，**未填全不能下一步**（「下一步」按钮 disabled）。校验失败时字段下方显示 hint（复用 `.modal__hint` 红字）。

### 1.3 说明文案

字段下方显示用途说明（`--text-tertiary` 小字）：
> 「企业名称与组织代码用于知识库分享鉴权（KNOWLEDGE_SHARE_CODE / SHARE_MAP），仅本机存储，用于初始化分享配置」

### 1.4 布局（视觉稿 Frame S1）

```
[avatar 首字母]
欢迎使用 MyKnowledge
设置你的身份信息，开始初始化 AI 协作

昵称 [____________]
邮箱 [____________]  (格式不正确时红字 hint)
企业名称 [____________]  (用于知识库分享鉴权)
组织代码 [____________]
[下一步]  (disabled 直至 4 字段全有效)
```

---

## 二、Step 2.1 平台多选（开关）

### 2.1 目标

从 6 平台中选择要初始化的 AI 客户端。**只列平台名 + 开关，不展示 kind 细节**（kind 在 2.2 执行时自动处理）。

### 2.2 平台列表（6 平台，复用 store.js `clientPlatforms`）

| 平台 | key | dot 渐变 | kinds |
|------|-----|----------|-------|
| Claude Code | ClaudeCode | `#d97706→#f59e0b` | mcp/hooks/agent |
| Claude Desktop | ClaudeDesktop | `#b45309→#f59e0b` | mcp |
| CodeBuddy IDE | CodeBuddyIDE | `#6366f1→#818cf8` | mcp/hooks/agent |
| WorkBuddy | WorkBuddy | `#0ea5e9→#22d3ee` | mcp/hooks/agent |
| Enchanté | Enchante | `#9333ea→#a855f7` | mcp/agent |
| Cursor | Cursor | `#0891b2→#06b6d4` | mcp/hooks/agent |

### 2.3 每行结构（复用设置 Modal 风格）

```
[平台渐变 dot]  [平台名]  [未安装标注?]  [开关 toggle]
```

- **平台渐变 dot**：16px 圆形，`background: 该平台 dot 渐变`（复用现有 `clientPlatforms[].dot`）
- **平台名**：`--text-sm` 500 `--text-primary`
- **开关**：与设置 Modal toggle **一致**（`.toggle` + knob）
  - 选中 → `toggle--on`（accent 实色）
  - 未选 → `toggle--off`（灰）
- **未安装标注**（`clientInstalled(platform) === false`）：
  - 开关 **灰禁用**（`toggle--off` + `opacity 0.4` + `disabled`，与设置 Modal `toggle--failed` 一致）
  - 行尾加**「未安装」标签**：`--text-2xs` `--text-tertiary` 灰字（`badge` 圆角）

### 2.4 至少选 1 逻辑

- **选中数提示**：列表底部「已选 N/6 个平台」（N≥1 时可下一步）
- **未选任何平台**：「下一步」disabled + 提示「请至少选择 1 个平台」
- 未安装平台**不可选**（开关禁用），不计入可选

### 2.5 布局（视觉稿 Frame S2.1）

```
[步骤指示条 ●—●—○]
Step 2 of 3 · AI 协作初始化
选择要初始化的 AI 客户端

[◍] Claude Code    [开关 on]
[◍] Claude Desktop [开关 on]
[◍] CodeBuddy IDE  [开关 on]
[◍] WorkBuddy      [开关 off]
[◍] Enchanté       [未安装] [开关 禁用灰]
[◍] Cursor         [开关 off]

已选 3/6 个平台
[上一步] [下一步]
```

---

## 三、Step 2.2 执行 + 结论

### 3.1 进入即执行

- 用户点 2.1「下一步」→ **进入 2.2 即自动执行**（为已选平台按 kinds 开启 MCP/Hooks/Agent，Enchante 生成 deeplink）
- **执行时长**：进度条/加载圈**至少播放 0.36s**（0.36s 或 0.42s——见 §五动画规范），让用户感知"正在执行"

### 3.2 执行中（进度条）

- 顶部显示**进度条**（`.progress`：track 灰 + bar accent 紫，从左到右）
- 或**加载圈**（`.spinner` accent 紫 24px）
- 伴随文案：「正在为 N 个平台初始化 AI 协作…」
- 执行中「上一步/下一步」disabled（或隐藏）

### 3.3 执行完成（结论）

**结论按平台分行**，每行：
```
[平台渐变 dot] [平台名]：[做了什么]
```
- **做了什么**（按平台 × kind 组合）：
  - 正常平台：「已开启 MCP / Hooks / Agent」（按该平台 kinds 实配了哪些）
  - Enchante（deeplink）：「已生成专属链接（deeplink）」
  - 未安装跳过：该行标注「未安装，已跳过」（`--text-tertiary`）
- **每行状态点**：成功 `success` 绿 / 跳过 `muted` 灰

**查看指引**（结论下方）：
> 「你可以在 设置 → MCP / Hooks / Agent 中查看或调整」
> 一行小字：「可在个人设置中关闭」（`--text-tertiary`）

### 3.4 布局（视觉稿 Frame S2.2 执行态 + 结论态）

**执行态**：
```
[步骤指示条 ●—●—○]
Step 2 of 3 · AI 协作初始化
正在为 3 个平台初始化 AI 协作…

[████████████████░░░░] 42%
[spinner 或进度条 ≥0.36s]
```

**结论态**：
```
[步骤指示条 ●—●—○]
Step 2 of 3 · AI 协作初始化
初始化完成，已为所选平台开启协作能力

[◍] Claude Code：已开启 MCP / Hooks / Agent   ●
[◍] Claude Desktop：已开启 MCP               ●
[◍] CodeBuddy IDE：已开启 MCP / Hooks / Agent ●
[◍] Enchanté：已生成专属链接（deeplink）       ●
[◍] WorkBuddy：未安装，已跳过                 ○

你可以在 设置 → MCP / Hooks / Agent 中查看或调整
可在个人设置中关闭
[上一步] [下一步]
```

---

## 四、Step 3 完成（延续现有）

- ✓ 完成图标（`--color-success` 48px）
- 「初始化完成」标题 + 「你的知识库已准备好与 AI 协作」
- **沿用现有** Step3 总结列表（`guideSummary`）
- 按钮：「开始使用」（进 dashboard）

> 视觉上延续现有 Step3（视觉稿 Frame S3），仅补充动画过渡。

---

## 五、动画规范（重点）

### 5.1 时长规则（硬性）

- **所有步骤间过渡动画 ≥0.36s**
- **时长必须为 0.06 的整数倍**：0.36s / 0.42s / 0.48s / 0.54s / 0.60s …
- 执行进度条/加载圈也 **≥0.36s**（0.36s 或 0.42s）

### 5.2 步骤切换过渡（Step1 ↔ 2.1 ↔ 2.2 ↔ 3）

| 方向 | 过渡 | 时长 | 缓动 |
|------|------|------|------|
| 进入新步骤 | `opacity 0→1` + `translateY(8px→0)` | 0.42s | `cubic-bezier(0.4,0,0.2,1)` |
| 离开旧步骤 | `opacity 1→0` + `translateY(0→-8px)` | 0.36s | 同上 |
| 2.2 执行中 → 结论 | 进度条完成后，结论 `opacity 0→1` + `scale(0.98→1)` | 0.48s | `ease-out` |

**实现提示**（前端）：CSS `transition` + 步骤切换时 `x-transition`（Alpine）或 class 切换；**时长用 0.06 倍数**（0.36/0.42/0.48s 等），缓动统一 `cubic-bezier(0.4,0,0.2,1)`。

### 5.3 执行进度条动画

- 进度条从 0→100%，**时长 0.36s 或 0.42s**（0.06 倍数）
- 后端真实执行通常更快 → 前端**保证最少播放时长**（如实际 <0.36s 则补足到 0.36s，用 `min-duration` 或延时）

### 5.4 触屏/弱化

- `prefers-reduced-motion`：时长减半（0.18s 起）或关闭位移仅淡入（无障碍）

---

## 六、新增样式类（components.css）

```css
/* Step1 身份：4 字段表单（复用 .modal__input/.modal__hint） */
.guide-field { margin-bottom: 12px; }
.guide-field__label {
  display: block;
  margin-bottom: 4px;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
.guide-field__hint {
  margin-top: 4px;
  font-size: var(--text-2xs);
  color: var(--text-tertiary);
}
.guide-field__hint--error { color: var(--color-danger); }

/* Step2.1 平台多选行 */
.guide-platform-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.guide-platform-row__dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  flex-shrink: 0;
}
.guide-platform-row__name { flex: 1; font-size: var(--text-sm); font-weight: 500; color: var(--text-primary); }
.guide-platform-row__not-installed {
  font-size: var(--text-2xs);
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}
.guide-platform-row .toggle--disabled {
  background: #d1d5db;
  opacity: 0.4;
  cursor: not-allowed;
}

/* Step2.1 选中数提示 */
.guide-selection-count {
  margin-top: 12px;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

/* Step2.2 进度条 */
.guide-progress {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: var(--bg-tertiary);
  overflow: hidden;
  margin: 16px 0;
}
.guide-progress__bar {
  height: 100%;
  border-radius: 3px;
  background: var(--accent);
  transition: width var(--transition-interactive);
  animation: guide-progress 0.42s ease-out forwards;  /* 0.06 倍数 */
}
@keyframes guide-progress { from { width: 0; } }

/* Step2.2 结论行 */
.guide-conclusion-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--text-sm);
  color: var(--text-primary);
}
.guide-conclusion-row__action { color: var(--text-secondary); }
.guide-conclusion-row__action--skip { color: var(--text-tertiary); }
.guide-conclusion-hint {
  margin-top: 16px;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
.guide-conclusion-sub {
  margin-top: 4px;
  font-size: var(--text-2xs);
  color: var(--text-tertiary);
}

/* 步骤切换过渡（0.06 倍数） */
.guide-step-enter {
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 0.42s cubic-bezier(0.4, 0, 0.2, 1), transform 0.42s cubic-bezier(0.4, 0, 0.2, 1);
}
.guide-step-enter-active { opacity: 1; transform: translateY(0); }
.guide-step-leave {
  opacity: 1;
  transform: translateY(0);
  transition: opacity 0.36s cubic-bezier(0.4, 0, 0.2, 1), transform 0.36s cubic-bezier(0.4, 0, 0.2, 1);
}
.guide-step-leave-active { opacity: 0; transform: translateY(-8px); }
@media (prefers-reduced-motion: reduce) {
  .guide-step-enter, .guide-step-leave { transition-duration: 0.18s; }
}
```

**无 design-token 增量**：全复用现有 token（accent、color-success/danger、text-primary/secondary/tertiary、bg-tertiary、border-subtle、radius-sm、text-2xs/xs/sm、transition-interactive）。

---

## 七、store.js 新增/扩展（供前端参考）

```js
// data() 新增
setupCompany: "",      // 企业名称 KNOWLEDGE_SHARE_CODE
setupOrgCode: "",      // 组织代码 SHARE_MAP
guideSelected: [],     // Step2.1 已选平台 key 数组（初始空）
guideExecuting: false, // Step2.2 执行中标志（进度条控制）
guideExecDone: false,  // Step2.2 执行完成（结论显示）
guideExecPercent: 0,   // 进度 0-100

// Step1 校验（4 字段全有效才可下一步）
guideStep1Valid() {
  return !!(this.setupNickname.trim() && this.setupEmail.trim()
    && this.isValidEmail(this.setupEmail)
    && this.setupCompany.trim() && this.setupOrgCode.trim());
  // + 企业名称/组织代码格式校验（按 /api/config-status schema）
},

// Step2.1 至少选 1
guideStep2Valid() { return this.guideSelected.length > 0; },

// Step2.2 执行（进入即触发）：最小播放 0.36s/0.42s
async guideExecute() {
  this.guideExecuting = true;
  this.guideExecPercent = 0;
  const t0 = performance.now();
  // ... 为 guideSelected 各平台按 kinds 调 configureClient / generateEnchanteDeeplink ...
  const elapsed = performance.now() - t0;
  const min = 420; // 0.42s（0.06 倍数）
  if (elapsed < min) await sleep(min - elapsed);  // 补足最小播放时长
  this.guideExecuting = false;
  this.guideExecDone = true;
  this.guideExecPercent = 100;
},
```

---

## 八、验收对照

| 验收点 | 验证 |
|--------|------|
| Step1 4 字段全必填 | 未填全「下一步」disabled；校验失败红字 hint |
| 企业名称/组织代码校验 | 格式校验（按 /api/config-status schema） |
| Step2.1 6 平台多选 | 每行 dot+名+开关；选中 on / 未选 off |
| 未安装禁用 | `clientInstalled=false` → 开关灰禁用 +「未安装」标签 |
| 至少选 1 | 未选「下一步」disabled + 提示；选中数提示 |
| Step2.2 执行进度 | 进入即执行，进度条 ≥0.36s（0.42s） |
| Step2.2 结论 | 按平台分行（做了什么/未安装跳过）+ 设置查看指引 +「可在个人设置中关闭」 |
| 动画时长 | 所有过渡 ≥0.36s 且为 0.06 整数倍 |
| 风格协调 | 与设置 Modal toggle/dot/状态一致 |
| 构建通过 | `python3 frontend/build.py` |
| 后端回归 | `pytest tests/ --ignore=tests/frontend -q` |

---

## 九、零 token 增量 + 边界

- **零 design-token 增量**：全复用现有 token
- **不动后端**：Step1 写分享配置的 REST 端点由后端另派；`GET /api/config-status` 只读参考
- **不动设置 Modal 现有 5 平级导航结构**（引导页独立设计，风格协调即可）
- **不改其他页面**

---

*本规范与现有引导向导（index.html 1608-1717）+ 设置 Modal（5 平级 / 5 态开关）协调。前端开发 agent 据此实施。*

---

## 十、补充设计：大 modal 规格 + Enchante 专属按钮（2026-08-18 架构师追加）

### 10.1 大 modal 规格（引导页）

引导 modal 从普通 modal 改为**大 modal**（适配 4 页内容，不全屏，风格与设置 modal 协调）：

| 属性 | 值 | 对照 |
|------|-----|------|
| 宽度 | **840px**（> 设置 modal 760px） | 容纳 Step1 4 字段 / Step2.1 6 平台 / Step2.2 结论 |
| 高度 | **640px**（> 设置 modal 540px） | 4 页内容垂直容纳 |
| 圆角 | `--radius-xl`（14px） | 同设置 modal |
| 背景 | `--card-bg` + `backdrop-filter: blur(24px)` | 同设置 modal |
| 边框 | `0.5px solid rgba(0,0,0,0.06)` | 同设置 modal |
| 阴影 | `0 16px 48px rgba(0,0,0,0.12)` | 同设置 modal |
| 内边距 | 上下 24px / 左右 28px | 比设置 modal 略宽，容纳表单/列表 |

**实现**：`.guide-modal`（新类），复用 `.modal` 基础，覆盖尺寸：
```css
.guide-modal {
  width: 840px;
  max-width: 840px;
  height: 640px;
  max-height: 640px;
  padding: 24px 28px;
  border-radius: var(--radius-xl);
  background: var(--card-bg);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 0.5px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.12);
}
```

### 10.2 Enchante 专属按钮（2.2 结论页）

当 2.1 选择 Enchante，2.2 结论页 Enchante 行显示**专属按钮**（区别于其它平台"已开启"）。

**交互**（复用现有 `generateEnchanteDeeplink`，`store.js:1539`）：
- 点击 → `api.getClientConfigDeeplink(platform)` → **复制链接 + 隐藏 a 触发打开 + toast**「已生成并复制专属链接，若未自动打开 Enchanté，请粘贴到浏览器地址栏」
- 复用现有 `deeplinkBusy` 状态（busy 时按钮 disabled + "生成中…"）

**视觉**（复用 `.btn--deeplink`）：
- 醒目（accent 紫实色，区别于其它"已开启"的文本）
- 文案：「**⚡ 打开安装链接**」（引导手动安装）

**状态机**：

| 状态 | 触发 | 按钮文案 | 视觉 |
|------|------|----------|------|
| **初始** | 结论页首次显示 | 「⚡ 打开安装链接」 | accent 实色 `.btn--sm btn--deeplink` |
| **点击后** | 生成 deeplink 成功 | 「已生成链接 · 可再次点击」 | accent 实色（保持可点） |
| **生成中** | `deeplinkBusy` | 「生成中…」 | disabled + spinner |
| **未安装** | `clientInstalled=false` | 「⚡ 打开安装链接」 | **置灰禁用**（opacity 0.45）+ 旁提示「请先安装 Enchanté」 |

**结论页 Enchante 行说明**（按钮旁/下方小字）：
> 「MCP 需手动安装完成：点击按钮生成专属链接并打开」

**HTML 参考**：
```html
<!-- 2.2 结论页 Enchante 行 -->
<div class="guide-conclusion-row">
  <span class="guide-conclusion-row__dot" :style="...Enchante gradient..."></span>
  <span class="guide-conclusion-row__name">Enchanté</span>
  <span class="guide-conclusion-row__action">MCP 需手动安装</span>
  <button class="btn btn--sm btn--deeplink"
          :disabled="$store.app.deeplinkBusy || !$store.app.clientInstalled('Enchante')"
          @click="$store.app.generateEnchanteDeeplink('Enchante')">
    <span x-text="$store.app.deeplinkBusy ? '生成中…'
                  : ($store.app.deeplinkClicked ? '已生成链接 · 可再次点击' : '⚡ 打开安装链接')"></span>
  </button>
  <span class="guide-conclusion-row__hint"
        x-show="!$store.app.clientInstalled('Enchante')">请先安装 Enchanté</span>
</div>
```

**新增 store 状态**：`deeplinkClicked`（bool，点击后标记，文案变"已生成链接"）。

### 10.3 新增/调整样式类

```css
/* 大 modal（引导页） */
.guide-modal { /* 见 §10.1 */ }

/* Enchante 专属按钮（复用 .btn--deeplink）+ 禁用态 */
.btn--deeplink:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
/* 结论行 Enchante 行（含按钮）布局 */
.guide-conclusion-row--deeplink {
  display: flex;
  align-items: center;
  gap: 12px;
}
.guide-conclusion-row__hint {
  font-size: var(--text-2xs);
  color: var(--text-tertiary);
}
```

**无 design-token 增量**（复用 card-bg、radius-xl、btn--deeplink、accent、text-tertiary）。
