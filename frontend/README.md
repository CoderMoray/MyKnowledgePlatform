# MyKnowledge 前端

## 架构概览

**单页应用（SPA）**——只有一个 `index.html`，通过 Hash 路由（`#dashboard`、`#project/xxx`、`#view/xxx` 等）切换视图。没有额外的 HTML 页面，所有"页面"本质上都是同一个 HTML 内的 `<div>` 通过 Alpine.js `x-show` 条件渲染。

```
index.html (唯一入口)
  ├─ 仪表盘     #dashboard
  ├─ 项目浏览   #project/{项目名}
  ├─ 文档阅读   #view/{文档路径}
  ├─ 文档编辑   #edit/{文档路径}
  └─ 系统状态   #status
```

> **不是多 Tab 页面**——路由切换时不打开新标签页，所有内容在同一个浏览器窗口内切换。

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 框架 | Alpine.js 3.x | 响应式状态 + 条件渲染 + 事件，CDN 加载 |
| 编辑器 | TipTap 2.x | WYSIWYG 所见即所得，ProseMirror 内核 |
| Markdown | marked + turndown | 阅读态渲染 + 保存时转回 Markdown |
| 代码高亮 | highlight.js | 阅读视图代码块着色 |
| 头像 | Gravatar | 从 author 邮箱自动获取 |
| 设计系统 | Raycast | Light/Dark/System 三模式，毛玻璃 + Indigo 紫 |

## 快速开始

```bash
# 开发模式（源文件，可热修改）
open index.html
# 或
python3 -m http.server 8081

# 启动后端（另一个终端，必须）
cd ../backend && uvicorn main:app --port 8080 --host 127.0.0.1

# 构建生产版本
python3 build.py
# → index.standalone.html（CSS/JS 全部内联，可直接部署）
```

## 文件结构

```
frontend/
├── index.html              ← 唯一 HTML 入口（SPA 壳 + 所有视图模板）
├── index.standalone.html   ← 构建产物（python3 build.py 生成）
├── build.py                ← 构建脚本
├── README.md               ← 本文件
├── css/
│   ├── design-tokens.css   ← 🎨 设计令牌（色彩/排版/间距/圆角/阴影/毛玻璃）
│   ├── reset.css           ← 浏览器默认样式重置
│   ├── layout.css          ← 页面大布局（header/sidebar/content）
│   ├── sidebar.css         ← 左侧项目列表
│   ├── viewer.css          ← 文档阅读视图
│   ├── editor.css          ← TipTap 编辑器 + 工具栏
│   ├── components.css      ← 通用组件（按钮/卡片/弹窗/toast/标签/头像）
│   └── markdown-content.css← 渲染后的 Markdown 正文样式
└── js/
    ├── app.js              ← Alpine 入口（初始化 + 组件注册）
    ├── store.js            ← 全局状态（currentView/currentPath/isLocked/theme）
    ├── api.js              ← 后端 API 封装（fetch + 统一错误处理）
    ├── router.js           ← Hash 路由解析与导航
    ├── renderer.js         ← Markdown 阅读态渲染（marked 配置 + ref链接）
    ├── converter.js        ← Markdown ↔ HTML 转换（marked + turndown）
    └── utils.js            ← 工具函数（日期/转义/toast/MD5/Gravatar）
```

## 修改指南：改什么该找哪个文件

### 改外观/样式

| 你想改的 | 找这个文件 |
|----------|-----------|
| **主色调/字体/间距/圆角** | `css/design-tokens.css`（改一处，全局生效） |
| 页面整体布局比例 | `css/layout.css` |
| 侧边栏项目列表样式 | `css/sidebar.css` |
| 文档卡片外观 | `css/components.css`（搜索 `.card`） |
| 按钮样式 | `css/components.css`（搜索 `.btn`） |
| Markdown 正文排版（标题/列表/表格/代码块） | `css/markdown-content.css` |
| 编辑器工具栏样式 | `css/editor.css` |
| 弹窗/modal 样式 | `css/components.css`（搜索 `.modal`） |
| 主题切换控件样式 | `css/components.css`（搜索 `.theme`） |

### 改交互/功能

