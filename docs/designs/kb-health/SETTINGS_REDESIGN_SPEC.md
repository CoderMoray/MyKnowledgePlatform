# 设置 Modal 右半页重设计 + AI 协作分组重构 设计规范

> 作者：前端视觉/交互设计 agent
> 日期：2026-08-18
> 用途：本规范为「设置 Modal 右半页重设计 + AI 协作分组重构 + 检测健壮性」任务的**设计权威**。前端开发 agent 据此改 `frontend/index.html` + `frontend/js/store.js` + `frontend/css/components.css`；后端不动，API 契约复用。
> 设计稿 SVG：`docs/designs/kb-health/export/99_57-20260818_111503579.svg`（Frame G4 · modal）
> 截图：`docs/designs/kb-health/screenshots/screenshot-99_57-20260818_111443509.png`

---

## 〇、TL;DR

**范围**：只重设计设置 Modal 右半页 + 左导航分组项；不改其他页面、不改后端。
**核心改动**（5 项）：
1. **左导航重构（5 平级）**：**账号 / 通用 / MCP / Hooks / Agents**（5 平级按钮，**无「AI 协作」分组标签**）
2. **开关替代按钮**：MCP/Hooks/Agents 页内用 **toggle** 表示配置状态，去掉「配置」按钮
3. **去掉复制按钮**：删除原「复制 prompt 给 AI」按钮
4. **fallback 改为可交互文本**：配置失败后，行内显示「一键复制 prompt 给你的 AI」可点击文本（替代 toast 兜底）
5. **检测健壮性 + client_installed 5 态**：右半页 header 加「重新检测」按钮 + null 与 false UI 明确区分 + `client_installed` 平台级 5 态状态机

**导航层级决策（最终版，2026-08-18 架构师裁决）**：**5 平级**（账号 / 通用 / MCP / Hooks / Agents）。用户最初明确此意图，尊重之；取消「AI 协作分组标签 + 3 子项」方案。

**平台命名定稿**：**Claude Code**（CLI）/ **CodeBuddy**（IDE）。

**状态机（最终版）**：3 态（true/false/null）扩展为 **5 态**（× `client_installed` 平台级 bool）——详见 §2.3。

---

## 一、左导航重构（5 平级：账号/通用/MCP/Hooks/Agents）

### 1.1 当前现状
- 左导航 3 项：`account` / `general` / `ai`（`settings-nav__item`）
- `settingsGroup` 单值（`store.js:73`）

### 1.2 目标形态（最终决策：5 平级）
左导航 **5 平级按钮**，无「AI 协作」分组标签：

```
设置
├─ 账号                    (settings-nav__item)
├─ 通用                    (settings-nav__item)
├─ MCP                     (settings-nav__item)
├─ Hooks                   (settings-nav__item)
├─ Agents                  (settings-nav__item)
└─ v1.0.0 · MyKnowledge
```

### 1.3 为什么 5 平级（架构师最终裁决）
- 用户最初明确「左导航最终为 账号/通用/MCP/Hooks/Agents」，尊重其意图
- 三个 kind（MCP/Hooks/Agents）虽语义上是「AI 协作能力」，但作为独立配置页平级展示，每个 kind 一页，清晰直接
- 实现成本最低（`settingsGroup` 单值 5 枚举，无分组/子项逻辑）
- **已取消**早前「AI 协作分组标签 + 3 子项」方案（架构师裁决：用户倾向 5 平级）

### 1.4 不再需要「AI 协作可点击展开/收起」
- 5 平级下，三个 kind 直接平级，无需折叠/展开

### 1.5 settingsGroup 状态值（store.js）
```js
settingsGroup: "account",  // 初始值
// 合法值：account / general / mcp / hooks / agent
```
5 个值，单状态简单。`settingsNav(group)` 接受 5 个值。

