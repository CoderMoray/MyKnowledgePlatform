# MyKnowledge 前端架构设计方案

> 状态：实施中 | 日期：2026-07-24 | 修订：v2.0（Raycast 默认主题 + Light/Dark/System + 设计令牌就位）

---

## 0. 一句话定位

**单页 Web 应用（SPA）**，纯静态部署在 `frontend/` 目录，通过 `fetch()` 直接调用本地 FastAPI（`127.0.0.1:8080`），零构建步骤、零外部依赖的 CDN 运行时。

---

## 1. 技术选型

### 1.1 框架：Alpine.js（+ 原生 JS 模块）

| 候选方案 | 体积 | 构建步骤 | 适用性判断 |
|----------|------|----------|-----------|
| **Alpine.js 3.x** ✅ | ~15KB gzip | 无（CDN `<script>`） | **推荐**。响应式数据、条件渲染、列表渲染、事件绑定，恰好覆盖 Web UI 全部需求 |
| 纯 Vanilla JS | 0 | 无 | 需手写 DOM diff/状态管理，当功能超过 3 个页面时维护成本剧增 |
| Vue 3 (CDN) | ~33KB gzip | 无 | 能力强但体量偏大，且组件系统对此项目规模略显「杀鸡用牛刀」 |
| React (CDN) | ~40KB gzip | 需要 JSX 转译 | 必须有构建步骤（或 `htm` 运行时），不符合「零构建」要求 |

**决策：** Alpine.js。理由：
- **零构建步骤** — `<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3">` 即可
- **响应式状态** — `x-data` / `x-bind` / `x-show` / `x-for` 覆盖树形导航、锁状态、编辑器切换
- **DOM 事件** — `@click` / `@submit` / `@keydown` 与原生行为一致
- **渐进增强** — 不改造 HTML 结构也能生效，与现有 `index.html` 骨架兼容

### 1.2 阅读态渲染：marked + highlight.js

| 库 | 体积 | 角色 |
|----|------|------|
| **marked** ✅ | ~20KB gzip | Markdown → HTML 渲染引擎，可定制 renderer 处理 `ref:` 链接 |
| **highlight.js** | ~10KB gzip | 代码块语法高亮，marked 的渲染增强（类比 pygments 之于 Python markdown） |
| **js-yaml** | ~15KB gzip | YAML 解析器，用于从 Markdown 文件中提取 frontmatter 元数据（类比 PyYAML） |

三者是**独立互补的库**，不是 marked 的子包。marked 负责正文渲染，highlight.js 负责代码着色，js-yaml 负责元数据解析。均从 CDN 加载，零依赖。

**链接处理方案（三种类型）：**
`marked` 的 `renderer.link` 判断 `href` 前缀，生成不同的 HTML：

| 前缀 | 渲染 | 行为 |
|------|------|------|
| `ref:` | `<a class="ref-link" data-ref-path="...">` | hover 文档摘要卡片，点击跳转文档 |
| `http(s)://` | `<a class="ext-link" data-ext-link="...">` | hover 显示 URL，点击新标签页打开 |
| `ref:` 不存在 | 同上 | hover 红色「文件不存在」提示 |

hover 延迟 200ms 弹出，移出 200ms 关闭。`fixed` 定位在链接右下方。

### 1.3 编辑器方案：TipTap 2.x（WYSIWYG 所见即所得）

**核心原则：用户永远不看到 Markdown 源码。** 编辑时面对的是渲染后的富文本界面，像用 Word 一样直接操作格式化内容。

| 候选方案 | 体积 | 判断 |
|----------|------|------|
| **TipTap 2.x** ✅ | ~120KB gzip | ProseMirror 内核，无头设计（UI 完全自定义），200+ 扩展，Markdown 快捷键支持（`# ` → 标题、`**text**` → 加粗），可输出 HTML/Markdown/JSON |
| Milkdown | ~80KB gzip | ProseMirror 内核，Markdown-native WYSIWYG，但社区小、文档少 |
| Quill | ~100KB gzip | 老牌富文本，但架构不如 ProseMirror 现代，定制能力弱 |
| Slate | ~50KB | 灵活但需大量手写逻辑，不适合 MVP |

**决策：TipTap 2.x。**

**为什么 TipTap 是正确选择：**

