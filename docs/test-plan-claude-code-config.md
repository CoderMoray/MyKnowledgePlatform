# 测试方案：MVP AI 平台（Claude Code / CodeBuddy IDE）MCP / Hooks / Agent 配置写入 + 设置页开关双向联动

> 状态：待 mentor 审阅
> 分支：`test/claude-code-config-verify`
> 覆盖平台：**ClaudeCode + CodeBuddyIDE**（`backend/client_config.py` 注释里写明的 MVP
> 两平台，共用同一套 `configureClient` 增量合并逻辑，仅落盘目录不同）。
> WorkBuddy（代码标 not built）/ Cursor / ClaudeDesktop / Enchante 本方案不覆盖。
> 自动化测试：
> - `tests/test_client_config_verify.py`（后端 / API 层，参数化 ×2 平台，56 例）
> - `tests/frontend/test_client_config_toggle.py`（前端静态 12 例 + 浏览器 12 例 = 6 用例 ×2 平台）

---

## 1. 验证目标

验证并保证「Claude Code」「CodeBuddy IDE」两个 AI 平台在**初始化配置后**：

1. **配置写入正确**：MCP / Hooks / Agent 三种配置分别正确写入平台对应的配置文件。
2. **设置页开关双向控制**：设置页里这三个开关能正确双向控制
   - 开 → 写入配置
   - 关 → 移除配置
   - 再开 → 恢复写入
3. **三个开关互相独立**，互不串扰。

> **重要前提**：Claude Code / CodeBuddy IDE 本身在国内网络下无法联网运行，但这**不影响本任务**——
> 要验的是「配置文件写入」和「设置页开关读写逻辑」，**全部纯本地验证**
> （检查配置文件内容 + 前端逻辑），不需要真的把它们跑起来联网。

---

## 2. 前置调研（读代码得出的现状）

### 2.1 Claude Code 的三种配置分别写到哪、什么格式

单一来源：`backend/AiClientConfig/platforms.json` → `platforms.ClaudeCode`（macOS）：

| kind | 配置文件 | 键 / 形式 | 生成函数 |
|------|----------|-----------|----------|
| **mcp** | `~/.claude.json` | `mcpServers.MyKnowledge` = 一个 stdio server 对象 | `client_config.mcp_entry("ClaudeCode")` |
| **hooks** | `~/.claude/settings.json` | `hooks.PreToolUse[]` 里追加一个 matcher | `client_config.hooks_matcher("ClaudeCode")` |
| **agent** | `~/.claude/agents/MyKnowledge-agent.md` | 一个 Markdown 文件（YAML frontmatter + 正文） | `client_config.agent_content("ClaudeCode")` |

三类落在**三个不同文件**（`~/.claude.json` / `~/.claude/settings.json` / `~/.claude/agents/…`），
天然隔离——这是「三个开关互相独立」的结构性基础。

**MCP 条目**（`~/.claude.json` → `mcpServers.MyKnowledge`）：

```json
{
  "type": "stdio",
  "command": "<python 解释器>",            // 开发/PyPI：sys.executable；桌面 App(frozen)：打包二进制
  "args": ["-m", "backend.cli", "mcp"],   // frozen 时为 ["--mcp"]
  "env": {
    "MYKNOWLEDGE_ROOT": "<知识库根目录>",
    "MYKNOWLEDGE_CLIENT": "ClaudeCode"     // MCP 进程心跳上报时标识调用方
  }
}
```

**Hooks 条目**（`~/.claude/settings.json` → `hooks.PreToolUse[]`）：

```json
{
  "matcher": "Bash|Write|Edit",
  "hooks": [
    { "type": "command",
      "command": "curl -s -X POST http://127.0.0.1:8080/hooks/pre-tool-use -H 'Content-Type: application/json' -d @-" }
  ]
}
```

- Claude Code 把 PreToolUse 的 JSON payload 写到 hook 命令的 **stdin**，`-d @-` 让 curl 从 stdin 读 body。
- matcher 用 `Bash|Write|Edit`（Claude PreToolUse 按工具名匹配，光 `Bash` 会漏掉 Write/Edit）。

**Agent 文件**（`~/.claude/agents/MyKnowledge-agent.md`）：正文取自
`backend/AiClientConfig/agents/MyKnowledge-agent.md`，frontmatter 取自
`agents/frontmatter.json` 里 ClaudeCode 对应 variant（`name` / `description` / `tools` / `model: inherit`）。

