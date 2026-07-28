# MyKnowledge — 产品工作流

> 本文档描述从人类安装到 AI Agent 完成知识管理的完整工作流。
> 流程图使用 Mermaid 绘制，GitHub / Obsidian / Typora 等工具可原生渲染。

---

## 一、系统全景

```mermaid
%%{init: {'theme': 'neutral', 'flowchart': {'curve': 'basis'}}}%%
flowchart TB
    subgraph Human["👤 人类用户"]
        A1[终端操作]
        A2[Web UI ⏳]
    end

    subgraph Agent["🤖 AI Agent Client<br/>(CodeBuddy / Trae / WorkBuddy 等)"]
        B[MCP Client]
    end

    subgraph KB["📁 知识库 ~/.myknowledge/"]
        C[MCP Server<br/>python -m backend.cli mcp]
        C --- D[Storage<br/>Markdown + Git]
        C --- E[REST API<br/>uvicorn]
    end

    subgraph Frontend["🖥️ Web UI (开发中)"]
        F[Alpine.js SPA]
        F ---|http| E
    end

    Human -->|mcp.json 配置| B
    B -->|stdio MCP| C
    A1 -->|myknowledge init| KB
    A1 -->|myknowledge serve| E
    A2 -->|浏览器| F
```

---

## 二、安装与初始化

```mermaid
flowchart LR
    Start(("开始")) --> Install["安装包<br/>pip install myknowledge"]
    Install --> Init["初始化知识库<br/>myknowledge init<br/>→ ~/.myknowledge/"]
    Init --> Login["设置身份<br/>myknowledge login<br/><email> <昵称>"]
    Login --> MCPConfig["配置 MCP<br/>在 agent client 的 mcp.json 写入"]

    MCPConfig --> MCPConfigSub{两种方式}
    MCPConfigSub -->|方式 A：在线安装| Online["pip install -e .<br/>command: myknowledge mcp"]
    MCPConfigSub -->|方式 B：直接运行| Offline["command: python -m backend.cli mcp"]

    Online --> Done(("✅ 就绪"))
    Offline --> Done
```

### 2.1 安装

```bash
git clone https://github.com/CoderMoray/MyKnowledgePlatform
cd MyKnowledgePlatform
pip install -e .
```

### 2.2 初始化知识库

```bash
myknowledge init                      # 创建 ~/.myknowledge/
myknowledge login your@email.com 昵称  # 设置身份（写操作必需）
```

### 2.3 配置 Agent Client MCP

在 agent client（如 CodeBuddy）的 MCP 配置文件中添加：

```json
{
  "mcpServers": {
    "myknowledge": {
      "type": "stdio",
      "command": "myknowledge",
      "args": ["mcp"],
      "description": "MyKnowledge 知识管理平台"
    }
  }
}
```

---

## 三、Agent Client 工作流（核心）

这是 AI Agent 与知识库交互的完整流程。
MCP 先抛去锁才能读 diff；写完释放锁。

```mermaid
%%{init: {'theme': 'neutral'}}%%
flowchart TD
    Start(["🤖 Agent 开始会话"])

    Start --> AcquireLock["🔒 maint__acquire_lock<br/>获取写锁"]

    AcquireLock --> ReadKB["📖 导航阶段"]
    ReadKB -->|nav__read_readme| ReadRoot{"阅读根 readme<br/>了解项目结构"}
    ReadRoot -->|有项目| ListProjects["nav__list_dir projects/ 列出项目<br/>或 nav__find 搜索 / nav__exists 确认"]
    ReadRoot -->|无项目| CreateFirst["write__create_document<br/>创建第一篇文档<br/>→ 自动创建项目"]
    ReadRoot -->|直接读文档| ReadDoc["nav__get_document<br/>或 nav__get_document_with_refs"]

    ListProjects --> Explore["nav__list_dir(recursive=True)<br/>递归展开目录树"]
    Explore --> ReadMoreDocs["nav__get_document<br/>阅读具体文档"]
    CreateFirst --> ReadKB

    ReadMoreDocs --> Decide{"判断下一步"}

    Decide -->|"修改已有知识"| Update["✏️ write__update_document<br/>更新文档内容/summary"]
    Decide -->|"新建知识"| Create["📄 write__create_document<br/>支持 dry_run 预览<br/>if_exists 控制覆盖行为"]
    Decide -->|"删除文档"| Delete["🗑️ write__delete_document<br/>删除后 git 可恢复"]
    Decide -->|"改项目元信息"| ProjectMeta["📋 write__update_project_meta<br/>改 name / summary / status"]
    Decide -->|"改名/移动"| Rename{"改名还是移动？"}
    Decide -->|"读 diff"| ReadDiff["🔍 maint__read_diff<br/>读未处理的变更"]
    Decide -->|"验证完整性"| Validate["✅ maint__validate_doc<br/>检查 frontmatter + ref"]
    Decide -->|"重建索引"| Rebuild["🔄 maint__rebuild_index<br/>手动重建 readme + 索引"]
    Decide -->|"分享"| Share["📦 share__publish<br/>导出分享包 .mkpkg"]
    Decide -->|"导入"| Import["📥 share__import_share<br/>导入分享包"]
    Decide -->|"完成工作"| Release["🔓 maint__release_lock"]

    Rename -->|"项目改名（同级）"| RenameProj["write__rename_project<br/>目录 + ref 全部替换"]
    Rename -->|"项目移动（换父级）"| MoveProj["write__move_project<br/>跨父级移动 + rebuild"]
    Rename -->|"文档改名"| RenameDoc["write__rename_document<br/>文件 + ref 全部替换"]

    Update --> WriteThrough["⏳ 自动流程：<br/>① write_document<br/>② gen.rebuild（更新 readme）<br/>③ gen.rebuild_project_status<br/>④ git commit<br/>⑤ broadcast（SSE 通知前端）"]
    Create --> WriteThrough
    Delete --> WriteThrough
    Create --> WriteThrough
    ProjectMeta --> WriteThrough
    RenameProj --> WriteThrough
    RenameDoc --> WriteThrough

    WriteThrough --> AutoArchive{"⑥ status 检查"}
    AutoArchive -->|"非 active"| Archive["📦 shutil.move<br/>projects/X → archive/X<br/>+ rebuild + commit"]
    AutoArchive -->|"active"| Keep[("不动")]
    Archive --> Keep

    Keep --> Decide

    ReadDiff --> ProcessDiff{"有差异?"}
    ProcessDiff -->|"有"| Decide
    ProcessDiff -->|"无"| Decide

    Release --> End(["结束会话"])
```

