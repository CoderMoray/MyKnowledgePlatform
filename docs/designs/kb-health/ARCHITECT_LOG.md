# KB 结构体检 · 前端视觉设计架构日志

> 作者：前端视觉/交互设计 agent · 归档：2026-08-17
> 用途：合并原 `ARCHITECT_FEEDBACK.md` / `ARCHITECT_PROMPT.md` / `ARCHITECT_COMPLETE.md` 的关键信息，作为本功能视觉设计的**最终架构日志**。与 `SPEC.md`（语义核心）并存：SPEC 是设计语义权威，本文是「交付 + 裁决执行 + 知识缺口 + git 归属」记录。

---

## 1. 交付物总览

**根目录**：`/Users/chrismoray/Desktop/Moray/MyOpenSource/MyKnowledge_PlatForm/docs/designs/kb-health/`

| 产物 | 位置 | 说明 |
|---|---|---|
| SPEC.md | `docs/designs/kb-health/SPEC.md` | 语义核心（1096 行，含 §20 实际实现微调记录） |
| ARCHITECT_LOG.md | 本文 | 架构日志（合并记录） |
| SVG 矢量稿 ×7 | `export/` | A 健康空态 / B 有问题分组 / C 修复弹窗 / D 加载态 / E 就绪信号紧凑徽章 / F 引导页 3 步 / **G 配置 modal（Trae/OpenCode 范式：左导航 3 分组 + 右卡片）** |
| PNG 人审参考 | `screenshots/` | 每 frame 最新截图 + 2 张旧方案 PNG |
| 画布 | ardot「新文件」page `5:1` | 云端 file 714694871087289 |

**SVG 明细（`export/`，20260817 最新版）**：
- `5_2-...svg` Frame A 健康空态（标注"仅视觉参考 · 以 index.html 实际实现为准"）
- `5_37-...svg` Frame B 有问题分组（同上标注）
- `5_122-...svg` Frame C 修复确认弹窗（同上标注）
- `5_138-...svg` Frame D 加载态（同上标注；标题已修为"知识健康检查"）
- `5_284-...svg` Frame E 就绪信号（**紧凑徽章**四态）
- `5_165-...svg` Frame F 引导页 3 步（标注"阶段三待实现：当前 setup 为单步 modal，3 步向导为未来 AI 协作初始化设计"）
- `57_6-...svg` Frame G 配置 modal（**Trae/OpenCode 范式**：居中 modal + 左侧导航 **3 分组**（账号/通用/AI 协作）+ 右侧多卡片内容）

---

## 2. 架构师裁决执行结果（Q1-Q4 / Q7 / D）

| 裁决 | 结果 | 落地 |
|---|---|---|
| **Q1** 健康页 A/B/C/D 保留 +标注 | ✅ | 画布 4 frame 底部标注已写入；SVG 已重导 |
| **Q2** 引导页 F 保留 3 步 +标注"阶段三待实现" | ✅ | 画布 F 标注已写入；SVG 已重导 |
| **Q3** 配置 G 3 tab 全做 + modal 弹窗（不新增 `#settings` 路由）| ✅ | SVG 居中 modal + 3 tab，对齐 `openModal('edit-identity')`（`index.html:511`）|
| **Q4** SVG 文本转 path 限制知悉 | ✅ | SPEC §20.3 记录，不阻塞（前端靠 SPEC+PNG 实施）|
| **Q7** designs/ 部分管理（md 入库、export/screenshots ignore）| ✅ | `.gitignore` 加 `docs/designs/**/export/` + `docs/designs/**/screenshots/`；md 已 `git add` |
| **D** SPEC 追加实际实现微调记录 | ✅ | SPEC.md 新增 §20（20.1 落地范围 / 20.2 差异对照表 / 20.3 SVG 状态 / 20.4 后续 agent 提示）|

---

## 3. 暴露的知识缺口 + 修正（团队流程改进）

> 根因：本 agent 接手时**未先探查 `frontend/` 判断哪些已由前端 agent 落地**，导致初始 SVG 若干处与真实渲染不符。已修正并记入 SPEC §20 与 §20.4。

已修正的「落地 vs SPEC 理想态」差异：
1. **h1 文案**：SPEC「知识库结构体检」→ 实际「**知识健康检查**」（`index.html:1095`）
2. **chip 配色**：SPEC 灰 → 实际 count>0=`--accent-subtle`+`--accent`；count=0=`--bg-tertiary`+`opacity:.5`（`components.css:1820-1848`）
3. **按钮位置**：概览卡右上 → 实际**标题区（page-header）右侧**（`index.html:1098-1120`）
4. **就绪信号**：大卡 → 实际**紧凑徽章**（`layout.css:462-483`：padding 3px 10px、圆角20px、6px dot、`--text-xs`）
5. **配置页**：独立 `#settings` → 实际**居中 modal**（对齐 `openModal('edit-identity')`，不新增路由）
6. **引导页**：3 步向导 → 实际当前**单步 setup modal**（`index.html:1571-1604`），3 步为未来设计

