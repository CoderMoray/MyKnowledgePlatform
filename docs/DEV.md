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

- 695 个后端测试全绿（含 S15 renames 20 个 + S16 ref 空格 34 个 + nav__find 全文搜索 12 个 + validator 结构诊断 30 个 + diagnose REST 7 个 + frontmatter-in-content 拦截 7 个 + heal 14 个 + 精准 git 提交 4 个 + events 类型化 5 个 + diagnose 写结果文件 1 个 + client-config 102 个 + connection 25 个 + hooks 29 个 + hooks_forward 6 个 + trash empty-all/分页/精准删除 12 个 + git staged-guard/repo-relative 6 个 + config 分享配置 28 个 + doctor 分享检查 5 个 + CLI 分组帮助 10 个 + config/share 写端点 9 个）
- 覆盖：storage 读写/list/search/全文搜索、MCP 工具（全部 20 个）、write-through、lock、share publish/import/merge、CLI、readme 生成器、git manager、rename 映射、ref 空格路径、validator 知识库结构诊断、GET /api/diagnose、GET /api/diagnose/saved、write__* content 误传 frontmatter 拦截、heal（move_document + /api/heal/move + /api/heal/rebuild + maint__move_document）、git 精准提交（commit(paths=...) + staged-guard 跳过无变更 + repo-relative 解析）、events 类型化（broadcast(event_type) + /api/events 下发 {version,type}）、maint__knowledgebase_diagnose 写结果文件、AI 客户端配置（GET /api/client-config + POST/DELETE /api/client-config/:platform/:kind + MCP/hooks/Agent 增量合并写入 + remove_kind 移除 + client_installed 检测 + WorkBuddy 平台支持 + mcp_entry 注入 MYKNOWLEDGE_CLIENT + /api/mcp/heartbeat 心跳连接检测 + connection 字段 + kinds 能力面 + Enchante 平台（SKILL.md + deeplink））、hooks（POST /hooks/pre-tool-use 管控 AI 裸操作知识库 + CodeBuddy 工具名归一化 + hooks_forward 模块调用 + hooks_matcher 平台差异化 + Agent md 模板化 backend/AiClientConfig/agents/ + ClaudeDesktop MCP-only 平台 + frontmatter.json 多平台配置 + PascalCase 平台标识符（ClaudeCode/ClaudeDesktop/CodeBuddyIDE/WorkBuddy/Cursor））、Cursor 全能力平台接入（mcp+hooks+agent，hooks 写入 ~/.cursor/hooks.json 的 version:1 + preToolUse + matcher Shell + hooks_forward，agents 写入 ~/.cursor/agents/MyKnowledge-agent.md，client_installed 检测 ~/.cursor）+ Cursor Shell 工具归一化（hooks.py）+ hooks 设计目录 backend/AiClientConfig/hooks/（6 平台 json，schema 一致 + supports_hooks 对齐 kinds）、分享配置（CLI config set/show/unset + 读取优先级 backend/.env→~/.myknowledge/.env + GET /api/config-status + POST /api/config/share 写端点（部分更新/校验/幂等）+ doctor 分享配置检查项（非阻塞、脱敏显示、未配置引导 + backend 存在性提示）+ CLI 分组友好帮助（无参数/-h 打印分组命令列表）+ share.py 读来源对齐优先级，不影响分享往返）、trash（empty all=true 清空全部 + GET /api/trash 分页 + POST body trash_paths 精准删除 + delete_trash_items）

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

### 版本一致性守门（2026-08-18 引入）

**背景**：`0.7.5` 发版曾漏改 `pyproject.toml`（PyPI 元数据停在 0.7.0），
导致 `pip install` 包元数据与 CLI 版本不一致、`upgrade` 检测错乱。

**版本单一来源架构**：

| 文件 | 角色 | 发版时改？ |
|---|---|---|
| `backend/__version__.py` | **权威来源**（CLI/doctor/upgrade 显示） | ✅ 唯一必改 |
| `desktop/package.json` | Electron 产物版本（electron-builder 读它命名 dmg/zip） | ✅ 桌面发版时同步 |
| `pyproject.toml` | **已 `dynamic = ["version"]`** 派生自 `__version__.py`（setuptools 静态 AST 解析，不触发包导入/h11 检查） | ❌ 无需改 |

**L1 — pre-push hook（本地自动守门）**：

- 脚本：`.githooks/pre-push`（进 git，随仓库共享）
- 启用（一次性，本地配置不进 git）：`git config core.hooksPath .githooks`
  （与 pre-commit 同目录，一次配置两者皆生效）