### 1.6 HTML 结构（index.html L1722-1759 替换，5 平级）
```html
<div class="settings-nav">
  <div class="settings-nav__title">设置</div>
  <!-- 账号 -->
  <button class="settings-nav__item"
          :class="{ 'settings-nav__item--active': $store.app.settingsGroup === 'account' }"
          @click="settingsNav('account')">
    <svg ...>...</svg> 账号
  </button>
  <!-- 通用 -->
  <button class="settings-nav__item"
          :class="{ 'settings-nav__item--active': $store.app.settingsGroup === 'general' }"
          @click="settingsNav('general')">
    <svg ...>...</svg> 通用
  </button>
  <!-- MCP（平级） -->
  <button class="settings-nav__item"
          :class="{ 'settings-nav__item--active': $store.app.settingsGroup === 'mcp' }"
          @click="settingsNav('mcp')">
    <svg ...>...</svg> MCP
  </button>
  <!-- Hooks（平级） -->
  <button class="settings-nav__item"
          :class="{ 'settings-nav__item--active': $store.app.settingsGroup === 'hooks' }"
          @click="settingsNav('hooks')">
    <svg ...>...</svg> Hooks
  </button>
  <!-- Agents（平级） -->
  <button class="settings-nav__item"
          :class="{ 'settings-nav__item--active': $store.app.settingsGroup === 'agent' }"
          @click="settingsNav('agent')">
    <svg ...>...</svg> Agents
  </button>
  <div class="settings-nav__version" x-text="..."></div>
</div>
```

### 1.7 新增 CSS（components.css）
> **注意**：5 平级**不需要** `.settings-nav__group-label` 与 `.settings-nav__item--child`（分组标签/子项缩进方案已取消）。左导航样式沿用现有 `.settings-nav__item` / `.settings-nav__item--active`，无需新增 nav 相关 CSS。
> 若需为 5 项加图标，给 `.settings-nav__item` 内加 16px svg 即可（复用现有 `settings-nav__item svg` 规则，若已有）。

---

## 二、右半页 AI 协作重设计（开关 + 三态 + fallback 交互）

### 2.1 现状痛点（用户指出）
- 用「配置」按钮表达状态：占位、低密度、不直观
- 复制 prompt 与配置按钮同时存在：信息密集、决策疲劳
- 检测失败与未配置 UI 几乎无区分（都是灰点 + 不同文本）

### 2.2 目标形态
- **开关替代按钮**：toggle 是平台 kind 状态的唯一控件
- **去掉复制按钮**：行内不再放按钮
- **fallback 改为可交互文本**：失败后行下方显示「一键复制 prompt 给你的 AI」（点击触发 copyClientPrompt）
- **5 态 UI 区分**（3 态 × `client_installed`）：
  - `已就绪`（installed + true）→ 开关**实色开** + 状态点 success 绿 + 文本"已配置"
  - `未配置`（installed + false）→ 开关**关**（灰 track）+ 状态点 muted 灰 + 文本"未配置 · 点击开关开启"
  - `已写配置但客户端未装`（!installed + true）→ 开关**浅色开** + 状态点 success 绿(淡) + 文本"请在安装 {客户端} 后使用"
  - `客户端未装且未配置`（!installed + false）→ 开关**浅色关** + 状态点 muted 灰(淡) + 文本"请先安装 {客户端}"
  - `检测失败`（null）→ 开关**灰禁用** + 状态点 warning 橙 + 文本"检测失败 · 点击重新检测"（红色）

> `{客户端}` = 平台标签变量（Claude Code / CodeBuddy）。

### 2.3 开关 5 态交互规范（client_installed × clientStatus）

**后端契约**：`GET /api/client-config` → `{claude: {client_installed, mcp, hooks, agent}, codebuddy: {...}}`
- `client_installed`：平台级 bool（该客户端是否已安装）
- `mcp/hooks/agent`：kind 级 bool（MyKnowledge 条目是否存在）

**状态机**（`clientStatus(platform,kind)` true/false/null × `clientInstalled(platform)` true/false）：

| # | 状态 | 判定 | 开关视觉 | 状态点 | 状态文本 | 交互 |
|---|---|---|---|---|---|---|
| 1 | **已就绪** | installed + true | `toggle--on`（accent 实色，knob 右） | success 绿 | "已配置" | 开关可点：`configureClient`（重配/移除） |
| 2 | **未配置** | installed + false | `toggle--off`（灰，knob 左） | muted 灰 | "未配置 · 点击开关开启" | 开关可点：`configureClient` |
| 3 | **已写配置但客户端未装** | !installed + true | `toggle--on-soft`（**浅色开**） | success 绿(淡) | "请在安装 {客户端} 后使用" | 开关可点：`configureClient`（写配置） |
| 4 | **客户端未装且未配置** | !installed + false | `toggle--off-soft`（**浅色关**） | muted 灰(淡) | "请先安装 {客户端}" | 开关可点：`configureClient`（写配置） |
| 5 | **检测失败** | clientStatus === null | `toggle--failed`（灰 opacity 0.4） | warning 橙 | "检测失败 · 点击重新检测"（红字 500） | **开关禁用**；点击文本 = 「重新检测」 |

