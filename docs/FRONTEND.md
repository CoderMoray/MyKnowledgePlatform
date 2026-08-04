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
      "resolved": true
    },
    {
      "path": "https://example.com",
      "title": "外部链接",
      "type": "external",
      "resolved": true
    }
  ]
}
```

**`refs[i].type`**：`"ref"`（内部 KB 引用）或 `"external"`（http/https 外链）。外部链接无 `content` 字段。
**代码块/行内代码/图片链接**中的链接不会被解析。

### 读取

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/document/{path}` | 文档全文。响应含 `summary` 和 `version`（乐观锁指纹） |

### 写入

| 方法 | 路径 | Body | 说明 |
|------|------|------|------|
| POST | `/api/document/{path}` | `{content, summary?, doc_type?}` | 新建知识 |
| PUT | `/api/document/{path}` | `{content?, summary?, expected_version?}` | 更新知识（支持乐观锁） |
| DELETE | `/api/document/{path}` | — | 删除知识 |
| PUT | `/api/project/{path}` | `{name?, summary?, status?}` | 改项目元信息 |

> 写入接口可能返回 **423 Locked**。返回 423 表示 AI 正在操作知识库，
> Web UI 应进入只读模式，提示用户「AI 正在同步」。

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
