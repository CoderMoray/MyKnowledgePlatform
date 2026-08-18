# MyKnowledge REST API — Web UI 前端开发参考

## 目录结构

```
frontend/
├─ index.html          ← 入口页
├─ css/
│   └─ style.css       ← 全局样式
├─ js/
│   ├─ api.js          ← REST API 请求封装
│   └─ app.js          ← 主界面逻辑
└── README.md          ← 前端说明（如需）
```

## 启动方式

### 知识库目录

后端通过 `MYKNOWLEDGE_ROOT` 环境变量决定读取哪个知识库目录：

- **未设置时**：默认 `~/.myknowledge/`（全局知识库）
- **设为 `.myknowledge_test`**：读取项目内的测试知识库

### 启动

```bash
# 后端 API + 前端静态文件，一个命令搞定
myknowledge serve --root .myknowledge_test --port 8080 --reload

# 浏览器打开 http://127.0.0.1:8080/
```

后端自动挂载 `frontend/` 目录的静态文件，`GET /` 直接返回 `index.standalone.html`。

### 开发（改前端代码时）

如果频繁改 `index.html` / `css/` / `js/`，需要跑 `python3 frontend/build.py` 重建 standalone 文件 → 刷新浏览器。

## API 参考

### 导航

| 方法 | 路径 | 说明 | 返回 |
|------|------|------|------|
| GET | `/api/readme/{path}` | 读路由索引 | Markdown 全文 |
| GET | `/api/list/{path}` | 列目录 | 表格文本 |
| GET | `/api/search?q=<关键词>&limit=<n>` | 全库文档搜索（标题/正文分级排序） | `{results, total}` |
| GET | `/api/document/{path}` | 读文档全文 | Markdown 全文 |
| GET | `/api/document/{path}/meta` | 读文档 frontmatter JSON | `{id, type, summary, author, maintainer, created, updated}` |
| GET | `/api/document/{path}/refs` | 读文档 + 引用拼接 | Markdown 全文 |
| POST | `/api/export` | 导出项目为加密 .mkpkg／.zip | binary blob |

`{path}` 为 KB 相对路径，如 `common-knowledge/补贴标准.md`、`projects/以旧换新`。

**`/api/document/{path}/refs` 响应格式：**
```json
{
  "content": "---\n...frontmatter...\n---\n\nbody",
  "refs": [
    {
      "path": "common-knowledge/other.md",
      "title": "链接文本",
      "type": "ref",
      "content": "引用文档全文",
      "resolved": true,
      "ref_status": "normal"
    },
    {
      "path": "common-knowledge/deleted.md",
      "title": "已删除引用",
      "type": "ref",
      "content": "⚠ 引用路径不存在",
      "resolved": false,
      "ref_status": "in_trash"
    },
    {
      "path": "https://example.com",
      "title": "外部链接",
      "type": "external",
      "resolved": true,
      "ref_status": "normal"
    }
  ]
}
```

**`refs[i].type`**：`"ref"`（内部 KB 引用）或 `"external"`（http/https 外链）。外部链接无 `content` 字段。
**代码块/行内代码/图片链接**中的链接不会被解析。

**`refs[i].ref_status`**：引用目标的状态，前端可用它区分死链的两种类型：
- `"normal"`：目标正常存在（`resolved: true`）。
- `"in_trash"`：目标已被删除但仍在垃圾箱、可恢复（`resolved: false`）。前端可展示「引用已进垃圾箱」并提示恢复。
- `"dead"`：目标从未存在（`resolved: false`）。前端可提示用户补充知识或更新引用。

> 兼容性：`ref_status` 是新增字段，旧前端忽略即可，不影响既有 `resolved`/`content` 语义。

**含空格路径（S16）**：`refs[i].path` 统一为**解码后的真实路径**（`%20` → 空格）；`resolved`/`ref_status` 对 `%20` 编码与空格原文两种写法均正确分类（空格路径项目如 `projects/MyKnowledge 项目知识管理平台/...`）。

**写入时 ref 目标校验（S16）**：`POST/PUT /api/document/{path}` 响应含 `ref_warnings` 字段，为**结构化数组**（空数组=全部正常），仅提示不阻断写入。每条 `{type, ref_path, display_text}`：
- `type`：`"dead"`（目标不存在）| `"in_trash"`（在垃圾箱）| `"empty"`（`[文本](ref:)` 空 target）
- `ref_path`：目标路径（`empty` 时为 `""`）
- `display_text`：链接显示文本（引用意图证据，`empty` 时即 `[文本]` 部分）
- 外链（http/https）→ 跳过不校验
`PUT`（update）只检查**本次改动引入**的引用（原有内容里的问题不返回，与 MCP 一致）。
同时写入内容中的 `ref:` 路径空格会自动规范化为 `%20`（幂等，前端已编码的不受影响）。

