# MyKnowledge 前端实现状态（唯一状态/待办文档）

> 最后更新：2026-08-13
> 说明：本文件为前端**唯一**状态文档（原 `docs/TODO.md` 已并入本文件的"待办清单"章节并删除）。
> 设计决策详见：`docs/archive/FRONTEND_INTERACTION_FEEDBACK.md`（历史设计确认，已实现，归档备查）

---

## 📋 待办清单（按优先级排序，完成即划掉）

### P0 数据安全 / 正确性（优先）

- [x] **锁状态过期不刷新 UI** ✅ 已解决（2026-08-04 验证）：`store.init()` 有 15s 轮询 `checkLock` + doc.js `Alpine.effect` 监听 `isLocked` 响应遮罩
- [x] **"Node cannot be found" warning** ✅ 已解决（2026-08-04 验证）：单 DOM 改造后编辑器复用（不再销毁重建），进编辑/退出/切文档 console 干净
- [x] **数据一致性（乐观锁）** ✅ 已完成（2026-08-05 双窗口实测通过）：后端 `version=sha256(f"{summary}\x00{content}")[:12]` + 409 冲突；前端保存带 `expected_version`、编辑中收到 SSE 变更主动弹 diff 弹窗（内容不静默覆盖）、冲突可视化（两栏行号 diff + summary 差异 + 保留我的/采用服务端/取消）；detail 见 `docs/backend-optimistic-lock-prompt.md`

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
- `tests/frontend/test_paste_markdown.py`（P 系列 24 用例）；场景矩阵 `doc/test/testing-plan-paste-markdown.md`（8 批 48 场景）
- 前端全量 **71/71**（edit_switch 42 + hover 5 + paste 24）+ 后端 **337/337**

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
