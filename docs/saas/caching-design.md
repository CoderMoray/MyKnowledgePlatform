# 缓存机制设计文档 (Caching Design Spec)

> 定位：本文是**工程实现规则**，给封装 harness / 网关的开发者照着落地。
> 概念入门见 `training/05_context_and_caching.md`；业务视角见 `PRD.md`。
> 适用范围：仅 **prompt caching / 前缀缓存**（厂商 API 特性），不涉及响应缓存、语义缓存。

---

## 1. 目标与范围

- **目标**：在 token 计费下，通过前缀缓存降低重复上下文（Agent Prompt + KB）的推理成本。
- **范围**：仅限请求体的前缀缓存；缓存的"计算"在厂商侧，本系统只负责**构造稳定前缀 + 声明断点**。
- **职责分层**：
  - **harness（opencode 封装）**：构造 messages、在正确位置注入断点、维护 recency_index、执行 compaction。
  - **LiteLLM 网关**：透传 `cache_control` 给厂商，记录 cache 写入/命中 token 用于计费。
  - **厂商**：执行前缀缓存（KV 存储、折扣计价、TTL 驱逐）。

---

## 2. 分层模型 (T0–T3)

| 层级 | 内容 | 稳定性 | 是否缓存 | 断点 | 说明 |
|---|---|---|---|---|---|
| **T0** | System + 全局索引 + Agent 提示词 + 工具描述 | 全用户相同，会话内不变 | ✅ 缓存（断点①） | ① 在 T0 末尾 | 体量小（~3K token），跨用户共享 1 条 |
| **T1** | 当前活跃子项目 KB 全文（pin） | 每用户/租户不同，仅**切换子项目**时变 | ✅ 缓存（断点②） | ② 在 T1 末尾 | 重量级（10K–100K+ token），每 KB 变体 1 条 |
| **T2** | 近期检索片段 + 对话历史 | 每轮变化 | ❌ 不缓存 | 断点②之后 | 动态检索结果放此处，每轮重新发送 |
| **T3** | 当前用户消息 | 每轮变化 | ❌ 不缓存 | 末尾 | 永不在任何断点之前 |

**铁律**：T2/T3 严禁出现在任何断点之前。

---

## 3. 断点规则（必须）

1. **断点①**置于 T0 末尾、**断点②**置于 T1 末尾。每轮请求都带这两个断点。
2. **显式型厂商**（通义千问 / 智谱 GLM / Anthropic）：在 messages 对应位置注入
   `cache_control: {"type": "ephemeral"}`。单请求最多 4 个断点。
3. **自动型厂商**（DeepSeek / OpenAI）：无需标记，重复前缀自动缓存（≥1024 token 阈值）。
   唯一杠杆 = **保持前缀稳定且够长**。
4. **断点每轮必带**：厂商不记忆你的偏好，每次请求自行声明。
5. **前缀必须位于请求开头**：不能在前缀前插时间戳/用户名/随机串，否则整段缓存失效。

---

## 4. 缓存匹配与隔离语义

- **内容寻址**：缓存键 = 断点前整段 token 序列**逐字节相等**。不是按用户、不是按 key、不是子串匹配。
- **单中央 provider key**：仅作鉴权凭证，不参与缓存寻址。相同前缀跨用户共享 → 最大化命中率。
- **多租户结果**：
  - T0 全用户相同 → **1 条**共享缓存。
  - T1 每 KB 变体不同 → **每变体 1 条**（每用户多轮复用，不跨用户）。
  - 缓存总条目 ≈ `1（共享 T0）+ N（不同 KB 数）`，**不是"用户数 = 缓存数"**。
- **不会乱匹配**：不同 KB 前缀全不等 → 独立条目，互不干扰。近似/子串不会误命中。

---

## 5. 重记触发条件

- 仅当**断点前内容变化**才重记（一次 write）：
  - T0 变（你改了 system prompt）；
  - T1 变（用户**切换子项目**）。
- **T2/T3 高频变化在断点后 → 不触发重记**。
- **重记频率 ≈ 子项目切换次数，不是对话轮次**。
  - 例：20 轮对话、切了 2 次子项目 → 缓存仅重记 2 次（2 次 write），其余 18 轮命中。
- **写入代价**：未命中需重算 + 存 KV；Anthropic 写入价 +25%，DeepSeek/通义按全价或折扣计。
  故 **T1 切换要稀少**（靠"停留晋升"压低）。

---

## 6. 升降级规则（Promotion / Demotion）

> 升级 = 内容从低缓存层移到高缓存层（**T2 → T1**，即"每轮重发不缓存"变为"pin 缓存"）。
> 降级 = 反向，或从 pin 中移除。