### 2.1b CodeBuddy IDE 的三种配置（对照 Claude Code）

单一来源：`backend/AiClientConfig/platforms.json` → `platforms.CodeBuddyIDE`（macOS）。
落盘逻辑、增量合并、`write_kind` / `remove_kind` / `detect_platform` 与 Claude Code **完全同一套代码**，
只是目录与格式细节不同：

| kind | Claude Code | CodeBuddy IDE |
|------|-------------|---------------|
| **mcp** 文件 | `~/.claude.json` | `~/.codebuddy/mcp.json` |
| mcp 键 / 形式 | `mcpServers.MyKnowledge`（stdio；`args=["-m","backend.cli","mcp"]`；`env.MYKNOWLEDGE_CLIENT="ClaudeCode"`） | `mcpServers.MyKnowledge`（同结构；`env.MYKNOWLEDGE_CLIENT="CodeBuddyIDE"`） |
| **hooks** 文件 | `~/.claude/settings.json` | `~/.codebuddy/settings.json` |
| hooks matcher | `"Bash\|Write\|Edit"` | `"*"`（match 所有工具；`hooks.py` 内部放行 MCP 调用，宽 matcher 安全） |
| hooks command | `curl -s -X POST …/hooks/pre-tool-use … -d @-`（curl 读 stdin） | dev：`python3 -m backend.hooks_forward`；桌面 App(frozen)：`"<二进制>" --hooks-forward`（转发脚本读 stdin） |
| **agent** 文件 | `~/.claude/agents/MyKnowledge-agent.md` | `~/.codebuddy/agents/MyKnowledge-agent.md` |
| agent frontmatter | `name` / `description` / `tools` / `model: inherit` | 同上 **+** `agentMode: manual` / `enabled: true` / `enabledAutoRun: true` / `mcpServers: MyKnowledge`（CodeBuddy 专属字段，`frontmatter.json` variant 提供） |

其余一致：三类落在三个不同文件（`~/.codebuddy/mcp.json` / `~/.codebuddy/settings.json` /
`~/.codebuddy/agents/…`）→ 天然隔离；关 = 物理删除（`pop` / 移除 matcher / `unlink`），非停用标记；
只动 MyKnowledge 条目，用户其他配置保留；再开 = 增量合并写回，内容逐字段等价。

设置页三个 CodeBuddy IDE 开关走的前端代码路径与 Claude Code **完全相同**
（`configureClient(plat.key, kind.key)` + `clientStatus`），见 2.2；仅 `plat.key` 不同。

### 2.2 设置页三个开关如何读写这些配置

**读（开关的「开 / 关」视觉态）**：

```
index.html  toggle 的 class
  └─ $store.app.clientStatus(plat.key, kind.key)          // store.js
       └─ return this.clientConfig[platform][kind]         // bool
            └─ this.clientConfig = await api.getClientConfig()   // loadClientConfig()
                 └─ GET /api/client-config
                      └─ client_config.detect_all() → detect_platform("ClaudeCode")
                           ├─ mcp   : "MyKnowledge" in (~/.claude.json).mcpServers
                           ├─ hooks : ~/.claude/settings.json 里有 command 含 /hooks/pre-tool-use 的 matcher
                           └─ agent : ~/.claude/agents/MyKnowledge-agent.md 存在
```

即：**开关状态 = 后端对真实配置文件的检测结果**。不存在「前端自己记状态」。

**写（点击开关）**：

```
index.html  @click="$store.app.configureClient(plat.key, kind.key)"
  └─ store.js  configureClient(platform, kind):
       prev   = !!this.clientConfig[platform][kind]        // 当前检测态
       target = !prev                                      // 取反
       this.clientConfig[platform][kind] = target          // optimistic 先翻
       target ? api.setClientConfig(platform, kind)        // 开：POST /api/client-config/<p>/<k>
              : api.deleteClientConfig(platform, kind)     // 关：DELETE /api/client-config/<p>/<k>
       await this.loadClientConfig()                       // 回读真实态（权威）
       // 失败：loadClientConfig 回弹真实态 + 行内 fallback 文本（5s）
```

- 单写锁 `clientConfiguring`：`if (this.clientConfiguring) return;`——同一时刻只允许一个写入，
  防止并发点击导致的串扰 / 竞态。
- 后端路由：
  - `POST /api/client-config/{platform}/{kind}` → `client_config.write_kind()`
  - `DELETE /api/client-config/{platform}/{kind}` → `client_config.remove_kind()`

