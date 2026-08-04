# MyKnowledge 依赖版本记录

> 记录所有依赖包的锁定版本，作为发版 / 复现 / 升级的基准。
> 后端来源：`pyproject.toml` + `requirements.txt`；前端来源：`frontend/README.md`。
> 每次升级依赖后，更新本文件 + 对应来源文件。

---

## 后端（Python）

### 运行时依赖

| 包 | 锁定版本 | 约束 | 作用 |
|----|---------|------|------|
| mcp | 1.29.0 | `>=1.0.0` | MCP 协议 |
| PyYAML | 6.0.2 | `>=6.0` | YAML frontmatter |
| GitPython | 3.1.30 | `>=3.1` | Git 操作 |
| fastapi | 0.110.0 | `>=0.100.0,<0.111.0` | REST API 框架 |
| uvicorn | 0.49.0 | `>=0.23.0` | ASGI 服务器 |
| python-multipart | 0.0.31 | `>=0.0.6` | FastAPI 表单解析 |
| pydantic | 2.13.4 | `>=2.0` | 数据模型 |
| aiosqlite | 0.22.1 | `>=0.19` | SSE 事件版本 |

### 依赖约束（重要兼容说明）

| 包 | 约束 | 原因 |
|----|------|------|
| **httpx** | `>=0.23,<0.28` | `starlette 0.36.x` 的 `TestClient` 与 `httpx>=0.28` 不兼容（`Client.__init__() got an unexpected keyword argument 'app'`）。2026-08-05 本机从 0.28.1 降至 0.27.2 |
| starlette | 0.36.3 | 由 `fastapi>=0.100,<0.111` 间接锁定（<0.37） |
| pytest | 9.0.3 | 测试框架 |
| pytest-asyncio | 1.4.0 | async 测试支持 |

### 可选 / 开发依赖

| 包 | 锁定版本 | 作用 |
|----|---------|------|
| oss2 | 2.15.0 | OSS 云同步（可选，改配置启用） |
| apscheduler | 3.10.4 | 定时任务（可选 SyncJob） |

---

## 前端（CDN）

全部 CDN 加载，零 npm install。CDN import map 定义在 `index.html` 的 `<script type="importmap">` 块。

| 库 | 锁定版本 | 来源 | 作用 |
|----|---------|------|------|
| alpinejs | 3.13.5 | jsdelivr | SPA 框架 |
| marked | 11.1.1 | jsdelivr | MD→HTML |
| highlight.js | 11.9.0 | jsdelivr | 代码高亮 |
| turndown | 7.1.3 | jsdelivr | HTML→MD |
| @tiptap/core | 2.1.13 | jsdelivr | 编辑器内核 |
| @tiptap/starter-kit | 2.1.13 | jsdelivr | 编辑器扩展 |
| @tiptap/extension-link | 2.1.13 | jsdelivr | 链接编辑 |
| @tiptap/extension-table | 2.1.13 | jsdelivr | 表格编辑 |
| Gravatar | — | — | 作者头像 |

### 已知 Patch：TipTap Link 扩展

**问题**：TipTap 2.1.13 的 Link `parseHTML` 不强制 `href` 为字符串，部分 URL 会被转成 `[object Object]` 导致链接丢失。官方 2.6.0 修复（issue #4929）。

**Workaround**：`js/components/doc.js` → `PatchedLink`（强制 `parseHTML` 返回字符串）。

**移除条件**：升级 @tiptap 全家桶到 ≥ 2.6.0 后，删掉 `PatchedLink` 改回 `LinkExt.configure()`。

---

## 升级流程

1. 修改来源文件（`pyproject.toml` / `requirements.txt` / `frontend/README.md`）
2. 更新本文件对应版本
3. 后端改动跑 `python -m pytest tests/ --tb=short -v --ignore=tests/frontend`
4. 前端改动跑 `python3 frontend/build.py`
5. 确认无回归后发版