> 兼容性：旧前端若读 `ref_warnings`（字符串数组形态）需按新契约适配；不读则无影响。

### 垃圾箱

| 方法 | 路径 | Body | 说明 |
|------|------|------|------|
| GET | `/api/trash` | `?offset=0&limit=50` | 分页列出垃圾箱（document/project、original_path、deleted_at、trash_path）→ `{items, total, has_more}`（默认 limit 50，前端半懒加载） |
| POST | `/api/trash/restore` | `{trash_path}` | 恢复条目到原路径 |
| POST | `/api/trash/empty` | — | 永久清空超过 30 天的条目（GC，自动清除用）→ `{status, removed}` |
| POST | `/api/trash/empty?all=true` | — | 清空全部垃圾箱（前端「清空垃圾箱」按钮，用户确认后手动触发）→ `{status, removed}` |
| POST | `/api/trash/empty` | body `{trash_paths: [...]}` | 精准删除指定条目（前端 checkbox 多选）→ `{status, removed}`（优先级最高；非法路径 400） |

**`DELETE /api/document/{path}`** 现在将文档移入垃圾箱而非删除，返回 `{"status": "trashed", "trash_path": "..."}`，30 天内可恢复。

**`DELETE /api/project/{path}`** 同理，将整个项目移入 `trash/projects/`（非永久删除），返回 `{"status": "trashed", "trash_path": "..."}`。项目进垃圾箱后，引用其内部文档的 `ref_status` 会变为 `in_trash`（可恢复）。恢复约束：项目在垃圾箱时，其下文档的单独恢复会被拒绝，需先恢复项目。

**`GET /api/document/{path}` 404 响应**区分三种情况：
- 旧路径有 rename 映射且目标存在 → `{"detail": "renamed", "redirect_to": "<新路径>"}`（前端可 `location.replace` 到新路径重新加载）
- 路径曾在 git 中被删除 → `{"detail": "deleted", "deleted_at": "<ISO 时间>"}`
- 路径从未存在 → `{"detail": "not_found"}`

前端可据此显示「文档已改名（自动跳转）」「文档在 X 被删除」「文档不存在」。

> rename 映射由后端在 rename 时持久化（`<kb_root>/.renames.json`，不进 git），链式 rename（A→B→C）会折叠为直接指向最终路径；目标文档被删除后映射自动失效，退化为 deleted/not_found。