### 2.3 「关掉开关」的实际行为：**删除**，不是「保留但停用」

`client_config.remove_kind("ClaudeCode", kind)`：

| kind | 关掉时的动作 | 结果 |
|------|--------------|------|
| mcp | `mcpServers.pop("MyKnowledge")` | 键被**物理删除**（`{"mcpServers": {}}`），无残留停用标记 |
| hooks | 过滤掉 command 命中我们签名的 matcher | matcher 从 `PreToolUse[]` 中**移除** |
| agent | `path.unlink()` | agent 文件**被删除** |

- 只动 MyKnowledge 相关条目——用户自己的其他 `mcpServers` / 其他 hooks matcher / 无关设置项**全部保留**。
- 幂等：对已不存在的条目再执行 remove 也成功（不报错）。
- 没有「保留但停用」这种中间态。

「再次打开」= `write_kind()` 重新增量合并写回，内容与初次写入**等价**。

---

## 3. 三次核心检验

每次都对比「设置页开关状态」（`GET /api/client-config` 的结果，= 开关视觉态数据源）
↔「平台实际配置文件」，两者**必须一致**。**每条检验对 ClaudeCode 与 CodeBuddyIDE
两个平台各跑一遍**（后端测试用 `@pytest.fixture(params=["ClaudeCode","CodeBuddyIDE"])`
参数化，前端浏览器测试用 `@pytest.mark.parametrize("plat", [...])`）。

下表以 Claude Code 为例；CodeBuddy IDE 的对应文件 / 格式见 §2.1b，检验项与断言逻辑相同。

### 检验一：初始化后

| 项 | 预期（ClaudeCode） | 预期（CodeBuddyIDE） |
|----|------|------|
| mcp 文件 | `~/.claude.json` → `mcpServers.MyKnowledge`，`type=stdio`，`args=["-m","backend.cli","mcp"]`，`env.MYKNOWLEDGE_CLIENT="ClaudeCode"` | `~/.codebuddy/mcp.json` → 同结构，`env.MYKNOWLEDGE_CLIENT="CodeBuddyIDE"` |
| hooks 文件 | `~/.claude/settings.json` → `PreToolUse[]` 含 1 个我们的 matcher，`matcher="Bash\|Write\|Edit"`，`curl … -d @-` | `~/.codebuddy/settings.json` → 同，`matcher="*"`，command 含 `hooks_forward` / `--hooks-forward` |
| agent 文件 | `~/.claude/agents/MyKnowledge-agent.md` 存在，`---` frontmatter 开头，正文含 `# MyKnowledge Agent` | `~/.codebuddy/agents/MyKnowledge-agent.md` 存在，额外含 `agentMode:` / `enabled:` / `mcpServers:` frontmatter |
| `GET /api/client-config` → `<平台>` | `{mcp: true, hooks: true, agent: true}` | 同 |
| 设置页三个开关 | 均显示为**开** | 同 |

自动化：`test_client_config_verify.py::TestCheck1_InitializedState`（6 例 ×2 平台）、
`test_client_config_toggle.py::TestConfigToggleBrowser::test_switch_reflects_backend_state`（×2 平台）。

### 检验二：关掉某开关

对 mcp / hooks / agent 分别：`DELETE /api/client-config/<平台>/<kind>`

| 项 | 预期 |
|----|------|
| 对应配置文件 | 该 kind 的 MyKnowledge 条目**被移除**（键删除 / matcher 删除 / 文件删除），非停用标记 |
| 用户其他配置 | 保留（其他 mcpServers、其他 hooks、PostToolUse、无关设置项都在） |
| `GET /api/client-config` → `<平台>[kind]` | `false` |
| 该开关 | 显示为**关**；另外两个开关**不变** |

自动化：`TestCheck2_ToggleOff`（5 例 ×2 平台，含「关=删除非停用」「保留用户其他配置」「幂等」）、
`test_client_config_toggle.py::…::test_toggle_off_sends_delete_then_on_sends_post`（×2 平台）。

### 检验三：再次打开

`POST /api/client-config/<平台>/<kind>`

| 项 | 预期 |
|----|------|
| 对应配置文件 | 条目**恢复写入**，内容与初次写入**逐字段等价** |
| `GET /api/client-config` → `<平台>[kind]` | `true` |
| 该开关 | 恢复为**开** |
| 多轮 关→开→关→开 | 状态稳定，无漂移 |

