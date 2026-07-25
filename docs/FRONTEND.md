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

### 开发时

```bash
# 终端 1：启动后端（不带 --root 则用全局 ~/.myknowledge/）
myknowledge serve --root .myknowledge_test --port 8080 --reload

# 终端 2：启动前端 HTTP 服务器
cd frontend && python3 -m http.server 8081

# 浏览器打开 http://127.0.0.1:8081/index.html
```

### 生产环境

最终由 `myknowledge serve` 统一启动：

```bash
myknowledge serve                 # 启动 FastAPI + 自动打开浏览器
                                  # 或走 pywebview 原生窗口
```

## API 参考

### 导航

| 方法 | 路径 | 说明 | 返回 |
|------|------|------|------|
| GET | `/api/readme/{path}` | 读路由索引 | Markdown 全文 |
| GET | `/api/list/{path}` | 列目录 | 表格文本 |
| GET | `/api/document/{path}` | 读文档全文 | Markdown 全文 |
| GET | `/api/document/{path}/meta` | 读文档 frontmatter JSON | `{id, type, summary, author, maintainer, created, updated}` |
| GET | `/api/document/{path}/refs` | 读文档 + 引用拼接 | Markdown 全文 |

`{path}` 为 KB 相对路径，如 `common-knowledge/补贴标准.md`、`projects/以旧换新`。

### 写入

| 方法 | 路径 | Body | 说明 |
|------|------|------|------|
| POST | `/api/document/{path}` | `{content, summary?, doc_type?}` | 新建知识 |
| PUT | `/api/document/{path}` | `{content?, summary?}` | 更新知识 |
| DELETE | `/api/document/{path}` | — | 删除知识 |
| PUT | `/api/project/{path}` | `{name?, summary?, status?}` | 改项目元信息 |

> 写入接口可能返回 **423 Locked**。返回 423 表示 AI 正在操作知识库，
> Web UI 应进入只读模式，提示用户「AI 正在同步」。

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