---

## 4. 关键设计决策（最终形态）

- **配置 = 居中 modal 弹窗 + 左导航 3 分组（账号 / 通用 / AI 协作）+ 右多卡片**（Trae/OpenCode 范式），不新增独立路由；入口 user-menu「设置」，对齐「编辑个人信息」modal 交互。账号 1 卡；通用含「外观(双层主题)/引导/关于」多卡；AI 协作按类型 3 卡（MCP/hooks/Agent）各平台分列。
- **引导页 = 3 步向导**（身份 / AI 协作初始化 / 完成）**待阶段三实现**；当前 setup 为单步 modal。
- **就绪信号 = 紧凑徽章**（复用 `.status-indicator`），四态：健康绿 / 存疑红（high>0）/ 存疑黄（high=0）/ 未检查灰。
- **零 design-token 增量**：所有色值/字号/间距/圆角/阴影复用 `design-tokens.css`；新增样式类仅写入 `components.css`。

---

## 5. 已知限制

- **SVG 文本被转 path**：ardot `export_nodes` 的 SVG 格式把文本节点转为 `<path>`，**不含可读中文 `<text>` 元素**。SVG 矢量精确，但前端 agent 不能 `read_file` 读出中文字面，实施需靠 SPEC.md（语义）+ PNG screenshots（视觉）。
- **ardot 服务偶发不可用**：本任务曾连续 fetch failed（4+ 次），按 SPEC §18 原则不无限重试、不编造结果；恢复后已补写画布标注并重导完成。

---

## 6. designs/ git 归属说明

- **入库**：`SPEC.md` + `ARCHITECT_LOG.md`
- **被 `.gitignore` 忽略（不入库）**：`docs/designs/**/export/`（SVG 生成物）、`docs/designs/**/screenshots/`（PNG 体积大）
- **不处理**：`frontend/css/layout.css` + `frontend/index.html`（前端 agent 独立工作，另行安排）
- git 提交由架构师/负责人执行（本 agent 不 commit）。

---

## 7. 零修改声明

- `frontend/*.js / *.html`：未改（`frontend/index.html`、`frontend/css/layout.css` 的改动是前端 agent 工作）
- `backend/`：未改
- `design-tokens.css`：零 design-token 增量，100% 复用现有 token

---

## 8. 后续设计迭代：设置 Modal 右半页重设计（2026-08-18）

> 本节为追加迭代记录。原 §1-§7 任务已归档；本轮为独立任务「设置 Modal 右半页重设计 + AI 协作分组重构 + 检测健壮性」的设计交付。

### 8.1 本轮设计交付物（追加）

| 产物 | 位置 |
|---|---|
| **设计规范** | `docs/designs/kb-health/SETTINGS_REDESIGN_SPEC.md`（含导航重构 / 开关三态 / fallback 交互 / 检测健壮性 / 不改范围 / 验收对照） |
| **视觉稿 SVG** | `export/99_3-20260818_104724369.svg`（Frame G4 · modal 完整） |
| **截图** | `screenshots/screenshot-99_3-20260818_104615502.png` |
| **反馈 prompt** | `ARCHITECT_FEEDBACK_SETTINGS.md`（给架构师/前端开发 agent） |
| **画布** | ardot page `5:1`，Frame G4 nodeId `99:3` |

### 8.2 5 项核心改动

1. **左导航重构**：账号 / 通用 / AI 协作(分组标签) / MCP / Hooks / Agents
2. **开关三态替代按钮**：true 开 / false 关 / null 灰禁用 + 检测失败红字
3. **去掉「复制 prompt 给 AI」按钮**
4. **fallback 改为可交互文本**：行内 accent 紫淡底"配置失败 · 一键复制 prompt 给你的 AI →"
5. **「⟳ 重新检测」按钮**：右半页 header 右上，调 `loadClientConfig()`

### 8.3 关键设计决策

- **导航层级 5 分组选择**：用户首选 5 平级（账号/通用/MCP/Hooks/Agents），我推荐 **AI 协作作分组标签 + 3 子项**（理由：语义维度不同、IA 清晰、实现成本一致、对照 Trae 模式）。**最终由架构师拍板**。
- **fallback 消失时机**：规范建议 5 秒自动清除 + 点击可提前关闭。
- **遮罩聚焦**：仅 settings modal 遮罩加深到 `rgba(0,0,0,0.35)`，其他 modal 保持 `0.28`。

### 8.4 边界（明确）

