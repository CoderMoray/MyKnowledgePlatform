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

### Step 5 — 检修工具（maint__ 共 7 个） ✅

- `validate_doc` / `read_diff` / `check_integrity`
- `rebuild_index` — 手动重建 readme
- `knowledgebase_diagnose` — 知识库结构健康诊断（纯只读，validator.py，2026-08-14 新增）
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

### Step 9 — rename 旧路径 404 重定向（S15）✅

- `backend/renames.py` — 新增模块：rename 映射持久化（`<kb_root>/.renames.json`）
- 存储：隐藏点文件（目录列表天然隐藏），经 `.git/info/exclude` 忽略（repo-local，不进版本库、不污染 git status）
- `rename_document()` 成功后记录 `old → new`；链式 rename（A→B→C）写入时折叠为直接指向最终路径，查询时也跟随链（带防环）
- 删除文档（`move_doc_to_trash`）时移除指向该文档的映射 → 已删除路径显示 deleted 而非跳转
- `GET /api/document/{path}` 404 时查映射，命中且目标存在 → `{"detail": "renamed", "redirect_to": "<新路径>"}`；目标不存在退化为 not_found/deleted
- MCP（`write__rename_document`）与 REST（`PUT /api/document/rename`）共用 `rename_document` 底层，映射两条路径均覆盖
- 映射文件读写失败不阻塞 rename/delete 主流程（best-effort try/except 兜底）

### Step 10 — ref 空格路径支持（S16）✅

- 扫描容错：`_extract_all_refs` 统一提取（链接语法 + balanced parens）并对 `ref:` 路径 `unquote`（%20 → 空格）；`maint__check_refs` 复用该提取器，替代裸正则 `ref:([^)\s]+)`（旧正则截断空格、%20 不解码 → 误报 dead）
- `ref_status` 入口 `unquote`（幂等：%20→空格、空格→空格），任何调用方传 %20 都先解码再判 exists/trash
- 写入规范化：`normalize_ref_content` 将 `[text](ref:...)` 链接内空格 → `%20`（幂等，只动 ref 链接，不碰普通文本/外链）；MCP 写工具（create/update）与 REST 写端点（POST/PUT）共用
- 写入校验：`_classify_ref_targets` 扫描 ref 目标分类（dead/in_trash/empty，结构化）——MCP 侧 `check_ref_targets` 在其上拼 AI 指令文案（含 in_trash 已删除天数、空 target 链接文本）；REST `ref_warnings` 为前端契约结构化数组 `[{type, ref_path, display_text}]`。`write__update_document` 支持 `dry_run=True` 写前预览；update 只检查本次改动引入的引用（`old_content` 差集，REST 与 MCP 一致）
- rename 联动：`rename_document` / `rename_project` / `move_project` 的 ref 替换改用双 pattern（空格原文 + `%20` 编码），替换值统一 `%20` 编码落盘——防规范化后 %20 ref 在 rename 时漏替换变隐性死链
- CLI 无直接写文档入口（写文档走 MCP/REST），该需求项不适用；share 导入不做规范化（保持内容忠实）
- 新增 `tests/test_ref_spaces.py`（46 个测试），全量 361 passed

### Step 11 — nav__find 全文搜索升级 ✅

- `nav__find` 从「按文件名模糊搜索（返回文本表格）」升级为「全文搜索（名称+摘要+正文，返回 dict JSON）」
- 抽取 `Storage.search_documents(q, limit)` 到 `storage.py`（单份实现），合并文档路（`type="doc"`）与项目路（`type="project"`，path 去掉 `/readme.md`），复用 REST `_score` 7 级评分逻辑（原样，不改）
- 返回结构：`{query, hint, results[{type, path, name, score, matched_in}], total}`；`score` 1-7 排序（name+summary+body > name+summary > name+body > summary+body > name > summary > body），`matched_in` 供复查
- `api_search` 重构为调 `search_documents`，REST 返回格式**逐字段不变**（`{path, title, summary, snippet}`），`kind` 参数语义保留（`all`→doc / `projects`→project，根 readme 以 `path=""` 返回）
- 去掉 `scope` 参数（全库搜），`limit` 固定 10；`find_by_name` 保留不删（已无调用方）
- 预期行为变化：不再搜普通目录（内容搜索只能搜 `.md`）
- **根 readme 命中时不返回**（`path=""` 无法 feed to `nav__get_document`——REST 侧空 path 表示根，MCP 侧无等价语义；`search_documents` 保留根 readme 供 REST `kind=projects`，`nav__find` 展示层过滤）
- 新增 `tests/test_nav_find.py`（12 个测试），全量 349 passed

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

