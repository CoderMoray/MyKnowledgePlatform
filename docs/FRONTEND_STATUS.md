# MyKnowledge 前端实现状态（唯一状态/待办文档）

> 最后更新：2026-08-14
> 说明：本文件为前端**唯一**状态文档（原 `docs/TODO.md` 已并入本文件的"待办清单"章节并删除）。
> 设计决策详见：`docs/archive/FRONTEND_INTERACTION_FEEDBACK.md`（历史设计确认，已实现，归档备查）

---

## 📅 2026-08-19 增量（已完成）

### Enchante Agent 一键安装 deeplink（前端）
- 后端新端点 `GET /api/client-config/Enchante/agent-deeplink`（仅 Enchante，`enchante://agent/install`），前端接入完成：
- `api.js` 新增 `getClientConfigAgentDeeplink(platform)` 调 `/agent-deeplink`。
- `store.js`：
  - `usesDeeplink(platform, kind)` 由「仅 Enchante MCP」扩为「Enchante MCP + Agent」（两 kind 均无配置文件，走客户端捕获链接）。
  - `generateEnchanteDeeplink(platform, kind)` 按 kind 分发：agent → `/agent-deeplink`，mcp → `/deeplink`；复用「复制剪贴板 → 隐藏 a 唤起 → toast」流程。
  - `deeplinkClicked` 由单布尔改为按 kind 对象 `{mcp, agent}`，新增 `deeplinkClickedFor(kind)` 供结论页按 kind 展示「已生成 · 可再次点击」态。
- `index.html`：
  - 设置 modal：Enchante MCP/Agent 行均显示 deeplink 按钮（`⚡ 生成 MCP 链接` / `⚡ 生成 Agent 链接`），不走 toggle；@click 带 kind.key 分发。
  - 引导页 Step2.2 结论：Enchante 拆「⚡ 生成 MCP 链接」+「⚡ 生成 Agent 链接」两个入口，分别调对应 kind。
- 测试：`tests/frontend/test_stage3.py` 更新（agent-deeplink 断言、usesDeeplink 规则、Enchante agent 行=deeplink 按钮、结论页两按钮）；21/21 通过 + smoke 22 通过。

---

## 📋 待办清单（按优先级排序，完成即划掉）

### P0 数据安全 / 正确性（优先）

- [x] **锁状态过期不刷新 UI** ✅ 已解决（2026-08-04 验证）：`store.init()` 有 15s 轮询 `checkLock` + doc.js `Alpine.effect` 监听 `isLocked` 响应遮罩
- [x] **"Node cannot be found" warning** ✅ 已解决（2026-08-04 验证）：单 DOM 改造后编辑器复用（不再销毁重建），进编辑/退出/切文档 console 干净
- [x] **数据一致性（乐观锁）** ✅ 已完成（2026-08-05 双窗口实测通过）：后端 `version=sha256(f"{summary}\x00{content}")[:12]` + 409 冲突；前端保存带 `expected_version`、编辑中收到 SSE 变更主动弹 diff 弹窗（内容不静默覆盖）、冲突可视化（两栏行号 diff + summary 差异 + 保留我的/采用服务端/取消）；设计决策见 `docs/DESIGN.md`「2.5.9 文档乐观锁」

### P1 编辑器 / 体验（飞书对齐）

- [ ] **第二波：富文本扩展**（需先定"markdown 内联 HTML 存储"方案）：
  - 对齐：左 / 中 / 右（`<p style="text-align:...">`）
  - 字体颜色（A 图标 → 色板，`<span style="color:...">`）
  - 背景色 / 高亮（`<span style="background:...">`，含"恢复默认"）
  - 技术方案：marked raw HTML 保留 / turndown span 规则 / 回归新增用例
- [x] **+ 加号菜单** ✅ 已完成（2026-08-05）：空行行首 hover 出现 + 按钮（平滑滑动），点击弹插入菜单（复用斜杠选项，表格内过滤表格项）；提交 `2d10c06`/`7c3d49f`
- [x] **文档卡片 hover 删除** ✅ 已完成（2026-08-11）：dashboard/项目视图卡片 hover 右上角浮出删除按钮 → delete-doc 确认模态 → 移入垃圾箱（提交 d9659f1 同批）
- [ ] **文档卡片 hover 重命名**：卡片 hover 重命名（未做，待定）
- [ ] **离线场景补齐**（A2 部分实现，当前只有横幅 + 草稿恢复）：
  - 全屏阻断弹窗：导航到新页面 / 冷启动离线无草稿 / Setup 页
  - toast 提示（3s）：点击操作按钮（新建/删除/保存）时离线
  - 冷启动离线 + 有草稿 → 直接进编辑恢复模式（5b 场景）