**点开关调用**：`configureClient(platform, kind)`（已存在，`store.js:1316`，防重复 `clientConfiguring`）

**!installed 时开关仍可点**（用户决策：置灰但可交互）：点开关调 `configureClient`（后端会 mkdir 写配置）；成功后显示「浅色开 + 请在安装 X 后使用」。

**浅色开视觉**：`.toggle--on-soft`（track 用 accent 40% 透明度或浅紫），比实色开浅，区分「已配置（装好）」vs「已写配置但未装」。

> **裁决硬约束（2026-08-18）**：!installed 态**仅用**「浅色开关（on-soft/off-soft）+ 安装提示文本」表达，**不新增**「未安装」badge/标签（会增视觉噪音）。

**回弹规则**：
- 开关点击 → 立即**视觉切换**（optimistic）→ 调 configureClient
- 成功：`loadClientConfig()` 后真实状态刷新，开关位置保持
- 失败：开关**回弹到原位置**，行下方显示 fallback 可交互文本

### 2.4 fallback 可交互文本（替代 toast 兜底）

**触发**：开关点击后，configureClient 失败（`api.setClientConfig` reject 或返回非 success）

**显示位置**：在该行下方（同一卡内，行间隔 6px）

**样式**：accent 淡紫底（`var(--accent-subtle)`）+ accent 紫字 + 箭头 →

**内容**：`配置失败 · 一键复制 prompt 给你的 AI →` + 副标 `(点击复制 · copyClientPrompt)`

**点击行为**：调 `copyClientPrompt(platform, kind)`（已存在，`store.js:1337`，复制 prompt 到剪贴板 + toast）

**消失**：复制成功 toast 后自动消失；或 5 秒后自动消失；或用户点行关闭按钮

### 2.5 HTML 结构（替换 index.html L1839-1865）
```html
<!-- MCP / Hooks / Agents 复用同一模板，差异仅 kind -->
<div x-show="$store.app.settingsGroup === 'mcp'">  <!-- 也可 hooks / agent -->
  <div style="display:flex;align-items:flex-start;justify-content:space-between;">
    <div>
      <h3 class="settings-body__title">MCP</h3>
      <p class="settings-body__desc">AI 客户端直连本地知识库工具</p>
    </div>
    <button class="btn btn--ghost" @click="loadClientConfig()">⟳ 重新检测</button>
  </div>
  <div class="settings-card">
    <div class="settings-card__title">MCP 服务状态</div>
    <div class="settings-card__desc">开关打开 = 为该平台配置 MCP；关闭 = 移除配置</div>
    <template x-for="plat in $store.app.clientPlatforms" :key="'mcp-' + plat.key">
      <div>
        <div class="ai-platform-row" :data-platform="plat.key" :data-kind="'mcp'">
          <span class="status-indicator__dot"
                :class="{
                  'status-indicator__dot--success': $store.app.clientStatus(plat.key, 'mcp') === true,
                  'status-indicator__dot--muted':   $store.app.clientStatus(plat.key, 'mcp') === false,
                  'status-indicator__dot--warning': $store.app.clientStatus(plat.key, 'mcp') === null
                }"
                :style="$store.app.clientStatus(plat.key, 'mcp') !== null && !$store.app.clientInstalled(plat.key) ? 'opacity:0.5' : ''"></span>
          <span class="ai-platform-row__name" x-text="plat.label"></span>
          <!-- 5 态状态文本 -->
          <span class="ai-platform-row__state"
                :class="{
                  'ai-platform-row__state--ok':   $store.app.clientStatus(plat.key, 'mcp') === true && $store.app.clientInstalled(plat.key),
                  'ai-platform-row__state--soft': $store.app.clientStatus(plat.key, 'mcp') !== null && !$store.app.clientInstalled(plat.key),
                  'ai-platform-row__state--off':  $store.app.clientStatus(plat.key, 'mcp') === false,
                  'ai-platform-row__state--fail': $store.app.clientStatus(plat.key, 'mcp') === null
                }"
                x-text="$store.app.clientStatus(plat.key, 'mcp') === null
                        ? '检测失败 · 点击重新检测'
                        : !$store.app.clientInstalled(plat.key)
                          ? ($store.app.clientStatus(plat.key, 'mcp') ? '请在安装 ' + plat.label + ' 后使用' : '请先安装 ' + plat.label)
                          : ($store.app.clientStatus(plat.key, 'mcp') ? '已配置' : '未配置 · 点击开关开启')"></span>
          <!-- 5 态开关 -->
          <button class="toggle"
                  :class="{
                    'toggle--on':       $store.app.clientStatus(plat.key, 'mcp') === true && $store.app.clientInstalled(plat.key),
                    'toggle--off':      $store.app.clientStatus(plat.key, 'mcp') === false && $store.app.clientInstalled(plat.key),
                    'toggle--on-soft':  $store.app.clientStatus(plat.key, 'mcp') === true  && !$store.app.clientInstalled(plat.key),
                    'toggle--off-soft': $store.app.clientStatus(plat.key, 'mcp') === false && !$store.app.clientInstalled(plat.key),
                    'toggle--failed':   $store.app.clientStatus(plat.key, 'mcp') === null
                  }"
                  :disabled="$store.app.clientStatus(plat.key, 'mcp') === null || $store.app.isClientConfiguring(plat.key, 'mcp')"
                  @click="$store.app.clientStatus(plat.key, 'mcp') === null
                          ? loadClientConfig()
                          : configureClient(plat.key, 'mcp')">
            <span class="toggle__knob"></span>
          </button>
        </div>
        <!-- fallback 可交互文本：配置失败时显示 -->
        <div class="ai-platform-fallback"
             x-show="$store.app.clientFallback === plat.key + '-mcp'">
          <span x-text="'配置失败 · 一键复制 prompt 给你的 AI →'"></span>
          <span class="ai-platform-fallback__hint" x-text="'（点击复制 · copyClientPrompt）'"></span>
        </div>
      </div>
    </template>
  </div>
</div>
```

