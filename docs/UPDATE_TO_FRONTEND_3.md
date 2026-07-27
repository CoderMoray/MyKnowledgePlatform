# 后端第三次修改总结（向前端 AI）

## 一、新功能

### 1.1 `GET /api/list/{path}` 新增 `summary` 字段
所有条目（目录和 `.md` 文件）现在都返回 `summary` 字段：

```json
{
  "name": "技术选型.md",
  "path": "common-knowledge/技术选型.md",
  "is_dir": false,
  "summary": "技术栈选型及理由"
}
```

目录读 `readme.md` 的 frontmatter summary，`.md` 文件读自身 frontmatter summary。summary 为空时返回 `""`（不返回 `None`）。

**影响**：纯新增字段，消费处已有 `||` fallback，无需前端改动。

### 1.2 子项目摘要已补全
- 前端设计与开发 → `Alpine.js + TipTap WYSIWYG 编辑器 SPA 前端`
- 后端设计与开发 → `FastAPI + MCP 协议 + Markdown/Git 存储后端`

### 1.3 测试项目已走正规归档流程
| 项目 | 状态 | 位置 |
|------|------|------|
| 用户认证系统 | completed | `MyKnowledge 项目知识管理平台/archive/` |
| 数据迁移工具 | cancelled | `MyKnowledge 项目知识管理平台/archive/` |

## 二、Bug 修复

### 2.1 `ensure_dir` 白名单
之前 `rebuild()` 的 ensure_dir 对 `("", ".")` 以外所有路径都触发，导致 `"projects"` 等系统目录也被创建子目录。改为白名单——只有以 `projects/` 或 `archive/` 开头的路径才触发。

**影响**：`projects/` 下不会再出现 `common-knowledge/`、`archive/` 等脏目录。

### 2.2 summary 为 `None` 的问题
YAML frontmatter 中 `summary:`（无值）会被解析成 `None`，`meta.get("summary", "")` 返回 `None`。改为 `meta.get("summary") or ""`。

**影响**：前端不会收到 `null` 值，永远是字符串。

### 2.3 残留目录清理
- `projects/readme.md` → `git rm`
- `MyKnowledge 项目知识管理平台/projects/` 下的 `archive/`、`common-knowledge/`、`projects/`、`readme.md` → `git rm` / 直接删除后 commit

## 三、无需关注

- 白名单改动在 `readme_generator.py`，仅后端 rebuild 逻辑影响，前端无感
- 前端不需要为 `summary` 字段做任何适配，已有 `||` fallback