### 读取

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/document/{path}` | 文档全文。响应含 `summary` 和 `version`（乐观锁指纹） |

### 写入

| 方法 | 路径 | Body | 说明 |
|------|------|------|------|
| POST | `/api/document/{path}` | `{content, summary?, doc_type?}` | 新建知识 |
| PUT | `/api/document/{path}` | `{content?, summary?, expected_version?}` | 更新知识（支持乐观锁） |
| DELETE | `/api/document/{path}` | — | 移入垃圾箱（30 天可恢复） |
| DELETE | `/api/project/{path}` | — | 移入垃圾箱（30 天可恢复，返回 `{"status":"trashed","trash_path":...}`） |
| PUT | `/api/project/{path}` | `{name?, summary?, status?}` | 改项目元信息 |

> 写入接口可能返回 **423 Locked**。返回 423 表示 AI 正在操作知识库，
> Web UI 应进入只读模式，提示用户「AI 正在同步」。若持有锁的会话设置了
> `agent` 标识，423 的 `detail` 会附带「（持有者: xxx）」。
>
> **`GET /api/lock`** 返回当前锁状态：`{locked, pid, agent, since_ts, expires_ts, since, expires_at, expired}`。
> - `since_ts` / `expires_ts`：**epoch 秒**，跨时区安全，前端 `new Date(since_ts*1000)` 直接可用。
> - `since` / `expires_at`：人类可读 ISO 8601（含本地时区偏移，如 `2026-08-07T20:19:45+08:00`）。
> - `expires_at` 语义 = 锁的**硬超时上限**（获取时刻 + 5 分钟），**不是 AI 预计完成时间**——AI 可能提前释放。前端展示建议用「AI 正在操作 · 锁最长剩余 X 分钟」。
> - `agent`：持有锁会话的标识（契约见 MCP 工具 `maint__acquire_lock` 描述），未设置则为空串。

### 乐观锁（PUT /api/document）

- **`version` 指纹**：`sha256(f"{summary}\\x00{content}")[:12]`，content 为纯 body（不含 frontmatter）
- **GET 返回** `summary` + `version`；前端存下 version，编辑后回传给 PUT 的 `expected_version`
- **PUT 带 `expected_version`**：与当前文档指纹不匹配 → **409**，响应体：
  ```json
  {
    "error": "conflict",
    "message": "文档已被其他会话修改",
    "current_version": "...",
    "content": "<最新内容>",
    "current_summary": "<最新摘要>"
  }
  ```
- **409 优先于死链 400**：冲突检测先于内容校验
- **不带 `expected_version`**：行为不变（强制覆盖，逃生舱）
- 保存成功响应含新 `version`（含 no-op 时）

### 维护

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 项目状态概览（纯文本） |
| GET | `/api/status/detail` | 结构化 JSON（项目数/文档数） |
| GET | `/api/lock` | 锁状态 JSON（`{locked, pid, since, expires_at}`） |
| POST | `/api/check` | 完整性检查 + GC |
| GET | `/api/diagnose` | 知识库结构诊断（只读 JSON，结果写入 KB 根 `.diagnose-result.json`） |
| GET | `/api/diagnose/saved` | 读取上次诊断结果（读/算分离；无结果或损坏返回 `{saved: false}`） |
| POST | `/api/heal/move` | 批量移动孤儿文档到同级 `common-knowledge/`（body: `{paths, target_rel?}`）→ `{moved, failed}` |
| POST | `/api/heal/rebuild` | 重建 readme 索引层 + project-status（body: `{layers?, all?}`）→ `{rebuilt, project_status}` |
| GET | `/api/client-config` | 检测 AI 客户端（Claude/CodeBuddy）的 MyKnowledge 配置状态 → `{claude: {client_installed,mcp,hooks,agent}, codebuddy: {client_installed,mcp,hooks,agent}}`（client_installed=客户端是否安装） |
| POST | `/api/client-config/:platform/:kind` | 增量写入该平台该 kind 的 MyKnowledge 配置（platform: claude\|codebuddy；kind: mcp\|hooks\|agent）→ `{platform, kind, file, status, detected}` |
| POST | `/hooks/pre-tool-use` | AI 客户端 PreToolUse hook：判定知识库裸操作 allow/deny（Claude/Cursor 兼容）→ `{hookSpecificOutput, permission, agent_message, user_message}` |

## 可编辑字段清单

所有可编辑字段使用统一交互——**文本框 + 保存按钮**，不弹窗、不右键。

### ✅ 可编辑

| 位置 | 字段 | 前端交互 | 后端 API | 说明 |
|------|------|---------|---------|------|
| 项目 | `name` | 文本框 + 保存 | `PUT /api/project/{path}/rename` | 后端自动 mv 目录 + 替换 ref + rebuild |
| | `summary` | 文本框 + 保存 | `PUT /api/project/{path}` | 修改后自动 rebuild 父层 readme |
| | `status` | 下拉选择 + 保存 | `PUT /api/project/{path}` | 同步更新 project-status.md |
| 知识文档 | **文件名** | 文本框 + 保存 | `PUT /api/document/{path}/rename` | 后端自动 mv 文件 + 替换 ref + rebuild |
| | `summary` | 文本框 + 保存 | `PUT /api/document/{path}` | 修改后自动 rebuild 父层 readme |
| | **正文** | TipTap WYSIWYG 编辑器 | `PUT /api/document/{path}` | 编辑后存为 Markdown |

### 👁️ 仅展示（不可编辑）

| 位置 | 字段 | 前端展示 |
|------|------|---------|
| 知识 doc frontmatter | `author` / `maintainer` | 头像/badge |
| | `created` / `updated` | 日期标签 |
| | `id` / `type` / `template` | 标签/badge |
| 项目 readme frontmatter | `id` | 标签 |
| readme 正文 | — | 无编辑入口（系统派生，rebuild 覆盖） |
| project-status.md | — | 无编辑入口（系统生成，不可改） |

## 安全性

- 后端绑定 `127.0.0.1` 仅本地可访问
- 无外部网络暴露风险
- 前端使用 `fetch()` 直接请求 `http://127.0.0.1:{port}`
- 如果将来需要浏览器端身份，可以加简单的 token 验证（当前不需要）

## 头像

author / maintainer 格式为 `昵称 <邮箱>`。
头像使用 **Gravatar**（全球通用头像），前端计算：

```javascript
async function avatarUrl(email) {
  const hash = await crypto.subtle.digest(
    "MD5",
    new TextEncoder().encode(email.trim().toLowerCase())
  );
  const hex = Array.from(new Uint8Array(hash))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
  return `https://www.gravatar.com/avatar/${hex}?s=32&d=mp`;
}
```

用户上传头像功能未来再添加。
