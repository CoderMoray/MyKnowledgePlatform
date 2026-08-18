# MyKnowledge 文档索引

> 本项目所有文档统一收拢在 `docs/`（根目录不散落文档）。本文档是导航入口，帮你在海量文档中快速定位。

---

## 目录导航

| 子目录 | 用途 | 代表性文档 |
|--------|------|-----------|
| `designs/` | **前端设计稿**（前端设计专家产物：SPEC 语义核心 + SVG 视觉稿 + PNG 人审参考） | `kb-health/SETTINGS_REDESIGN_SPEC.md`、`kb-health/SPEC.md`、`kb-health/ARCHITECT_LOG.md` |
| `KnowledgeGraph/` | 知识图谱子系统的设计与实现 | `DESIGN.md`、`IMPLEMENTATION.md` |
| `product-flow/` | 产品流程 | `workflow.md`、`index.html`（流程可视化） |
| `saas/` | SaaS 相关（缓存设计、PRD） | `PRD.md`、`caching-design.md`、`caching-discussion-log.md`；`training/` 子目录 |
| `tasks/` | 具体开发任务文档 | `backend-external-links.md`、`frontend-remove-ext-link-parsing.md` |
| `test/` | 测试计划/说明 | `testing-plan-edit-switch.md`、`testing-plan-paste-markdown.md`、`dependency-upgrade-fastapi.md` |
| `archive/` | 归档文档（不再活跃） | `FRONTEND_INTERACTION_FEEDBACK.md` |

---

## 顶层核心文档索引

| 文档 | 一句话说明 |
|------|-----------|
| [`DEV.md`](./DEV.md) | 开发指南：环境、测试、规范 |
| [`FRONTEND.md`](./FRONTEND.md) | 前端 API 契约（后端 REST 接口定义）——前端对接的权威 |
| [`FRONTEND_ARCHITECTURE.md`](./FRONTEND_ARCHITECTURE.md) | 前端架构设计（目录结构、状态、路由） |
| [`FRONTEND_STATUS.md`](./FRONTEND_STATUS.md) | 前端实现状态追踪 |
| [`DESKTOP_APP.md`](./DESKTOP_APP.md) | 桌面 App 打包：体积构成、构建链、发布规范 |
| [`DESIGN.md`](./DESIGN.md) | 总体设计说明 |
| [`AI-SETUP.md`](./AI-SETUP.md) | AI 协作配置（Claude Code / CodeBuddy MCP 接入） |
| [`TASK-card-hover-rename.md`](./TASK-card-hover-rename.md) | 任务：卡片 hover rename 相关 |
| [`TASK-frontend-test-speed.md`](./TASK-frontend-test-speed.md) | 任务：前端测试提速 |

---

## 目录与入库约定

- **入库存档**：`docs/` 下的 `.md`（SPEC、DEV、FRONTEND、测试计划等）都随项目入库版本化。
- **不入库**（.gitignore 忽略）：`docs/designs/**/export/*.svg`（生成视觉稿）、`docs/designs/**/screenshots/*.png`（人审参考）。它们由前端设计专家产生，仅作实现参考，不纳入版本控制。
- **设计稿路径**：`docs/designs/<功能>/`，SVG 在 `export/`、PNG 在 `screenshots/`、语义规范在 `<功能>/SPEC.md`（见 `.codebuddy/agents/MK 前端设计专家.md`）。

---

## 版本号与发布

- 系统版本号唯一来源：`backend/__version__.py` 的 `__version__`
- 发布流程详见 [`DESKTOP_APP.md`](./DESKTOP_APP.md)
