<h1 align="center">MyKnowledge</h1>

<p align="center">
  <strong>Local-first 知识管理平台</strong>
  <br/>
  Markdown 为真相源 · Git 为版本底座 · MCP 为 AI 接口
  <br/>
  <sub>让任意 AI agent 客户端存取你的知识，越用越厚</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"/>
  <img src="https://img.shields.io/badge/python-≥3.10-blue" alt="Python"/>
  <img src="https://img.shields.io/badge/MCP-ready-green" alt="MCP"/>
</p>

---

## 📦 安装

```bash
git clone https://github.com/CoderMoray/MyKnowledgePlatform
cd MyKnowledgePlatform
pip install -e .
```

## 🚀 快速开始

```bash
# 1. 初始化知识库
myknowledge init                     # → ~/.myknowledge/
myknowledge login your@email.com 昵称 # 设置身份（写操作必需）

# 2. 启动 Web UI
myknowledge serve                    # → http://127.0.0.1:8080

# 3. 配置 AI Agent MCP
# 在 CodeBuddy / WorkBuddy 等 agent client 的 MCP 配置中添加：
# command: myknowledge mcp
```

## 🧠 使用方式

### 方式 A：AI Agent（核心）

通过 MCP 协议让 AI 直接管理知识库。支持 18 个工具：

| 分组 | 用途 | 工具数 |
|------|------|:-----:|
| `nav__` | 导航和阅读 | 4 |
| `write__` | 创建、更新、删除、改名 | 6 |
| `maint__` | 加锁、读 diff、重建索引、验证 | 6 |
| `share__` | 导出/导入分享包 | 2 |

```text
AI 工作流：acquire_lock → read → write → release_lock
```

### 方式 B：Web UI（开发中）

FastAPI + Alpine.js SPA，浏览器中浏览和编辑知识。

```bash
myknowledge serve --port 8080
# → http://127.0.0.1:8080
```

## 📁 项目结构

```
MyKnowledge/
├── backend/                 # Python 后端
│   ├── cli.py              # CLI 入口（init / mcp / serve / login）
│   ├── mcp_server.py       # 18 个 MCP 工具
│   ├── main.py             # FastAPI REST API
│   ├── storage.py          # Markdown 文件读写
│   ├── readme_generator.py # Readme 索引生成
│   ├── git_manager.py      # Git 版本控制
│   ├── events.py           # SSE 实时更新
│   ├── share.py            # 分享包（.mkpkg）加密/导入导出
│   ├── config.py           # 身份管理 + 环境变量
│   └── templates/          # Readme 模板
├── frontend/               # Web UI（Alpine.js SPA）
│   ├── index.html          # 主页面
│   ├── css/                # 样式（Raycast 设计系统）
│   └── js/                 # JavaScript
├── docs/                   # 设计文档
├── tests/                  # 测试
└── pyproject.toml          # 包配置
```

## 🏗️ 知识库结构

```
~/.myknowledge/              ← 知识库根
├── readme.md                ← 路由索引
├── common-knowledge/        ← 知识文档（.md）
├── projects/                ← 项目（递归）
│   ├── 项目A/              ← 每个项目一层
│   │   ├── readme.md
│   │   ├── common-knowledge/
│   │   ├── projects/        ← 子项目
│   │   └── archive/         ← 已归档子项
│   └── ...
├── archive/                 ← 已归档项目
├── project-status.md        ← 所有项目状态一览
└── _templates/              ← 模板文件
```

## 🧩 核心特性

| 特性 | 说明 |
|------|------|
| **纯文本存储** | Markdown + YAML frontmatter，无锁定 |
| **Git 版本控制** | 每次 AI 写入自动 commit，全程可追溯 |
| **MCP 原生支持** | 18 个工具，AI agent 开箱即用 |
| **本地优先** | 数据全在你本地，可选 OSS 云同步 |
| **路径安全** | 白名单校验，防止 AI 误写系统目录 |
| **自动归档** | 项目状态变更自动移入 archive/ |
| **Web UI** | Alpine.js SPA + TipTap 编辑器 |
| **加密分享** | .mkpkg 格式，字段池加密 |
| **无 LLM 依赖** | 不内置模型，推理在 agent client |

## 📖 文档

- [`docs/DESIGN.md`](docs/DESIGN.md) — 完整设计文档
- [`docs/product-flow/workflow.md`](docs/product-flow/workflow.md) — 产品工作流（Mermaid 流程图）
- [`docs/FRONTEND.md`](docs/FRONTEND.md) — 前端开发参考
- [`backend/`](backend/) — 后端源码，各文件独立文档

## 🧪 测试

```bash
pytest tests/ -v
```

## 🙏 致谢

**设计者 & 创建者**：[Moray Liang](https://github.com/CoderMoray)

MyKnowledge 的设计与初始实现由 Moray Liang 完成。后续所有贡献者将
在 [`NOTICE`](NOTICE) 文件中记录署名。

## 📄 许可

[Apache License 2.0](LICENSE) — © 2026 Moray Liang

允许自由使用、修改、分发，但必须保留原始版权声明和许可文本。