1. **纯 WYSIWYG** — 用户永远看不到 `## heading **bold**` 这种 Markdown 源码。输入 `# ` 自动变成标题样式，选中文字按 `Ctrl+B` 直接加粗渲染，和 notion/confluence 的编辑体验一致
2. **Markdown 快捷键** — 支持 `# ` `## ` `- ` `> ` ` ``` ` `**text**` 等常用 Markdown 输入习惯，内核自动转换，兼容 Markdown 用户的肌肉记忆
3. **自定义 extension** — 可以写一个 `RefLink` Node 来渲染知识引用 `[文档](ref:path)`，编辑时显示为特殊样式标记，可点击预览
4. **导入导出** — 加载时 `.md` → marked 转 HTML → TipTap 导入；保存时 TipTap 导出 HTML → turndown 转 Markdown → 写回后端

**Markdown ↔ WYSIWYG 转换链路：**

```
┌─ 加载 ─────────────────────────────────────────────┐
│  GET /api/document/{path}                           │
│       ↓ .md 原文                                    │
│  marked 渲染 → HTML                                  │
│       ↓                                             │
│  TipTap 导入 HTML → ProseMirror 内部模型             │
│       ↓                                             │
│  用户看到 WYSIWYG 富文本界面（无源码）                │
└────────────────────────────────────────────────────┘

┌─ 保存 ─────────────────────────────────────────────┐
│  用户编辑完成，点击保存                               │
│       ↓                                             │
│  TipTap 导出 HTML                                   │
│       ↓                                             │
│  turndown 转换 → 干净 Markdown                       │
│       ↓                                             │
│  PUT/POST /api/document/{path}                      │
└────────────────────────────────────────────────────┘
```

**前端侧额外依赖：**
- **turndown**（~15KB gzip）— HTML → Markdown 转换器，保存时用。同样是 CDN 加载

> **为什么不做 Markdown ↔ ProseMirror 直接互转？** ProseMirror-JSON 与 Markdown 的语义模型不完全对齐（列表嵌套、引用块、复杂表格），直接用 HTML 做中介格式最可靠，也有成熟工具链 (marked + turndown) 保证。

### 1.4 CSS 方案：CSS Custom Properties + 简洁组件样式

不引入 CSS 框架（Tailwind/Bootstrap 太重），用 CSS variables 组织设计令牌：

```css
:root {
  --color-bg: #fafafa;
  --color-surface: #fff;
  --color-border: #e5e7eb;
  --color-text: #1a1a2e;
  --color-text-secondary: #6b7280;
  --color-primary: #4f46e5;
  --color-locked: #f59e0b;     /* 锁状态警告色 */
  --sidebar-width: 260px;
  --font-mono: 'SF Mono', 'Fira Code', monospace;
  --font-sans: -apple-system, BlinkMacSystemFont, sans-serif;
  --radius: 8px;
}
```

后期扩展暗色模式只需加 `[data-theme="dark"]` 变量覆盖，零额外 CSS。

---

## 2. 技术栈总览

```
运行时（CDN，零 npm install）：

  框架 & 状态：
    alpinejs@3          — 响应式框架（~15KB gzip）

  渲染（阅读态）：
    marked               — Markdown → HTML（~20KB gzip）
    highlight.js         — 代码语法高亮（~10KB gzip）
    js-yaml              — frontmatter 元数据解析（~15KB gzip）

  编辑器（WYSIWYG）：
    @tiptap/core         — WYSIWYG 编辑器内核
    @tiptap/starter-kit  — 常用扩展集合（标题/加粗/列表/引用/代码块）
    @tiptap/extension-link  — 超链接
    turndown             — HTML → Markdown（保存时，~15KB gzip）

