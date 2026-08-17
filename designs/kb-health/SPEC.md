# KB 结构体检视图（#health）— 设计规范

> 本文档为 `#health` 视图的**语义核心**，是前端开发 agent 实施时的唯一权威依据。
> 当 ardot 画布可用时，配合 `export/*.svg` 矢量稿使用；当前画布适配器暂不可用，本文档已包含完整视觉规范，开发 agent 可据此直接实施。
> 旧方案的两张 PNG（人审参考）保留在 `screenshots/`，**不作为实施依据**。

---

## 1. 设计原则

- **贴合现有 design-tokens**：所有色值/字号/间距/圆角/阴影均引用 `frontend/css/design-tokens.css`，不另起炉灶
- **不新增 token**：现有色板已覆盖本场景所需（语义色 success/warning/danger + 中性灰阶 + accent 紫）
- **零多模态交接**：前端 agent 通过本 SPEC 的语义说明 + SVG 矢量文本实施，无需读 PNG
- **复杂区独立收敛**：需 AI 判断的 issue 单独成块，提供「复制问题清单」一键导出，避免淹没主列表

---

## 2. 视图信息架构

> **全局前置元素（阶段二/三）**：
> - **阶段二**：顶部 `status-indicator` 被替换为**就绪信号**（§3.5），位于所有视图之上、`#health` 视图之外，点击进 `#health`。
> - **阶段三**：**引导页**（§3.6，首次自动触发，`!identitySet` 时）与**配置页**（§3.7，`#settings`，user-menu「配置」入口）同为应用级界面，不属 `#health` 视图内部，一并在此规范。

```
#health 视图
├── 页面标题区
│   ├── page-label: "知识库结构体检"
│   ├── page-title: "知识库结构体检"
│   └── page-subtitle: "检测知识目录结构健康度，识别并修复结构性问题"
│
├── 健康概览卡（健康徽标 + 数字概览 + 刷新按钮 + lazy 按钮）
│   ├── 徽标：健康 / 发现问题
│   ├── 总览数字：扫描文件 / 发现问题 / 高危问题
│   ├── 分组计数芯片：position / metadata / index / ref / illegal / system
│   ├── 右上次扫描时间
│   └── lazy 按钮「我懒得看了，交给 AI 吧」[右上，与「重新检查」并列，total_issues>0 时显示]
│
├── 加载态（复用现有 .loading-state）
│
├── 问题清单（按 type 分组，无问题组隐藏）
│   ├── 分组标题 [全选框 · type · 中文标签 · 数量] [+ 组头单按钮（position/index/system）·「筛选需 AI 协助 →」锚点]
│   └── issue 行 [勾选框（仅非复杂分组）· severity 色标 · path · message · action 标签]
│
├── 修复确认弹窗（阶段 B：点组头单按钮触发，复用 .modal）
│   ├── 标题：修复知识位置 / 重建索引
│   ├── 勾选项 path 列表 + 小描述
│   └── [复制 prompt] 次按钮 + [确认执行] 主按钮 + 关闭
│
└── 复杂区（needs_semantic=true 的 issue 单独成块）
    ├── 标题：需 AI 判断的复杂问题 · N 项
    ├── 副说明：无法自动修复 · 复制结构化 prompt 给 AI 处理后，回填重查
    └── 「复制 prompt 交 AI」按钮 [右上]
```

### 信息密度模式

- **默认（中密度）**：与现有 `.trash-list` 接近（行高 12-14px、字号 12-13px）
- **健康徽标区**：单卡片占据顶部，引导主视觉

---

## 3. 页面标题区

复用现有 `.page-title` / `.page-subtitle` 模式（见 `index.html` 第 991-992 行 trash 视图）。

| 元素 | token | 数值 |
|---|---|---|
| page-label | `.page-label` | accent 紫，字号 `--text-sm`，字间距 0.08em，大写 |
| page-title | `.page-title` | `--text-4xl` (26px)，字重 600，字距 -0.02em |
| page-subtitle | `.page-subtitle` | `--text-sm` (12px)，`--text-tertiary`，下边距 `--space-6` |

> 与 trash/status 视图保持视觉节奏一致。

---

## 3.5 阶段二 · 就绪信号（顶部 status-indicator 替换）

### 3.5.1 目标与位置

让用户在**顶部一眼**看到知识库的就绪状态（结构健康程度），点击进 `#health` 处理。

- **替换对象**：`frontend/index.html` 顶部的 `status-indicator`（第 379-389 行，原显示 AI 连接/锁定/编辑状态点）→ 改为就绪信号
- **保留不动**：`sidebar-footer__status`（第 301 行）继续显示 AI/锁定状态（`systemStatus` / `mcpStatusInfo`），不替换
- **数据源**：`/api/diagnose/saved`（只读上次检查结果，不触发检查；返回 `{saved, issues, summary, generated_at}`）

### 3.5.2 三态文本与颜色（等长短语）

| 状态 | 判定 | 文本 | 状态点色 | token |
|---|---|---|---|---|
| 健康 | `saved && summary.total_issues === 0` | 「知识状态健康」 | 绿 | `--color-success` |
| 存疑 | `saved && summary.total_issues > 0` | 「N 个知识存疑」 | 有 high → 红，否则黄 | `--color-danger` / `--color-warning` |
| 未检查 | `!saved`（无 saved 结果） | 「尚未触发检查」 | 灰 | `--text-muted`（灰阶） |

**等长短语说明**：
- 「知识状态健康」= 6 字
- 「N 个知识存疑」= N 为实际数字（如「3 个知识存疑」），前缀固定
- 「尚未触发检查」= 6 字
- 三态文本**均不含**「点此体检」等动作字眼，保持语义状态 + 等长节奏

**存疑色判定**：`summary.by_type` 中存在 `high` severity 计数 > 0 → 状态点红；否则黄。

### 3.5.3 视觉规范

| 属性 | 值 |
|---|---|
| 容器 | 复用 `.status-indicator` 容器（保留现有尺寸/圆角/背景/内边距，仅改内部内容与语义色） |
| 状态点 | 复用 `.status-indicator__dot`，直径 8px，`border-radius:50%`，颜色按上表 |
| 文本 | 复用容器现有字号 `--text-xs` (12px)，`--text-secondary`，字重 500 |
| hover | 就绪信号可点击（跳 `#health`）→ hover 时：背景 `--bg-secondary`，状态点微放大（scale 1.15），光标 `pointer` |
| 点击 | `window.location.hash = 'health'`（不弹 toast） |

**就绪信号内部布局**（对齐现有 status-indicator 结构）：
```
[● 状态点 8px]  知识状态健康 / 3 个知识存疑 / 尚未触发检查
```

### 3.5.4 更新机制（设计约定）

| 时机 | 行为 |
|---|---|
| 首次进入应用 | 读 `/api/diagnose/saved` 初始化就绪信号 |
| SSE 订阅 | 订阅 MCP 自检广播的 `diagnose` 类型事件 → 触发重读就绪信号 |
| 前端本地刷新 | 进入 `#health` 手动「重新检查」后，前端本地刷新就绪信号（复用 `healthSummary` 数据） |
| 后端离线 | 就绪信号隐藏或降级为 `--text-muted`（不渲染语义色，避免误导） |

### 3.5.5 新增样式类（复用现有 token）