自动化：`TestCheck3_ToggleBackOn`（3 例 ×2 平台，含「恢复内容等价」「多轮循环稳定」）、
`test_client_config_toggle.py::…::test_full_off_on_cycle_via_ui`（浏览器逐个关再逐个开，×2 平台）。

### 补充：三个开关各自独立、互不影响

| 场景 | 预期 |
|------|------|
| 关 mcp | hooks / agent 的检测态与文件不变 |
| 关 hooks | mcp / agent 不变 |
| 关 agent | mcp / hooks 不变 |
| 开某个关着的 kind | 不会顺带打开另外两个 |
| 8 种开/关组合矩阵 | 设置页开关矩阵 ↔ 配置文件矩阵**逐一完全一致** |
| ClaudeCode ↔ CodeBuddyIDE | 同一 home 下两平台配置各写各的，关掉一个平台全部不影响另一个 |

自动化：`TestCheck4_SwitchIndependence`（4 例 ×2 平台，含 `test_independent_state_matrix` 遍历 8 组合）、
`TestCrossPlatformIsolation`（2 例，两平台互不干扰）、
`test_client_config_toggle.py::…::test_three_switches_independent`（浏览器点关 hooks，断言只对 hooks 发一次 DELETE，×2 平台）。

---

## 4. 自动化测试 vs 手动验证

### 自动化覆盖

| 层 | 文件 | 覆盖（ClaudeCode + CodeBuddyIDE 均参数化 ×2） |
|----|------|------|
| **后端 / API** | `tests/test_client_config_verify.py`（`fake_home` 隔离 + `TestClient` 打真实路由；`params=["ClaudeCode","CodeBuddyIDE"]`） | 三次核心检验的**配置文件内容 + 检测态 + 开关联动**全链路；关=删除非停用；保留用户配置；独立性 8 组合矩阵；两平台互不干扰；引导契约护栏（拒绝非法 kind、重复初始化保持开启） |
| **前端 · 静态** | `tests/frontend/test_client_config_toggle.py::TestConfigToggleStatic`（源码断言，总是运行） | 开关视觉态绑定 `clientStatus`；点击调 `configureClient(plat.key, kind.key)`；`configureClient` 双向取反 + POST/DELETE 分支 + 回读；单写锁；`guideExecute` 用 `.key` 且只「确保开启」；两平台 `kinds` 与 toggle 标记平台无关 |
| **前端 · 浏览器** | `tests/frontend/test_client_config_toggle.py::TestConfigToggleBrowser`（Playwright，全量 mock `/api/**`，真跑 Alpine，不碰真实 `~/.claude` / `~/.codebuddy`、不需 8080 后端；`@parametrize("plat", ["ClaudeCode","CodeBuddyIDE"])`） | 开关 on/off class ↔ mock 配置态一致；点击发对方向 HTTP 动词并回读翻转；三开关独立；关→开完整循环；`guideExecute` 不误删已配置项 / 未配置时写全三种 |

**为什么前端写路径用 mock 而不用真后端**：仓库既有前端浏览器测试（`test_stage3.py`）明确
「只 GET 检测 + 渲染，不实际 POST 写入用户全局配置」——真后端会写到跑测试这台机器的真实
`~/.claude` / `~/.codebuddy`。本方案用 `page.route` 拦截全部 `/api/**`，内存态模拟后端，
既真实驱动 Alpine 开关逻辑，又零副作用。

### 需手动验证（自动化未覆盖 / 不适合自动化）

| 项 | 手动步骤 |
|----|----------|
| 桌面 App 内引导页真机走查 | `myknowledge serve` → 浏览器打开 → 初始化引导选 Claude Code / CodeBuddy IDE → 走完 → 去 `~/.claude*` / `~/.codebuddy*` 核对三份文件 |
| 设置页开关视觉/交互细节 | 设置 → MCP/Hooks/Agents 三页，对两个平台逐个点开关，观察 knob 滑动动画、toast 文案（「已就绪 / 已关闭」）、失败时行内 fallback |
| Claude Code / CodeBuddy IDE 真机联调（**国内网络不可行，出于完整性列出**） | 有外网环境时：配置写入后启动客户端，确认它能加载 MyKnowledge MCP server、PreToolUse hook 生效、专用 Agent 可用 |
| 「重新运行初始化引导」回归 | 已配置某平台 → 设置→通用→重新运行初始化引导→选同一平台→走完 → 确认三份配置**仍在**（不被清掉） |
| DMG 真机安装 | 见 §6（本次已打包，供 mentor 安装验证六平台默认配置） |

---

## 5. 回归说明