无需构建，浏览器直接运行。
```

---

## 3. 前端目录结构

```
frontend/
├── index.html                 # 入口 SPA 壳
├── css/
│   ├── variables.css          # CSS 自定义属性（设计令牌）
│   ├── reset.css              # 最小化 reset
│   ├── layout.css             # 主布局（sidebar + content）
│   ├── sidebar.css            # 侧边栏树形导航
│   ├── viewer.css             # 文档阅读视图
│   ├── editor.css             # 编辑器视图
│   ├── components.css         # 通用组件（按钮、面包屑、状态栏、弹窗）
│   ├── markdown-content.css   # 渲染后的 Markdown 内容样式（对标 GitHub）
│   └── tiptap.css              # TipTap 编辑器样式覆盖
├── js/
│   ├── app.js                 # Alpine 主 store + 初始化（SPA 入口）
│   ├── api.js                 # REST API 客户端（fetch 封装 + 统一错误处理）
│   ├── store.js               # 全局状态管理（Alpine.store）
│   ├── router.js              # Hash 路由（#/browse/... 等）
│   ├── renderer.js            # 阅读态 Markdown 渲染（marked + ref: 链接浮层）
│   ├── converter.js           # Markdown ↔ WYSIWYG 转换（marked + turndown）
│   ├── utils.js               # 工具函数（路径拼接、日期格式化）
│   └── components/
│       ├── sidebar.js         # 侧边栏：文件树加载 + 展开/折叠 + 客户端搜索
│       ├── toolbar.js         # 工具栏：新建、编辑、删除、刷新
│       ├── dashboard.js       # 仪表盘：项目概览、最近更新
│       ├── viewer.js          # 文档阅读器：渲染 Markdown + 引用展开
│       ├── editor.js          # WYSIWYG 编辑器：TipTap 初始化 + Markdown 转换
│       ├── breadcrumb.js      # 面包屑导航
│       ├── status-bar.js      # 底部状态栏：锁状态 + 同步状态
│       └── modals.js          # 确认弹窗（删除确认、锁提示等）
└── README.md                  # 前端说明（已有）
```

### 为什么这样拆分？

| 文件 | 职责 | 拆分原则 |
|------|------|---------|
| `store.js` | 全局状态（当前路径、文档内容、锁状态、加载状态） | 单一数据源 |
| `router.js` | URL ↔ 视图映射 | 独立于框架，可替换 |
| `renderer.js` | 阅读态 `marked` 配置 + `ref:` 链接浮层 | 纯函数，可测试 |
| `converter.js` | Markdown → HTML（加载） + HTML → Markdown（保存） | 纯转换逻辑，不依赖 DOM |
| `api.js` | 所有 fetch 请求 | 统一拦截 423 / 404 / 500 |
| `components/*.js` | 每个 UI 组件的 Alpine 初始化和事件注册 | 一个文件一个组件，职责单一 |

---

## 4. 页面路由设计

使用 Hash 路由（`#/...`），纯前端处理，无需服务器支持。

| 路由 | 视图 | 说明 |
|------|------|------|
| `#/` | 仪表盘 | 知识库总览：最近修改、项目列表、快捷入口 |
| `#/browse/` | 树形浏览器 | 根目录文件树 |
| `#/browse/<path>` | 树形浏览器 | 项目/子目录文件树（`path` 为 KB 相对路径） |
| `#/view/<path>` | 文档阅读器 | 渲染 Markdown 全文 + 引用展开 |
| `#/edit/<path>` | 文档编辑器 | 编辑已有文档 |
| `#/new?parent=<path>` | 文档编辑器 | 在指定目录下新建文档 |
| `#/status` | 系统状态 | 项目完整性检查结果、GC 报告 |

### 路由逻辑

```
用户点击侧边栏文档 → router.navigate('view', path)
                                 ↓
                         store.currentPath = path
                         store.currentView = 'viewer'
                                 ↓
                         触发 viewer 组件加载 /api/document/{path}
```

所有路由切换均为客户端行为，不刷新页面。

---

## 5. 核心交互流程

### 5.1 启动流程

```
页面加载
  │
  ├─ [并行]
  │     ├─ fetch /api/status        → 获取项目状态
  │     └─ fetch /api/list/         → 获取根目录结构
  │
  ├─ 渲染侧边栏文件树
  ├─ 渲染仪表盘概览
  └─ 启动锁状态轮询（每 30s 一次）
```

### 5.2 浏览文档 + ref: 引用展开

```
侧边栏点击文档
  │
  ├─ /api/document/{path}           → 获取 Markdown 原文
  ├─ marked 渲染为 HTML 阅读视图
  ├─ 检测文档中所有 [text](ref:path::section) 引用
  │     ├─ 渲染为可交互的 📄 文档名 标记
  │     └─ 点击任一引用 → 浮层加载 /api/document/{path}/refs 显示引用内容
  └─ 引用浮层支持嵌套展开（引用文档中又有 ref: 链接，可继续点击）
```

#### 5.2.1 ref 链接格式约定（前端定稿，后端 S16 对齐）

链接结构：`[显示文本](ref:目标路径[::章节标题])`——三段语义独立：显示文本 / 目标路径（KB 相对路径）/ 章节锚点（可选）。

1. **空 target 渲染**：`[文本](ref:)`（ref 后为空/纯空格）→ **不渲染为链接，显示为纯文本"文本"**（链接文字保留）。
   实现：renderer.js ref 分支 `if (!rawPath.trim()) return text || ""`（提交 2524463）。
   「文本」部分是**引用意图证据**——后端空 target 文案可引导 AI 顺着显示文本找回目标。
2. **空格编码规则**：存储用 **`%20` 编码**（`[文本](ref:门店%20周报.md)`）。
   - 前端：编辑器输入自动 `replace(/ /g, "%20")`；渲染解码 `%20→空格` 显示；保存（Turndown）输出空格原文
   - 后端 S16：读入 unquote（`%20→空格`），写盘 normalize（`空格→%20`，幂等）——**正好兜住前端保存的空格原文**，落盘统一 `%20`
   - 两端闭环：**存储 %20、显示/编辑解码空格、后端 unquote+normalize 兜底**
3. **链接文本语义**：`[文本]` = 用户可见的显示文本——编辑器输入（用户填写或选中文字）、粘贴/手写 markdown 原文，均**非空、非系统占位符、可读可靠**；空 target 时前端保留该文本作为引用意图。

### 5.3 编辑文档（WYSIWYG 所见即所得）

```
用户点击「编辑」→ 进入编辑视图
  │
  ├─ 加载 .md → marked 转 HTML → TipTap 导入 → 显示富文本
  ├─ 顶部表单：标题 / 摘要（frontmatter summary）输入框
  ├─ 主体：TipTap WYSIWYG 编辑器（无 Markdown 源码，纯富文本操作）
  │     ├─ 工具栏：加粗 / 斜体 / 标题 / 列表 / 引用 / 代码块 / 链接 / ref引用
  │     ├─ Markdown 快捷键：输入 # ## - > ``` 自动转换
  │     └─ ref: 链接渲染为特殊标记 📄 文档名，可点击预览但不能在编辑器中修改引用内容
  └─ 底部：保存 / 取消

保存时：
  TipTap.getHTML() → turndown → 干净 Markdown
  POST /api/document/{path}  (新建)
  或 PUT /api/document/{path}  (更新)
  │
  ├─ 成功 → 刷新侧边栏（readme 重建后文件列表可能变化） + 跳转阅读视图
  └─ 423 Locked → 弹窗提示「AI 正在操作」，保持编辑内容不丢失
```

### 5.4 删除文档

```
点击「删除」→ 确认弹窗（显示文件名 + 路径）
  │
  ├─ 确认 → DELETE /api/document/{path}
  │     ├─ 成功 → 侧边栏移除该条目 + 跳转父目录
  │     └─ 423 → 提示只读
  └─ 取消 → 关闭弹窗
```

---

## 6. 锁定状态处理

### 6.1 锁状态检测策略

后端在写入操作时按需检测 `.lock` 文件。前端有两种策略：

| 策略 | 实现 | 优劣 |
|------|------|------|
| **推断式** ✅ | 写入请求返回 423 → 标记为 locked；下次成功写入 → 标记为 unlocked | 零额外请求，但锁释放后不能立刻感知 |
| 轮询式 | 每 30s GET `/api/status` 或专用 lock endpoint，解析是否锁定 | 实时但增加请求 |

**推荐：混合策略。**
- 每 60s 轮询 `GET /api/lock` 获取锁状态
- 同时写入请求返回 423 → 立即标记为 locked（不等待下次轮询）
- 锁状态变化时在 UI 即时反映

### 6.2 UI 表现

当 `store.isLocked === true` 时：

| 区域 | 只读模式表现 |
|------|-------------|
| 全局顶部 | 黄色横幅：「⚠️ AI 正在操作知识库，当前为只读模式」 |
| 工具栏 | 【新建】【编辑】【删除】按钮全部 `disabled` + 灰色 |
| 编辑器 | 切换为只读预览模式，提示用户等 AI 完成后再编辑 |
| 侧边栏 | 照常浏览，无影响 |
| 查看文档 | 照常阅读，无影响 |

锁解除后，横幅消失，按钮恢复可用。

### 6.3 锁超时（死锁）

后端定义 `_LOCK_TIMEOUT`（5 分钟），超时的锁会被自动清除。前端无需感知超时逻辑——后端返回 423 时才通知前端。如果用户看到锁提示超过 5 分钟仍未解除，应检查 AI agent 是否异常退出。

---

## 7. MVP 功能清单

以**「能浏览 + WYSIWYG 编辑 + 锁感知 + 仪表盘 + ref:引用」**为最小闭环。

| 编号 | 功能 | 优先级 | 说明 |
|------|------|--------|------|
| M1 | 侧边栏文件树 | P0 | 从 `/api/list/` 递归加载，目录可展开/折叠，文档可点击，支持客户端搜索过滤 |
| M2 | Markdown 文档阅读 | P0 | `/api/document/{path}` → marked 渲染为富文本（表格、代码、列表、图片） |
| M3 | 面包屑导航 | P0 | 显示当前路径层级，每级可点击跳转 |
| M4 | 创建新文档 | P0 | 弹窗：文件名 + 摘要 → 进入 WYSIWYG 编辑器，POST 创建 |
| M5 | WYSIWYG 编辑文档 | P0 | TipTap 富文本编辑，用户不看到 Markdown 源码。`Ctrl+B` 加粗、`# ` 变大标题 |
| M6 | 删除文档 | P0 | 确认弹窗 → DELETE |
| M7 | 锁状态感知 | P0 | 轮询 `GET /api/lock` + 写入 423 推断 → 全局只读提示 + 禁用编辑按钮 |
| M8 | 仪表盘 | P0 | 页面加载即首页，展示项目数/文档数/最近更新/快速入口 |
| M9 | `ref:` 引用展开 | P0 | **阅读态**：点击引用标记浮层预览引用内容。**编辑态**：引用显示为 `📄 文档名` 标记，可点击预览但不可修改引用源 |
| M10 | Markdown 快捷键 | P0 | TipTap 内置：`# ` `## ` `- ` `> ` ` ``` ` `**text**` 自动转为格式化内容 |
| M11 | 编辑项目元信息 | P2 | 修改项目 name/summary/status（`PUT /api/project/`） |
| M12 | 系统完整性检查 | P2 | `POST /api/check` + 展示 GC 结果 |

> **M10 是 TipTap starter-kit 自带能力**，不是额外开发量。只要安装即得。

### MVP 不做的（Phase 2+）

- 全文搜索（需要 FTS5 服务端或客户端索引库）
- 分享包 UI（`.mkpkg` 导入/导出）
- Git diff 可视化
- 拖拽排序/移动文件
- 暗色模式
- PWA 离线支持
- 多标签页编辑
- 图片上传

---

## 8. 后端 API 依赖（前端调用清单）

所有端点已就绪，无需后端变更。前端仅做调用。

| 前端功能 | 调用的 API | 数据格式 |
|----------|-----------|----------|
| 加载侧边栏 | `GET /api/list/{path}` | 制表符分隔文本 → 前端解析 |
| 浏览文件树深层 | `GET /api/list/{path}`（逐层展开，非递归） | 同上 |
| 查看文档 | `GET /api/document/{path}` | Markdown 原文 → marked 渲染 |
| 查看文档+引用 | `GET /api/document/{path}/refs` | Markdown + 拼接引用 |
| 创建文档 | `POST /api/document/{path}` (`{content, summary}`) | JSON → JSON |
| 更新文档 | `PUT /api/document/{path}` (`{content, summary}`) | JSON → JSON |
| 删除文档 | `DELETE /api/document/{path}` | — |
| 编辑项目元信息 | `PUT /api/project/{path}` (`{name, summary, status}`) | JSON → JSON |
| 仪表盘数据 | `GET /api/status/detail` | JSON（结构化状态） |
| 锁状态轮询 | `GET /api/lock` | JSON `{locked, pid, since}` |
| GC + 检查 | `POST /api/check` | JSON |

---

## 9. 扩展性评估

基于对这个项目的理解和经验，以下是我认为 MVP 之外应该考虑的增强：

### 9.1 短期（MVP 后第一轮迭代）

| 增强 | 价值 | 复杂度 |
|------|------|--------|
| **客户端全文搜索** | 用 lunr.js 或 FlexSearch（~10KB），在侧边栏加载完整文件树后本地索引 + 实时过滤。适合文档量 < 500 的场景 | 低 |
| **键盘快捷键** | `Ctrl+K` 搜索文件、`Ctrl+E` 编辑当前文档、`Ctrl+S` 保存 — 显著提升效率 | 低 |
| **文件修改状态追踪** | 编辑器「未保存」提醒 + 侧边栏标记有未提交修改的文档（与 Git dirty 对照） | 低 |
| **阅读位置记忆** | 切换文档时记住滚动位置，返回时恢复 | 极低 |

### 9.2 中期（1-2 个月）

| 增强 | 价值 | 复杂度 |
|------|------|--------|
| **双栏对比模式** | 同时查看两份文档（适合合并冲突、对比版本）。本质是两个 viewer 并排 | 中 |
| **暗色模式** | CSS variables 切换，一次性投入，长期受益 | 低 |
| **拖拽重组** | 侧边栏拖拽文件到不同目录（重命名/移动的 UI），对应 `move` API | 中 |
| **Git 历史可视化** | 展示文件的 commit log + diff（需要新增 `GET /api/document/{path}/history` 接口） | 中 |
| **分享包 Web UI** | 可视化 `.mkpkg` 的创建（选择项目 → 加密导出）和导入（预览内容 → 确认合并） | 高 |

### 9.3 长期（3 个月+）

| 增强 | 价值 | 复杂度 |
|------|------|--------|
| **知识图谱视图** | 基于 `[ref:]` 引用关系渲染 D3.js 力导向图，展示文档间关联 | 高 |
| **PWA 离线模式** | Service Worker 缓存静态资源 + API 响应，断网也能浏览已加载的文档 | 中 |
| **多知识库切换** | 如果用户有多个 `.myknowledge/` 目录，提供切换入口 | 中 |
| **Web 端 AI 助手面板** | 嵌入一个对话面板，通过 MCP 协议与本地 agent 通信（不内置 LLM，只做消息中转） | 高 |
| **移动端适配** | 响应式侧边栏（抽屉式） + 触控优化 | 中 |

### 9.4 特别建议：不在前端做但应想清楚的

- **协作冲突**：如果两个 Web UI 同时编辑同一文档（多 Tab 场景），当前靠 `.lock` 机制保护写入，但前端应在前端提示「此文档可能已在其他标签页被修改」——可通过 `updated` frontmatter 时间戳对比实现乐观锁。
- **大文件处理**：如果 Markdown 文件超过 100KB，marked 渲染可能卡顿。建议在 viewer 中对超长文档做虚拟滚动（或至少分页加载）。

---

## 10. 实施建议

### 10.1 分步策略

```
Step 1: 基础设施（1 个文件）
  ├─ index.html 改造成 SPA 壳（引入 Alpine/marked/highlight.js CDN）
  ├─ css/variables.css + reset.css + layout.css
  └─ 验证：页面加载，sidebar + content 区域渲染到位

Step 2: 只读浏览（5-6 个文件）
  ├─ api.js（fetch 封装 + lock 轮询）
  ├─ sidebar.js（加载树 + Alpine 绑定 + 客户端搜索过滤）
  ├─ renderer.js（marked 配置 + ref: 链接浮层）
  ├─ viewer.js（文档阅读器）
  ├─ dashboard.js（仪表盘首页）
  ├─ breadcrumb.js
  └─ 验证：能浏览整个知识库，查看文档渲染效果，ref: 引用可展开

Step 3: 写入能力（3-4 个文件）
  ├─ converter.js（marked + turndown 转换逻辑）
  ├─ editor.js（TipTap WYSIWYG 编辑器 + Markdown 快捷键）
  ├─ modals.js（删除确认 + 新建文档弹窗）
  ├─ store.js（锁状态 + 全局状态）
  └─ 验证：WYSIWYG 编辑 → 保存回 .md → 阅读态渲染一致；423 时正确进入只读模式

Step 4: 抛光（剩余）
  ├─ status-bar.js
  ├─ toolbar.js
  ├─ router.js
  └─ 验证：完整闭环，所有路由可导航
```

> **下一步**：方案已确认，开始编码。
---

> **下一步**：方案已确认，开始编码。