- 行为：push 前比对 `backend/__version__.py` 与 `desktop/package.json`、
  `README.md`、`README.zh.md` 的版本号（README 检查「当前版本」描述），
  任一不一致 → **中止 push** 并打印各处实际值；解析失败同样中止。
- 跳过（不建议）：`git push --no-verify`

**发版流程（更新后）**：只改 `backend/__version__.py`（桌面发版再加
`desktop/package.json`）→ pre-push 校验一致 → 打 tag → push。

### PyPI 打包范围（2026-08-18 修复）

**背景**：`0.7.5` 的 wheel 只带 `frontend` package-data，`backend/templates`（init 模板）与
`backend/AiClientConfig`（platforms.json/agents/hooks）**缺失** → `pip install` 后
`myknowledge init` 无模板、`/api/client-config` 直接崩。且 `packages.find` 无白名单，
`dist-backend/`（PyInstaller onedir 产物）被误当包收进 wheel（261 文件 / 2.78MB 冗余）。

**修复**：

| 项 | 配置 |
|---|---|
| backend 数据文件 | `[tool.setuptools.package-data] backend = ["templates/*", "AiClientConfig/*.json", "AiClientConfig/agents/*", "AiClientConfig/hooks/*"]` |
| 包白名单 | `[tool.setuptools.packages.find] include = ["backend*", "frontend*"]`（防 dist-backend/build/desktop 再混入） |

**验证**（wheel 实测）：AiClientConfig 10 文件 ✅ / templates 2 文件 ✅ / standalone ✅ /
dist-backend **0** ✅ / 74 文件 **781K**（原 438 文件 8.09MB）。构建后若出现
`File exists: build/bdist...` 报错，是构建缓存冲突：`rm -rf build myknowledge.egg-info` 再跑。

**wheel 构建命令**：`python3 -m pip wheel . --no-deps --no-build-isolation -w /tmp/wheeltest`

**桌面打包（PyInstaller）对照**：`scripts/build-backend.sh` 已含
`--add-data backend/templates` + `backend/AiClientConfig` + `backend/hooks_forward.py`，
桌面侧无需改动。


**前端分发（2026-08-10 修复）**：

- **源码 clone**：`index.standalone.html` 被 .gitignore 忽略不在 git 里 → 后端 serve 检测缺失时
  **自动跑 `frontend/build.py`**（`_ensure_standalone`，带锁防并发）再响应；需要 python3 + node。
- **PyPI 安装**：frontend 作为包（`frontend/__init__.py`）+ `pyproject.toml` package-data 携带
  `index.standalone.html`/`index.html`/`js/`/`css/`/`vendor/`/`tiptap-bundle.mjs` 进 wheel；
  后端 `_frontend_dir()` 优先定位安装包内 frontend（import frontend 包路径）。发布前 publish.yml
  已先跑 build → wheel 自带最新 standalone。
- **依赖锁定**：`mcp>=1.0.0,<2.0`（mcp 2.x 移除 `mcp.server.fastmcp`，1.29 仍兼容）。

### hooks_forward 打包适配（2026-08-18）

**背景**：CodeBuddy PreToolUse hook（stdin→后端 `/hooks/pre-tool-use`，fail-open）的
`command` 原来是 `python3 -m backend.hooks_forward`（模块调用）。在桌面 App（PyInstaller
onedir 打包）下不可行——onedir 无独立 python 可执行（`sys.executable` 是 bootloader），
不能跑 python 脚本。

**改造**：
- `hooks_forward.py` **完全独立**（不再 `from backend.client_config import HOOK_ENDPOINT`）：
  - 自带 `HOOK_ENDPOINT` 常量（默认 `http://127.0.0.1:8080/hooks/pre-tool-use`，与
    `client_config.py` 默认一致；可用环境变量 `MYKNOWLEDGE_HOOK_ENDPOINT` 覆盖）。
  - 抽出 `forward(raw: str) -> str` 核心函数（stdin 串 → hook → 返回 stdout 串，fail-open），
    便于单测，不依赖 stdin/stdout。
  - 可独立运行：`python3 <path>/hooks_forward.py`（无需 backend 包）。
- `_hooks_command_codebuddy()` **环境感知**：
  - 开发 / PyPI 安装（非 frozen）：保持 `python3 -m backend.hooks_forward`。
  - 桌面 App（`sys.frozen`）：`"<sys.executable>" --hooks-forward` —— **复用冻结的
    myknowledge-backend 二进制本身**作为 hook 执行器，不额外产出一个可执行文件。