### 6.1 recency_index 结构（harness 内存表）

```json
{
  "sub_project_id": {
    "last_access": 1700000000,   // 最近访问时间戳
    "dwell_rounds": 0,           // 连续聚焦轮次
    "mention_count": 0,          // 滑动窗口(最近5轮)内提及次数
    "pinned": false,             // 当前是否在 T1
    "weight": 0.0                // 综合权重(见 6.3)
  }
}
```

### 6.2 升级（T2 → T1）触发条件（满足任一）

- **连续聚焦**：同一子项目 `dwell_rounds ≥ 3`，或累计停留 ≥ 90s。
- **高频提及**：滑动窗口（最近 5 轮）内 `mention_count ≥ 3`。
- **显式锚定**：用户指令"聚焦/切换到 项目X"，或 harness 检测到子项目切换意图。

升级动作：加载该子项目 KB（全文或稳定核心）进 T1，断点②置于其后。= 一次 write（该变体缓存 miss），之后多轮命中。

### 6.3 并发 pin 上限 M

- 同时 pin 在 T1 的子项目数上限 **`M = 3`**（默认，可按上下文预算调）。
- 升级第 M+1 个时，先执行降级（6.4）。

### 6.4 降级（T1 → T2 或移出）触发条件

- **空闲驱逐**：某 T1 块 `now - last_access ≥ T_idle`（默认 **10 min**）→ 取消 pin，降级回 T2（按需重新 grep）；其缓存条目随厂商 TTL（~5–10 min）自然过期。
- **容量驱逐（LRU）**：升级超出 M 时 → 驱逐 `last_access` 最旧的 pin 块。
- **平局裁决**：recency 相同 → 驱逐 `weight` 较低者。`weight = 0.5·freq_norm + 0.3·recency_norm + 0.2·relevance_norm`。

### 6.5 升降级代价与目标

- 每次升级 = 一次 T1 write（缓存 miss，付写入价）。
- 降级不付额外费，仅释放 pin，缓存条目 TTL 后自然清。
- **目标**：通过调 `T_idle` 与 `M`，让升级尽可能"稀有"——把重记次数压到接近"子项目切换次数"。

### 6.6 与 Kimi K3 同构（仅供理解，非实现依赖）

- KDA 压缩旧信息 ≈ 本设计的 recency 压缩；MLA 全局精读 ≈ T1 全文 pin；3:1 配比 ≈ "稳定缓存为主 + 偶尔全量重读"。

---

## 7. 压缩与替换规则

### 7.1 压缩触发

- **T1 总 token 超预算**：`T1_total > BUDGET_T1`（默认 **120K**，预留生成余量于 128K/200K 上下文）。
- **单子项目过大**：某子项目 KB > `BUDGET_PER_SUB`（默认 **60K**）→ 仅压缩该块。
- **防抖**：两次压缩间隔 ≥ 30s，避免抖动。

### 7.2 压缩梯度（按优先级降级）

| 层级 | 内容形态 | 适用 chunk |
|---|---|---|
| **L0 全文** | 原始文本 | 最近引用、权重最高 |
| **L1 摘要** | 单轮 LLM 摘要 | 中相关、较旧 |
| **L2 索引** | 仅 标题+路径+一行描述 | 最不相关/最旧 |

### 7.3 压缩算法（权重排序）

```
recency_weight = 0.5 · freq_norm        // 提及频次归一
               + 0.3 · recency_norm     // 越近越高
               + 0.2 · relevance_norm   // 与当前 query 相关度
```
- 按 `recency_weight` 降序：top X → L0 全文；next Y → L1 摘要；其余 → L2 索引。
- 摘要由一次 compress pass（调模型）生成，结果可缓存复用。

### 7.4 替换规则（T1 容量满时）

策略：**优先压缩保活，其次 LRU 驱逐**。

1. 若待升级子项目仍相关 → 先对最旧 pin 块做压缩（L0→L1/L2）腾出空间，**保留其条目**。
2. 若最旧块已无 relevance → 直接 **LRU 驱逐**（移出 pin）。
3. **T0 永不替换**（共享稳定）。T2/T3 每轮重生，无替换策略。

> 替换与压缩均改变 T1 内容 → 触发断点②缓存重写（一次 write），净收益为正（上下文变小，后续每轮更便宜，且可重新 pin）。

### 7.5 与缓存交互

- 升级 / 压缩 / 替换均改变断点②前缀 → 该块缓存失效、重写一次（付出一次 write）。
- 压缩后 T1 变小 → 后续每轮更便宜，且可重新 pin 成缓存块②。
- **TTL 会吃掉低频红利**：缓存空闲 ~5–10 分钟被驱逐；用户停顿超 TTL，那块缓存重付（见 §8）。