```css
/* 就绪信号状态点色（复用现有 status-dot 体系 + 语义色） */
.status-indicator__dot--success { background: var(--color-success); }
.status-indicator__dot--danger  { background: var(--color-danger); }
.status-indicator__dot--warning { background: var(--color-warning); }
.status-indicator__dot--muted   { background: var(--text-muted); }

/* 就绪信号整体 hover（可点击进 #health） */
.status-indicator--readiness {
  cursor: pointer;
}
.status-indicator--readiness:hover {
  background: var(--bg-secondary);
}
.status-indicator--readiness:hover .status-indicator__dot {
  transform: scale(1.15);
}
.status-indicator--readiness .status-indicator__dot {
  transition: transform 0.15s ease;
}
```

> 全部**复用现有 token**（success/danger/warning、text-muted、bg-secondary、status-indicator 容器），无 design-token 增量。新增类仅进 components.css。

> **阶段二说明**：就绪信号是**替换**顶部 `status-indicator`，非新增独立元素；`sidebar-footer__status` 的 AI/锁定状态**不动**。若前端已有 `.status-indicator__dot--danger/warning`（见 index.html 第 385-387 行内联），新增类与之一致，仅补 `--success` / `--muted` 两种。

---

## 3.6 阶段三 · 引导页（初始化向导）

### 3.6.1 目标

引导用户完成 MyKnowledge AI 协作环境初始化：**身份 + MCP/hooks/专用 Agent 配置**。首次自动触发（`!identitySet` 时），专注初始化；体检不强推（靠 `#health` / 就绪信号入口）。

### 3.6.2 引导页形态

扩展现有 setup 视图（`currentView === 'setup'` / `modal === 'setup'`）为**三步向导**。复用现有 `.setup-modal` / `.modal` 容器与 step 指示条。

**布局**（复用现有 setup-modal 结构）：
```
┌──────────────────────────────────────┐
│  ● ○ ○  Step 1 of 3 · 身份            │  ← 步骤指示
│                                      │
│  [ 名称输入 ]                          │
│  [ 邮箱输入 ]                          │
│                                      │
│        [ 上一步 ]       [ 下一步 ]      │
└──────────────────────────────────────┘
```

**步骤条**：三步横排点/节，当前步实色，已完成步打勾，未到步浅色。
- 现有 setup 已有 step 指示（`setup-step-1`/`setup-step-2`），扩展为 3 步
- 步骤 1：`● 身份`；步骤 2：`○ AI 协作`；步骤 3：`○ 完成`

### 3.6.3 Step1 身份（扩展现有 setup 视图）

| 元素 | 样式 |
|---|---|
| 标题 | `.modal__title`，`--text-lg`，「设置你的身份」 |
| 名称输入 | 复用现有 setup 名称字段（`.form-input`，`--text-sm`，圆角 `--radius-md`，边框 `--border-color`） |
| 邮箱输入 | 复用现有 setup 邮箱字段（同上） |
| 校验 | 邮箱格式校验；空名称禁用「下一步」 |
| 下一步 | `.btn--primary`；保存身份后进入 Step2 |

> 与现有 setup 身份 modal 逻辑一致，仅纳入向导步骤框架。

### 3.6.4 Step2 AI 协作初始化（半自动化）

每个平台一项，显示**检测状态 + 操作按钮**。

| 配置项 | 检测状态 | 操作按钮 | 兜底 |
|---|---|---|---|
| MCP | MCP 连接状态 | 「自动配置」 | 「复制 prompt 给 AI」 |
| hooks | hooks 文件是否存在 | 「生成 hooks」 | 「复制 prompt 给 AI」 |
| 专用 Agent | agents 文件是否存在 | 「创建 Agent」 | 「复制 prompt 给 AI」 |

**检测状态呈现**（三种）：
- `已配置`（绿勾）：复用 `.status-indicator__dot--success` + 「已就绪」文案
- `未配置`（灰点）：`.status-indicator__dot--muted` + 「未配置」文案
- `检测中`（spinner）：复用 `.spinner` 小号

**按钮三态**：
- 可操作（accent 实色 `.btn--sm`）
- 配置完成/适配成功（绿，`--color-success` 边框 + 勾）
- 非适配平台/失败（灰/禁用，显示「复制 prompt 给 AI」兜底）

> **半自动化原则**：前端按钮触发 → 后端生成配置 → 前端再检测 → 显示成功/失败。**不做一键全做**，每个平台独立按钮。非适配平台（如 hooks 不适用于当前部署）不硬生成，给「复制 prompt 给 AI」兜底。

**兜底「复制 prompt 给 AI」**：复制该平台配置 prompt → toast（复用 §7.5 toast 模式）。样式 `.btn--sm` 透明 + accent 字（复用 `.anchor-link` / `.btn-lazy-ai` 思路）。

### 3.6.5 Step3 完成

| 元素 | 样式 |
|---|---|
| 完成图标 | lucide `check-circle` 或 `party-popper`，48×48px，`--color-success`，opacity 0.9 |
| 标题 | 「初始化完成」，`--text-lg`，`--text-primary` |
| 总结列表 | 每项状态（MCP/hooks/Agent/身份），复用检测状态点 + 文案 |
| 主按钮 | 「开始使用」→ 跳 `#dashboard`；`.btn--primary` |
| 次按钮 | 「进入知识体检」→ 跳 `#health`（可选，不强推） |

### 3.6.6 引导页新增样式类

```css
/* 引导步骤指示（3 步） */
.guide-steps {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
.guide-steps__dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-2xs);
  font-weight: 600;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
}
.guide-steps__dot--active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.guide-steps__dot--done {
  background: var(--color-success);
  border-color: var(--color-success);
  color: #fff;
}
.guide-steps__line {
  flex: 1;
  height: 1px;
  background: var(--border-color);
}

/* 引导/配置：AI 协作配置项行 */
.ai-config-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  margin-bottom: 8px;
}
.ai-config-item__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
.ai-config-item__actions {
  display: inline-flex;
  gap: 8px;
  margin-left: auto;
}
```
> 全部**复用现有 token**（accent、color-success、bg-tertiary/secondary、border-color、text-muted、radius-md、spinner、status-indicator__dot），无 design-token 增量。

---

## 3.7 阶段三 · 配置页（常驻）

### 3.7.1 目标与入口

常驻配置页，维护身份/主题/AI 协作配置。

- **入口**：右上角 `user-menu`（index.html 第 453-462 行）加「配置」项，点击进 `#settings`（路由新增 `currentView === 'settings'`）
- **路由**：`#settings`（与现有 dashboard/project/view/edit/new/status/trash/health/setup 并列）
- **导航入口位置**：user-menu 下拉菜单「编辑个人信息」旁/下方加「配置」

### 3.7.2 配置页布局

```
#settings 视图
├── 页面标题区（复用 .page-title）
│   ├── page-title: "配置"
│   └── page-subtitle: "维护 MyKnowledge AI 协作环境"
├── 三 tab 导航（复用 .tab-nav 体系）
│   ├── Tab Profile：用户基础信息
│   ├── Tab General：主题切换 + 重新运行引导 + 关于
│   └── Tab AI Setting：MCP / hooks / 专用 Agent
└── tab 内容区（每 tab 一卡片，复用 .card-glass）
```

### 3.7.3 Tab Profile（用户基础信息）

| 元素 | 样式 |
|---|---|
| 头像 | 复用现有 avatar（昵称首字母圆角方块，`--accent` 底白字） |
| 名称 | 只读文本 `--text-md`，或可编辑输入 `.form-input` |
| 邮箱 | 只读 `--text-sm` `--text-secondary` |
| 保存 | 「保存」`.btn--primary` → toast 成功 |

> 头像 fallback：无头像时显示昵称首字母（复用现有 avatar 逻辑）。

### 3.7.4 Tab General（主题 + 引导 + 关于）