- `desktop_server.py` 增加 `--hooks-forward` 子命令：读 stdin → `hooks_forward.main()`
  转发 → stdout。因 `desktop_server` 顶层 `from backend import hooks_forward`，
  PyInstaller 会把它 trace 进 PYZ 包（而非仅 datas 数据文件），使冻结二进制内可 import。

**打包执行方案（待打包阶段验证，backlog）**：
- 现状 spec 仍把 `backend/hooks_forward.py` 放 `datas`（供开发环境 `python <path>` 独立运行）；
  `desktop_server` 的 import 会额外把它编入 PYZ，两者共存不冲突。
- 冻结后 `~/.codebuddy/settings.json` 的 hooks command 将写成
  `<App资源路径>/myknowledge-backend --hooks-forward`（代码在 `sys.frozen` 分支生成），
  由 Electron App 内的同一二进制处理，fail-open 语义不变。

**测试**（`tests/test_hooks_forward.py` + `tests/test_client_config.py`）：
- hooks_forward 源码不含 `backend` import（standalone 约束断言）；
- `python <path>/hooks_forward.py` 子进程可独立跑通 mock 输入（fail-open）；
- `desktop_server --hooks-forward` 转发并 fail-open；
- `_hooks_command_codebuddy()` 开发/冻结两分支 + 空格路径加引号 + `write_kind` 落盘命令。

### Cursor 平台接入 + hooks 设计目录（2026-08-18）

**背景**：Cursor 是全能力平台（mcp + hooks + agent），全局配置 `~/.cursor/mcp.json`、
`~/.cursor/hooks.json`、`~/.cursor/agents/`。MCP 已实测通过；hooks 协议（stdin JSON →
stdout JSON，退出码 2=阻止、其他 fail-open）与 hooks_forward 兼容。

**Cursor 接入**（kinds=[mcp, hooks, agent]）：
- `platforms.json` 新增 Cursor：`config_dir="~/.cursor"`、`mcp_file="~/.cursor/mcp.json"`、
  `hooks_file="~/.cursor/hooks.json"`、`agents_dir="~/.cursor/agents"`；无 cli_names（无 CLI，
  config_dir 存在即 installed）。
- `_platform_paths` 新增 `hooks_file` 键：Cursor 独立映射到 hooks.json，其余平台回退到
  settings_file（`_resolve_path("")` 返回 `Path('.')` truthy，空串须先判空）。
- **hooks 写 `~/.cursor/hooks.json`**：`{version:1, hooks:{preToolUse:[{type:command,
  command: hooks_forward, matcher: Shell|Write|Delete, timeout:10000,
  failClosed:false}]}}`（增量合并，保留 version:1 与已有 hooks）。Cursor 条目
  `command` 直接挂在条目上（无嵌套 hooks 列表），`_matcher_is_mine` 增加
  direct-command 识别。Cursor preToolUse matcher 按工具类型匹配（官方枚举
  Shell/Read/Write/Grep/Delete/Task/MCP，无独立 Edit——文件编辑归 Write；
  Delete 为原生工具），须同时覆盖 Shell 与 Write/Delete，否则文件直写/删除
  不会被拦截（见下方 matcher bugfix）。
- `hooks.py` `_TOOL_ALIASES` 增加 `"Shell": "Bash"`（Cursor preToolUse 用 Shell 而非 Bash），
  使对 KB 裸写命令的拦截判定生效。
- agent 写 `~/.cursor/agents/MyKnowledge-agent.md`（frontmatter name/description + 正文，
  frontmatter.json 新增 Cursor variant）。
- `mcp_entry("Cursor")` 注入 `MYKNOWLEDGE_CLIENT=Cursor`（心跳自动上报）。

**hooks 设计目录 `backend/AiClientConfig/hooks/`**（每平台一个 json，平台名当文件名）：
- 各平台 hooks 设计的**权威记录**（代码生成 hooks 配置以此为参考）。
- schema：`{platform, display, supports_hooks, event, matcher, matcher_note, command,
  protocol, exit_code_deny:2, fail_open:true, notes}`；不支持 hooks 的平台
  （ClaudeDesktop/Enchante）`supports_hooks=false` + notes 说明。
- 6 文件：ClaudeCode / CodeBuddyIDE / WorkBuddy / ClaudeDesktop / Cursor / Enchante。
- `AiClientConfig` 整目录已由 spec `datas` 携带，hooks/ 子目录自动进包，无需改 spec。