### 2.6 新增 store.js 状态（clientFallback + clientInstalled + 平台标签）
```js
data() {
  return {
    // ... 现有 ...
    /** 配置失败回弹时显示在行下方的「一键复制 prompt」key，null = 不显示 */
    clientFallback: null,  // 形如 "claude-mcp"
    /** 平台级「客户端是否已安装」（后端 client_installed，只读） */
    // 读取：this.clientConfig?.[platform]?.client_installed，见下方 clientInstalled()
  };
}

/** 平台标签定稿：Claude Code（CLI）/ CodeBuddy（IDE） */
clientPlatforms: [
  { key: "claude",    label: "Claude Code" },  // ← 从 "Claude" 改为 "Claude Code"
  { key: "codebuddy", label: "CodeBuddy" },
],

/** 平台级客户端是否已安装（返回 bool 或 undefined） */
clientInstalled(platform) {
  return this.clientConfig?.[platform]?.client_installed;
},

// configureClient 失败时设置 fallback 文本 + 5 秒后自动清除
async configureClient(platform, kind) {
  if (this.clientConfiguring) return;
  this.clientConfiguring = { platform, kind };
  this.clientFallback = null;
  try {
    const res = await api.setClientConfig(platform, kind);
    await this.loadClientConfig();
    // ... toast 成功 ...
  } catch (e) {
    // 配置失败：开关回弹（loadClientConfig 后真实状态刷新）+ 行下显示 fallback
    this.clientFallback = `${platform}-${kind}`;
    setTimeout(() => { this.clientFallback = null; }, 5000);
    // 不再 toast「配置失败」（用行内 fallback 文本替代）
  } finally {
    this.clientConfiguring = null;
  }
}
```

> **5 态判定**：在 HTML 中组合 `clientStatus(platform,kind)`（true/false/null）+ `clientInstalled(platform)`（true/false/undefined）得 5 态。`clientInstalled` 为 undefined 时按未安装处理（保守）。

