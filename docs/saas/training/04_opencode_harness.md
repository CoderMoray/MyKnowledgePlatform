# 04 · opencode harness 封装

> 本文讲怎么把 `opencode`（或其 fork `mimo`）**藏进你的安装包**，当本地 agent 运行时用。前提：已读 `01`/`02`。

---

## 4.1 为什么是 opencode / mimo

- **opencode / mimo** 是可本地运行的 CLI Agent，自带文件工具 `glob/grep/read`——正好在你的 Markdown KB 上检索、阅读、总结，**不需要额外向量库/RAG 层**。
- **mimo 是 opencode 的 fork，MIT 协议**：明确允许 fork/修改/再分发/商用，打包最省心。
- **封装选 opencode 而非 mimo 的原因**：mimo 的持久记忆 `.mimo/memory.json` 写在 **cwd（即你的知识库目录）**，会污染用户 KB；opencode 记忆存用户级目录，不污染 cwd。测试期建议用 opencode。

## 4.2 两种运行模式

| 模式 | 命令 | 适合 | 生命周期管理 |
|---|---|---|---|
| **A · 本地 serve（推荐）** | `opencode serve --port 4096 --cwd <KB>` | 体验好、流式、低延迟 | 应用启动起、退出 kill |
| **B · subprocess JSON** | `opencode run "<q>" --format json ...` | 最简单、无状态 | 用完即走，无需回收 |

**模式 A 伪代码（Electron/Tauri 侧）**：

```js
import { spawn } from 'child_process';
const KB = userData('knowledge');
let proc; const PORT = 4096;

export async function startLLM() {
  proc = spawn('opencode', ['serve','--port',PORT,'--cwd',KB,
    '--model','opencode/glm-5-free'], { stdio:'ignore' });
  await waitPort(PORT);                 // 等 serve 起来
}
export function stopLLM(){ proc?.kill(); }   // 应用退出清理
```

用户**完全看不到终端**，只看到你的 UI。

## 4.3 打包进安装包

- **Electron**：`extraResources` 把对应平台（mac/win/linux）的 opencode 二进制塞进去。
- **Tauri**：`externalBin` / sidecar。
- 体积几十 MB 可接受；前端是你的 React/Alpine 组件，不渲染 opencode 的 TUI。

## 4.4 Session 隔离（防止用户会话交叉）

- **每用户独立进程/实例**：避免全局工具状态（cwd/glob）互相污染。
- **`--session <uid>`**：opencode 按 session 隔离上下文，多轮连贯且不串。
- 测试期若用"每请求独立 run"（模式 B），天然隔离、无需回收；代价是每次冷启动 2–10s，低频可接受。

## 4.5 工具白名单（安全锁死）

只许 agent 读 KB，**禁止改文件、禁止跑 bash**：

```bash
opencode run "<q>" --cwd <KB> --session <uid> \
  --allowedTools view,glob,grep,ls \
  --format json
```

> 这是防止 agent 误改/破坏用户知识库的关键一道。

## 4.6 免费 → 付费：切换 provider

付费后，把客户端 `opencode.json` 的 provider 切到你的网关（带用户虚拟 Key），**用户无感**：

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

背后：opencode 只是本地运行时 + 工具层，**模型供应商可换**。你卖的是"切换那一下的套餐"。

## 4.7 实施清单

- [ ] 本地装 opencode，验证 `serve` 与 `run` 两种模式
- [ ] 用 Electron `extraResources` / Tauri `externalBin` 打包二进制
- [ ] 加 `--session <uid>` + `--allowedTools view,glob,grep,ls`
- [ ] 封装 start/stop，应用退出清理
- [ ] 实现"升级后写 opencode.json 切网关"的推送逻辑
- [ ] 确认 mimo 记忆污染问题（用 opencode 或重定向记忆路径）

→ 下一节：`05_context_and_caching.md` 讲上下文与缓存（harness 最该显式处理的部分）。