### Hook matcher 按工具名触发 bugfix（2026-08-19）

**背景**：用户用 Claude Code 实测发现，用 Write 工具直接写 KB 文件完全没被拦截。
根源不在后端 `hooks.py` 判定逻辑（Write/Edit/Delete 的 `file_write` 分支早就写好），
而在 **Claude 平台侧的 PreToolUse hook 是按「工具名」触发的**：`hooks_matcher()`
里 Claude/WorkBuddy 分支的 `matcher` 写死为 `"Bash"`，于是 hook 只在调用 Bash 工具前
触发，Write/Edit 调用根本不发到后端，`hooks.py` 的 `file_write` 分支成了死代码。

**改动**：
- `hooks_matcher()` ClaudeCode/WorkBuddy 分支：`matcher: "Bash"` →
  `"Bash|Write|Edit"`（Claude 的 matcher 用 `|` 分隔多工具名；Delete 暂不覆盖，
  Claude Code 无对应原生工具名）。
- Cursor 分支同样有同类隐患（原 `matcher: "Shell"` 只匹配 Shell 工具）：
  → `"Shell|Write|Delete"`。Cursor 官方文档（cursor.com/docs/hooks）确认其
  preToolUse matcher 工具类型为 Shell/Read/Write/Grep/Delete/Task/MCP（**无独立
  Edit，文件编辑归 Write**；**Delete 为原生工具**）。故覆盖 Shell + Write + Delete
  即可拦截全部 KB 写操作；删文件的 Delete 对 Cursor 是必须加的（直删文件否则绕过）。
- CodeBuddyIDE 分支本就是 `matcher: "*"`（全工具），`hooks.py` 内部对 MCP 放行，
  宽 matcher 安全，无需改。
- 同步更新权威记录 `backend/AiClientConfig/hooks/{ClaudeCode,WorkBuddy,Cursor}.json`
  的 `matcher` / `matcher_note`。

> **Delete 差异（经官方文档核实）**：Claude Code 的 PreToolUse matcher 工具名
> （Bash/Write/Edit/Read/Glob/Grep/Agent/WebFetch/WebSearch/AskUserQuestion/
> ExitPlanMode）**不含 Delete**——Claude 删文件走 Bash `rm`，已被 Bash 分支的
> `_DESTRUCTIVE_PATTERNS` 拦截，故 Claude 不需要也不应加 Delete。**Cursor 则有原生
> Delete 工具**，故其 matcher 必须包含 Delete，否则删除操作会绕过 hook。

**生效前提（重要，非热更新）**：
1. 改的是写入 `~/.claude/settings.json` 的**静态 JSON**，旧 `"Bash"` 条目不会自动变。
   必须重新触发一次 `write_kind("ClaudeCode", "hooks")`（UI「开关」重开一下），
   新 matcher 才落盘。
2. 新 hook 配置要**新会话**才被 Claude Code 读取（重启对话是必要不充分条件——
   关键是先把配置内容改对再重启）。

### Enchante 独立 Agent deeplink 接入（2026-08-19）

**背景**：为 Enchanté 提供「一键创建独立专属 Agent」能力——用户在 Enchanté 顶部
Agent 下拉框中直接选「MyKnowledge 知识管理专家」专属角色，原子化绑定 MCP 工具 +
Agent 人设。协议细节经 Enchante 确认（2026-08-19，7 项）。**产品决策：不再提供
独立 skill**（Agent 能力全部来自 role + MCP 工具），故 skillNames 留空、SKILL.md
写路径移除。

**Deeplink 协议**（Enchante 提供并确认）：
```
enchante://agent/install?name=<URL_ENCODED_AGENT_NAME>&config=<BASE64_JSON_PAYLOAD>
```
- `name`：**展示名（Display Name）**，非内部 ID——Enchanté 用本地 UUID 作 Agent
  主键，支持中文/空格。本实现用 `"MyKnowledge 知识管理专家"`（所有平台 agent 统一
  名；区别于 MCP install 的 `name=MyKnowledge`）。
- payload JSON schema（Enchanté 确认）：
  ```json
  {
    "role": "<人设 Prompt，复用 _agent_template()/MyKnowledge-agent.md 纯正文>",
    "skillNames": [],
    "mcpServers": {
      "MyKnowledge": {
        "displayName": "MyKnowledge", "description": "...", "icon": "book.closed",
        "config": mcp_entry("Enchante")   // 复用标准 MCP stdio 配置
      }
    }
  }
  ```
