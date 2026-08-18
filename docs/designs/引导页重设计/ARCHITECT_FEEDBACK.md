# 前端视觉设计 agent → MyKnowledge 架构师：「引导页重设计」补充反馈

> 作者：前端视觉/交互设计 agent
> 日期：2026-08-18
> 用途：本反馈覆盖架构师 7 个裁决的回应 + 2 个补充设计需求（A. 大 modal 规格 / B. Enchante 专属按钮）。可直接转发架构师。

---

## 〇、一句话结论

按你（架构师）的 7 个裁决 + 2 个补充需求，**更新 SPEC.md** 并**新建视觉稿 S2.2b**：

1. **大 modal 规格**：引导 modal 改为 **840×640**（> 设置 modal 760×540），风格协调
2. **Enchante 专属按钮**（2.2 结论页）：4 态——初始「⚡ 打开安装链接」/ 点击后「已生成链接 · 可再次点击」/ 生成中「生成中…」/ 未安装「置灰禁用 + 请先安装 Enchanté」

**设计三件套更新**（`docs/designs/引导页重设计/`）：
- `SPEC.md`（**510 行**，§十 补充 104 行）
- `export/106_1/37/87/125/163-...svg`（5 帧：S1/S2.1/S2.2/S3 + **S2.2b 大 modal + Enchante 四态**）
- `screenshots/screenshot-106_*.png` ×5

---

## 一、对你 7 个裁决的回应

| # | 裁决 | 我的处理 |
|---|------|---------|
| 1 | 字段命名 ✅ | SPEC §1.1 维持「企业名称（KNOWLEDGE_SHARE_CODE）」+「组织代码（SHARE_MAP）」并列 |
| 2 | 校验严格度 ✅ | SPEC §1.2 邮箱标准 + 企业名称非空 + **组织代码三位正整数**（与后端 `POST /api/config/share` share_map 一致） |
| 3 | 仅下限 1，无上限 ✅ | SPEC §2.4 保持"至少选 1"（6 平台全选无妨） |
| 4 | 进度条 0.42s ✅ | SPEC §5 维持 0.42s（0.06 整数倍）|
| 5 | 动画 0.36/0.42/0.48s ✅ | SPEC §5 维持 |
| 6 | 平台列表扩展 ✅ | 复用 `clientPlatforms` 数据驱动 |
| 7 | 执行态无需单独视觉稿 ✅ | SPEC §3.2 描述足够 |

---

## 二、补充需求 A：大 modal 规格

### 2.1 规格

| 属性 | 值 | 对照 |
|------|-----|------|
| 宽度 | **840px** | > 设置 modal 760px |
| 高度 | **640px** | > 设置 modal 540px |
| 圆角 | `--radius-xl`(14px) | 同设置 modal |
| 背景 | `--card-bg` + `backdrop-filter: blur(24px)` | 同设置 modal |
| 边框 | `0.5px solid rgba(0,0,0,0.06)` | 同设置 modal |
| 阴影 | `0 16px 48px rgba(0,0,0,0.12)` | 同设置 modal |
| 内边距 | 24px / 28px | 比设置 modal 略宽 |

### 2.2 实现

- **新类 `.guide-modal`**：复用 `.modal` 基础，覆盖尺寸
- **不**改设置 modal 现有结构
- 视觉稿 S2.2b 演示大 modal 框架 + 内容布局

---

## 三、补充需求 B：Enchante 专属按钮

### 3.1 视觉稿（S2.2b）四态

| 状态 | 文案 | 视觉 |
|------|------|------|
| **初始** | 「⚡ 打开安装链接」 | accent 实色 `.btn--sm btn--deeplink` |
| **点击后** | 「已生成链接 · 可再次点击」 | accent 实色 + 描边（保持可点）|
| **生成中** | 「生成中…」 | disabled + opacity 0.7（`deeplinkBusy`）|
| **未安装** | 「⚡ 打开安装链接」 | **置灰禁用**（opacity 0.45）+ 旁提示「请先安装 Enchanté」 |

### 3.2 交互

- 复用现有 `generateEnchanteDeeplink`（`store.js:1539` → `getClientConfigDeeplink` → **复制链接 + 隐藏 a 触发打开 + toast**「已生成并复制专属链接，若未自动打开 Enchanté，请粘贴到浏览器地址栏」）
- 复用现有 `deeplinkBusy` 状态
- **新增 store 状态**：`deeplinkClicked`（bool，点击后标记，文案变"已生成链接"）

### 3.3 Enchante 行说明

按钮旁小字：「MCP 需手动安装完成：点击按钮生成专属链接并打开」

### 3.4 未安装禁用

`!clientInstalled('Enchante')` → 按钮 `disabled`（opacity 0.45）+ 旁「请先安装 Enchanté」提示

---

## 四、SPEC.md 修订（§十 新增 104 行）

- §10.1 大 modal 规格（840×640 + CSS）
- §10.2 Enchante 专属按钮（4 态 + 交互 + HTML 参考）
- §10.3 新增/调整样式类（`.guide-modal`、`.btn--deeplink:disabled`、`.guide-conclusion-row--deeplink`、`.guide-conclusion-row__hint`）

**零 design-token 增量**：全复用现有 `--card-bg` / `--radius-xl` / `--text-tertiary` / accent。

---

## 五、产物清单（本机绝对路径）

- **设计规范**：`docs/designs/引导页重设计/SPEC.md`（**510 行**，§十 补充 104 行）
- **视觉稿 SVG**：
  - `export/106_1-...svg`（S1）/ `106_37-...svg`（S2.1）/ `106_87-...svg`（S2.2 升级含 Enchante 按钮）/ `106_125-...svg`（S3）
  - **`export/106_163-...svg`**（**S2.2b · 大 modal 框架 + Enchante 按钮四态**）
- **人审截图**：`screenshots/screenshot-106_*.png` ×5

---

## 六、需架构师确认的决策

1. **大 modal 尺寸 840×640**：是否合适（> 设置 modal 760×540 略大）？是否需要更大或更小
2. **Enchante 专属按钮文案**：「⚡ 打开安装链接」是否足够醒目？或用「⚡ 完成 Enchante MCP 安装」
3. **点击后态文案**：「已生成链接 · 可再次点击」是否清晰？或简化为「已生成 · 再次点击」
4. **未安装禁用文案**：「请先安装 Enchanté」是否明确？或加具体安装指引
5. **新增 store 状态 `deeplinkClicked`**：仅用于 2.2 结论页显示文案；是否需要持久化（跨页面）或仅本次 session

---

## 七、待前端开发 agent 实施（补充）

按 SPEC §十 实施：

1. **`frontend/css/components.css`**：新增 `.guide-modal` 样式（840×640 + backdrop-blur + 阴影）
2. **`frontend/index.html` L1608-1717**：引导 modal 容器加 `guide-modal` 类；2.2 结论页 Enchante 行加专属按钮（含 4 态 + 旁小字）
3. **`frontend/js/store.js`**：新增 `deeplinkClicked: false`；在 `generateEnchanteDeeplink` 成功回调设 `deeplinkClicked = true`
4. **不动后端**；**不动设置 modal**

---

## 八、零修改声明

- `frontend/*.js / *.html`：未改（**待前端开发 agent 按 SPEC §十 实施**）
- `backend/`：未改
- `design-tokens.css`：零 token 增量

---

*本反馈 + SPEC.md §十 + 5 个 SVG = 引导页重设计 + 补充设计交付。前端开发 agent 据此施工，架构师拍板决策点（§六）。*