- **不动后端**：API 契约（`GET/POST /api/client-config`）完全复用
- **不改其他页面**：引导页 setup、账号卡、通用主题切换、其他 modal 保持原样
- **不改现有 store.js 函数签名**：`clientStatus`/`configureClient`/`copyClientPrompt`/`loadClientConfig` 复用，仅扩展 `configureClient` 失败处理（加 `clientFallback` 状态）
- **零 design-token 增量**：所有新样式类复用现有 token

### 8.5 待前端开发 agent 实施

按 `SETTINGS_REDESIGN_SPEC.md` 实施三处改动（`index.html` L1722-1869 替换 + `store.js` 加 `clientFallback` + `components.css` 新增样式类），验收 9 项对照 §6 验收清单。

---

## 9. 最终版迭代：5 平级导航 + Claude Code + client_installed 5 态（2026-08-18）

> 本节为 §8 设计规范的**最终版追加**。覆盖原 §1 导航 IA 决策、平台标签命名、开关 3 态 → 5 态状态机。

### 9.1 架构师 4 项裁决 + 3 处追加

| 裁决/追加 | 结果 |
|---|---|
| 1. 导航层级 | **5 平级**（账号 / 通用 / MCP / Hooks / Agents；取消「AI 协作分组标签 + 3 子项」）|
| 2. fallback 自动消失 | 5 秒 |
| 3. 遮罩加深范围 | 仅 settings modal 0.35 |
| 4. 开关动画库 | 纯 CSS toggle（无 framer-motion） |
| 5. 平台标签 | **「Claude」→「Claude Code」**（codebuddy 保持「CodeBuddy」）|
| 6. `client_installed` 5 态 | **核心追加**：3 态扩展为 5 态（含「浅色开」+「请在安装 X 后使用」提示） |
| 7. SVG 视觉稿同步 | Frame G4f 重建（含 5 态演示行） |

### 9.2 `client_installed` 5 态状态机

| 状态 | 判定 | 开关 | 状态点 | 文本 |
|------|------|------|--------|------|
| 已就绪 | installed + true | `toggle--on`（accent 实色）| success 绿 | "已配置" |
| 未配置 | installed + false | `toggle--off`（灰） | muted 灰 | "未配置 · 点击开关开启" |
| **已写配置但未装** | !installed + true | **`toggle--on-soft`**（accent 40%） | success 绿(淡) | "请在安装 {客户端} 后使用" |
| **未装且未配置** | !installed + false | **`toggle--off-soft`**（#e5e7eb 浅色关） | muted 灰(淡) | "请先安装 {客户端}" |
| 检测失败 | clientStatus === null | `toggle--failed`（灰 opacity 0.4） | warning 橙 | "检测失败 · 点击重新检测"（红字） |

**关键决策**：`!installed` 时开关**仍可点**（用户裁决：置灰但可交互）——点开关调 `configureClient`（后端 mkdir 写配置），成功后显示「浅色开 + 请在安装 X 后使用」。

### 9.3 本轮设计交付物（更新/新增）

| 产物 | 状态 |
|---|---|
| `SETTINGS_REDESIGN_SPEC.md` | **更新**（§1 5 平级 / §2 5 态 / §2.5 HTML / §2.6 store.js / §2.7 CSS）|
| `export/99_57-20260818_111503579.svg` | **Frame G4f**（5 平级 + Claude Code + 5 态视觉稿）|
| `screenshots/screenshot-99_57-20260818_111443509.png` | 最终版截图 |
| `ARCHITECT_FEEDBACK_SETTINGS.md` | **重写**为最终版反馈（含 3 处追加决策）|
| 旧 G4（`99_3-...`/`99:3`）| **已删除**（分组标签版过期）|

### 9.4 待前端开发 agent 实施（按最终版）

按 `SETTINGS_REDESIGN_SPEC.md`（最终版）实施：
- `index.html` L1722-1759：**5 平级** nav item（**不实现** group-label/child）
- `index.html` L1839-1865：5 态开关 + 5 态状态文本 HTML
- `store.js`：`clientPlatforms` 标签改「Claude Code」+ 新增 `clientInstalled` + 扩展 `configureClient` 失败处理
- `components.css`：新增 `.toggle--on-soft` / `.toggle--off-soft` / `.ai-platform-row__state--soft`（**不实现** `.settings-nav__group-label` / `.settings-nav__item--child`）

### 9.5 边界（明确）

- **不动后端**：API 契约（`GET/POST /api/client-config`）完全复用
- **不改其他页面**：引导页 setup、账号卡、通用主题切换、其他 modal 保持
- **零 design-token 增量**

---

*归档完成。本任务阶段三（引导 3 步 / 配置弹窗实现）近期不推进，可归档。后续 agent 接手本功能前，先探查 `frontend/` 确认已落地实现，再以 SPEC + 本日志为准。*