| 分组 | 内容 | 样式 |
|---|---|---|
| 主题切换 | light/dark/system 三选（复用现有 theme-switcher 下拉 `theme` / `designTheme`） | 复用现有主题切换组件 |
| 重新运行引导 | 「重新运行初始化引导」按钮 | `.btn` 次级 → 跳 `#setup` 向导 Step1 |
| 关于 | 版本号（`systemVersion` / `kbVersion`） | `.text-tertiary`，`--text-xs` |

### 3.7.5 Tab AI Setting（MCP / hooks / 专用 Agent）

复用 §3.6.4 的 `.ai-config-item` 行结构，三平台独立，**必须分平台不做一键全做**：

| 配置项 | 检测状态 | 操作按钮 | 兜底 |
|---|---|---|---|
| MCP | MCP 连接状态 | 「自动配置」 | 「复制 prompt 给 AI」 |
| hooks | hooks 文件 | 「生成 hooks」 | 「复制 prompt 给 AI」 |
| 专用 Agent | agents 文件 | 「创建 Agent」 | 「复制 prompt 给 AI」 |

**检测状态**：`已配置`（绿勾 success）/ `未配置`（灰点 muted）/ `检测中`（spinner）
**操作按钮**：`.btn--sm` accent；失败/非适配 → 「复制 prompt 给 AI」兜底（透明 accent 字）

### 3.7.6 半自动化交互（跨引导页/配置页共用）

**交互闭环**：按钮触发 → 后端生成配置 → 前端再检测 → toast 反馈：
- 成功：`.toast--success`，「{平台} 已就绪」
- 失败：`.toast--error`，「{平台} 配置失败」+ 提供「复制 prompt 给 AI」兜底
- 检测中：按钮转 spinner + disabled

**「复制 prompt 给 AI」兜底**（跨页共用）：
- 触发：复制该平台配置 prompt → toast（复用 §7.5 模式）
- 样式：`.btn--sm` 透明 + accent 字（复用 `.btn-lazy-ai` 变体）
- 语义：非适配平台/自动配置失败时兜底，引导用户交 AI 处理（对齐「不静默修复」原则——配置需语义判断，不强制自动生成）

### 3.7.7 配置页新增样式类

```css
/* 配置页 tab 导航（复用现有 .tab-nav 体系，若已有则无需新增） */
.settings-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
}
.settings-tabs__item {
  padding: 8px 16px;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: var(--transition-interactive);
}
.settings-tabs__item--active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

/* 配置页卡片 */
.settings-card {
  padding: 20px;
  border-radius: var(--radius-xl);
  background: var(--card-glass-bg);
  border: 1px solid var(--card-glass-border);
  box-shadow: var(--shadow-card);
}
```
> 全部**复用现有 token**（card-glass-bg、card-glass-border、shadow-card、accent、border-color、text-secondary、radius-xl/md），无 design-token 增量。若前端已有 `.tab-nav` 组件，`settings-tabs` 直接复用该体系。

---

## 4. 健康概览卡（核心视觉）

### 4.1 容器

| 属性 | token / 值 |
|---|---|
| 容器 | `.card-glass`（已有：玻璃态背景 + 阴影） |
| 内边距 | 上下 `--space-6`（24px）、左右 `--space-6`（24px） |
| 圆角 | `--radius-xl` (14px) |
| 阴影 | `--shadow-card` |
| 背景 | `--card-glass-bg` (rgba(255,255,255,0.7) light) |
| 边框 | `--card-glass-border` (0.5px solid) |

### 4.2 健康徽标（左侧主视觉）

健康徽标 = **彩色大圆点 + 文字标签**，传达即时状态。

