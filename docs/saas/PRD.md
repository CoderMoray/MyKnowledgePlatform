# PRD：MyKnowledge 知识库 Agent 的 SaaS 化方案

> **文档性质**：产品需求文档（PRD）
> **双读者设计**：第 1–6 节面向业务/产品/决策（关注"为什么、做什么、赚什么"）；第 7–11 节面向技术/架构/开发（关注"怎么做、边界在哪"）。第 12 名词表供双方查阅。
> **关联文档**：技术实施所需的背景知识见 `training/` 目录（面向无 AI 背景的开发者）。

---

## 1. 背景与问题

- MyKnowledge 目前是一套**纯 Markdown 存储引擎**的知识管理平台（本地/云端存储知识，前端做编辑与检索）。
- 我们希望**嵌入 LLM 能力**，做一个"项目知识管理 Agent"：用户用自然语言在自有知识库上提问、检索、总结、跨子项目追问。
- **核心约束**：
  1. 现阶段**不想花钱**（不买算力集群、不预付大额模型费）；
  2. 处于**测试期**，约 **7–8 人**使用，人均日交互 **30–50 次**，低频；
  3. 未来要做收费（Freemium + 模型代币），但**不可能自建算力集群**；
  4. 模型调用**只用国内厂商**（数据不出境、合规、价格低）。

## 2. 产品目标与非目标

**目标**
- 以**零/极低运营成本**验证"知识库 Agent"的产品假设；
- 跑通"软件免费引流 + 模型按 token 持续收费"的商业模式；
- 设计一个**可水平扩展、合规、易计费**的 LLM 接入架构。

**非目标（本期不做）**
- 不自建模型、不买 GPU 集群；
- 不做跨企业的复杂多租户隔离（测试期单组织内 7–8 人）；
- 不追求自研 RAG/向量库（先用 opencode 的文件检索能力）。

## 3. 用户与场景

**测试期用户画像**
- 同一组织内的项目成员，使用自有项目知识库；
- 会在**多个子项目之间做知识跳跃式提问**（例如先看 A 子项目的架构，再跳到 B 子项目问接口）；
- 非重度 AI 用户，交互频次低。

**典型场景**
| 场景 | 描述 |
|---|---|
| 知识问答 | "在知识库里找出关于鉴权流程的所有内容并总结" |
| 跨子项目追踪 | "A 子项目和 B 子项目里都提到了 `TokenService`，它们的实现差异是什么？" |
| 文档生成 | "根据知识库里的设计文档，生成一份接口说明" |

## 4. 解决方案概述（一页纸）

采用 **Local-First（本地优先）+ 瘦云** 架构：

- **LLM 运行时下沉到用户机器**：把 `opencode`（或其 fork `mimo`）打包进客户端安装包，用户在本地调用模型。
- **云只做它本该做的事**：账号管理 + 知识云存储（Markdown 同步）+ 计费钱包。
- **模型供应可插拔**：免费期用 opencode 内置免费模型；付费后用你自建的 LiteLLM 网关（统一国内厂商接口）。

```
┌──────────── 用户机器（本地优先）────────────┐
│  你的产品 UI (封装，不暴露终端)              │
│     └─ opencode / mimo harness (agent 层)    │
│           ├─ 上下文/记忆/工具(glob,grep,read)│
│           └─ 调模型 (免费模型 或 你的网关)    │
└───────────────────┬────────────────────────┘
                    │ 仅同步 KB + 账号/计费
┌───────────────────▼────────────────────────┐
│  你的云端 SaaS                              │
│  账号 · Markdown 知识库存储 · 钱包/套餐     │
│     └─ LiteLLM 网关 (国内厂商统一接口/计费) │
└────────────────────────────────────────────┘
```

> 为什么不是"云上挂一个 opencode 常驻"？见第 9 节决策 D1。

## 5. 商业模式与定价

**分层（Freemium + 模型代币）**

| 层级 | 包含 | 你的成本 | 作用 |
|---|---|---|---|
| 免费版 | 软件 + 限免模型（opencode 免费 / 本地 Ollama）+ 用量阉割（如 50 次/月） | ≈ 0 | C 端口碑、拉新 |
| Pro 套餐 | 软件高级功能 + 基础 token 池（如 100 万 token/月） | 仅套餐内实际用量 | 主收入 |
| 补充包 | 超额 token 包（按量买，类似流量包） | 按实际用量 | 高活用户增收 |
| 未来专属模型 | 高级套餐项（托管第三方推理） | 第三方托管费 | 溢价 |

**三个零成本杠杆（让免费版不烧钱）**
1. 默认走 opencode **免费模型**（你零成本，有限额）；
2. 或引导**本地 Ollama**（用户自己算力，你零成本）；
3. 免费层**严格用量上限** + 超额引导升级。

**Unit Economics**：用户越多，你的边际成本只有"账号 + 存储带宽"，**没有推理费**（推理费要么用户本地承担，要么用户买 token 包时你按量付厂商并加 markup）。

## 6. 关键商业结论（已论证）