### 3.1 工作流要点

| 步骤 | 工具 | 说明 |
|------|------|------|
| **🔒 加锁** | `maint__acquire_lock` | 必须先加锁才能写。无锁时写操作报错，引导 AI 执行维护流程 |
| **📖 导航** | `nav__read_readme` / `nav__list_dir`（支持 `recursive`）/ `nav__exists` / `nav__find` | 先确认路径再操作，避免盲目翻目录 |
| **✏️ 写操作** | `write__create_document`（`dry_run` 预览 / `if_exists` 策略）/ `write__update_document` / `write__update_project_meta` / `write__delete_document` | 路径必须符合白名单（`common-knowledge/` / `projects/` / `archive/`） |
| **✏️ 改名/移动** | `write__rename_project` / `write__move_project` / `write__rename_document` | 改名同级，移动换父级，自动替换 ref |
| **🔁 自动流程** | _write_through | 写完自动触发 rebuild + git commit + SSE broadcast |
| **📦 归档** | 自动 | status 为非 active 时自动移入 archive/ |
| **🔍 维护** | `maint__read_diff` / `maint__validate_doc` / `maint__rebuild_index` / `maint__check_integrity` | 检查变更、完整性和 GC 清理 |
| **🔓 解锁** | `maint__release_lock` | AI 完成工作后释放锁 |

---

## 四、路径规则（AI 必读）

所有写工具不接受以下路径：

| 禁止 | 原因 |
|------|------|
| `..` | 路径穿越 |
| `/` 开头 | 绝对路径 |
| 非 `.md` 结尾（文件） | 只支持 Markdown |
| `projects` / `archive` | 系统目录 |
| 不存在的项目目录 | 先用 `nav__list_dir` 列出 |

正确示例：

```
common-knowledge/术语表.md                              → 根层知识
projects/首页重构/common-knowledge/改版方案.md            → 项目内知识
projects/MyKnowledge 项目知识管理平台/projects/前端设计与开发 → 子项目
archive/首页重构                                    → 归档项目目录
```

路径格式错误时，MCP 工具会返回带恢复指引的报错：

```
路径错误：projects

「projects」是系统目录，不是项目。

恢复方法：
  1. 调 nav__list_dir(project_rel="projects") 列出所有活跃项目
  2. 用列出的项目名构造正确路径重试
```

---

## 五、状态与归档

```mermaid
stateDiagram-v2
    [*] --> active：创建项目
    active --> completed：完成
    active --> cancelled：取消
    active --> abandoned：废弃

    completed --> Archived：_auto_archive
    cancelled --> Archived：_auto_archive
    abandoned --> Archived：_auto_archive

    Archived --> [*]：30天后 garbage_collect
```

| 状态 | 位置 | 前台显示 |
|------|------|----------|
| `active` | `projects/` | 🟢 进行中 |
| `completed` | `archive/` | ✅ 已完成 |
| `cancelled` | `archive/` | ⏹ 已取消 |
| `abandoned` | `archive/` | ❌ 已废弃 |

---

## 六、版本

```json
// GET /api/version
{
  "system": "0.5.0",   // 后端 __version__.py
  "kb": "c10b1c4"       // AI checkpoint 对应的 commit hash
}
```

- `system`：系统版本，手动维护
- `kb`：知识库版本，来自 `agent-commit.txt`（AI 处理完变更后写入）。首次使用时空，显示"当前未创建任何知识"

---

## 七、异常处理

### 锁被占用

```text
错误：写锁不存在 → 调 maint__acquire_lock
错误：LOCK BUSY    → 其他 AI 正在操作，稍后重试
```

### 路径错误

```text
路径不存在 → 调 nav__list_dir 列出现有项目
路径格式错误 → 参考第四节正确格式
路径穿越禁止 → 使用 KB 相对路径
```

### 写操作失败

```text
文档已存在 → 用 write__update_document 替代 write__create_document
无写锁     → 先调 maint__acquire_lock
git 冲突   → 调 maint__read_diff 查看差异，确认后重试
```
