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

## 前端（本地 vendor + npm）

**已从 CDN 改为本地化**（2026-08-05 前端 smoke 测试修正时确认）：
- 运行时库（Alpine.js、TipTap 等）内联在 `frontend/vendor/`，构建时打入 `index.standalone.html`，**无 CDN、离线可用**
- 构建/测试工具依赖走 npm，锁定版本由 `frontend/package-lock.json` 管理

| 库 | 位置 | 版本来源 |
|----|------|---------|
| Alpine.js | `frontend/vendor/`（内联） | 见 `frontend/README.md` 依赖节 |
| TipTap 全家桶 | `frontend/vendor/` + `tiptap-bundle.mjs` | 见 `frontend/README.md` |
| marked | npm devDependency | `package-lock.json`（`^11.1.1`） |
| turndown | npm devDependency | `package-lock.json`（`^7.1.3`） |
| jsdom | npm devDependency | `package-lock.json`（`^24.1.0`） |
| highlight.js | `frontend/vendor/`（内联） | 见 `frontend/README.md` |

> npm 依赖的**精确锁定版本**以 `package-lock.json` 为准（`^` 为兼容范围）。

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