- **不改动任何既有测试文件**。两个新测试文件独立新增。
- `frontend/js/store.js` 的功能修复（见下「发现的问题」）触发 `frontend/build.py` 的
  `?v=` 内容哈希更新 → `frontend/index.html` 里 `store.js?v=` 一行随之更新（CI 的
  `frontend/check_build.py` ④ 版本化一致性检查要求二者匹配）。`index.standalone.html`
  为 `.gitignore` 忽略的构建产物，不入库。
- 基线（改动前，clean `main`）既有测试状态：
  - `tests/`（后端全量）：**全绿**（`758 passed`，含无关的 `.myknowledge_test` 集）。
  - `tests/frontend/test_stage3.py`：`17 passed, 8 skipped`（skip = 需 8080 后端）。
  - `tests/frontend/test_client_config.py` 对应的后端 `tests/test_client_config.py`：**全绿**。
  - `tests/frontend/test_smoke.py::TestRouteRendering` 的 3 例
    （`test_no_modal_visible_on_load` / `test_dashboard_shows_title` / `test_trash_view_renders`）
    **改动前即失败**（缺少 `backend_running` skip 守卫，无 8080 后端时 dashboard 无数据 →
    标题区 `x-show` 隐藏）。**与本次改动无关**，改动后仍是同样这 3 例失败，无新增失败。
- 改动后（含第二部分补的 CodeBuddy IDE 覆盖）：
  - `tests/test_client_config_verify.py`：`56 passed`（ClaudeCode + CodeBuddyIDE 参数化 + 两平台互不干扰）
  - `tests/frontend/test_client_config_toggle.py`：`24 passed`（静态 12 + 浏览器 12 = 6 用例 ×2 平台）
  - `tests/frontend/test_stage3.py`：`17 passed, 8 skipped`（不变）
  - `tests/test_client_config.py`：不变全绿
  - 后端全量 `787 passed`（基线 758 + 新增 29）
  - `tests/frontend/` 全量：`88 passed, 115 skipped, 3 failed`（3 failed = 上述 `test_smoke.py` 既有失败，无新增）
  - `frontend/check_build.py`：`28/29`（唯一失败 `⑤ 编辑保存往返测试` 缺 `frontend/node_modules`
    的 turndown，**改动前即如此**，CI 会装依赖）；`④ ?v= 版本化一致性` ✓

---

## 发现的问题（测 → 修 → 再测）

### 问题 #1：初始化引导一个配置都写不进去（kind 传成对象 → 后端 400）

- **现象**：走「初始化引导 / 重新运行初始化引导」，Step 2.2「正在为 N 个平台初始化 AI 协作…」
  执行完、结论页显示「初始化完成，已为所选平台开启协作能力」，但 `~/.claude.json` /
  `~/.claude/settings.json` / `~/.claude/agents/` **三份文件一个都没被写**。设置页三个开关仍是「关」。
- **根因**：`frontend/js/store.js` `guideExecute()`：
  ```js
  for (const kind of this.platformKinds(platform)) {      // ← platformKinds() 返回 {key,label,desc} 对象数组
      await this.configureClient(platform, kind);          // ← 把整个对象当 kind 传下去
  }
  ```
  `configureClient` → `api.setClientConfig(platform, {对象})` →
  URL `/api/client-config/ClaudeCode/${encodeURIComponent({对象})}` =
  `/api/client-config/ClaudeCode/%5Bobject%20Object%5D` →
  后端 `write_kind("ClaudeCode", "[object Object]")` → `kind not in KINDS` → **HTTP 400** →
  被 `guideExecute` 里的 `catch (e) {}` 静默吞掉。同文件其他调用点（`guideConfigItems`）
  都正确取了 `kind.key`，唯独 `guideExecute` 漏了。
- **修复**（`frontend/js/store.js`，最小改动）：
  ```js
  for (const kindMeta of this.platformKinds(platform)) {
      const kind = kindMeta.key;                           // ← 取字符串 key
      if (this.clientStatus(platform, kind) === true) continue;   // 见问题 #2
      try { await this.configureClient(platform, kind); } catch (e) { /* 不中断后续 */ }
  }
  ```
- **验证**：`test_client_config_toggle.py::…::test_guide_execute_writes_all_three_when_unconfigured`
  （改前红：`guideExecute` 对 ClaudeCode 发出的是非法 kind、0 个有效 POST；改后绿：mcp/hooks/agent 各一个 POST）。
  后端护栏 `test_client_config_verify.py::TestGuideExecuteContract::test_object_like_kind_is_rejected`。