### 2.7 新增 CSS（components.css）
```css
/* AI 平台行：开关 + 平台名 + 状态（信息密度降低） */
.ai-platform-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
  border-top: 1px solid var(--border-subtle);
}
.ai-platform-row__name {
  flex: 1;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}
.ai-platform-row__state {
  font-size: var(--text-xs);
  color: var(--text-secondary);  /* 改进：secondary 非 tertiary */
  white-space: nowrap;
}
.ai-platform-row__state--ok   { color: var(--color-success); }
.ai-platform-row__state--off  { color: var(--text-tertiary); }
.ai-platform-row__state--soft { color: var(--text-secondary); }  /* !installed 浅色提示 */
.ai-platform-row__state--fail { color: var(--color-danger); font-weight: 500; }

/* 开关（5 态：on / off / on-soft / off-soft / failed） */
.toggle {
  position: relative;
  width: 36px;
  height: 20px;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
  transition: background var(--transition-interactive);
}
.toggle__knob {
  position: absolute;
  top: 3px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  transition: left var(--transition-interactive);
}
/* 1 已就绪：实色开（装好） */
.toggle--on  { background: var(--accent); }
.toggle--on .toggle__knob { left: 19px; }
/* 2 未配置：关（可点） */
.toggle--off { background: #d1d5db; }
.toggle--off .toggle__knob { left: 3px; }
/* 3 已写配置但未装：浅色开（accent 40%） */
.toggle--on-soft  { background: rgba(99, 102, 241, 0.4); }
.toggle--on-soft .toggle__knob { left: 19px; }
/* 4 未装且未配置：浅色关（更淡灰） */
.toggle--off-soft { background: #e5e7eb; opacity: 0.7; }
.toggle--off-soft .toggle__knob { left: 3px; }
/* 5 检测失败：灰禁用 */
.toggle--failed {
  background: #d1d5db;
  opacity: 0.4;
  cursor: not-allowed;
}
.toggle--failed .toggle__knob { left: 3px; opacity: 0.7; }
.toggle:disabled { cursor: not-allowed; }

/* fallback 可交互文本（行内） */
.ai-platform-fallback {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 6px 0 12px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  background: var(--accent-subtle);
  color: var(--accent);
  font-size: var(--text-xs);
  font-weight: 500;
  cursor: pointer;
}
.ai-platform-fallback:hover { background: rgba(99, 102, 241, 0.1); }
.ai-platform-fallback__hint {
  font-size: var(--text-2xs);
  color: var(--text-tertiary);
  font-weight: 400;
}
```
**全复用现有 token**：accent、accent-subtle、color-success/danger、border-subtle、text-primary/secondary/tertiary、radius-md、text-xs/sm/2xs、transition-interactive。

---

## 三、右半页视觉重设计（对比度 + 布局）

### 3.1 对比度提升（核心痛点）

| 元素 | 原样式 | 新样式 |
|---|---|---|
| `.settings-body__desc` | `--text-xs` + `--text-tertiary`（弱灰） | `--text-sm` + `--text-secondary`（次级灰，可读层级） |
| `.settings-card__desc` | `--text-2xs` + `--text-tertiary`（10px 极弱灰） | `--text-xs` + `--text-secondary`（11px 次级灰） |
| `.settings-card__title` | `--text-sm` 600 `--text-primary` | **保持**（已正确） |
| `.settings-body__title` | `--text-lg` 600 `--text-primary` | **保持** |

**效果**：建立清晰 **title (primary) → desc (secondary) → 正文** 三级层次。

### 3.2 布局改进：引导卡一行排布

**现状**（index.html L1824-1830）：
```
引导卡
├─ 标题"引导"（上）
├─ 描述"重新运行初始化引导..."（上）
└─ 按钮"重新运行初始化引导"（独占一行，下方 margin-top:12px）
```

**改进**（一行排布）：
```
引导卡（flex space-between）
├─ 左：标题 + 描述（flex column）
└─ 右：按钮「重新运行初始化引导」
```

**HTML**：
```html
<div class="settings-card">
  <div class="settings-card__row">
    <div class="settings-card__row-text">
      <div class="settings-card__title">引导</div>
      <div class="settings-card__desc">重新运行初始化引导，再次配置身份与 AI 协作</div>
    </div>
    <button class="btn" @click="$store.app.rerunGuide()">重新运行初始化引导</button>
  </div>
</div>
```

**CSS**：
```css
.settings-card__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.settings-card__row-text {
  flex: 1;
  min-width: 0;
}
```

### 3.3 面板/遮罩聚焦感

| 元素 | | 新 |
|---|---|---|
| `.modal-overlay` 背景 | `rgba(0,0,0,0.28)` | `rgba(0,0,0,0.35)`（适度加深，聚焦 modal） |

**注意**：仅 settings modal 的遮罩可加；其他 modal（setup/health-fix）保持原值。

---

## 四、检测健壮性

### 4.1 「重新检测」入口

