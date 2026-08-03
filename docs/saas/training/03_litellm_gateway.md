# 03 · LiteLLM 网关实操

> 本文给你能跑起来的配置与接口骨架。**前提**：你已读完 `01`（知道 LLM 是无状态函数）、`02`（知道网关只管路由+计费）。

---

## 3.1 先澄清两个常见误解

| 误解 | 真相 |
|---|---|
| "LiteLLM 很贵" | 开源 **MIT**、**自托管**，就跑个 Python 进程（~400MB、CPU 即可）。**不按调用收费**，不是 OpenRouter 那种加价 SaaS。贵的是模型费，付给厂商的。 |
| "我要预付费" | 对软件本身**不预付费**。对接国内模型可在平台留 ¥100 按量扣，或用 **BYOK**（用户填自己 Key，你零垫付）。 |

## 3.2 它解决了什么痛点

- **统一接口**：100+ 模型走同一 OpenAI 兼容 endpoint，各家协议差异它翻译 → 你不用给每个模型写适配。
- **虚拟 Key**：给每用户发一把 Key，带 `budget`（预算）+ `rate_limit` + `model_access`。
- **Spend Tracking**：按 Key/用户实时计量 token 与花费。
- **预算硬停**：超预算直接返 **429**，绝不爆账单。

## 3.3 最小 `config.yaml`（仅国内按量 API）

```yaml
model_list:
  - model_name: deepseek-chat
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: os.environ/DEEPSEEK_KEY
  - model_name: zhipu-glm
    litellm_params:
      model: zhipu/glm-4-flash   # 免费档可先用
      api_key: os.environ/ZHIPU_KEY
  - model_name: qwen-plus
    litellm_params:
      model: qwen/qwen-plus
      api_key: os.environ/QWEN_KEY

litellm_settings:
  # 让网关记录缓存命中 token，便于计费/监控
  cache: false            # 注意：这是 LiteLLM 自己的响应缓存，和厂商 prefix cache 是两回事
  telemetry: false
```

启动：`litellm --config config.yaml --port 4000`

## 3.4 虚拟 Key：注册与升级（后端调管理员接口）

```python
import httpx
ADMIN = "sk-your-litellm-master-key"   # 你自己的主密钥，绝不发给客户端

# 用户注册/升级时，发一把带预算的虚拟 Key
r = httpx.post("http://localhost:4000/v1/key/generate",
    headers={"Authorization": f"Bearer {ADMIN}"},
    json={
        "user_id": "user_123",
        "max_budget": 30.0,            # 本月预算上限（元）
        "budget_duration": "monthly",
        "models": ["deepseek-chat", "zhipu-glm", "qwen-plus"],
        "rpm_limit": 60,
    })
virtual_key = r.json()["key"]         # 推送到客户端 opencode.json
```

- **免费版**：注册即发低/零预算 Key。
- **升级/补充包**：调 `/key/update` 调高 `max_budget`，或新发一把。
- 开 1 个和开 1 万个同成本（循环调一次 API）。

## 3.5 读取花费 → 扣钱包（实时计费）

```python
# 用 LiteLLM 记录的"真实厂商成本"作基准
spend = httpx.get(f"http://localhost:4000/v1/key/info?key={virtual_key}",
                  headers={"Authorization": f"Bearer {ADMIN}"}).json()
real_cost = spend["spend"]             # 厂商真实花费（元）
user_wallet -= real_cost * MARKUP     # 你的加价
```

> 预算耗尽时网关直接返 429，用户请求被拦，**不会超额**。这是双保险的第二道（第一道是你的钱包余额）。

## 3.6 cache 透传

LiteLLM **原样转发**请求里的 `cache_control` 标记给厂商（见 `05`）。你不用在网关做任何缓存逻辑，只需确认 harness 发出的请求带了断点。

## 3.7 实施清单

- [ ] `pip install litellm`，写 `config.yaml`（仅国内 provider）
- [ ] 起服务，用 curl 验通一个模型
- [ ] 调 `/key/generate` 发测试虚拟 Key
- [ ] 后端接 `/key/info` 读 spend → 扣钱包
- [ ] 设 `max_budget` + 429 拦截确认生效
- [ ] 确认 `cache_control` 能透传到厂商（用 `usage.prompt_tokens_details.cached_tokens` 验证）

→ 下一节：`04_opencode_harness.md` 看 agent 层怎么封装。
