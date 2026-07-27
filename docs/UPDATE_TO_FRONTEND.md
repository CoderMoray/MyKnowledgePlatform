# 后端修改与 Bug 修复总结（供前端 AI 参考）

> 请继续完成你的设计和开发，以下修改已落地，你只需在后续实现中注意这些已修复的问题即可，**不需要**主动修改你的方案来适配。

## 一、后端 API 返回格式变更（需特别注意）

以下端点**之前返回纯文本，现在改为 JSON**：

| 端点 | 旧格式 | 新格式 |
|------|--------|--------|
| `GET /api/list/{path}` | `PlainTextResponse` 表格文本 | `{"items": [{"name", "path", "is_dir", "modified"}]}` |
| `GET /api/document/{path}` | `PlainTextResponse` Markdown | `{"content": "body", "meta": {...}}` |
| `GET /api/document/{path}/refs` | `PlainTextResponse` Markdown+附录 | `{"content": "...", "refs": [{"path", "title", "content", "resolved"}]}` |

此外：

- **`GET /api/document/{path}/meta`** 不变，仍返回 JSON
- **`GET /api/status/detail`** 新增 `recent` 数组（最近 10 篇文档，按 `updated_at` 降序），每条含 `{path, name, updated_at, summary, project}`
- **新增 `GET /api/project/{path}`** — 返回项目 readme frontmatter
- **新增 `GET /api/version`** — 返回 `{"system": "0.5.0", "kb": "xxx"}`（kb 来自 `agent-commit.txt` checkpoint）
- **`GET /api/list/` 返回的 `items` 每条新增 `path` 字段**（完整 KB 相对路径）

## 二、Bug 修复

### 2.1 Sidebar 项目列表为空
**原因**：`loadProjects()` 调用 `GET /api/list/`（根目录），拿到 `.events/`、`archive/` 等系统目录，而非 `projects/` 内的实际项目。且 sidebar 模板过滤 `p.type === 'project'`，但后端返回 `is_dir`。

**修复**：`loadProjects()` 改为调 `GET /api/list/projects`；sidebar 模板去掉 `type` filter，直接遍历 `$store.app.projects`。

### 2.2 仪表盘项目数/文档数为 0
**原因**：`dashboardComponent` 遍历 `store.projects` 按 `type==='project'` 过滤，后端无此字段。

**修复**：`projectCount` 和 `documentCount` 改为读取 `statusSummary.projects.total` 和 `statusSummary.documents`。

### 2.3 仪表盘最近更新为空
**原因**：`loadDashboard()` 解析根目录列表的 `type==='document'` 构建最近更新，同样字段不匹配。

**修复**：改为直接读取 `statusData.recent`（后端已完成递归扫描全库文档）。

### 2.4 文档内容加载失败（白屏 / 无内容）
**原因**：`loadDocument()` 调 `api.getDocumentWithRefs(path)` 期望 `data.content` / `data.refs`，但后端返回纯文本 Markdown。

**修复**：`GET /api/document/{path}/refs` 改为返回 JSON `{content, refs}`。

### 2.5 引用预览浮层标题为空
**原因**：`loadRefPreview()` 访问 `data.title` / `data.summary`，但纯文本响应无这些字段。

**修复**：`GET /api/document/{path}` 改为返回 JSON `{content, meta}`，前端改为读 `data.meta.summary`。

### 2.6 路由冲突导致 `/refs` 和 `/meta` 请求被吞
**原因**：`GET /api/document/{path:path}` 通配路由注册在 `/meta` 和 `/refs` 之前，`{path:path}` 贪婪匹配吞掉后缀。

**修复**：将通配路由移至 `/meta` 和 `/refs` 之后注册。

### 2.7 Setup 页面不跳转（身份已配置仍卡在 setup）
**原因**：`handleRoute()` 遇到 `hash === "setup"` 无条件显示 setup，即使 `identitySet` 已为 true。

**修复**：加判断——身份已配置时自动跳 `#dashboard`。

### 2.8 头像裂图
**原因**：user-menu 头像使用 Gravatar `<img>`，依赖网络请求，且 `@error` 与 `x-show` 冲突导致后备不显示。

**修复**：移除 Gravatar，改为本地渲染昵称首字母（`avatar--fallback` CSS），与 setup 页一致。

## 三、其他后端新增功能

| 功能 | 说明 |
|------|------|
| **SSE 实时更新** | `GET /api/events` 推送 `updated` 事件，前端 `EventSource` 订阅后自动重载当前视图（不影响你的设计，后需接入） |
| **CORS 中间件** | 允许前端从 `8081` 端口跨域访问后端 `8080` |
| **项目目录自动补齐** | `ReadmeGenerator.rebuild()` 自动创建 `common-knowledge/`、`projects/`、`archive/` |
| **版本 API** | `/api/version` 返回系统版本 + 知识库 checkpoint 版本 |
| **`.events` 隐藏** | SSE 事件目录不再出现在目录列表中 |
| **`fastapi<0.111.0`** | requirements.txt 锁定版本 |

## 四、对前端的影响

**你的设计方案无需因这些修复而改变。** 这些修正是为了让前端已有的代码能正确工作。需要注意的只有两点：

1. 如果你后续调用了 `api.list()`、`api.getDocument()`、`api.getDocumentWithRefs()`，**返回值格式现在是 JSON**，不是纯文本
2. `sidebarComponent` 中的 `goToProject(path)` 正常可用，path 为 `"projects/项目名"` 格式；`toggleSection`/`isCollapsed` 方法已保留但不再用于 children 展开（sidebar 改为平铺项目列表）
3. 如果需要版本号，调 `GET /api/version`，前端 `$store.app.systemVersion` 和 `$store.app.kbVersion` 已在 store 中
