# MyKnowledge 开发管理

> 对应 [DESIGN.md](DESIGN.md) v0.6。Phase 1-2 核心存储层 + MCP 已完成。
> 按 Step 推进，每一步完成后更新状态。

---

## 已完成

### Step 1 — 配置文件 + 基础工具 ✅

- `config.py` — `resolve_root` / `load_oss_env` / `get_identity` / `set_identity`
- `storage.py` — frontmatter 解析、文件读写、目录遍历、id 生成、名称搜索、递归列表
- `git_manager.py` — git init / auto-commit / diff / checkpoint

### Step 2 — readme 生成器 ✅

- `readme_generator.py` — `rebuild()` / `rebuild_project_status()` / `garbage_collect()`
- 项目状态四段式：进行中 / 已完成 / 已取消 / 已废弃（30 天自动清理）

### Step 3 — MCP 服务 + 只读工具（nav__ 共 6 个） ✅

- `mcp_server.py` — FastMCP 应用，自动 heartbeat 注入、路径校验（白名单 + 恢复指引）
- 读 readme / 读全文 / 读全文+引用拼接 / 列目录（支持递归展开）/ 路径存在性检查 / 名称模糊搜索

### Step 4 — 写入工具（write__ 共 8 个） ✅

- `create_document`（支持 `dry_run` 预览 + `if_exists` 策略）/ `update_document` / `update_project_meta`
- `delete_document` / `delete_project`（删除目录 + 替换 ref + rebuild）/ `rename_project` / `move_project` / `rename_document`
- 写入时自动：rebuild 父层 readme → rebuild 项目状态 → git commit
- 写入时自动注入 `author` / `maintainer` frontmatter
- 非 active 项目自动归档到 `archive/`

### Step 5 — 检修工具（maint__ 共 6 个） ✅

- `validate_doc` / `read_diff` / `check_integrity`
- `rebuild_index` — 手动重建 readme
- `nav__maintenance_procedure` prompt — 会话开始时的自动维护流程
- `.lock` 机制 — 写锁（5 分钟超时，Web UI 检查 423 Locked）
  - v0.5 改进：**写操作自动加解锁**，每个 `write__*` 工具执行前后自动 acquire/release
  - 不再需要手动调 `maint__acquire_lock` / `maint__release_lock` 包裹写操作
  - 只读流程结束后仍可手动调 `release_lock` 更新 checkpoint
  - **死锁自动检测（2026-08-09 新增）**：锁的持有进程已死（崩溃/`serve --reload` 杀进程/异常退出导致 `finally` 未释放）→
    - `acquire_lock` 视为死锁**立即强占**（不等 5 分钟超时）
    - `_check_write_allowed`（423 判定）不拦死锁 → 前端不显示锁
    - `GET /api/lock` 报 `locked:false, deadlock:true`（前端可用 `deadlock` 字段提示）
    - `maint__release_lock` 诚实反馈：无锁/他人 BUSY/死锁顺手清理

### Step 6 — CLI 入口 ✅

- `myknowledge init` — 依赖检查 + 目录创建 + 模板复制 + git init
- `myknowledge mcp` — 启动 MCP server
- `myknowledge check` — GC + 项目状态更新
- `myknowledge login/whoami` — 身份设置
- `myknowledge publish/import-share` — 分享包
- `myknowledge serve` — 启动 REST API（FastAPI + SSE）

### Step 7 — 分享包（share__ 共 2 个） ✅

- `share.py` — `publish()` / `import_share()`
- `.mkpkg` 格式：manifest（5 明文字段）+ date-driven 10 字段池加密
- 加密包含 `.env` 中的 `SHARE_MAP` 和 `KNOWLEDGE_SHARE_CODE`
- 没有 `.env` 时退化为纯 manifest 加密（向后兼容）
- 文件级合并（按 maintainer + 字节对比分类新增/跳过/更新/冲突/待确认删除）

### Step 8 — MCP 工具分组 ✅

- `get_document_with_refs(path)` — 读文档时自动拼接 ref 引用
- 正文 Markdown 链接语法：`[text](ref:path)` / `[text](ref:path::标题)`
- 支持 `::标题` 精确段落引用（截取 `## 标题` 内容）
- 读时实时拼接，不缓存，不产生副本
- 防循环，损坏引用不抛错
- 在 `publish --with-context` 中集成外部引用扫描与打包
- DESIGN.md `2.5.11` 节完整记录了语法和规则

### 路径校验规则（`_validate_path`）✅

所有 MCP/CLI 写路径经 `backend/mcp_server.py::_validate_path` 校验，错误信息带恢复指引，按序执行：