- 486 个后端测试全绿（含 S15 renames 20 个 + S16 ref 空格 34 个 + nav__find 全文搜索 12 个 + validator 结构诊断 30 个 + diagnose REST 7 个 + frontmatter-in-content 拦截 7 个 + heal 14 个 + 精准 git 提交 4 个 + events 类型化 5 个 + diagnose 写结果文件 1 个 + client-config 17 个）
- 覆盖：storage 读写/list/search/全文搜索、MCP 工具（全部 20 个）、write-through、lock、share publish/import/merge、CLI、readme 生成器、git manager、rename 映射、ref 空格路径、validator 知识库结构诊断、GET /api/diagnose、GET /api/diagnose/saved、write__* content 误传 frontmatter 拦截、heal（move_document + /api/heal/move + /api/heal/rebuild + maint__move_document）、git 精准提交（commit(paths=...)）、events 类型化（broadcast(event_type) + /api/events 下发 {version,type}）、maint__knowledgebase_diagnose 写结果文件、AI 客户端配置（GET /api/client-config + POST /api/client-config/:platform/:kind + MCP/hooks/Agent 增量合并写入）

### 前端构建守门（2026-08-09 引入）

**背景**：后端静态服务（`backend/main.py`）加载的是 `frontend/index.standalone.html`（单文件内联版），
而它被 `.gitignore` 忽略、无版本追溯；曾出现"改前端源码但没人 build → 分发版本落后"。

**L1 — pre-commit hook（本地自动守门）**：

- 脚本：`.githooks/pre-commit`（进 git，随仓库共享）
- 启用（一次性，本地配置不进 git）：`git config core.hooksPath .githooks`
- 行为：暂存区包含 `frontend/(js|css|vendor)/*`、`frontend/index.html`、`frontend/tiptap-bundle.mjs`
  → 自动跑 `frontend/build.py` + `check_build.py`，任一失败**中止提交**；通过后把 build 写回的
  `?v=` 更新 `git add frontend/index.html` 随提交入库。
- 非前端 commit（后端/测试/文档）→ 直接放行，零开销。
- 跳过（不建议）：`git commit --no-verify`

**L2 — CI 兜底**：

- `.github/workflows/frontend-build.yml`：push main / PR 时跑 `build.py` + `check_build.py`
  （需 `npm install` 装 jsdom/turndown 供 roundtrip 测试）
- `.github/workflows/publish.yml`：PyPI 发布前同样跑 build + check——防止过期的 standalone 被打进包分发

**构建命令**（手动）：`cd frontend && python3 build.py && python3 check_build.py`

**check_build.py（2026-08-09 重构为"构建忠实性检查"）**：不再硬编码历史特征断言，
期望全部从当前源码推导——① HTML 结构完整性（index.html 的 id/x-data 全含）② JS 内联完整性
（被引用的 js/ 注册符号全含）③ CSS 内联完整性（CSS_ORDER 选择器全含）④ `?v=` 与文件内容
md5 一致 ⑤ roundtrip（turndown 转换）。前端演进不会让检查变红，只有 build 真破坏产物才失败。

**前端分发（2026-08-10 修复）**：

- **源码 clone**：`index.standalone.html` 被 .gitignore 忽略不在 git 里 → 后端 serve 检测缺失时
  **自动跑 `frontend/build.py`**（`_ensure_standalone`，带锁防并发）再响应；需要 python3 + node。
- **PyPI 安装**：frontend 作为包（`frontend/__init__.py`）+ `pyproject.toml` package-data 携带
  `index.standalone.html`/`index.html`/`js/`/`css/`/`vendor/`/`tiptap-bundle.mjs` 进 wheel；
  后端 `_frontend_dir()` 优先定位安装包内 frontend（import frontend 包路径）。发布前 publish.yml
  已先跑 build → wheel 自带最新 standalone。
- **依赖锁定**：`mcp>=1.0.0,<2.0`（mcp 2.x 移除 `mcp.server.fastmcp`，1.29 仍兼容）。

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