### P2 小项 / 待讨论

- [ ] **动态 icon 接入**：`cardIconSvg()` 已写好未调用（关键词→SVG 映射）
- [ ] **E2 元信息展示时机**：正文 vs 折叠（待讨论，设计原文 docs/archive/FRONTEND_INTERACTION_FEEDBACK.md）
- [ ] **区块 ⋮⋮ 菜单**：内容块行首（可选，非核心）
- [ ] **主题切换过渡动画**（F，低优先级）
- [ ] 响应式 & 移动端（G，明确不考虑）；快捷键（H3，未来考虑）

### 后端协作讨论（待排期）

- [ ] 锁机制 / git commit 策略 / AI 整理时机（后端 AI 协作讨论）

---

## 📅 2026-08-04 增量（已完成，7-30 → 8-04）

### 编辑器飞书化
- 浮动格式条（自实现定位，绕开官方 BubbleMenu 的 tippy 依赖）
- 斜杠菜单：H1-H4/列表/引用/代码块/分割线/表格；上下文过滤（表格内不显示表格项）；方向键滚动跟随
- 编辑态实时代码高亮（CodeBlockLowlight，Decoration 渲染安全）
- 自动保存 1s debounce + IndexedDB 离线草稿（含"放弃草稿"按钮）

### 双 DOM → 单容器
- 删除 viewer__body（marked 阅读容器），ProseMirror 常驻，阅读态 = `editable: false`（无闪烁/无跳位/滚动保持）
- ref hover 卡片 / 点击跳转迁移到 editor.dom 委托；bubble 只读态不弹（选中文字是复制行为）
- 点击进编辑 / 编辑态点击外部退出：document capture 阶段监听（ProseMirror stopPropagation 不影响）

### 保存零差异 + 回归测试
- **36/36 全绿**：`cd frontend && node tests/save-regression.mjs`（往返 17 + 斜杠插入 10 + 触发 3 + 过滤 2 + 单DOM 2 + 切文档 2）
- 软换行无损往返（\n↔br，跳过纯空白节点）；嵌套列表 2 空格；分割线 `---`；空 H1 只删开头占位

### ref 链接链路彻底修复
- isAllowedUri 拒绝 ref: 协议 → parseHTML/renderHTML 覆写（编辑态链接样式 + 保存不丢）
- hover 预览 ::section 后缀 404 → split("::")[0]
- 切文档 setContent 丢失预处理 → `_prepareEditorHtml()` 统一（onCreate + 切文档共用）

### 浮动条第一波
- T 块类型下拉（正文/标题1-4/有序/无序）；下划线（`<u>` 内联 HTML 存储）；缩进（列表嵌套，非列表置灰）；链接浮层（替代 prompt，选中文字作显示名）；自定义 tooltip 0.18s；SVG 线条图标（替换 emoji）

### 基建 / 数据
- CDN 全本地化（frontend/vendor/）；build contenthash 版本化 + 后端 HTML no-cache（普通刷新即最新）
- 数据恢复：技术选型.md / 编辑保存测试.md 从 git 恢复 + 补回 ref 链接

---

## 📅 2026-08-11 ~ 08-13 增量（已完成）

### 文档卡片 hover 交互（dashboard 公共知识 + 项目视图「知识」卡片）
- 摘要常显（与项目卡片同构）；hover 下拉展开正文预览（marked 取文本、保留分行、200 字截断、4 行省略号）
- 预览内 `ref:` 引用渲染为可点击链接（点击跳转引用文档，stopPropagation 不触发卡片打开）
- 底部「被 N 篇文档引用」行（0 引用不显示）
- 卡片删除按钮（hover 右上角浮出）→ delete-doc 确认模态
- **预览缓存失效**（d9659f1）：缓存键 = doc.modified 版本 + loadDashboard/loadProjectDocuments 后 `invalidateDocPreviewCache()`——编辑保存后返回主页 hover 预览更新

### 渲染修复
- **marked 5.x link renderer 签名兼容**（2524463）：`(href,title,text)` → 单一对象参数——此前 ref:/ext 分支永不触发，链接渲染异常（截图：链接不可点）
- ref: 空/纯空格目标 → 不渲染链接（纯文本），避免空路径死链