- **Guard 0 长度闸门**（2026-08 新增，防"无限长/无限深"输入）：
  - 单段 ≤ **255 字节** = POSIX `NAME_MAX`，主流文件系统（ext4/APFS/HFS+）单文件名/目录名的真实硬上限。注意是字节：UTF-8 中文 1 字 3 字节，255 字节 ≈ 85 个中文字。
  - 段数 ≤ **64**（≈32 层项目嵌套）——经验值，真实结构仅 2-3 层嵌套，64 段远超任何真实使用，用于给树遍历上界。
  - **不设总长度上限**：完整文件路径（kb_root + 相对路径）由操作系统 `PATH_MAX` 兜底（落盘返回 `ENAMETOOLONG`）。因 PATH_MAX 平台不一（Linux 4096 / macOS 1024），后端不应模拟或拍死一个值。
- **Guard 1 路径穿越**：含 `..` 段拒绝
- **Guard 2 绝对路径**：以 `/` 开头拒绝
- **Guard 3 文档文件**：须 `.md` 结尾；前缀白名单（`common-knowledge/`、`projects/`、`archive/`）；**项目树结构校验**（项目层下只允许 `common-knowledge/`、`projects/`、`archive/`——`projects/P/xxx.md`、`projects/P/子项目/` 均拒绝，子项目必须套 `projects/`）；**`readme.md` 排除**（系统层索引/项目元信息，由 readme 生成器管理，文档工具不得创建/覆盖/删除）
- **Guard 4 项目目录**：`projects`/`archive` 本身是系统目录非项目；须 `projects/` 或 `archive/` 开头；同样过项目树结构校验
- **Guard 5 存在性**：传入 storage 时，file/dir 须真实存在

REST 侧经 `backend/main.py::_guard_doc_write_path` 走同一校验（转 400）。

### 测试

- 17 个测试文件，189 个测试通过，3 个前端 smoke 测试因 CDN 环境待修复
- 覆盖：storage 读写/list/search、MCP 工具（全部 20 个）、write-through、lock、share publish/import/merge、CLI、readme 生成器、git manager

### 前端构建守门（2026-08-09 引入）

**背景**：后端静态服务（`backend/main.py`）加载的是 `frontend/index.standalone.html`（单文件内联版），
而它被 `.gitignore` 忽略、无版本追溯；曾出现"改前端源码但没人 build → 分发版本落后"。

**L1 — pre-commit hook（本地自动守门）**：

- 脚本：`.githooks/pre-commit`（进 git，随仓库共享）
- 启用（一次性，本地配置不进 git）：`git config core.hooksPath .githooks`
- 行为：暂存区包含 `frontend/(js|css|vendor)/*`、`frontend/index.html`、`frontend/tiptap-bundle.mjs`
  → 自动跑 `frontend/build.py`（内联生成 standalone + 更新 `?v=` + node --check 语法校验），
  失败**中止提交**；通过后把 build 写回的 `?v=` 更新 `git add frontend/index.html` 随提交入库。
- 非前端 commit（后端/测试/文档）→ 直接放行，零开销。
- 跳过（不建议）：`git commit --no-verify`

**L2 — CI 兜底**：

- `.github/workflows/frontend-build.yml`：push main / PR 时跑 `build.py`（保证源码永远可构建）
- `.github/workflows/publish.yml`：PyPI 发布前同样跑 build——防止过期的 standalone 被打进包分发

**构建命令**（手动）：`cd frontend && python3 build.py`

**⚠ check_build.py 待修（2026-08-09 发现 24 项过期断言）**：其静态检查停留在早期构建时点，
未跟随前端演进——CDN 依赖（项目已迁本地 vendor/）、"view/edit 路由应已删除"（edit 路由
1f8b15b 已回归）、`Object.assign` meta 拍平（已改展开运算符）、CSS 双引擎选择器、page-splash/
ProseMirror--readonly 等元素。当前**不作为硬门禁**（hook/CI 只跑 build.py）；修复后应重新
纳入 hook + CI。待修清单见上轮 check_build 输出的 24 项 ✗。

---

## 待办 — 当前优先级

### 安装分发

- [ ] `install_myknowledge.command` — macOS 一键安装脚本（OSS wheel → venv → 桌面快捷方式）
- [ ] OSS 上传流程文档
- [ ] MCP 配置示例文本（复制粘贴即用）

### Step 9 — Web UI ✅ 后端骨架完成

- [x] `backend/main.py` — FastAPI REST API（导航/写入/维护，复用 Storage）
- [x] `frontend/` 目录 + `index.html` 入口
- [x] `docs/FRONTEND.md` — API 参考 + 前端目录结构
- [x] SSE `/api/events` 实时通知
- [x] `GET /api/mcp` MCP 心跳状态
- [x] `GET /api/version` 版本信息
- [ ] 前端页面开发（由专用前端 agent 完成）

### Step 10 — OSS 云同步

- SyncJob 定时同步
- OSS 分享链接
