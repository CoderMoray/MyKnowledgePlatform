# 后端第二次修改总结（向前端 AI）

## 一、发现的问题

### 1.1 `gen.rebuild("projects")` 导致系统目录被创建
**问题**：`PUT /api/project/projects/首页重构` 时，`parent = "projects"`，调用了 `gen.rebuild("projects")`。`rebuild()` 中的 `ensure_dir` 把 `"projects"` 当作项目层，在 `projects/` 下创建了 `common-knowledge/`、`projects/`、`archive/`、`readme.md`。

**影响**：Sidebar 和仪表盘出现不应存在的空目录/文件。

### 1.2 所有 MCP 写工具没有路径校验
**问题**：`write__create_document(path="projects", ...)` 等调用可以通过任意路径触发 `write_document` 中的 `_ensure_dir`，静默创建目录树。AI 丢失上下文后可能传错路径。

### 1.3 归档项目在 sidbar 全部显示为"已废弃"
**问题**：`$store.app.archived` 来自 `GET /api/list/archive`，返回条目只有 `{name, path, is_dir, modified}`，**没有 `status` 字段**。前端模板用了 `project.status || 'abandoned'` 全部回退为废弃。

### 1.4 项目状态变更不会自动归档
**问题**：修改项目 readme 的 `status` 为 `completed`/`cancelled` 后，项目仍留在 `projects/` 下，不会自动移入 `archive/`。

### 1.5 `loadProjects()` 数据源错误
**问题**：`loadProjects()` 调 `GET /api/list/`（根目录），拿到的是 `.events/`、`archive/`、`projects/` 等系统目录，而不是 `projects/` 内的实际项目。

## 二、后端修改

| 修复 | 文件 | 说明 |
|------|------|------|
| 路径校验 | `mcp_server.py` | 新增 `_validate_path()`，覆盖所有 MCP 写工具。禁止 `..`、绝对路径、非 `.md` 后缀、非白名单前缀 |
| 自动归档 | `mcp_server.py` + `main.py` | 新增 `_auto_archive()`：写完数据后检查 readme status，非 active 自动 `shutil.move` 到 `archive/` + rebuild + commit |
| rebuild 路径修复 | `main.py` | `PUT /api/project/{path}` 中 `parent="projects"` 时改为重建根 readme |
| list 增加 `status` 字段 | `main.py` | `GET /api/list/{path}` 对子目录条目增加 `status` 字段（读 readme frontmatter） |

## 三、前端修改

| 文件 | 改动 |
|------|------|
| `store.js` | `loadProjects()` 改为调 `api.list("projects")`（之前是 `api.list()`） |
| `index.html` | Sidebar 模板从嵌套 `project.children` 简化为平铺项目列表，去掉 `type==='project'` filter |
| `app.js` | `dashboardComponent` 中 `projectCount`/`documentCount` 改为读 `statusSummary` |
| `store.js` | `loadDashboard()` 最近更新改为直接读 `statusData.recent` |
| `index.html` | Footer 显示系统版本 + 知识库版本；Brand 区域显示 V0.5.0 |
| `store.js` | 新增 `loadVersion()`，`init()` 中调用 |
| `store.js` | 新增 `systemVersion`/`kbVersion` 状态变量 |
| `index.html` | 头像从 Gravatar `<img>` 改为本地首字母 `avatar--fallback` |
| `css/layout.css` | 新增 `.sidebar-brand__info`、`.sidebar-brand__version` |
| `css/components.css` | 新增 `.sidebar-footer__version--kb` |
| `renderer.js` | `loadRefPreview` 改为读 `data.meta.summary` |

## 四、对前端的影响

### 4.1 Sidebar 项目列表现在正确了
从 `GET /api/list/projects` 获取，不再显示系统目录。点击项目名跳转 `#project/{path}`。

### 4.2 归档项目显示正确状态徽章
`GET /api/list/archive` 现在返回的条目带 `status` 字段，对应 readme 的 status（`completed`/`cancelled`/`abandoned`）。

### 4.3 项目/文档数字正确
`dashboardComponent` 的 `projectCount` 和 `documentCount` 现在读 `statusSummary`，不是遍历 `store.projects`。

### 4.4 版本号显示
- Brand 区域：`V0.5.0`（系统版本）
- Footer：`知识库版本：xxx` 或 `知识库：当前未创建任何知识`

### 4.5 文档阅读页面
`GET /api/document/{path}` 返回 JSON `{content, meta}`，不是纯文本。前端已适配。

### 4.6 文档引用页面（refs）
`GET /api/document/{path}/refs` 返回 JSON `{content, refs}`。前端已适配。

## 五、无需关注的修改

- 路径校验（`_validate_path`）仅影响 MCP 工具调用，前端无感知
- 自动归档（`_auto_archive`）仅影响后端数据写入，前端正常刷新即可看到变化
- `_validate_project_rel` 重命名为 `_validate_path`，`maint__rebuild_index` 校验已同步更新
