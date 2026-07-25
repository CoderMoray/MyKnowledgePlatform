# MyKnowledge 开发管理

> 对应 [DESIGN.md](DESIGN.md) v0.4。Phase 1-2 核心存储层 + MCP 已完成。
> 按 Step 推进，每一步完成后更新状态。

---

## 已完成

### Step 1 — 配置文件 + 基础工具 ✅

- `config.py` — `resolve_root` / `load_oss_env` / `get_identity` / `set_identity`
- `storage.py` — frontmatter 解析、文件读写、目录遍历、id 生成
- `git_manager.py` — git init / auto-commit / diff / checkpoint

### Step 2 — readme 生成器 ✅

- `readme_generator.py` — `rebuild()` / `rebuild_project_status()` / `garbage_collect()`
- 项目状态四段式：进行中 / 已完成 / 已取消 / 已废弃（30 天自动清理）

### Step 3 — MCP 服务 + 只读工具 ✅

- `mcp_server.py` — FastMCP 应用
- `read_readme` / `list_dir` / `get_document`

### Step 4 — 写入工具 + write-through ✅

- `create_document` / `update_document` / `update_project_meta`
- 写入时自动：rebuild 父层 readme → rebuild 项目状态 → git commit
- 写入时自动注入 `author` / `maintainer` frontmatter

### Step 5 — 检修工具 ✅

- `validate_doc` / `read_diff` / `check_integrity`
- `rebuild_index` — 手动重建 readme
- `nav__maintenance_procedure` prompt — 会话开始时的自动维护流程
- `.lock` 机制 — AI 操作时锁 Web UI 写入（设计已定，实现待 Web UI）

### Step 6 — CLI 入口 ✅

- `myknowledge init` — 依赖检查 + 目录创建 + 模板复制 + git init
- `myknowledge mcp` — 启动 MCP server
- `myknowledge check` — GC + 项目状态更新
- `myknowledge login/whoami` — 身份设置
- `myknowledge publish/import-share` — 分享包

### Step 7 — 分享包 ✅

- `share.py` — `publish()` / `import_share()`
- `.mkpkg` 格式：manifest（5 明文字段）+ date-driven 10 字段池加密
- 加密包含 `.env` 中的 `SHARE_MAP` 和 `KNOWLEDGE_SHARE_CODE`
- 没有 `.env` 时退化为纯 manifest 加密（向后兼容）

### 测试

- 13 个测试文件，106 个测试全部通过

---

## 待办 — 当前优先级

### Step 8 — 知识引用 ✅

- `get_document_with_refs(path)` — 读文档时自动拼接 ref 引用
- `delete_document(path)` — 删除文档工具
- 正文 Markdown 链接语法：`[text](ref:path)` / `[text](ref:path::标题)`
- 支持 `::标题` 精确段落引用（截取 `## 标题` 内容）
- 读时实时拼接，不缓存，不产生副本
- 防循环，损坏引用不抛错
- DESIGN.md `2.5.11` 节完整记录了语法和规则
- **待办**：分享包 `--with-context`
- **待办**：MCP 协议目前无原生工具分组功能，当前用前缀命名 (`nav:`, `write:`, `maint:`, `share:`) 模拟。如后续协议支持分组暴露，按组分别注册。

### 安装分发

- [ ] `install_myknowledge.command` — macOS 一键安装脚本（OSS wheel → venv → 桌面快捷方式）
- [ ] OSS 上传流程文档
- [ ] MCP 配置示例文本（复制粘贴即用）

### Step 9 — Web UI ✅ 后端骨架完成

- [x] `backend/main.py` — FastAPI REST API（导航/写入/维护，复用 Storage）
- [x] `frontend/` 目录 + `index.html` 入口
- [x] `docs/FRONTEND.md` — API 参考 + 前端目录结构
- [x] `myknowledge serve` CLI 命令
- [ ] 前端页面开发（由专用前端 agent 完成）

### Step 10 — OSS 云同步

- SyncJob 定时同步
- OSS 分享链接