| 你想改的 | 找这个文件 |
|----------|-----------|
| **页面结构/路由/视图模板** | `index.html`（所有 `<template>` 和 `x-show` 块） |
| 仪表盘数据获取 | `js/store.js`（`loadDashboard` 方法） |
| 文档加载逻辑 | `js/store.js`（`loadDocument` 方法） |
| 编辑器初始化 | `js/app.js`（`editorComponent`） |
| API 请求/端点 | `js/api.js` |
| 路由规则 | `js/router.js`（`route()` 函数） |
| 锁状态轮询策略 | `js/app.js`（`lockPolling`） |
| ref 引用渲染行为 | `js/renderer.js` |
| Markdown 转换行为 | `js/converter.js` |
| 工具函数（日期/MD5/Gravatar） | `js/utils.js` |

### 改设计令牌（换主题）

`css/design-tokens.css` 是三段式结构：

```css
:root { /* Light 默认 */ }
[data-theme="dark"] { /* Dark 手动切换 */ }
@media (prefers-color-scheme: dark) { /* System 跟随系统 */ }
```

修改对应块即可。**后续新增主题**（Intercom/Warm Editorial 等）只需加新的 `[data-theme="xxx"]` 块。

### 改完后

```bash
python3 build.py    # 重新内联生成 standalone
```

## 设计系统

默认主题：**Raycast（毛玻璃极简 + Indigo 紫调）**

- Light 底色 `#FAFAFA` / Dark 底色 `#1C1C1E`
- 主题切换 0.4s 平滑渐变
- 三个选项：Light / Dark / System（跟随 macOS 系统外观）
- 全部 WCAG AA 对比度合规

后续可选主题（设计令牌架构已预留）：
- Intercom — 柔和蓝 B2B 温度感
- Warm Editorial — 暖白纸张书卷感

## 链接类型

阅读态支持三种链接，hover 弹出差异化卡片：

| 链接 | 正则 | 卡片内容 | 引用列表 |
|------|------|---------|---------|
| 知识引用 `[text](ref:path::section)` | `ref:` | 文档摘要 + 打开文档 | 可点击跳转 |
| 外部链接 `[text](https://...)` | `http(s)://` | URL + 打开链接↗ | 「外部」灰标 + 新标签页 |
| 死链 `ref:` 指向不存在文件 | 同知识引用 | 「文件不存在」红色提示 | 「已失效」红标 |

后端 `/api/document/{path}/refs` 返回 `type: "ref"|"external"` + `resolved: true|false`。

编辑器保存链接经过 `PatchedLink` 自定义扩展强制 `parseHTML` 为字符串，确保 href 不被 TipTap 2.1.13 损坏（官方 2.6.0+ 修复）。
- Mistral AI — 象牙白法式优雅
- Resend — 建筑感瑞士极简

## 依赖

全部 CDN 加载，零 npm install：

| 库 | 版本 | 来源 | 作用 |
|----|------|------|------|
| alpinejs | 3.13.5 | jsdelivr | SPA 框架 |
| marked | 11.1.1 | jsdelivr | MD→HTML |
| highlight.js | 11.9.0 | jsdelivr | 代码高亮 |
| turndown | 7.1.3 | jsdelivr | HTML→MD |
| @tiptap/core | 2.1.13 | jsdelivr | 编辑器内核 |
| @tiptap/starter-kit | 2.1.13 | jsdelivr | 编辑器扩展 |
| @tiptap/extension-link | 2.1.13 | jsdelivr | 链接编辑 |
| @tiptap/extension-table* | 2.1.13 | jsdelivr | 表格编辑 |
| Gravatar | — | — | 作者头像 |

CDN import map 定义在 `index.html` 的 `<script type="importmap">` 块中。

### 已知 Patch：Link 扩展 href 序列化

**问题**：TipTap 2.1.13 的 Link 扩展 `parseHTML` 不强制 `href` 为字符串，ProseMirror 属性解析器会把某些 URL 转成 `[object Object]`，导致编辑保存后链接丢失。此 bug 在 2.6.0 官方修复（issue #4929）。

**Workaround**（`js/components/doc.js` → `PatchedLink`）：

```js
addAttributes() {
    return {
        ...this.parent?.(),
        href: {
            default: null,
            parseHTML(element) {
                return element.getAttribute('href'); // 强制字符串，绕过类型推断
            },
        },
    };
}
```

**移除条件**：升级 @tiptap 全家桶到 ≥ 2.6.0 后，直接删掉 `PatchedLink`，改回 `LinkExt.configure()`。

## 注意事项

- 后端必须运行在 `127.0.0.1:8080`（或设置 `window.__MYK_API_BASE__`）
- `GET /api/document/{path}/meta` 需要后端支持
- 头像使用 Gravatar，`author` 字段格式为 `"昵称 <邮箱>"`
- 构建产物 `index.standalone.html` 不应手动编辑——修改源文件后重新构建