- **role**：必须**纯正文，无 YAML frontmatter**（Enchanté 直接作 System Prompt 注入）。
- **skillNames**：可选字段；**本实现留空 `[]`**——不再提供独立 skill，Agent 能力
  来自 role + mcpServers，无对象可绑定。
- **重复安装**：弹「Conflict Resolution」浮窗（Replace / Rename / Skip），非静默幂等。
- **卸载**：无 uninstall 协议——Agent 须在 Settings→Agents 手动删。

**实现**：
- `backend/client_config.py`：`enchante_agent_deeplink()`（确认 schema）+
  `_base64_quote()`（MCP/agent 共用 `+`→`%2B` 转义）；`role` 复用
  `_agent_template()`，`skillNames: []`，`mcpServers` 内嵌 `mcp_entry("Enchante")`。
- **skill 移除**：删除 `_skill_template()`/`_skill_content()`/`_skills_dir()` 与
  `SKILL.md` 模板；`write_kind/remove_kind('Enchante','agent')` 改为短接返回
  `status:"deeplink"`（不写本地文件）；`detect_platform('Enchante')['agent']=false`
  （deeplink 安装无本地文件）；Enchante 在 `_agent_target_path`/`_agent_file_exists`/
  `agent_content` 不再走 skill 分支；platforms.json 移除 `skills_dir`。
- `backend/main.py`：`GET /api/client-config/Enchante/agent-deeplink`（非 Enchante 400）。
- 前端（已完成）：设置 modal Enchante MCP/Agent 行均显示 deeplink 按钮（不走 toggle），
  引导页 Step2.2 拆「生成 MCP 链接」+「生成 Agent 链接」两入口。

**测试**：`tests/test_client_config.py` 更新为确认后 schema 断言（name 展示名、
`{role, skillNames: [], mcpServers}` 结构、base64 round-trip、端点 400、Enchante
agent deeplink 短接）。后端测试 704 全绿。

### CLI config 子命令 + 分享配置状态 API（2026-08-18）

**背景**：分享配置（KNOWLEDGE_SHARE_CODE + SHARE_MAP）原先只能手动编辑 `backend/.env`。
本轮让 `myknowledge config` 命令把分享配置写入 `~/.myknowledge/.env`（用户级可写），
并暴露只读状态 API 供前端引导。OSS 键不涉及。

**读取优先级**（`backend/config.py`）：
- `effective_env_file()`：`backend/.env` 存在优先 → `~/.myknowledge/.env` fallback →
  none（fallback 目标是用户文件，便于后续写入生效）。
- `load_share_env()` 返回 `{share_code, share_map}`（share_map 缺省 `"000"`）。
- `share.py::_load_env()` 改为调 `load_share_env()`（优先级一致）→ publish/import 读取
  同一生效来源，**分享往返不受影响**（确认不破坏现有分享功能）。

**CLI `myknowledge config`**（`backend/cli.py`）：
- `config` / `config show`：显示生效来源、脱敏分享码（`mask_share_code`：前 2+后 2，中段
  `***`，≤4 位全 `****`）、SHARE_MAP；backend/.env 存在时警告「存在且优先」。
- `config set KEY=VALUE`：写 `~/.myknowledge/.env`（`write_share_env`：首次创建带注释模板，
  就地更新已有键 / 追加新键，保留无关行）；backend 存在时警告「可能不生效」；改
  KNOWLEDGE_SHARE_CODE 时提示「旧 .mkpkg 失效」。
- `config unset KEY`：移除键（`unset_share_env`，幂等）。
- 仅允许 SHARE_KEYS 两键（KNOWLEDGE_SHARE_CODE / SHARE_MAP）。

**REST `GET /api/config-status`**（`backend/main.py`）：
- 返回 `{share_configured: bool, env_source: "backend"|"myknowledge"|"none", message}`。
- `share_configured` 仅当 KNOWLEDGE_SHARE_CODE + SHARE_MAP 均配置；**绝不泄露分享码明文**
  （message 只含脱敏形式）。
- 前端用于「未配置 → 引导」（另派前端）。

**REST `POST /api/config/share`**（`backend/main.py`，2026-08-18）：
- 写分享配置到 `~/.myknowledge/.env`（复用 `write_share_env()`，与 CLI config 同一文件/逻辑）。
- body `{share_code?, share_map?}`，**部分更新**（缺省字段不变）；重复写覆盖（幂等）。
- 校验：`share_code` 非空（400「share_code 不能为空」）、`share_map` 三位正整数
  （400「share_map 须为三位正整数」）；两者皆空 400「至少提供一个字段」。