- **位置**：右半页 header 右上（与标题/副说明同一行 flex space-between）
- **文案**：「⟳ 重新检测」（带 spinner 图标）
- **样式**：`.btn .btn--ghost`（透明 + accent 边框）
- **点击**：调 `loadClientConfig()`（`store.js:1301`，失败置 null；成功后刷新 clientConfig）
- **加载态**：按钮转 spinner + disabled（复用 `clientConfiguring` 思路或加 `clientDetecting`）

### 4.2 null 与 false UI 明确区分（已在 §2.3 体现）

**null 检测失败态**：
- 状态点：`status-indicator__dot--warning`（橙）
- 状态文本：`ai-platform-row__state--fail`（红色 `--color-danger` 500 weight）
- 开关：`toggle--failed`（opacity 0.4，禁用 pointer-events）
- 提示文本："检测失败 · 点击重新检测"

**false 未配置态**：
- 状态点：`status-indicator__dot--muted`（灰）
- 状态文本：`ai-platform-row__state--off`（tertiary）
- 开关：`toggle--off`（灰 track，可点）
- 提示文本："未配置 · 点击开关开启"

### 4.3 loadClientConfig 健壮性

**现有**（`store.js:1301-1308`）：
```js
async loadClientConfig() {
  try {
    const data = await api.getClientConfig();
    this.clientConfig = data || {};
  } catch (e) {
    this.clientConfig = null;  // UI 显示「检测失败」
  }
}
```

**健壮性补充**：
- 后端离线/异常 → clientConfig=null → UI 全行显示 null 态（开关禁用 + 检测失败）
- 用户点「重新检测」→ 重新调 loadClientConfig → 成功后 clientConfig 恢复 → UI 自动刷新
- **无永久 stuck**：每次重新检测都给恢复机会

---

## 五、不改的范围（明确边界）

- **不动后端**：API 契约（`GET /api/client-config`、`POST /api/client-config/{platform}/{kind}`）完全复用
- **不改其他页面**：引导页 setup、账号卡、通用主题切换、其他 modal（setup/health-fix）保持原样
- **不改 store.js 现有函数签名**：`clientStatus`/`configureClient`/`copyClientPrompt`/`loadClientConfig` 复用，仅扩展 `configureClient` 失败处理（加 clientFallback 状态）
- **不改 data() 现有字段**：仅新增 `clientFallback`（+ 可选 `clientDetecting` 加载态）
- **不破坏现有功能**：账号保存、通用主题切换、「重新运行初始化引导」仍工作

---

## 六、验收对照（前端开发 agent 执行）

| 验收点 | 验证方式 |
|---|---|
| 5 项导航切换正常 | 手工：点 账号/通用/MCP/Hooks/Agents 切换右半页 |
| MCP/Hooks/Agents 每页 2 平台开关状态正确 | 手工：观察 Claude/CodeBuddy 开关位置与状态文本 |
| true/false/null 三态视觉区分 | 手工：观察 success 绿 / muted 灰 / warning 橙 + 禁用开关 |
| 点开关触发配置（true/false 态） | 手工：点开关→ 后端 POST → 状态刷新 |
| 失败显示「一键复制 prompt」 | 手工：模拟后端失败 → 行内 fallback 文本出现 |
| 点 fallback 文本复制 prompt | 手工：点文本 → 剪贴板 toast |
| 「重新检测」恢复状态 | 手工：点按钮 → 后端 GET → 刷新 |
| 引导卡不独占一行 | 手工：通用页 → 引导卡 = 标题左/按钮右一行 |
| desc 可读 | 手工：副说明/卡描述 secondary 灰清晰可读 |
| 遮罩聚焦 | 手工：settings modal 打开时背景适度暗化 |
| 前端构建通过 | `python3 frontend/build.py` |
| 后端回归通过 | `pytest tests/ --ignore=tests/frontend -q` → 517 passed |

---

## 七、零设计-token 增量声明

新增样式类（`.settings-nav__group-label`、`.settings-nav__item--child`、`.ai-platform-row__name/state`、`.toggle`、`.toggle--on/off/failed`、`.toggle__knob`、`.ai-platform-fallback`、`.settings-card__row`、`.settings-card__row-text`）**全复用现有 design-token**（accent、accent-subtle、color-success/danger、border-subtle、text-primary/secondary/tertiary、radius-md、text-xs/sm/2xs、transition-interactive）。**无 design-tokens.css 修改**。