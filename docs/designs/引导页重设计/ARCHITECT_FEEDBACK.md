# 前端视觉设计 agent → MyKnowledge 架构师：「引导页重设计」设计反馈

> 作者：前端视觉/交互设计 agent
> 日期：2026-08-18
> 用途：本反馈覆盖「引导页 3 步改结构」任务的**设计交付物**与**关键决策**。可直接转发架构师。

---

## 〇、一句话结论

按你（架构师）的设计需求，产出**4 页 3 步结构 + 动画规范**的完整设计：

```
Step 1  身份（4 字段全必填 + 校验）
Step 2  ┌ 2.1 平台多选（6 平台开关，未安装禁用，至少选 1）
        └ 2.2 执行 + 结论（进度条 ≥0.36s → 按平台结论）
Step 3  完成（✓ 延续现有）
```

**动画规范（重点）**：步骤间过渡 = 淡入 + 位移/缩放，**时长 ≥0.36s 且为 0.06 整数倍**（0.36/0.42/0.48/0.54/0.60s）；2.2 执行进度条也 ≥0.36s。

**设计三件套**（存 `docs/designs/引导页重设计/`）：
- `SPEC.md`（**200+ 行**，语义规范）
- `export/106_1-...svg`（Frame S1 · Step1 身份 4 字段）/ `106_37-...svg`（S2.1 平台多选）/ `106_87-...svg`（S2.2 执行+结论）/ `106_125-...svg`（S3 完成）
- `screenshots/screenshot-106_*.png` ×4（人审参考）

---

## 一、范围与边界

| 项 | 状态 |
|---|---|
| **只做视觉/交互设计** | ✅（不写 HTML/JS 实现，前端开发另派） |
| **不改后端** | ✅（Step1 写分享配置的 REST 端点由后端另派） |
| **不动设置 Modal 现有 5 平级导航** | ✅（引导页独立设计，风格协调即可） |
| **零 design-token 增量** | ✅（全复用现有 token：accent、color-success/warning/danger、text-primary/secondary/tertiary、bg-tertiary、border-subtle、radius-sm、text-2xs/xs/sm、transition-interactive） |

---

## 二、关键设计决策

### 2.1 Step 1 身份 — 4 字段全必填

| 字段 | 对应 | 校验 | 占位示例 |
|------|------|------|---------|
| 昵称 | nickname | 非空 | 张三 |
| 邮箱 | email | **邮箱格式** | zhangsan@example.com |
| 企业名称 | `KNOWLEDGE_SHARE_CODE` | 非空 + 格式（按 /api/config-status schema）| Acme 科技 |
| 组织代码 | `SHARE_MAP` | 非空 + 格式 | acme-share |

- **4 字段全必填，未填全「下一步」disabled**（按钮半透明紫态）
- 校验失败字段下方红字 hint（复用 `.modal__hint--error`）
- 字段下方说明：「企业名称与组织代码用于知识库分享鉴权，仅本机存储」

### 2.2 Step 2.1 平台多选 — 6 平台开关

- **每行结构**：平台渐变 dot（16px，复用 `clientPlatforms[].dot`）+ 平台名 + 开关
- **开关** 与设置 Modal toggle **一致**（`.toggle` + knob，选中 `toggle--on` accent 实色）
- **未安装**（`clientInstalled=false`）：开关 **灰禁用**（opacity 0.4）+ 行尾**「未安装」标签**（`--text-2xs` 灰）
- **至少选 1**：未选「下一步」disabled + 提示「请至少选择 1 个平台」+ 列表底部「已选 N/6 个平台」
- **6 平台**（复用 store.js `clientPlatforms`）：ClaudeCode / ClaudeDesktop / CodeBuddyIDE / WorkBuddy / Enchanté / Cursor

### 2.3 Step 2.2 执行 + 结论

- **进入即执行**：为已选平台按 kinds 开启 MCP/Hooks/Agent，Enchanté 生成 deeplink
- **进度条** ≥0.36s（0.42s 0.06 倍数），用 `@keyframes guide-progress 0.42s ease-out`（CSS）或 `min-duration` 补足
- **结论按平台分行**：
  - 每行 = 平台渐变 dot + 平台名 + `: 做了什么` + 状态点（成功绿 / 跳过灰）
  - 「做了什么」按平台 × kind 组合（如 `已开启 MCP / Hooks / Agent`；Enchanté `已生成专属链接 (deeplink)`；未安装 `已跳过`）
- **查看指引**（结论下方）：「你可以在 设置 → MCP / Hooks / Agent 中查看或调整」
- **关闭小字**：「可在个人设置中关闭」(`--text-tertiary`)