- **软件 Freemium 引流，模型按 token 持续收钱**——对标 CodeBuddy"一个包包含基本所有模型"的套路。
- **Token Plan（开放平台按量 API）优于厂商个人 Coding Plan**：Coding Plan 的 TOS 禁多用户共享/商用、lump sum + 滚动窗口会塌、无法分用户计量。Token Plan 原生为多租户设计。
- **抽成（markup）行业惯例 10%–50%**；经济型国内模型（DeepSeek/通义/智谱）因绝对值极小可加 2x–3x，用户无感、你毛利高。
- **资金流**：用户付钱进你的 SaaS 钱包 → 你**统一持有少数几个 Provider 中央账户**按量扣厂商 → 每用户只发一把**虚拟 Key**（预算上限+计量标签），跨所有允许模型、预算共享。
- **计费可实时按真实费用**：LiteLLM 每次调用按"模型 × input/output token"算真实花费 → 后端读 spend → 钱包扣"真实花费 × markup"；预算耗尽网关硬返 429，绝不爆账单。

## 7. 功能需求（FR）

| 编号 | 功能 | 业务描述 | 验收标准 | 优先级 |
|---|---|---|---|---|
| FR-1 | 本地 LLM 运行时 | 安装包内置 opencode，用户无感调用 | 安装后首次启动能本地问答，不暴露终端 | P0 |
| FR-2 | 账号体系 | 注册/登录，云同步知识库 | 多端登录，Markdown 知识库可同步 | P0 |
| FR-3 | 免费模型问答 | 测试期用 opencode 免费模型 | 7–8 人低频可用，零成本 | P0 |
| FR-4 | 知识库检索问答 | 在用户 KB 上 glob/grep/read 检索后回答 | 能跨子项目给出带出处回答 | P0 |
| FR-5 | 套餐与钱包 | 免费/Pro/补充包，钱包余额 | 能充值、升级、查余额 | P1 |
| FR-6 | 虚拟 Key 开通 | 升级后自动发 Key 并写入客户端 | 升级成功即切换网关，无感 | P1 |
| FR-7 | 用量计量与限流 | 按用户实时计量、超预算拦截 | 预算耗尽返 429，不超额 | P1 |
| FR-8 | 上下文/记忆管理 | 多轮连贯、跨会话记忆 | 多轮追问不丢上下文 | P1 |
| FR-9 | 缓存优化（harness） | T0–T3 分层前缀 + 压缩 | 重型 KB 多轮成本显著下降 | P2 |
| FR-10 | 国内多模型网关 | 仅接国内厂商，统一接口 | 一键切换 DeepSeek/智谱/通义 | P1 |
| FR-11 | BYOK 选项 | 用户填自己 Key，你零垫付 | 用户自付模型费，你收订阅 | P2 |
| FR-12 | 专属模型（未来） | 托管第三方，经网关暴露 | 用户无感切换 | P3 |

## 8. 技术方案（给开发）

### 8.1 组件与职责

| 组件 | 职责 | 状态/技术 |
|---|---|---|
| 客户端 UI | 封装交互，隐藏 opencode 终端 | 现有前端（Alpine/TipTap） |
| opencode harness | **agent 层**：上下文、记忆、工具、KB 检索、注入 cache 断点 | 打包进安装包 |
| LiteLLM 网关 | **无状态**：路由、计费、预算、多模型统一接口、透传 cache | 自托管，MIT |
| 云端 SaaS | 账号、Markdown 存储、钱包/套餐、虚拟 Key 管理 | 现有 FastAPI 后端 |
| 厂商 Provider | 实际推理（DeepSeek/智谱/通义/Ollama） | 国内开放平台按量 API |

### 8.2 关键接口/配置

- **opencode serve（本地常驻）**：`opencode serve --port 4096 --cwd <KB> --model opencode/glm-5-free`
- **opencode run（每次对话）**：`opencode run <q> --attach http://127.0.0.1:4096 --cwd <KB> --session <uid> --format json --allowedTools view,glob,grep,ls`
- **切付费网关**（客户端 `opencode.json`）：
  ```json
  {
    "provider": {
      "myprovider": {
        "npm": "@ai-sdk/openai-compatible",
        "name": "MyKnowledge AI",
        "options": { "baseURL": "https://your-gateway/v1", "apiKey": "<用户虚拟Key>" },
        "models": { "pro-model": { "name": "Pro 模型" } }
      }
    }
  }
  ```
- **开通虚拟 Key（后端调 LiteLLM）**：
  ```python
  r = httpx.post("https://your-gateway/v1/key/generate",
      headers={"Authorization": f"Bearer {ADMIN}"},
      json={"user_id":"user_123","max_budget":30.0,"budget_duration":"monthly",
            "models":["deepseek/*","zhipu/*","qwen/*"],"rpm_limit":60})
  virtual_key = r.json()["key"]   # 推送到客户端 opencode.json
  ```

### 8.3 上下文与缓存设计（概要，详见 `training/05`）