### 问题 #2：重新运行初始化引导会把已配置的项**误关掉**

- **现象**（修完 #1 后才会显形；#1 存在时所有调用都 400，掩盖了它）：已经配置好 Claude Code
  的用户，点「设置 → 通用 → 重新运行初始化引导」，重新勾选 Claude Code 走一遍——
  期望是「确认 / 保持开启」，实际会把 mcp/hooks/agent **三个都关掉**（配置被删）。
- **根因**：`configureClient(platform, kind)` 是**双向开关**（`target = !prev`）。
  `guideExecute` 拿它当「确保开启」用：当 `prev` 已是 `true`，`target` 就变成 `false` → 走 DELETE。
  引导的语义自始至终是「初始化 / 开启」（UI 文案无一处是「切换」），对已开启项执行关闭是明确的逻辑错误。
- **修复**：同上一处，加一行 `if (this.clientStatus(platform, kind) === true) continue;`——
  引导只对**尚未开启**的 kind 调 `configureClient`（写操作幂等，POST 已开启项本也安全，
  这里直接跳过更省一次往返）。**不改 `configureClient` 本身**（设置页开关仍需要它的双向语义）。
- **验证**：`test_client_config_toggle.py::…::test_guide_reexecute_does_not_remove_configured`
  （改前红：对已配置 ClaudeCode 发 DELETE；改后绿：零 DELETE，配置保持）。
  静态断言 `test_guide_execute_only_ensures_on`。
  后端护栏 `test_client_config_verify.py::TestGuideExecuteContract::test_reinit_keeps_config_on`。

### CodeBuddy IDE：未发现新问题（第二部分）

把 CodeBuddyIDE 纳入同一套参数化验收后：

- **三次核心检验 + 开关独立性 + 两平台互不干扰全部通过**，无 CodeBuddyIDE 专属 bug。
- 问题 #1 / #2（`guideExecute`）**同样影响 CodeBuddyIDE**——它是所有非 Enchante 平台共用的
  引导执行路径。已由问题 #1/#2 的**同一处修复**覆盖；新增的浏览器用例对 CodeBuddyIDE 也参数化
  跑了一遍（改前红、改后绿），确认修复对两平台都生效。
- CodeBuddyIDE 的 hooks 命令是环境相关的（dev `python3 -m backend.hooks_forward` / frozen
  `"<二进制>" --hooks-forward`），`detect_platform` 与 `_hooks_cmd_for` 用的是同一个当前环境
  命令，因此测试里始终自洽——已通过 `_matcher_is_mine` 签名识别（与后端 detect 同源）验证。

### 未发现问题的部分（两平台通用）

- **设置页三个开关本身**（`configureClient` + `index.html` toggle 绑定）逻辑**正确**：
  开→POST、关→DELETE、再开→POST，回读 `loadClientConfig` 权威刷新，单写锁防串扰。
  三次核心检验在开关这条路径上、两个平台全部通过，无需修改。
- **后端 `write_kind` / `remove_kind` / `detect_platform`** 逻辑**正确**：增量合并、只删自己的条目、
  幂等、恢复内容逐字段等价、三文件天然隔离、两平台各写各的。既有 `tests/test_client_config.py`
  + 本次新增（ClaudeCode + CodeBuddyIDE）均通过。

---

## 6. 打包产物（供 mentor 真机验证）

用当前分支代码打了一个**默认配置（6 平台）**的 macOS DMG：

- 打包流程：`cd desktop && npm run build:backend`（`scripts/build-backend.sh`，PyInstaller onedir
  + MCP 冒烟）→ `npm run build:app`（`scripts/build-desktop.sh`，electron-builder）。
- 产物：`desktop/dist/MyKnowledge-0.7.7-arm64.dmg`，并复制一份到代码项目目录：
  **`~/Desktop/Apple internship/08_代码项目/MyKnowledge-0.7.7-arm64-0903.dmg`**
- 未签名（adhoc）：首次打开若被 Gatekeeper 拦，执行
  `xattr -dr com.apple.quarantine "/Applications/MyKnowledge.app"` 后再打开。
- 验证建议：打开 App → 初始化引导选 Claude Code / CodeBuddy IDE → 走完 →
  终端看 `~/.claude*` / `~/.codebuddy*` 三份文件；再「设置 → 通用 → 重新运行初始化引导」
  重跑一遍，确认配置**没被清掉**（问题 #2 的修复）。