### 2.4 Step 3 完成 — 延续现有

- ✓ check-circle + 「初始化完成」+ 「你的知识库已准备好与 AI 协作」
- 4 项总结（身份已设置 / MCP 已配置 / hooks 待配置 / 专用 Agent 已就绪）
- 「开始使用」主按钮 → dashboard

### 2.5 动画规范（硬性）

| 时机 | 过渡 | 时长 | 缓动 |
|------|------|------|------|
| 进入新步骤 | `opacity 0→1` + `translateY(8px→0)` | **0.42s**（0.06 整数倍）| `cubic-bezier(0.4,0,0.2,1)` |
| 离开旧步骤 | `opacity 1→0` + `translateY(0→-8px)` | **0.36s** | 同上 |
| 2.2 执行中 → 结论 | 结论 `opacity 0→1` + `scale(0.98→1)` | **0.48s** | `ease-out` |
| 2.2 进度条 | 0→100% | **0.42s** | `ease-out` |
| 触屏/弱化 | 时长减半或关闭位移 | `prefers-reduced-motion: reduce` |

**实现**：CSS `transition` + Alpine `x-transition` 或 class 切换；时长用 0.06 倍数。

---

## 三、产物清单（本机绝对路径）

- **设计规范**：`docs/designs/引导页重设计/SPEC.md`（**200+ 行**）
- **视觉稿 SVG**：
  - `export/106_1-20260818_220939916.svg`（Frame S1 · Step1 身份）
  - `export/106_37-20260818_220939920.svg`（Frame S2.1 平台多选）
  - `export/106_87-20260818_220939923.svg`（Frame S2.2 执行+结论）
  - `export/106_125-20260818_220939927.svg`（Frame S3 完成）
- **人审截图**：`screenshots/screenshot-106_*.png` ×4

---

## 四、需架构师确认的决策

1. **Step 1 字段命名**：「企业名称（KNOWLEDGE_SHARE_CODE）」与「组织代码（SHARE_MAP）」的**中文 label + 后端 key** 并列展示，是否合适？还是用更直白的中文（如「企业码」/「组织码」）
2. **Step 1 校验严格度**：
   - 邮箱用现有 `isValidEmail`
   - 企业名称/组织代码格式**具体规则**以后端 `GET /api/config-status` 返回的 schema 为准（前端按后端定义校验）。建议正则 `[A-Za-z0-9_-]{2,32}`——是否合适
3. **Step 2.1 至少选 1 + 上限**：是否需要「至少 1 但不超过 4」（避免一次配置太多失败体验差）？我的决策是**仅下限 1**
4. **Step 2.2 进度条最小播放时长**：**0.42s**（0.06 整数倍）是否够？后端真实执行通常 <0.42s，前端补足
5. **动画时长**：
   - 进入新步骤 **0.42s**，离开 **0.36s**，执行→结论 **0.48s**——是否符合"≥0.36s 且 0.06 整数倍"硬约束
6. **平台 6 个**：复用现有 `clientPlatforms`（ClaudeCode/ClaudeDesktop/CodeBuddyIDE/WorkBuddy/Enchanté/Cursor），未来扩展时前端自动适配
7. **执行态视觉稿**：本轮视觉稿只画了 S2.2 结论态（更信息丰富）；**执行态**（进度条 + spinner ≥0.36s）见 SPEC §3.2 描述，前端实现时按此

---

## 五、待前端开发 agent 实施

按 SPEC §六/§七 实施：

1. **`frontend/index.html` L1608-1717**：替换为新结构
   - Step1：4 字段表单 + 校验
   - Step2.1：6 平台多选 + 未安装禁用 + 至少选 1
   - Step2.2：执行（进度条）+ 结论（按平台分行）
   - Step3：延续现有（4 项总结）
2. **`frontend/js/store.js`**：
   - `data()` 新增：`setupCompany` / `setupOrgCode` / `guideSelected[]` / `guideExecuting` / `guideExecDone` / `guideExecPercent`
   - 新增 `guideStep1Valid()` / `guideStep2Valid()` / `guideExecute()`（含 min-duration 补足 0.42s）
3. **`frontend/css/components.css`**：新增样式类（见 SPEC §六）
4. **企业名称/组织代码格式校验**：按后端 `GET /api/config-status` schema 实施

---

## 六、零修改声明

- `frontend/*.js / *.html`：未改（**待前端开发 agent 按 SPEC 实施**）
- `backend/`：未改
- `design-tokens.css`：零 token 增量

---

*本反馈 + SPEC.md + 4 个 SVG = 引导页重设计交付完整三件套。前端开发 agent 据此施工，架构师拍板决策点（§四）。*
