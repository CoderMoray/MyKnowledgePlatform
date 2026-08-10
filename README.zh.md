# MyKnowledge

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-ready-green)](https://modelcontextprotocol.io/)
[![PyPI](https://img.shields.io/pypi/v/myknowledge)](https://pypi.org/project/myknowledge/)

Local-first 知识管理平台。以 Markdown 为真相源、Git 为版本底座、MCP 为 AI 接口标准。

任意 MCP 兼容的 AI agent 客户端（CodeBuddy、Trae、WorkBuddy 等）可直接存取你的知识库——越用越厚，数据始终归你。

---

## 特性

- **纯文本存储** — Markdown + YAML frontmatter，无锁定
- **Git 版本控制** — 每次写入自动 commit，全程可追溯
- **MCP 原生支持** — 22 个工具：导航、读写、改名、移动、删除、归档、分享
- **CLI 自助管理** — `doctor`（健康检查）、`version --check`（PyPI 版本检查）、`upgrade`（一键升级）、`mcp-config`（输出配置 JSON）
- **本地优先** — 数据全在你的机器上，可选 OSS 云同步
- **自动归档** — 已完成/取消/废弃的项目自动移入 `archive/`
- **自动加锁** — 每次写操作自动获取和释放写锁
- **Web UI** — Alpine.js SPA + TipTap 编辑器（开发中）
- **加密分享** — `.mkpkg` 格式，字段级加密

## 快速开始

```bash
# 安装
pip install myknowledge

# 初始化
myknowledge init                      # 创建 ~/.myknowledge/
myknowledge doctor                     # 验证一切就绪
myknowledge login your@email.com 昵称  # 写操作必需

# 启动 MCP 服务（供 AI agent 连接）
myknowledge mcp

# 或启动 Web UI
myknowledge serve                     # → http://127.0.0.1:8080

# 随时自查和升级
myknowledge doctor
myknowledge version --check
myknowledge upgrade
```

## 使用方式

### AI Agent（MCP）

在 MCP 兼容的 agent client 中配置：

```json
{
  "mcpServers": {
    "MyKnowledge": {
      "command": "myknowledge",
      "args": ["mcp"]
    }
  }
}
```

> **自动加锁**：每次写操作自动获取和释放写锁。系统自动重建索引、提交 git、通过 SSE 推送更新。

获取你的精确配置：`myknowledge mcp-config`

### Web UI

```bash
myknowledge serve --port 8080
# 浏览器打开 http://127.0.0.1:8080
```

## 项目结构

```
myknowledge/
├── backend/
│   ├── cli.py               # CLI：init / mcp / serve / login / doctor / upgrade / version / mcp-config
│   ├── mcp_server.py        # 22 个 MCP 工具
│   ├── main.py              # FastAPI REST API
│   ├── storage.py           # Markdown 读写
│   ├── readme_generator.py  # Readme 索引生成
│   ├── git_manager.py       # Git 操作
│   ├── events.py            # SSE 实时更新
│   ├── share.py             # 加密分享包
│   └── config.py            # 身份 + 环境配置
├── frontend/                # Alpine.js SPA（开发中）
├── docs/                    # 设计文档
└── tests/
```

## 知识库结构

```
~/.myknowledge/
├── readme.md                # 路由索引
├── common-knowledge/        # 知识文档 (.md)
├── projects/                # 项目（递归）
│   └── 项目名/
│       ├── readme.md
│       ├── common-knowledge/
│       ├── projects/        # 子项目
│       └── archive/         # 已归档子项
├── archive/                 # 已归档项目
├── project-status.md        # 项目状态一览
└── _templates/              # Readme 模板
```

## 自助安装

MyKnowledge 附带一份完整的 **AI 安装指南**（`docs/AI-SETUP.md`）。将内容复制给任意 MCP 兼容的 AI agent，它就会自动为你完成：

1. 检查环境依赖（Python / Git / pip）
2. 通过 `pip install myknowledge` 安装
3. 运行健康检查并初始化知识库
4. 引导你设置身份
5. 配置 MCP 接入你的 AI client
6. 设置定时任务：版本检查和知识库变更摘要

## 开发

```bash
git clone https://github.com/CoderMoray/MyKnowledge_PlatForm
cd MyKnowledge_PlatForm
pip install -e .
```

运行测试：

```bash
pytest tests/ -v
```

## 版本

- **系统版本**：定义在 `backend/__version__.py`（当前 0.7.0）
- **知识库版本**：从 `agent-commit.txt` checkpoint 读取的 git commit hash

## 许可

[Apache License 2.0](LICENSE) — Copyright 2026 Moray Liang

## 致谢

**设计者 & 创建者**：[Moray Liang](https://github.com/CoderMoray)

贡献者记录在 [`NOTICE`](NOTICE) 文件中。