### 粘贴 markdown 全量解析（方案 B）
- **分流 handlePaste**：行内-only 交回 tiptap 原生 pasteRules（`**`/`*`/`_`/`` ` ``/链接 已内置解析）；
  含块级模式（行首 `# `/`- `/`1. `/`> `/``` `/`---`）或 `ref:` 链接 → 接管
  （renderMarkdown → _prepareEditorHtml（ref href 转换）→ insertContent）——编辑态即所见即所得
- **PF5 代码块内**：纯文本兜底（不拆代码块）；**PF4 列表内**：行首 lift 脱出、行中保留列表（结果 a）
- **PD2 ref 章节锚点**：含 `ref:` 链接文本走接管，`href="ref:path::章节"` 完整保留
- 提交：65b1c85 / a4d0768 / 198d771 / b31939a

### 测试资产
- `tests/frontend/test_paste_markdown.py`（P 系列 24 用例）；场景矩阵 `docs/test/testing-plan-paste-markdown.md`（8 批 48 场景）
- 前端全量 **75/75**（edit_switch 42 + hover 5 + paste 24 + refwarn toast 4）+ 后端 **349/349**

### S16 引用异常提示（ref_warnings toast，4252a96）
- 后端 PUT/POST 返回结构化 `ref_warnings` `[{type, ref_path, display_text}]`（契约见 `docs/FRONTEND_ARCHITECTURE.md` 5.2.1）
- 前端 `showRefWarningsToast`：保存后消费（≤3 逐条「A」引用目标不存在 / >3 计数汇总），exitEdit 显式保存才提示（autosave 静默）
- 测试 `test_refwarn_toast.py` 4/4

### 测试基建修复
- **s3_rename flaky 修复**（836c413）：rename 异步竞态（backend_doc 单次 GET 太早）→ 新增 `wait_for_backend` 轮询 helper，显式等新路径 200 + 旧路径 404；S 系列 42/42 + s3×3 全绿
- 依赖升级（fastapi 0.141，后端 3234e39/2c7f557）前端 API 兼容回归通过（75 用例，无 API 差异）

---

## 📅 2026-08-13 ~ 08-14 增量（已完成）

### 文档卡片删除链路修复（c81dfe9）
- **Bug1 删除模态文档名空白**：delete-doc 模态读 `modalData.title`，但 `confirmDeleteDocument`/`confirmDeleteCard` 传 `name` → 弹窗文档名空白。修复：store.js 两处 payload 统一 `{path, title}`（viewer/doc 早已传 title）。测试 H5b。
- **Bug2 卡片删除原地不刷新**：原实现删除后 3s 倒计时设置相同 hash（dashboard/project）→ 浏览器不触发 hashchange → 不刷新（但实测被 SSE updated 事件兜底，卡片会消失）；真正问题是「3 秒后返回首页/项目」倒计时在同 hash 下是空操作 + 文案误导。按产品拍板：卡片删除（dashboard/project 视图）= 简单 toast + 显式刷新 `loadDashboard`/`loadProjectDocuments` + `refreshProjectTree`，不跳转；文档页删除（view/edit）= 保留 3 秒倒计时跳转。测试 H5c。
- **按钮 hover 样式对齐 header**（components.css）：hover 统一 `--color-danger`（原 `var(--danger)` **未定义** → 回退近黑，表现为黑色描边）、边框 1px→0.5px（与 `.btn-delete` 一致）、hover 加字重 500。**教训**：CSS 变量命名要统一（`--color-danger` 而非 `--danger`）；改 css/js 后必须跑 `frontend/build.py` 更新 `?v=`，否则浏览器缓存旧资源。

### loadDocument pending 态（ffc6d45）
- 新增 `store.docPending`（不并入全局 `loading`，避免误触发 splash）；`loadDocument` 在途置 true、finally 清 false（含 404→redirect 分支）。
- index.html：加载中显示「加载中…」；`viewer--empty` 空文档条件排除 `docPending`——**修复「加载中」被误显示为「文档不存在或无法加载」**。
- 真 404（非 deleted）错误文案改为「文档不存在或无法加载」（原为后端原始 `not_found`）。测试 S27。