| 状态 | 圆点色 | 文字色 | 标签 |
|---|---|---|---|
| 健康（0 问题） | `--color-success` (#10b981) | `--text-primary` | 「健康」 |
| 有问题（>0） | `--color-danger` (#ef4444) | `--text-primary` | 「发现问题」 |

实现细节：
- 圆点：直径 10px，`border-radius: 50%`，与文字垂直居中
- 文字：字号 `--text-sm` (12px)，字重 600
- 整体行：水平 flex，间距 `--space-2` (8px)，margin-bottom `--space-3` (12px)

### 4.3 概览数字（核心三联数字）

横向三联数字：**扫描文件 / 发现问题 / 高危问题**。

| 元素 | token |
|---|---|
| 数字 | `--text-3xl` (24px)，字重 700，字距 -0.02em，`--text-primary` |
| 标签 | `--text-2xs` (10px)，`--text-tertiary`，uppercase，letter-spacing 0.04em |
| 间距 | 三组间用 `--space-6` (24px) 分割 |
| "高危问题"数字 | 当 high > 0 时用 `--color-danger`，否则用 `--text-primary` |

布局：用 `.metric-cards` 模式（grid auto-fit minmax 160px）→ 改为水平 flex 三等分更紧凑。

### 4.4 分组计数芯片（次要信息）

将 `summary.by_type` 各 type 数量渲染为小芯片：

| 属性 | 值 |
|---|---|
| 容器 | flex-wrap 水平排列，gap 6px |
| 单芯片 | `.tag` 样式（已有，`--tag-bg` `--tag-text`，圆角 10px，padding 2px 8px） |
| 文本格式 | `position · 3` / `metadata · 2` / ... |
| 字号 | `--text-2xs` (10px) |
| 颜色 | 默认 `--tag-text` (--text-secondary)；count=0 时 opacity 0.4 |

> **新增样式类（请前端开发 agent 新增到 components.css）**：
> ```css
> .health-chip {
>   display: inline-flex;
>   align-items: center;
>   gap: 4px;
>   padding: 2px 8px;
>   border-radius: 10px;
>   background: var(--bg-tertiary);
>   font-size: var(--text-2xs);
>   font-weight: 500;
>   color: var(--text-secondary);
>   white-space: nowrap;
> }
> .health-chip__label { color: var(--text-tertiary); }
> .health-chip__count {
>   color: var(--text-primary);
>   font-weight: 600;
>   font-variant-numeric: tabular-nums;
> }
> .health-chip--zero { opacity: 0.4; }
> ```
> 该类为新增但**复用现有 token**，无 design-token 增量。

### 4.5 刷新按钮（右上角）

| 状态 | 样式 |
|---|---|
| 默认 | `.btn--primary`（accent 紫底白字） |
| loading | 文案变「刷新中...」+ spinner（禁用点击） |
| disabled (locked) | `.btn:disabled`（opacity 0.45） |

按钮规格来自现有 `.btn--primary` token。

### 4.6 顶部右侧元数据

- "上次体检 · 2 分钟前"（`.text-tertiary`，`--text-2xs` 字号，10px）

### 4.7 lazy 按钮「我懒得看了，交给 AI 吧」（阶段 B 新增）

位置：健康概览卡顶部右侧，与「重新检查」按钮**并列**（同排，主按钮旁）。

| 属性 | 值 |
|---|---|
| 文案 | 「我懒得看了，交给 AI 吧」（可带小 sparkle/sparkles 图标，lucide `wand-2` 或 `sparkles`） |
| 样式 | `.btn--sm`（secondary 透明底，accent 字，`--accent-subtle` hover）——弱化于主按钮「重新检查」 |
| 触发 | 复制**完整问题清单**（含复杂区 + 非复杂，全部 issue）为 prompt 到剪贴板 + toast |
| 显示条件 | **仅当 `total_issues > 0`** 时显示；无问题（健康态）时隐藏 |
| disabled | 知识库锁定 `--isLocked` 时禁用 |

> 语义：该按钮是「把全部问题交给 AI 处理」的一键入口，与复杂区「复制 prompt 交 AI」互补——复杂区只复制 `needs_semantic=true` 的子集，此按钮复制**全部**。两处复制 prompt 共用同一工具函数（`copyHealthPrompt(mode: 'complex' | 'all')`）。

新增样式类：
```css
/* lazy 按钮（阶段 B） */
.btn-lazy-ai {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: var(--radius-md);
  background: transparent;
  border: 1px solid var(--accent);
  color: var(--accent);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition-interactive);
  white-space: nowrap;
}
.btn-lazy-ai:hover { background: var(--accent-subtle); }
.btn-lazy-ai:disabled { opacity: 0.45; pointer-events: none; }
.btn-lazy-ai svg { width: 14px; height: 14px; }
```
> 复用现有 token（accent、accent-subtle、radius-md、text-sm、space-*），无 design-token 增量。

---

## 5. 加载态

复用现有 `.loading-state`（components.css 第 1092-1101 行）：

```html
<div class="loading-state">
  <div class="spinner"></div>
  <span>正在体检知识库结构...</span>
</div>
```

文本根据不同阶段调整（"扫描文件..." / "校验索引..." / "汇总结果..."）由前端开发 agent 控制时序。

---

## 6. 问题清单（分组列表）

### 6.1 分组卡片

每个 type 一张卡片，无问题组隐藏（不渲染）。

| 属性 | token / 值 |
|---|---|
| 容器 | `.card-glass` 同健康概览卡 |
| margin-top | `--space-4` (16px) |
| 内边距 | `--space-3` (12px) 上下 / `--space-4` (16px) 左右 |

### 6.2 分组标题行

水平布局：左侧标题 + 全选框 · 右侧「组头单按钮」+「筛选需 AI 协助 →」锚点。

**左侧**：
- 格式：`[全选框] {type 标识} · {中文标签} · {数量}`
  - 例：`position · 位置非法 · 3 项`
  - 例：`index · 索引过时 · 2 项`
- type 标识（`.tag--accent` 样式）：`--accent-subtle` 底，`--accent` 字，`--text-2xs` 字
- 中文标签：`--text-md` (14px)，字重 600，`--text-primary`
- 数量：`--text-2xs`，`--text-tertiary`
- 全选框：仅非复杂分组显示（见 §6.3），勾选全选/取消全选该组所有可勾选项

**右侧组头单按钮（阶段 B 新增）**：仅非复杂分组显示，一个按钮：

| type | 按钮文案 | 样式 |
|---|---|---|
| `position` | 「修复知识位置」 | `.btn--sm` accent（默认禁用态） |
| `index` | 「重建索引」 | `.btn--sm` accent（默认禁用态） |
| `system` | 「重建索引」 | `.btn--sm` accent（默认禁用态） |
| `metadata` | **不显示按钮** | 无（见下方说明） |
| `ref` / `illegal` | 不显示按钮 | 无（review 类问题走复杂区） |

按钮状态：
- **无勾选** → 浅色 disabled（`opacity:0.45`，继承 `.btn:disabled`）
- **≥1 勾选** → 可交互（accent 实色），点击弹出修复确认弹窗（§7.6），**只处理勾选项**

> **阶段 B 裁决**：`metadata`（add_metadata）**不做确认执行按钮**——元数据修复需要语义判断（summary 等），归入复杂区走复制 prompt 交 AI，避免前端自动补出错误元数据。

**右侧「筛选需 AI 协助 →」锚点**：
- **仅当该组内存在 `needs_semantic=true` 的 issue** 时显示，点击滚动/锚点到复杂区
- 是**纯导航**，不是修复动作
- 样式：`.btn--sm` 透明，accent 字（`--accent-subtle` hover）
- 该组内无 `needs_semantic` issue 时不显示

### 6.3 issue 行（含阶段 B 勾选框）

每条 issue 一行，行内布局：

```
[ 勾选框（仅非复杂分组） ] [ severity 色标 4×12px 条 ] [ path(等宽) ] [ message ] [ ...spacer... ] [ action 标签 ]
```

| 元素 | 样式 |
|---|---|
| 容器 | `display: flex; align-items: center; gap: 12px; padding: 10px 12px;` |
| 容器 hover | `background: var(--bg-secondary); border-radius: 8px;` |
| 勾选框 | **仅非复杂分组**（position / index / system）显示；复杂分组/复杂区不显示。原生 checkbox，`accent-color: var(--accent)`（与分享弹窗 share-project-item 一致） |
| severity 色标 | 高 4px × 12px 竖条，左缘绝对定位（`border-radius: 2px`）：high = `--color-danger` (#ef4444)，medium = `--color-warning` (#f59e0b)，low = `--color-info` (#3b82f6) |
| path | `font-family: var(--font-mono)`，`--text-xs` (12px)，`--text-secondary`，max-width 280px，超出 `text-overflow: ellipsis` |
| message | `--text-xs` (12px)，`--text-primary`，`flex: 1` |
| action 标签 | `.tag` 样式，小写文案：`移动` / `补齐元数据` / `重建索引` / `审查` |

**可勾选规则**：
- 仅 `position` / `index` / `system` 组的 issue 可勾选（非复杂，可自动修复）
- `metadata` / `ref` / `illegal` 组的 issue **不显示勾选框**（需语义判断，走复杂区）
- 组内已勾选项高亮该行背景（`--accent-subtle`，类似 active 行）

### 6.4 新增样式类

```css
/* issue 行容器 */
.issue-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  transition: var(--transition-interactive);
}
.issue-row:hover { background: var(--bg-secondary); }

/* severity 左侧色标 */
.issue-severity {
  width: 4px;
  height: 16px;
  border-radius: 2px;
  flex-shrink: 0;
}
.issue-severity--high   { background: var(--color-danger); }
.issue-severity--medium { background: var(--color-warning); }
.issue-severity--low    { background: var(--color-info); }

/* issue 路径（等宽） */
.issue-path {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 0;
}

/* issue 描述 */
.issue-message {
  font-size: var(--text-xs);
  color: var(--text-primary);
  flex: 1;
  min-width: 0;
}

/* 勾选框（阶段 B）：非复杂分组 issue 行头部 */
.issue-checkbox {
  accent-color: var(--accent);
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  cursor: pointer;
}

/* 已勾选 issue 行高亮（与分享弹窗选中态一致） */
.issue-row.is-checked {
  background: var(--accent-subtle);
}

/* 组头单按钮（阶段 B）：仅非复杂分组 */
.issue-group__action {
  white-space: nowrap;
  flex-shrink: 0;
}
.issue-group__action:disabled {
  opacity: 0.45;
  pointer-events: none;
}
```

> 这些类**复用现有 token**（color-danger/warning/info、font-mono、text-xs、bg-secondary、accent、accent-subtle），无 design-token 增量。

---

## 7. 复杂区（AI 判断收敛）

### 7.1 容器

| 属性 | token / 值 |
|---|---|
| 容器 | `.card-glass` 同其他卡片 |
| margin-top | `--space-6` (24px) |
| 特殊标识 | 顶部 1px 边 `--color-info` (#3b82f6) 弱化：`rgba(59,130,246,0.25)` |
| 内边距 | `--space-4` 上下 / `--space-6` 左右 |

### 7.2 标题行

```
[icon: brain / sparkle] 需 AI 判断的复杂问题 · N 项      [复制 prompt 交 AI]
```

| 元素 | 样式 |
|---|---|
| 左侧标题 | `--text-md` (14px)，字重 600，`--text-primary` |
| 副说明 | `--text-xs` (12px)，`--text-tertiary`，margin-top 4px：「需 AI 判断 · 复制 prompt 交 AI 用 MCP 工具复查修复后，回填重查」 |
| 右侧按钮 | `.btn--primary`，文案「复制 prompt 交 AI」，右侧加 copy icon（lucide `copy`） |

> **架构师裁决（决策点 2）**：复杂区按钮是主场景（修复主体 = AI）。复制 prompt 的意图是**让 AI 用 MCP 工具处理**（复查 + 修复），而非仅"判断"。具体 prompt 见 §7.4。

### 7.3 复杂区 issue 行

复用 §6.3 的 `.issue-row` 样式，仅去掉外层 `.card-glass` 容器背景（复杂区本身已有卡片背景）。

### 7.4 复制 prompt 内容

点击「复制 prompt 交 AI」时，复制以下 Markdown 到剪贴板（前端开发 agent 实现时按 backend `format_report()` 输出格式调整）：

```markdown
请用 MyKnowledge 的 MCP 工具（maint__knowledgebase_diagnose 复查 + write__ 系列修复）
处理以下知识库结构问题。每项请给出处理建议，并按需执行修复：
{所有 needs_semantic=true 的 issue 列表，Markdown bullet 格式}
---
扫描文件：{total_files} 个
```

> 说明：**不在 prompt 里写"知识库根"路径**——AI 经 MCP 工具（maint__knowledgebase_diagnose）自然持有当前知识库路径，无需前端传入。前端只负责把问题清单打包给 AI。

### 7.5 复制反馈

- 复制成功：复用现有 `.toast--success`（components.css 第 1066 行），文案：「已复制 N 条复杂问题 · 粘贴到 AI 对话」
- 复制失败：`.toast--error`，文案：「复制失败，请手动复制」

### 7.6 修复确认弹窗（阶段 B 新增）

点击分组头组头单按钮（§6.2，position/index/system）触发，**复用现有 modal 体系**（`store.openModal('health-fix', data)`，结构对齐 `frontend/index.html` 现有 modal + `frontend/js/store.js` 的 openModal/closeModal）。

**弹窗结构**（对齐现有 `.modal`）：

```
┌──────────────────────────────────────┐
│ [×]                                  │
│ 修复知识位置 / 重建索引         (title)│
│                                       │
│ 将修复选中的 N 项问题：                 │
│ • projects/A/common-knowledge/x.md    │  ← 勾选 issue 的 path 列表
│ • projects/B/common-knowledge/y.md    │
│ 确认后执行并自动重新检查。              │
│                                       │
│        [复制 prompt]   [确认执行]      │  ← 次按钮 / 主按钮
└──────────────────────────────────────┘
```

| 元素 | 样式 |
|---|---|
| 容器 | `.modal-overlay` + `.modal`（现有，宽 340-440px） |
| 标题 | `.modal__title`，`--text-lg`，`--text-primary`，文案 = 组头按钮文案（修复知识位置/重建索引） |
| 描述 | `.modal__description`，`--text-sm`，`--text-secondary`，说明「将修复选中的 N 项」+ 列勾选项 path（等宽，最多显示 5 项，超出折叠） |
| 主按钮「确认执行」 | `.btn--primary`，右对齐 |
| 次按钮「复制 prompt」 | `.btn`（secondary），左侧 |
| 关闭 | 右上 × + overlay 点击 + Esc（对齐现有 modal 交互） |
| 危险区分 | 该弹窗是**修复**（非删除），主按钮用 `.btn--primary`（accent），**不用** `.btn--danger` |

**弹窗状态**：
- 打开时：title 文案、勾选项 path 列表、按钮从 `store.modalData` 注入
- 确认执行：调 REST → toast（成功/失败）→ **自动重查**（`runHealthCheck()`）+ 关闭弹窗
- 复制 prompt：复制该组勾选项 prompt → toast（对齐 §7.4/§7.5 模式）

**新增样式类**：
```css
/* 修复弹窗内：勾选项 path 列表 */
.fix-modal__paths {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 12px 0;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  max-height: 140px;
  overflow-y: auto;
}
```
> 复用现有 token（bg-tertiary、radius-md、font-mono、text-xs、text-secondary），无 design-token 增量。

---

## 8. 空状态（无问题）

当 `total_issues === 0` 时，整个问题清单 + 复杂区隐藏，显示空状态。

| 属性 | token / 值 |
|---|---|
| 容器 | `.empty-state`（components.css 第 1103-1112 行） |
| 内边距 | `--space-8` (36px) |
| 图标 | lucide `shield-check` 或 `heart`，48×48px，`--text-muted`，opacity 0.3 |
| 标题 | 「知识库结构健康」，`--text-base` (13px)，`--text-secondary` |
| 描述 | 「全部 N 个文档结构正常，无需修复」，`--text-sm`，`--text-muted` |
| 操作 | 「再次体检」按钮 (`.btn`)，margin-top `--space-4` |

---

## 9. 严重度三色规范（severity color system）

| severity | 颜色 | token | 应用 |
|---|---|---|---|
| `high` | `#ef4444` | `--color-danger` | issue 行色标、高危数字 |
| `medium` | `#f59e0b` | `--color-warning` | issue 行色标 |
| `low` | `#3b82f6` | `--color-info` | issue 行色标 |

> **未新增 token**：直接复用 design-tokens.css 现有 `--color-danger / --color-warning / --color-info`，dark 模式下自动有对应色（`#f87171 / #fbbf24 / #60a5fa`）。

---

## 10. 设计 Token 增量声明

经逐项核对 design-tokens.css，**本设计未引入任何新增 design token**：

| 需求 | 复用现有 token |
|---|---|
| 健康徽标绿/红 | `--color-success` / `--color-danger` |
| 严重度高/中/低 | `--color-danger` / `--color-warning` / `--color-info` |
| 数字字号 | `--text-3xl` (24px) |
| 标签字号 | `--text-2xs` (10px) |
| 路径等宽 | `--font-mono` |
| 卡片背景/圆角/阴影 | `--card-glass-bg` / `--radius-xl` / `--shadow-card` |
| 按钮 | `.btn` / `.btn--primary` / `.btn--sm`（已有） |
| 标签 | `.tag` / `.tag--accent`（已有） |
| 加载态 | `.loading-state` / `.spinner`（已有） |
| 空状态 | `.empty-state` / `.empty-state__title` / `.empty-state__description`（已有） |
| Toast | `.toast` / `.toast--success` / `.toast--error`（已有） |

新增的样式类（A5：`.health-chip`, `.issue-row`, `.issue-severity`, `.issue-path`, `.issue-message`, `.complex-zone`, `.anchor-link`；阶段 B：`.issue-checkbox`, `.issue-group__action`, `.btn-lazy-ai`, `.fix-modal__paths`, `.issue-row.is-checked`；阶段二就绪信号：`.status-indicator__dot--success/--danger/--warning/--muted`, `.status-indicator--readiness`；阶段三引导页/配置页：`.guide-steps__dot/--active/--done/.guide-steps__line`, `.ai-config-item/__status/__actions`, `.settings-tabs/__item/--active`, `.settings-card`）**全部复用现有 token**，请前端开发 agent 将其添加到 components.css，**不动 design-tokens.css**。

---

## 11. 交互状态定义

| 场景 | 行为 |
|---|---|
| 首次进入视图 | 自动触发体检 |
| 手动点「重新体检」 | 按钮变「刷新中...」+ spinner；loading 态覆盖整个清单区 |
| 体检失败 | 显示 `.toast--error`：「体检失败 · 请检查后端连接」+ 保留旧数据 |
| 知识库已锁定 | 「重新体检」按钮 disabled（继承 `.btn:disabled`） |
| 复杂区为空 | 整块复杂区隐藏 |
| 复杂区有内容 | 默认展开，不折叠（MVP 不做折叠） |
| 点击 issue 行的 path | 跳转到该文档（`#doc/{encode(path)}`），MVP 不做 |
| 点击分组标题「筛选需 AI 协助 →」 | **纯导航**：滚动/锚点到复杂区 |
| 勾选 issue（仅非复杂分组） | 该行 `.is-checked` 高亮；组头按钮从 disabled → 可交互（≥1 勾选） |
| 组头全选框 | 全选/取消全选该组所有可勾选项；部分勾选时全选框呈中间态（indeterminate） |
| 点击组头单按钮（position/index/system） | 无勾选 = disabled；≥1 勾选 = 弹出修复确认弹窗（§7.6），**只处理勾选项** |
| 弹窗「确认执行」 | 调 REST → toast（成功/失败）→ 自动重查（`runHealthCheck()`）→ 关闭弹窗 |
| 弹窗「复制 prompt」 | 复制该组勾选项 prompt → toast（§7.4/§7.5 模式） |
| 点击「复制 prompt 交 AI」（复杂区） | 复制复杂问题 Markdown（§7.4）到剪贴板 + toast |
| 点击「我懒得看了，交给 AI 吧」 | 复制**全部问题** prompt（含复杂+非复杂）到剪贴板 + toast；`total_issues=0` 时按钮隐藏 |
| `metadata` 组 | **无组头按钮、无勾选框**——元数据修复归复杂区复制 prompt（阶段 B 裁决，§6.2） |

---

## 12. 布局断点

主视图固定桌面端 960-1280px 宽（与现有 `.doc-grid` / 仪表盘同宽）。

| 断点 | 行为 |
|---|---|
| ≥1024px | 三联数字 + 健康徽标一行展示 |
| 768-1023px | 三联数字自动收缩；分组卡片继续显示 |
| <768px | 不优化（MVP 桌面优先） |

---

## 13. 组件复用清单（前端开发 agent 实施时）

✅ 直接复用（已有类）：
- `.page-title` / `.page-subtitle`（page-header）
- `.card-glass`（卡片背景容器）
- `.btn` / `.btn--primary` / `.btn--sm`
- `.tag` / `.tag--accent`
- `.loading-state` / `.spinner`
- `.empty-state` / `.empty-state__title` / `.empty-state__description`
- `.toast` / `.toast--success` / `.toast--error`
- `--color-success` / `--color-danger` / `--color-warning` / `--color-info`

🆕 新增类（写入 components.css）：
- `.health-chip` / `.health-chip__label` / `.health-chip__count` / `.health-chip--zero`
- `.issue-row` / `.issue-severity` (+ `--high/--medium/--low` 修饰)
- `.issue-path` / `.issue-message`
- `.complex-zone`（复杂区容器）/ `.complex-zone__copy-btn`（复杂区「复制 prompt 交 AI」按钮）
- `.anchor-link`（分组标题「筛选需 AI 协助 →」纯导航锚点，`.btn--sm` 透明 + accent 字）
- `.issue-checkbox`（阶段 B：非复杂分组勾选框）
- `.issue-row.is-checked`（阶段 B：已勾选行高亮 `--accent-subtle`）
- `.issue-group__action`（阶段 B：组头单按钮，`.btn--sm` accent）
- `.btn-lazy-ai`（阶段 B：lazy 按钮「我懒得看了，交给 AI 吧」）
- `.fix-modal__paths`（阶段 B：修复弹窗内勾选项 path 列表）
- `.status-indicator__dot--success` / `--danger` / `--warning` / `--muted`（阶段二：就绪信号状态点色）
- `.status-indicator--readiness`（阶段二：就绪信号整体容器，cursor:pointer + hover 背景 + 状态点 scale）
- `.guide-steps__dot` / `--active` / `--done` / `.guide-steps__line`（阶段三：引导页步骤指示）
- `.ai-config-item` / `__status` / `__actions`（阶段三：引导页 + 配置页 AI 协作配置项行）
- `.settings-tabs` / `__item` / `--active`（阶段三：配置页 tab 导航）
- `.settings-card`（阶段三：配置页卡片）

> **阶段 B 说明**：组头单按钮（`.issue-group__action`）仅 `position` / `index` / `system` 组显示，`metadata` / `ref` / `illegal` 组不显示（后者走复杂区复制 prompt）。
> **阶段二说明**：就绪信号类复用现有 `.status-indicator` / `.status-indicator__dot` 容器，仅补状态点语义色 + readiness hover 修饰；`sidebar-footer__status` 不动。
> **阶段三说明**：引导页扩展现有 setup 视图（`.setup-modal`），配置页 tab 若前端已有 `.tab-nav` 体系则直接复用（`settings-tabs` 为可选别名）。检测状态点复用 `.status-indicator__dot--*` 语义色。全部新增类**复用现有 token**，无 design-token 增量。

---

## 14. 数据契约摘要（来自 backend/validator.py）

```python
ValidationIssue:
  path: str            # e.g. "notes/2024/架构.md"
  type: str            # "position" | "metadata" | "index" | "ref" | "illegal" | "system"
  severity: str        # "high" | "medium" | "low"
  message: str         # 中文描述
  action: str          # "move_to_peer_ck" | "add_metadata" | "rebuild_index" | "review" | "rebuild"
  needs_semantic: bool # true → 进复杂区

ValidationReport.summary:
  total_files: int
  total_issues: int
  by_type: dict[str, int]   # key = type, value = count
```

前端开发 agent 通过 `maint__knowledgebase_diagnose` MCP 工具或对应 REST 端点获取此结构。

---

## 15. 路由与视图接入

- 路由：`#health`
- 当前文件：`frontend/index.html` 已有 `currentView` 状态机（dashboard/project/view/edit/new/status/trash）
- 新增视图键值：`'health'`
- 视图容器：放在 `index.html` `status` 视图附近（`x-show="$store.app.currentView === 'health'"`）
- 导航入口：**侧边栏「垃圾箱」下方**（与现有系统级导航并列；架构师裁决，见 §6.2/§11）。前端 agent 据此位置实施，不自行拍板

> 此节仅供信息参考，本任务不修改 `frontend/*.js / *.html`。

---

## 16. 验收清单

| 检查项 | 通过条件 |
|---|---|
| 页面渲染 | 健康徽标/概览数字/分组/复杂区全部按 §4-§7 渲染 |
| 健康态 | `total_issues === 0` 时显示 §8 空状态 |
| 加载态 | 触发体检时显示 §5 spinner |
| 严重度 | 三色严格用现有 token，未引入硬编码 |
| 复杂区 | 仅展示 `needs_semantic === true` 的 issue，复制按钮存在 |
| 复制反馈 | toast 文案正确，成功/失败两态 |
| 勾选框（阶段 B） | 仅 `position`/`index`/`system` 组 issue 显示；`metadata`/`ref`/`illegal` 不显示；已勾选行 `.is-checked` 高亮 |
| 组头单按钮（阶段 B） | `position`→「修复知识位置」，`index`/`system`→「重建索引」；无勾选 = disabled，≥1 勾选 = 可交互弹窗 |
| 全选框（阶段 B） | 组头全选/取消全选；部分勾选呈 indeterminate 中间态 |
| 修复弹窗（阶段 B） | 复用 `.modal`，含【确认执行】主按钮 +【复制 prompt】次按钮 + 关闭；确认后调 REST → toast → 自动重查 |
| lazy 按钮（阶段 B） | 「我懒得看了，交给 AI 吧」复制全部问题 prompt；`total_issues=0` 时隐藏 |
| `metadata` 组 | 无组头按钮、无勾选框（阶段 B 裁决，归复杂区复制 prompt） |
| 「筛选需 AI 协助 →」 | 纯导航锚点，仅在该组含 `needs_semantic` issue 时显示 |
| 导航入口 | 侧边栏「垃圾箱」下方 |
| 就绪信号（阶段二） | 顶部 `status-indicator` 替换为就绪信号，三态文本等长：知识状态健康/「N 个知识存疑」/尚未触发检查；颜色 success/danger|warning/muted；点击进 `#health` |
| 就绪信号·未检查 | `!saved` 时显示「尚未触发检查」（灰 `--text-muted`） |
| 就绪信号·健康 | `total_issues=0` 时「知识状态健康」（绿 `--color-success`） |
| 就绪信号·存疑 | `total_issues>0` 时「N 个知识存疑」；有 high → 红 `--color-danger`，否则黄 `--color-warning` |
| sidebar-footer 保留 | AI/锁定状态（`systemStatus`/`mcpStatusInfo`）不动 |
| 引导页（阶段三） | 首次 `!identitySet` 自动触发，3 步（身份/AI 协作初始化/完成）；步骤条 + 半自动化配置项 |
| 配置页（阶段三） | `#settings`，user-menu「配置」入口；3 tab（Profile/General/AI Setting） |
| 引导/配置·半自动化 | 每平台独立按钮 + 检测状态（已配置 success/未配置 muted/检测中 spinner）；非适配/失败→「复制 prompt 给 AI」兜底；不做一键全做 |
| 配置页·Profile | 头像 fallback 首字母 + 名称/邮箱 + 保存 |
| 配置页·General | 主题切换（复用）+ 重新运行引导 + 关于版本 |
| 配置页·AI Setting | MCP/hooks/专用 Agent 三平台分列，检测状态 + 按钮 + 兜底 |
| Token 增量 | components.css 仅新增样式类，未引入任何 design-token 增量 |
| 暗色模式 | 所有颜色走 token，自动适配 dark/system 模式 |
| 空 issue 分组 | 不渲染（隐藏） |

---

## 17. 旧 PNG 处置

| 文件 | 原位置 | 新位置 | 用途 |
|---|---|---|---|
| `3_1-20260814_132346509.png` | `export/714694871087289/` | `screenshots/` | **仅人审参考**，不作为实施依据（已被本 SPEC + 未来 SVG 替代） |
| `3_186-20260814_132346511.png` | `export/714694871087289/` | `screenshots/` | 同上 |

旧的 export/714694871087289/ 目录已删除（空目录）。当 ardot 适配器恢复后，新设计的 SVG 将输出到 `designs/kb-health/export/`。

---

## 18. 关于 SVG 输出的状态声明

**当前状态（2026-08-14）**：ardot MCP 适配器返回 `NO_ADAPTER: Target adapter not connected`，连续 3+ 次重试均失败（间隔 4s/8s/12s/15s）。按 ardot 工具的明确错误指示"stop the task and do not attempt to continue the design task via any alternative path"，已停止在画布上操作。

**已交付**：
- ✅ 完整的 SPEC.md（本文件）：语义核心 + 精确数值 + token 引用 + 复用清单
- ✅ 旧 PNG 移到 `screenshots/`（人审参考）
- ✅ 目录结构清理（旧的 export/714694871087289/ 已删）

**待办（待 ardot 恢复后）**：
- 在画布上产出 SVG 矢量稿，输出到 `designs/kb-health/export/`
- SVG 视觉稿需与本 SPEC 一一对应（健康徽标/概览/分组/复杂区/空态/加载态/就绪信号三态 + 交互态/引导页 3 步/配置页 3 tab + 平台状态 + 兜底）

**对前端开发 agent 的指引**：在 SVG 矢量稿产出前，可据本 SPEC 实施；产出后请以 SVG 为视觉参考、以本 SPEC 为语义参考。

---

## 19. 反馈给架构师（自包含文本）

> 交付物位置：
> - SPEC.md: `/Users/chrismoray/Desktop/Moray/MyOpenSource/MyKnowledge_PlatForm/designs/kb-health/SPEC.md`
> - 旧 PNG（人审参考，不作为实施依据）: `designs/kb-health/screenshots/`
> - SVG 矢量稿: **待 ardot 适配器恢复后产出**，目录 `designs/kb-health/export/`
>
> 当前阻塞：ardot MCP adapter 报 `NO_ADAPTER`，3+ 次重试失败。按工具错误指示已停止画布操作，避免在不可用状态下编造视觉稿。
>
> 设计决策（均经架构师验收确认）：
> 1. **未新增任何 design-token** —— 严重度三色/健康徽标/卡片容器全部复用现有 `--color-danger/warning/info/success` + `.card-glass` + `.btn/.btn--primary/.btn--sm` + `.tag/.tag--accent` 等（架构师核验属实，确认采纳）
> 2. **新增的样式类（.health-chip / .issue-row / .issue-severity / .issue-path / .issue-message / .anchor-link）全部复用现有 token**，不引入新设计语义，仅写入 components.css
> 3. 复杂区单独收敛 `needs_semantic=true` 的 issue，配「复制 prompt 交 AI」按钮 + 复制后 toast 反馈
> 4. 加载态复用现有 `.loading-state/.spinner`，健康空态复用 `.empty-state`，无新增组件
>
> 已确认决策（架构师定夺）：
> - **决策点 1** ✅ 不新增 token，全部复用；新增类进 components.css，不动 design-tokens.css
> - **决策点 2** ✅ 复制 prompt 保持 Markdown，但前缀明确「让 AI 用 MCP 工具（maint__knowledgebase_diagnose 复查 + write__ 系列修复）处理」而非仅「判断」，且不写 KB 根路径（AI 经 MCP 自然持有）。见 §7.4
> - **决策点 3** ⚠️ MVP **不做分组批量修复按钮**（不静默修复原则），仅保留分组展示 + 复杂区复制 prompt；「筛选需 AI 协助 →」纯导航锚点可保留。见 §6.2/§11。**⚠️ 该决策已被阶段 B 覆盖**（见下）
> - **决策点 4** ✅ 路由 `#health`；导航入口定在**侧边栏「垃圾箱」下方**（架构师指定，前端 agent 不自行拍板）。见 §15
>
> ### 阶段 B 增补（非复杂问题修复交互）
> 架构师推进「阶段 B：非复杂问题修复交互」，**加回**修复按钮（覆盖 §6.2 的 A5 裁决）：
> - **§6.2 已更新**：非复杂分组（position/index/system）加回**组头单按钮**（修复知识位置/重建索引）+ **issue 行勾选框** + **组头全选框**
> - **§7.6 新增修复确认弹窗**：小描述 +【确认执行】主按钮 +【复制 prompt】次按钮 + 关闭；确认执行 → 调 REST → toast → 自动重查
> - **§4.7 新增 lazy 按钮**「我懒得看了，交给 AI 吧」：复制全部问题 prompt，`total_issues>0` 时显示
> - `metadata` 组**不做**确认执行按钮（归复杂区复制 prompt）；`ref`/`illegal` 组同样走复杂区
> - 复杂区（needs_semantic=true）维持现状
> - 全部新增类（`.issue-checkbox` / `.issue-group__action` / `.btn-lazy-ai` / `.fix-modal__paths` / `.issue-row.is-checked`）**复用现有 token**，无 design-token 增量
>
> ### 阶段二增补（就绪信号视觉设计）
> 架构师推进「阶段二：顶部就绪信号」，已新增 **§3.5 就绪信号**章节：
> - **替换对象**：顶部 `status-indicator`（原显示 AI/锁定/编辑状态点）→ 改为就绪信号；`sidebar-footer__status` 保留 AI/锁定状态**不动**
> - **数据源**：`/api/diagnose/saved`（只读，不触发检查）
> - **三态等长文本**：知识状态健康（绿 `--color-success`，total_issues=0）/「N 个知识存疑」（有 high 红 `--color-danger`，否则黄 `--color-warning`）/ 尚未触发检查（灰 `--text-muted`，无 saved）
> - **交互**：点击进 `#health`；hover 背景 `--bg-secondary` + 状态点 scale(1.15)；更新机制 = 首次读 saved + SSE 订阅 diagnose 事件重读 + 前端本地刷新
> - **新增类**（全复用现有 token）：`.status-indicator__dot--success/--danger/--warning/--muted` + `.status-indicator--readiness`
> - **无 design-token 增量**
>
> ### 阶段三增补（引导页 + 配置页视觉设计）
> 架构师推进「阶段三：初始化引导 + 常驻配置页」，已新增 **§3.6 引导页** 与 **§3.7 配置页** 章节：
> - **引导页（§3.6）**：首次 `!identitySet` 自动触发，3 步（Step1 身份 → Step2 AI 协作初始化 → Step3 完成）；扩展现有 setup 视图为三步向导，含步骤条 `.guide-steps__dot`
> - **Step2 AI 协作初始化**：MCP / hooks / 专用 Agent 三平台分列，每项显示检测状态（已配置 success / 未配置 muted / 检测中 spinner）+ 独立操作按钮；非适配平台 → 「复制 prompt 给 AI」兜底；**不做一键全做**
> - **配置页（§3.7）**：`#settings` 路由，user-menu「配置」入口；3 tab（Profile 用户信息 / General 主题+重新引导+关于 / AI Setting 三平台分列）；复用现有 `.card-glass`、theme-switcher、avatar
> - **半自动化交互**：前端按钮触发 → 后端生成配置 → 前端再检测 → toast（成功/失败）；失败/非适配 → 「复制 prompt 给 AI」兜底（对齐「不静默修复」原则——配置需语义判断，不强制自动生成）
> - **新增类**（全复用现有 token）：`.guide-steps__dot/--active/--done/.guide-steps__line`、`.ai-config-item/__status/__actions`、`.settings-tabs/__item/--active`、`.settings-card`（配置页 tab 若已有 `.tab-nav` 则直接复用）
> - **无 design-token 增量**

---

## 20. 实际实现微调记录（2026-08-15 架构师裁决追加）

> **目的**：`#health` 视图与就绪信号已由前端 agent 实际落地（`frontend/index.html` + `frontend/css/components.css` + `frontend/js/store.js`）。落地实现与本文档理想态存在若干**微调差异**。本章记录这些差异，避免未来 agent 用过时认知实施。**以实际实现（index.html/components.css）为权威，本文档其余章节为设计语义参考。**

### 20.1 落地范围声明

| 部分 | 落地状态 | 位置 |
|---|---|---|
| `#health` 视图（概览卡/问题清单/复杂区/空态/加载态） | ✅ 已落地 | `frontend/index.html:1089+` |
| 阶段 B（勾选框/组头按钮/修复弹窗/lazy 按钮） | ✅ 已落地 | 同上 + `frontend/js/store.js:1382+` |
| 阶段二就绪信号（顶部 status-indicator 替换） | ✅ 已落地 | `frontend/index.html:380-387` + `layout.css:462-483` + `components.css:2029-2043` |
| 阶段三引导页（3 步向导） | ⏳ **未落地**（当前 setup 为**单步 modal**） | `frontend/index.html:1571-1604` |
| 阶段三配置页 | ⏳ **未落地**（无 `#settings` 路由；设计已按裁决改为**配置 modal**） | — |

### 20.2 落地与 SPEC 理想态的差异对照（微调记录）

| 点 | 本文档（设计理想态） | 实际落地实现 | 说明 |
|---|---|---|---|
| 页面 h1 文案 | §3「知识库结构体检」 | **「知识健康检查」**（`index.html:1095`） | 以实际为准 |
| health-chip 配色 | §4.4 `--tag-bg` 灰底灰字 | **count>0 = `--accent-subtle` 底 + `--accent` 字；count=0 = `--bg-tertiary` 底 + `--text-tertiary` 字 + `opacity:0.5`**（`components.css:1820-1848`） | 以实际为准 |
| 「重新检查」+lazy 按钮位置 | §4.5/§4.7 概览卡右上 | **页面标题区（page-header）右侧**，与 h1 同一行 flex（`index.html:1098-1120`） | 以实际为准 |
| 就绪信号容器 | §3.5 复用 status-indicator | **紧凑徽章**：`padding:3px 10px`、`--radius-2xl`(20px)、`--accent-subtle` 底、6px 状态点、`--text-xs`(12px)（`layout.css:462-483`） | 以实际为准；**不画成大卡/无阴影/无注释** |
| 配置页形态 | §3.7 独立 `#settings` 路由页 | **配置 modal 弹窗**（居中 `.modal`，对齐「编辑个人信息」`openModal('edit-identity')` 交互，`index.html:511`；**不新增 `#settings` 路由**） | 架构师裁决：配置用居中 modal 承载 Profile/General/AI Setting 3 tab |
| 引导页形态 | §3.6 3 步向导 | **当前为单步 setup modal**（昵称+邮箱+开始使用，`index.html:1571-1604`）；**3 步向导为阶段三未来 AI 协作初始化设计**（待实现） | 3 步向导保留作未来参考 |
| 配置页入口 | §3.7.1 user-menu「配置」项 | 实际 user-menu 现有「编辑个人信息」(`openModal('edit-identity')`)；**「配置」入口待阶段三实现时加入** | — |
| 修复弹窗 | §7.6 复用 `.modal` | ✅ 已落地（`index.html:1606+`，`fix-modal__desc`/`fix-modal__paths` 见 `components.css:2045-2067`） | 一致 |
| 复杂区 | §7 `complex-zone` | ✅ 已落地（`index.html:1256+`；`components.css:1929-1973`） | 一致 |

### 20.3 SVG 视觉稿状态（2026-08-15）

- SVG 矢量稿已产出至 `designs/kb-health/export/`（7 个 frame：A 健康空态 / B 有问题分组 / C 修复弹窗 / D 加载态 / E 就绪信号紧凑徽章 / F 引导页 3 步 / G 配置弹窗）。
- **标注**：A/B/C/D 标注「仅视觉参考 · 以 index.html 实际实现为准」；F 标注「阶段三待实现：当前 setup 为单步 modal，3 步向导为未来 AI 协作初始化设计」。
- **已知限制**：ardot `export_nodes` 的 SVG 格式将文本节点转为 `<path>`，**不含可读中文 `<text>` 元素**；前端 agent 实施应以 SPEC（语义）+ PNG screenshots（视觉）为准，SVG 仅作矢量视觉参考。

### 20.4 后续 agent 提示

> 接手本功能后续设计/开发时：**先探查 `frontend/index.html` / `components.css` / `store.js` 确认已落地实现**，再判断是否需改设计。已落地部分以实际渲染为准；未落地部分（阶段三引导/配置）以本文档 §3.6/§3.7 + §20.2 差异表为准。
>
> 关于 ardot 适配器：建议本地 MCP 服务方排查连接问题（127.0.0.1:50501）。本任务因该故障降级为 SPEC-only 交付；SVG 为增强视觉参考非硬依赖，记入待办，待适配器恢复后补（落 `designs/kb-health/export/`）。