---

## 8. TTL 与收益现实

- 前缀缓存空闲 **~5–10 分钟**驱逐（短期）。
- 须在 TTL 内**多次复用**才回本（写入成本被摊薄）。
- **收益主体 = 同一用户多轮（TTL 内），不是并发人数**。
- **测试期（7–8 人低频，<0.5 req/min）缓存红利很小**——但架构现在就该埋好，上线高频才显现。
- **对账**：LiteLLM 记录 cache 写入/命中 token；每月用厂商真实账单核对单价漂移（留 10–20% buffer）。

---

## 9. Provider 实测参数（参考）

| 厂商 | 类型 | 最小缓存 token | TTL | 命中价 | 备注 |
|---|---|---|---|---|---|
| DeepSeek | 自动 | ≥1024 | ~数分钟 | 命中 10%（¥0.1/M vs 标准 ¥1/M） | 约 1.1–1.4 次复用即回本 |
| 通义千问 | 显式 `cache_control` | ≥1024 | 5 min | 命中 20% | 需在 messages 注入断点 |
| 智谱 GLM | 显式 `cache_control` | ≥1024 | 5 min | 命中折扣 | 同上 |
| Anthropic（对标） | 显式 | — | 5 min | 写入 +25% / 命中 10% | 未来接入参考 |
| OpenAI（对标） | 自动前缀 | — | 5–10 min | 命中折扣 | 未来接入参考 |

> 注：单价为社区 `pricing.json` 近似值，以厂商实时账单为准。

---

## 10. 监控

- **读取字段**（按厂商）：
  - OpenAI / 通义 / 智谱：`usage.prompt_tokens_details.cached_tokens`
  - Anthropic：`cache_creation_input_tokens` / `cache_read_input_tokens`
- **指标**：`缓存命中率 = cached_tokens / (cached_tokens + 非缓存 input)`。
- **告警**：命中率骤降 → 检查是否 T1 被塞了动态内容、或前缀前插了变量。

---

## 11. 反模式（必须遵守）

- ❌ 每轮动态检索结果写入 T1 → T1 每轮变 → 每次 write，缓存报废。
- ❌ 前缀前插时间戳/用户名/随机串 → 整段缓存失效。
- ❌ 把 T2/T3 放在断点之前 → 高频变化触发重记。
- ❌ 期望跨用户共享重型 KB 缓存（KB 每用户不同，无法跨用户共享）。
- ✅ T1 = 稳定 pin 块；动态检索进 T2；前缀从头稳定；断点每轮带。

---

## 12. 实施清单（harness）

- [ ] 构造 messages 顺序：`T0 → 断点① → T1 → 断点② → T2 → T3`
- [ ] 注入 `cache_control`（通义/智谱）或保持前缀稳定（DeepSeek）
- [ ] 实现 `recency_index` 表 + **升级规则**（dwell≥3 或 5轮内提及≥3 或显式锚定 → T2→T1 pin）
- [ ] 实现 **降级规则**（空闲 T_idle=10min 驱逐 / 超 M=3 容量 LRU 驱逐 / 平局按 weight）
- [ ] 实现 **压缩规则**（BUDGET_T1=120K、BUDGET_PER_SUB=60K 触发；L0/L1/L2 梯度 + recency_weight 排序；防抖 30s）
- [ ] 实现 **替换规则**（优先压缩保活，其次 LRU 驱逐；T0 永不替换）
- [ ] 读 `cached_tokens` 做命中率监控 + 告警
- [ ] LiteLLM 配置透传 `cache_control` 并记录 spend
- [ ] 测试期验证：切换子项目 → 观察 write 次数；多轮连问 → 观察 hit 次数

---

## 13. 与 PRD / 培训的关系

- 业务视角 / 收费模型 → `PRD.md`
- 概念入门（无 AI 背景同事）→ `training/05_context_and_caching.md`
- **工程实现规则（本文）→ `caching-design.md`**

---

## 14. 补充方案（待验证，未实施）：headroom 上下文压缩层

> 定位：作为 T0–T3 缓存 + L0/L1/L2 压缩的**外部补充**（可选组件，非核心依赖）。
> 评估日期：2026-08-06。结论：**契合但暂不实施**，先记录待验证。

### 14.1 是什么

- 本地运行的 **LLM 上下文压缩层**（`chopratejas/headroom`，Apache-2.0，实测版 0.33.0）。
- 在内容发往 LLM **之前**压缩：工具输出、日志、文件、RAG 片段、对话历史。压缩全在本地，不调 LLM，数据不出域。
- 核心机制：**CacheAligner**（只压缩最新轮、稳定前缀冻结）、**ContentRouter**（JSON/代码/日志/表格/文本分类型压缩器）、**Context Manager**（滚动窗口裁剪）、**CCR 可逆压缩**（原文存本地 SQLite `~/.headroom/ccr_store.db`，默认 TTL 1800s，带引用句柄可按需取回）。