- 模型 **API 无状态**，多轮连贯靠 agent 层**每轮重发** `System + 历史 + 工具结果 + 当前消息`；
- 缓存是**厂商 API 特性**（前缀 KV 缓存），你通过在请求体放 `cache_control` 断点**指定缓存到哪**；
- 分层前缀 `T0(System) → T1(KB) → T2(历史/检索) → T3(当前消息)`，**稳定块在前、可变块在后**；
- 多租户靠**内容寻址**天然隔离（KB 不同 → 缓存键不同）；
- 重型 KB 用 **recency 压缩**（全文→摘要→索引）控制成本，与 Kimi K3 的 KDA/MLA 同构。

## 9. 关键设计决策与理由

| 编号 | 决策 | 理由 |
|---|---|---|
| D1 | **Local-First 而非云上挂 opencode** | 云上挂：并发/限流/IP/TOS 全压你头上；本地优先：每人自带算力与额度，天然水平扩展，云成本最低 |
| D2 | **Token Plan（按量 API）而非 Coding Plan** | Coding Plan TOS 禁多用户共享/商用、lump sum+滚动窗口会塌、无法分用户计量；Token Plan 原生多租户 |
| D3 | **LiteLLM 自托管网关** | 开源 MIT、不按调用收费；统一 100+ 模型接口、虚拟 Key+预算+计量，维护成本被它吃掉 |
| D4 | **只用国内厂商** | 数据不出境、合规、中文强、价格极低（DeepSeek ¥1–2/百万 token、智谱 GLM-4-Flash 免费） |
| D5 | **opencode 而非 mimo 做封装** | mimo 的 `.mimo/memory.json` 写在 cwd 会污染知识库；opencode 记忆存用户级目录 |
| D6 | **缓存由 agent 层(harness)负责，不归 LiteLLM** | LiteLLM 只路由+计费；缓存断点/前缀稳定性/压缩是 agent 职责 |

## 10. 风险与合规

| 风险 | 说明 | 应对 |
|---|---|---|
| TOS（免费模型） | 免费模型限"试用/轻度使用" | 测试期 7–8 人低频可接受；上线切 Ollama/BYOK |
| 数据出域 | 免费/付费模型经第三方网关 | 测试期可接受；提供 Ollama 本地 / BYOK 零出域选项 |
| IP 限流（免费） | opencode 免费 `*-free` 按出口 IP 限流 | 多免费模型轮询；上线用按量 API（按 Key，IP 无关） |
| 缓存 TTL | 缓存空闲 ~5–10 分钟过期 | 低频期红利小，架构先埋好；高频才显著 |
| 计费漂移 | LiteLLM 单价表可能滞后 | 每月用厂商真实账单对账，留 10–20% buffer |
| mimo 记忆污染 | 目录级 memory.json 写进 KB | 用 opencode 或重定向记忆路径 |

## 11. 实施路线图

- **阶段 1 · 原型验证（现在）**：`opencode` 本地 serve + 免费模型，最快跑通知识库 Agent 体验；验证产品假设。零成本。
- **阶段 2 · 上线收费**：部署 LiteLLM 网关（仅国内按量 API）+ 虚拟 Key/钱包/套餐；免费版零成本、付费版赚 markup。
- **阶段 3 · 专属模型（未来）**：在第三方推理平台托管你的 fine-tune/蒸馏模型，经网关暴露成"你的专属模型"，不建集群也能卖差价。

## 12. 名词表

| 术语 | 含义（一句话） |
|---|---|
| LLM | 大语言模型，这里指模型推理服务 |
| Agent | 能循环调用工具（读文件等）的 AI 程序；本文指 opencode 这一层 |
| Local-First | 计算/推理在用户本地，云只辅助 |
| Token | 模型计费与计数的最小单位（中文约 1 字≈1 token） |
| Token Plan | 厂商开放平台**按量**API，按 token 计费，支持多租户 |
| Coding Plan | 厂商面向**个人开发者**的订阅，TOS 禁商用/多用户共享 |
| LiteLLM | 开源 LLM 网关，统一多模型接口、虚拟 Key、预算、计量 |
| 虚拟 Key | 发给用户的"预算上限+计量标签"，指向你的中央账户 |
| 中央账户 | 你持有的少数几个 Provider 账户，统一按量扣厂商 |
| Markup | 你在厂商成本价之上的加价（你的毛利来源） |
| Prompt Caching | 厂商对稳定请求前缀的 KV 缓存，命中打折 |
| cache_control 断点 | 你在请求里标"缓存到这"，告诉厂商哪段要缓存 |
| Session | 多轮对话的"上下文"，实际靠客户端重发历史制造 |
| opencode / mimo | 可本地运行、带文件工具的 CLI Agent；mimo 是 opencode 的 fork(MIT) |

## 13. 关联文档

- `training/README.md` — 培训导航与学习路径
- `training/01_ai_concepts_for_developers.md` — AI 概念速成（软件类比）
- `training/02_architecture_layers.md` — 架构与职责分层
- `training/03_litellm_gateway.md` — LiteLLM 网关实操
- `training/04_opencode_harness.md` — opencode harness 封装
- `training/05_context_and_caching.md` — 上下文与缓存机制
- `training/06_billing_and_markup.md` — 计费与 markup