- 返回与 `GET /api/config-status` 相同 shape（`{share_configured, env_source, message}`，
  反映写入后生效来源）；不泄露分享码明文。与 GET 共用 `_share_config_status()`。
- 前端引导页 Step1（企业名称 + 组织代码）保存用；测试 `tests/test_main.py`
  `TestApiConfigShareWrite`（9 个）。

**前端引导页重设计（4 页 3 步 + 大 modal，2026-08-18，纯前端不改后端）**：
- 引导向导从「3 步（身份 / AI 协作全列表 / 完成）」改为「4 页 3 步」：
  Step1 身份（昵称/邮箱/企业名称/组织代码 4 字段全必填，企业名称非空、组织代码三位正整数，
  后两字段经 `POST /api/config/share` 保存，失败 toast 不阻断）→ Step2.1 平台多选
  （`clientPlatforms` 数据驱动 6 平台，未安装灰禁用+「未安装」标注，至少选 1）→
  Step2.2 执行+结论（进度条 0.42s；Enchante 行专属「⚡ 打开安装链接」按钮四态：
  初始/点击后「已生成链接」/生成中/未安装防御态）→ Step3 完成（延续 guideSummary）。
- 大 modal `.guide-modal` 840×640 + 小屏兜底（max-width/max-height calc）+ overflow-y:auto；
  步骤过渡动画时长 ≥0.36s 且为 0.06 整数倍（enter 0.42s / leave 0.36s / 结论 0.48s），
  统一 cubic-bezier(0.4,0,0.2,1)，prefers-reduced-motion 减半。
- 设计权威：`docs/designs/引导页重设计/SPEC.md`（§1-§10 + §10.4 裁决）；
  前端改动 `frontend/index.html`(引导段) + `store.js`(guide* 状态/方法 + deeplinkClicked) +
  `modal.js`(guideNext/Prev 4 页流 + saveSetup 写分享) + `api.js`(setConfigShare) +
  `css/components.css`(.guide-*)。test_stage3 19 用例全绿。

**doctor 分享配置检查项**（`backend/cli.py` `cmd_doctor`，2026-08-18）：
- 新增第 7 项「分享配置」：显示来源（backend/.env / ~/.myknowledge/.env / 未配置）、脱敏分享码、SHARE_MAP。
- **非阻塞**：分享是可选项，`checks.append(..., True)` 恒 ok，不因未配置判 doctor 失败。
- 未配置时在 summary 追加引导：`myknowledge config set KNOWLEDGE_SHARE_CODE=<鉴权码> 与 SHARE_MAP=<三位正整数>`。
- 测试：`tests/test_cli_doctor.py`（4 个，backend/user/none/partial 四态）。

**doctor 分享检查增强 + CLI 分组帮助（2026-08-18）**：
- **doctor 分享检查增强**：未配置且 `backend/.env` 存在时，除现有引导外追加 backend 存在性提示
  「注意：若 backend/.env 存在，分享码以其中配置为准，用户级配置（~/.myknowledge/.env）可能不生效；
  需修改 backend/.env 或移除其分享配置」，帮用户理解"改了 config set 为什么不生效"。已配置不提示。
  `tests/test_cli_doctor.py` 增至 5 个（+backend 存在+未配置态）。
- **CLI 分组友好帮助（像 git）**：
  - 无参数 / 顶层 `-h` / `--help` → 打印 `用法 + 分组命令列表`（exit 0，不报 error）。
  - 5 组：知识库操作（init/check/rebuild/serve）、身份（login/whoami）、分享（publish/import-share/config）、
    AI 客户端（mcp/mcp-config）、系统（version/doctor/upgrade）。
  - 命令说明单一来源 `_CMD_HELP`（`add_parser(help=...)` 与分组显示共用）；`_GROUPS` 定义分组。
  - `main()`：`argv=None` 默认取 `sys.argv[1:]`（与 argparse 一致），空/顶层 help → 分组帮助；
    子命令 `<cmd> -h` 仍走 argparse 显示该子命令自身帮助。
  - subparsers 改 `required=False`（空 argv 由 main 拦截）。
  - **config 子命令复用分组帮助风格**（补充）：`myknowledge config -h`/`--help` 打印子表单清单
    （show/set/unset + 示例，exit 0）；`config` 无 action 仍为 show（向后兼容）。`_CONFIG_HELP` 单一来源。
  - 测试 `tests/test_cli_help.py`（10 个）。

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