### 垃圾箱死链检查性能（后端 856d9dc 已修，前端配合完成）
- **根因**：`/refs` 对死链调 `ref_status` → `list_trash` 逐个读 trash 文件（曾 4939 个）→ 每次 1.7~2.5s，拖慢 hover 预览与打开含死链文档。
- **后端已修**：trash_index.json 索引 + 进程内缓存（`perf(trash)` 856d9dc），/refs 死链 <1ms。
- **前端配合项状态**：① pending 态已完成（见上）；② **hover 预览轻量化结论——不需要新端点**：现有 `/refs` 每条已带 `resolved`/`ref_status`，「被 N 篇引用」用 `refs.length` 前端本地即可算，且性能已修复、轻量化动机消失，保持调用现状。
- 前端调用 `/refs` 的依赖关系不变（`openDocPreview` 用 `refs.length` 显示引用数；`loadDocument` 用 `refs` 详情渲染底部引用区块）。
- **语义取舍（独立产品决策，不混入本次）**：「被 N 篇引用」当前用 `refs.length`（**全部条目，含死链**）；架构建议的「过滤 `resolved===true` / `ref_status==='normal'` 的有效引用数」语义不同。轻量化不做 → 保持 `refs.length` 现状（H3 测试锁定该行为）；若产品要「有效引用数」语义（死链不计入），需单独提需求。

---

## ✅ 已完成（2026-07-29 快照，以下为当时状态）

### I1. 加载动画（Splash Screen）
- 首次加载：M logo + MyKnowledge + 5 步进度条 + 冲刺 + 完成动画；非首次跳过；SPA 内导航不触发
- splash 抽成独立模块 `splash.js`；动画速度区分首页/非首页
- **设计约定**：进度条踩坑记录见 `.workbuddy/memory/MEMORY.md`

### I2. Sidebar 交互
- 三态：固定 / 收起 / hover 悬浮；16px 左边缘触发器，拖拽调整宽度 + 吸附 168px
- **设计约定**：sidebar 始终在 flex 流内，不跳出 absolute；面包屑☰按钮控制折叠/展开

### I3. Sidebar Footer 状态指示
- 三态状态灯：🟢 用户使用中 / 🟡 用户编辑中 / 🔴 AI 编辑中（基于 `store.systemStatus`）
- 状态灯可点击跳转 `#status` 页；footer 布局：版本号左侧、状态灯右侧

### B1. 仪表盘三区布局
- 指标卡片行（项目总数+四色圆点 + 文档总数+版本号）；公共知识区 / 项目区 / 归档区
- 各区空时灰色提示；`projectStats` 前端合并活跃+归档统计；card-icon 统一 28×28
- **设计约定**：头像两级优先（自定义 > 首字母）；时间 7 天内相对/7 天以上绝对；.md 后缀不显示

### B2. 项目卡片 hover 面板
- hover 300ms 展开面板（知识/子项目/归档三区）；点击文档→#doc，点击项目→#project
- **设计约定**：子项目无标签，归档保留 status badge；数据源按嵌套架构读三个子目录

### B3. 最近更新
- 附在仪表盘下方；7 天及以内相对时间，7 天以上绝对日期

### 项目子页面（#project/{path}）
- 头部 page-label 动态父项目面包屑 + 返回按钮；三区布局（知识/子项目/归档）+ 空状态
- store 三个独立数组：`projectDocs` / `projectSubprojects` / `projectArchived`
- 字段映射：`updated_at` → `modified`（后端 API 字段统一）

### 主题
- 防闪：head 同步 script 设 data-theme + colorScheme + 背景色；暗色 icon 改 Lucide 弯月

### C1. 合并 #view + #edit → #doc/{path} ✅
- 路由统一为 `#doc/{path}`；`editorComponent`+`viewerComponent` → `docComponent`
- `editingMode` store 状态控制；编辑切换不再走路由（点击正文触发）
- 工具栏：只读态 [编辑][删除]，编辑态 [放弃][保存]；Sidebar 🟡 用 `editingMode` 判断
- **注**：单 DOM 改造后"只读态/编辑态"由 `editable` 控制，本项为早期实现，行为已被单 DOM 取代

### D1-D4. Ref 引用体系 ✅
- D1 ref 链接 hover 浮层卡片（ref 摘要 / 外链 / 死链三态）；D2 底部"引用知识"区块；D3 表格圆角样式；D4 ref 空格路径修复
- 渲染机制：marked renderer 检测 `ref:`/`http(s)://` → ref-link / ext-link
- **注**：单 DOM 后 hover/点击迁移到 editor.dom 委托（findLink 按 href 协议识别）

### E. 编辑器（早期实现，大部分已被飞书化取代）
- 编辑锁 acquire/release/heartbeat（10 分钟无心跳自动释放）；自动保存 1s debounce；Ctrl+S 保存
- IndexedDB 草稿 + 离线恢复横幅；历史版本列表 + diff + 恢复
- AI 锁态遮罩（红色呼吸闪烁）+ 锁横幅；Toast 居中