### 14.2 与本文方案的契合点

| 本文设计 | headroom 对应 | 关系 |
|---|---|---|
| T0–T3 分层 + 断点（稳定前缀、易变靠后） | CacheAligner 冻结历史前缀、只压 live zone | **同构**，理念一致，不冲突 |
| L1 摘要 / L2 索引（§7，"用一次模型调用做摘要"） | 本地压缩器（规则 + ONNX 小模型，零模型调用） | 可**替代 LLM 摘要**，免费 |
| 工具结果进 T2（grep/read 大块输出） | 官方主打场景："MCP tool outputs are the PERFECT use case" | 高契合（表格/JSON 压缩省 90%+） |
| 数据不出域 / 零模型成本 | 压缩全本地、仅 LLM 请求照常转发 | 符合约束 |

### 14.3 三种接入方式（对本项目）

| 方式 | 说明 | 本项目适用性 |
|---|---|---|
| **Library** | `compress_tool_result(content, tool_name, tool_args, user_query)` 直接调 | ✅ 首选（集成到读类 MCP 工具或 harness 层） |
| **Proxy** | 本地代理，`ANTHROPIC_BASE_URL` 指向 8787，对 Claude Code 透明 | ⚠️ 面向 Anthropic 生态；本项目走国内厂商需实测 litellm 链路 |
| **MCP Server** | 挂 `headroom_compress` / `headroom_retrieve` 工具，AI 主动调 | ✅ 可作 retrieve 兜底 |

> 注：`headroom install` 的 ToolTarget 原生支持 **opencode**（另支持 claude/codex/cursor/aider/copilot），可 `headroom wrap opencode` 接入 SaaS 方案的 opencode harness。

### 14.4 推荐集成形态（若未来实施）

1. **读类 MCP 工具加 `compressed: bool = False` 参数**（默认 False，向后兼容）：`nav__get_document(path, compressed=True)` 返回压缩结果。
2. **新增 retrieve 工具**：按引用句柄取回原文（CCR 兜底），实现"惰性加载"而非"有损压缩"。
3. **按工具配 profile**（headroom 原生 `MCPToolProfile`）：
   - `nav__list_dir`（表格）→ 高压缩（收益最大，省 90%+）
   - `nav__find`（结构化 JSON 搜索结果，含 query/hint/results/total）→ 低阈值压缩（结构化字段不宜高压缩，`matched_in`/`score` 是复查与排序依据，压缩易失真）
   - `nav__get_document` / `nav__read_readme`（文档全文）→ 低阈值（`min_tokens_to_compress≈500`）或压缩 + 强提示 retrieve
4. **修改前必须取回原文**：agent 基于压缩版直接 `write__update_document` 有改写风险，压缩返回需提示"修改前先 retrieve"。

### 14.5 关键限制与风险

- **M 系列 Mac 已知 bug**（issue #2742，0.33.0）：kompress 在 Apple Silicon 上压缩率可能≈0%，实施前必须先实测。
- **依赖重**：`headroom-ai` 带 onnxruntime + litellm + tiktoken；274MB 模型（kompress-v2-base）**首次运行时从 HuggingFace 下载**（非安装自带，存 `~/.cache/huggingface/`），全功能共约 400–800MB 磁盘。
- **常驻开销**：proxy 模式常驻进程约 300–700MB 内存；压缩瞬间 CPU 突刺 P50~12ms / P90~259ms / P99 可达 4s。
- **压缩率现实**：官方 60–95% 为最佳场景；生产实测中位数仅 ~4.8%。需在真实 KB + 中文 markdown 上 A/B 验证。
- **依赖位置**：只能作为 optional extra（如 `myknowledge[headroom]`），不进核心 `pyproject.toml` 依赖。

### 14.6 待验证清单（实施前）

- [ ] M 系列 Mac 真实压缩率（中文 markdown 文档 + `nav__list_dir` 表格两类样本）
- [ ] `compress_tool_result` 对中文 KB 文档的精度影响（压缩后能否准确回答问题）
- [ ] 国内厂商链路：headroom Library 模式 → 压缩 → DeepSeek/智谱/通义 的端到端正确性
- [ ] 压缩 + CCR 取回（retrieve）在知识问答场景的收益/成本净评估（对 7–8 人低频是否划算）
- [ ] 与 LiteLLM 网关共存时的依赖版本兼容性（headroom 依赖 litellm）
