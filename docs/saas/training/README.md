# 培训导航 · MyKnowledge 知识库 Agent

> **读者画像**：本项目实施人员，**具备软件开发能力，但没有 AI/LLM 背景**。
> **本文档目的**：让你在不啃 AI 论文的前提下，能动手实现"知识库 Agent"的 SaaS 化。
> **核心策略**：所有 AI 概念都用**你已知的软件概念做类比**（无状态函数、memoization、API 网关、scoped token……）。每张概念都标了"相当于你熟悉的什么"。

---

## 你应该按这个顺序读

| 顺序 | 文件 | 读完你能回答 | 预计耗时 |
|---|---|---|---|
| 0 | **本 README** | 整体地图、该先学什么 | 3 min |
| 1 | `01_ai_concepts_for_developers.md` | "LLM/Agent/缓存/token 到底是个啥"——用软件类比 | 20 min |
| 2 | `02_architecture_layers.md` | "云、网关、harness 各管什么"——职责边界 | 15 min |
| 3 | `03_litellm_gateway.md` | "怎么用 LiteLLM 统一接国内模型 + 发虚拟 Key" | 25 min |
| 4 | `04_opencode_harness.md` | "怎么把 opencode 藏进安装包当 agent 用" | 25 min |
| 5 | `05_context_and_caching.md` | "多轮上下文和缓存到底怎么 work、谁控制" | 30 min |
| 6 | `06_billing_and_markup.md` | "怎么收钱、token plan 怎么计费、抽多少" | 20 min |

## 各模块一句话

- **01**：把 LLM 想成一个"无状态函数"，把 Agent 想成"循环调工具的脚本"，把缓存想成"内容寻址的 memoization"。
- **02**：三件套——**云 SaaS**（账号/存储/钱）、**LiteLLM 网关**（路由/计费，无状态）、**opencode harness**（agent 层：上下文/记忆/工具）。
- **03**：LiteLLM 是开源、自托管、**不按调用收费**的 API 网关；你用它的管理员接口给每用户发"带预算的虚拟 Key"。
- **04**：把 opencode 打包进客户端，用 serve 模式当本地 agent 运行时；session 隔离、工具白名单锁死只许读 KB。
- **05**：模型 API 无状态，多轮靠"重发历史"；缓存是厂商特性，你用 `cache_control` 断点指定缓存哪段；重型 KB 用 recency 压缩。
- **06**：不做厂商个人套餐转售（违规），走按量 Token Plan；用户付钱进你钱包，你按量付厂商 + 加 markup；虚拟 Key 即预算。

## 上手前你需要装好的环境

- Node/Python 基础开发环境（你已有）
- 一个国内模型开放平台账号（DeepSeek / 智谱 / 通义，任选，拿 API Key）
- `opencode` 或 `mimo` 二进制（测试用，本地跑）
- `litellm`（`pip install litellm` 自托管网关）

> 不确定某概念时，先回 `01` 查类比，再回对应模块看落地。