### H2. 系统状态页（#status）✅
- 路由 + 状态页已实现（store.setView("status") + statusSummary）

### H3. 知识健康检查视图（#health）✅ 2026-08-14
- 规范来源：`docs/designs/kb-health/SPEC.md`（已定稿，唯一权威依据）
- 后端契约：`GET /api/diagnose`（真算+写 `.diagnose-result.json`，含 `generated_at`）、`GET /api/diagnose/saved`（读上次，含 `generated_at`）
- 前端实现：
  - 路由 `#health`（router.js）+ 侧边栏「知识健康检查」入口（垃圾箱下方）
  - 检查按钮两态：尚未检查=「开始检查」/ 有结果=「重新检查」；loading「刷新中...」
  - 进页先 `/api/diagnose/saved`：有 → 渲染上次结果 +「上次体检:本地时间」；无 → 空态「尚未检查」+ 检查按钮
  - 「重新检查」按钮常驻：调 `/api/diagnose` 覆盖结果；loading「刷新中...」+spinner；失败 toast 保留旧数据
  - 健康概览卡（徽标/三联数字/分组计数芯片）+ 按 type 分组列表（无问题组隐藏）+ 复杂区（needs_semantic 收敛）+ 空态/加载态
  - 严重度三色：high=danger / medium=warning / low=info（走 token，暗色自动适配）
  - 复杂区「复制 prompt 交 AI」：前缀已定稿（maint__knowledgebase_diagnose + write__ 系列）、Markdown bullet 全量 issue、`扫描文件：N 个` 结尾、不含 KB 根路径
- MVP 边界：不做分组批量修复按钮（修复主体是 AI）、不做轮询/SSE（仅手动重新检查）、不做 issue 行点击跳转
- 阶段 B 完成（2026-08-14）：非复杂分组修复交互 + lazy 按钮。后端契约 `/api/heal/move` + `/api/heal/rebuild`（已就绪）。
  - 非复杂分组（position/index/system）：issue 勾选框 + 组头全选（indeterminate）+ 组头单按钮（position→修复知识位置；index/system→重建索引）。无勾选 disabled；≥1 勾选可交互，只处理勾选项；已勾选行 `.is-checked` 高亮。
  - 修复确认弹窗（health-fix，复用 modal）：path 列表（最多 5 项折叠）+「确认执行」+「复制 prompt」+ 关闭。确认执行 → REST → toast → 自动重查 → 修复项消失。执行中「处理中...」+spinner 防重复。
  - lazy 按钮「我懒得看了，交给 AI 吧」（total_issues>0 显示）：复制全部问题清单 prompt（含复杂+非复杂，完整头部+maint 工具+扫描文件）+ toast。
  - metadata/ref/illegal 无勾选无按钮（走复杂区）；复杂区维持现状。
  - 后端 health-demo 演示项目仍保留（6 类错误脚手架）。
- 阶段 B 补强（2026-08-14）：修复进行中禁用所有修复相关操作。
  - store.js 新增 `isHealthHealing` getter；`toggleHealthSelect`/`toggleHealthGroupSelect`/`runHealthCheck`/`copyLazyHealthPrompt` 在修复中忽略点击。
  - `runHealthCheck({force:true})` 供修复成功后的内部自动重查绕过守卫。
  - index.html：勾选/全选/组头按钮/重新检查/开始检查/再次体检/lazy 按钮在 `isHealthHealing` 时 disabled。
  - 全选框 indeterminate 改用 `x-effect`（原 `:indeterminate.prop` 在 Alpine 未生效，已修正）。
  - 测试：补 6 用例（REST body 断言 / 自动重查 / 弹窗复制 prompt / 全选 indeterminate / 端到端闭环 / 修复中禁用）。
- 阶段 B 交付前补充（2026-08-14）：
  - `_writeClipboard` 改为同步手势栈优先 execCommand（修复非 https/file:// 下复制失败）。
  - `.btn-lazy-ai` 垂直 padding 对齐 `--space-2`（与重新检查按钮同高 36px）。
  - `.issue-group__action` 圆角统一 `--radius-md`（8px，替代 `.btn--sm` 的 4px）。
  - 进入页面/重查后默认全选可修复分组（`healthSelectAllFixable`，在 loadHealthSaved/runHealthCheck 调用）。
  - health-demo 重置为完整 6 类（position/metadata/index/ref/illegal/system 各≥1）。
