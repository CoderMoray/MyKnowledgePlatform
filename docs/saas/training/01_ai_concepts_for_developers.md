# 01 · AI 概念速成（用软件类比讲清楚）

> 面向**会写代码、没 AI 背景**的实施人员。每个概念都先给"它相当于你熟悉的什么"，再看正经定义和落地要点。

---

## 1.1 LLM = 一个无状态函数

```
response = llm(messages) -> { text, usage }
```

- **相当于**：你调一个 RPC/HTTP 接口 `f(request) -> response`。无状态、单次调用、不记得上次。
- **`messages`**：一个数组，每个元素是 `{role: "user"|"assistant"|"system", content: "..."}`。这就是"对话"的载体。
- **`usage`**：本次调用消耗了多少 token（计费单位）。
- **关键认知**：模型**没有 session、没有记忆**。所谓"多轮对话"是客户端把历史重新塞进 `messages` 再发一次（详见 `05`）。

## 1.2 Token = 计费与计数的最小单位

- **相当于**：API 按"字符数/请求次数"计费的最小粒度。
- **数量感**：中文约 **1 个汉字 ≈ 1 token**；英文约 1 词 ≈ 1.3 token。
- **为什么重要**：所有计费、上下文窗口限制、缓存收益都按 token 算，不是按"字"或"次"。

## 1.3 上下文窗口（Context Window）= 单次调用的输入+输出上限

- **相当于**：一个请求的 body 大小限制（比如 128K token）。超出就报错或截断。
- 我们的重型 KB（10 万 token）很容易顶满窗口 → 引出"上下文压缩"（见 `05`）。

## 1.4 Agent = 一个"循环调工具"的脚本

普通 `llm()` 只聊天；**Agent** 会：

```
loop:
    out = llm(messages + 工具列表)
    if out 想调工具(如 read_file):
        执行工具 -> 结果塞回 messages
        continue   # 再调一次 llm
    else:
        return out  # 最终回答
```

- **相当于**：你写的"根据模型返回决定调哪个函数"的 orchestration 脚本。
- **工具（tool/function calling）**：模型返回"我要调 `read_file('/a.md')`"，你本地执行，把结果拼回再问模型。opencode 自带 `glob/grep/read` 工具，正好在我们的 Markdown KB 上干活。

## 1.5 Session = 客户端制造的"有状态"假象

- **相当于**：HTTP 无状态，session 靠客户端每次重发 cookie/完整上下文实现。
- 模型侧无 session；agent 层（opencode）本地持有 transcript，每轮重发 `System + 历史 + 工具结果 + 当前消息`。

## 1.6 Prompt Caching = 内容寻址的 memoization

- **相当于**：你对函数输入做 **memoize**，但 key 不是参数名而是"前缀 token 序列的哈希"。相同前缀命中缓存，只算一次、且打折。
- **谁控制**：厂商提供能力（KV 缓存），**你用 `cache_control` 断点指定"缓存到这"**（详见 `05`）。

## 1.7 RAG = "先检索、再拼进 prompt 再问"

- **相当于**：你写代码时先 `grep` 出相关片段，再基于片段写逻辑；只不过这里把片段拼进 `messages` 再发给模型。
- 我们**暂不用向量库/embedding**，直接用 opencode 的 `glob/grep/read` 关键字检索 KB（够用、零额外工程）。

## 1.8 其他常见词速查

| 词 | 一句话 |
|---|---|
| 流式输出 | SSE / chunked response，边生成边返回 |
| 温度 temperature | 随机性参数，0=确定性，高=发散 |
| top_p | 核采样，控制候选词范围 |
| Embedding / 向量库 | 把文本转成向量做语义检索（本期不用） |
| Fine-tune / 蒸馏 | 在基模型上训练专属模型（未来，托管第三方） |
| 网关 Gateway | 统一入口，转发+鉴权+计量（我们的 LiteLLM） |

## 1.9 一句话总结

> LLM 是个**无状态函数**；**Agent** 是循环调工具的脚本；**缓存**是前缀 memoization；**session** 是重发历史；**网关** 是统一接口的 API 代理。这些你全都在写普通软件时见过。

→ 下一节：`02_architecture_layers.md` 看这些概念在我们的系统里各归谁管。
