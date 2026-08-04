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

### 测试

- 16 个测试文件，164 个测试通过，3 个前端 smoke 测试因 CDN 环境待修复
- 覆盖：storage 读写/list/search、MCP 工具（全部 20 个）、write-through、lock、share publish/import/merge、CLI、readme 生成器、git manager

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