- 阶段二完成（2026-08-15）：顶部就绪信号（替换 status-indicator）。
  - 后端契约：`/api/events`（SSE 事件带 type："write"|"diagnose"）、`/api/diagnose/saved`、MCP 自检广播 type="diagnose"。
  - 替换顶部 `status-indicator`（379-389 行）为就绪信号；`sidebar-footer__status`（301 行）保留 AI 状态不动。
  - 三态（SPEC §3.5，等长文本）：健康「知识状态健康」绿 / 存疑「N 个知识存疑」(有high红·无high黄) / 未检查「尚未触发检查」灰。
  - 可点击进 `#health`；hover 背景 `--bg-secondary` + 状态点 scale。
  - 更新机制：首次进入读 saved 初始化；SSE 订阅只对 type="diagnose" 响应（重读 saved），type="write" 忽略；#health 点重新检查后本地刷新；后端离线降级灰。
  - store.js：`readiness` 状态 + `readinessLabel/readinessDotClass/readinessTitle` getter + `loadReadiness/_syncReadinessFromHealth`。
  - 新增类：`.status-indicator__dot--success/--danger/--warning/--muted` + `.status-indicator--readiness`（components.css，复用 token）。
- 测试：`tests/frontend/test_health.py`（49 用例：A5 + 阶段 B + 阶段二就绪信号）+ `test_smoke.py` 22 用例回归通过 = 71 全绿

---

## 🐛 已知问题

| 问题 | 现象 | 状态 |
|------|------|:--:|
| 刷新闪黑 | 暗色系统+亮色主题时，刷新瞬间闪黑 | 浏览器级，前端不可控 |
| 刷新一帧旧页面 | 刷新时旧页面内容闪现一帧 | 待研究 bfcache/pageshow |
| "Node cannot be found" warning | 进页面即出现 | 待定位（已入待办 P0） |
| 沉浸式翻译扩展报错 | content_main.js token invalid（浏览器插件自身） | 与我们无关，忽略 |

---

## ✅ 已恢复（2026-07-28 17:07）

| 丢掉的改进 | 状态 | 备注 |
|-----------|:----:|------|
| app.js 拆分为 components/ | ✅ | `js/components/` 7 文件 |
| build.py JS 语法检查 + CDN 检查 | ✅ | `node --check` + curl 检测 CDN |
| viewer__summary 移入 header、加「摘要」标签 | ✅ | |
| ref 链接 hover 浮出卡片（三种链接类型） | ✅ | 单 DOM 后迁移 editor.dom 委托 |
| 编辑态点击区域外退回只读 | ✅ | 单 DOM 后 document capture 监听 |
| utils.js 删除死代码 md5（含 gravatarUrl） | ✅ | authorAvatar 纯首字母 |

## 🆕 新增（2026-07-29）

| 功能 | 状态 | 说明 |
|------|:--:|------|
| 后端完成外链解析 | ✅ | 前端改用后端 `type: "ref"\|"external"` |
| 外链规则（代码块/行内代码/图片跳过） | ✅ | |
| 死链改为软警告 | ✅ | 保存时死链不 400 |
| 编辑保存链接零差异 | ✅ | Link parseHTML 强制字符串（backport 2.6.0 fix） |
| 编辑保存往返测试 | ✅ | Node 22 用例，`check_build.py` 自动运行 |
| CMD+S / Ctrl+S 保存 | ✅ | 锁定时禁用 |
| AI 锁态遮罩 / 锁横幅 / Toast 居中 | ✅ | |
| 编辑器退出销毁重建 | ✅ | 早期方案；单 DOM 后改为复用（不销毁） |
| 分享导出弹窗 + /api/export | ✅ | 项目选择 + 加密 + 下载 |
| 乐观锁（后端就绪） | ✅ 待前端验证 | GET 返回 `version`，PUT 带 `expected_version`，冲突返回 409 |
| MCP 状态指示器 | ✅ | top-header 15s 轮询 |
| Headbar 面包屑重设计 / 文档页删除按钮 | ✅ | |
| 路由统一 view→doc、URL 清洁化 | ✅ | hashEncode 仅编码 `/` |
| CSS Grid hover 面板修复 / 面板纯 DOM 渲染 | ✅ | align-items:start；无 Alpine 响应式模板 |
| 行内 code 样式 / 页面 breadcrumb 加深 / 表格圆角 | ✅ | |
