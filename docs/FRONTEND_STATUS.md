# MyKnowledge 前端实现状态

> 最后更新：2026-07-28 16:52
> 设计决策详见：`docs/FRONTEND_INTERACTION_FEEDBACK.md`（设计原文备查，包含补充分支场景与讨论过程）

---

## ✅ 已完成

### I1. 加载动画（Splash Screen）
- 首次加载：M logo + MyKnowledge + 5 步进度条 + 冲刺 + 完成动画
- 非首次（同一 tab session）：跳过动画，splash 遮罩秒关
- SPA 内导航不触发 splash
- splash 抽成独立模块 `splash.js`
- **动画速度区分首页/非首页**：
  - 首页每步 60-90ms 随机
  - 非首页前3步 0-30ms + 后2步 30-60ms
- **设计约定**：进度条踩坑记录见 `.workbuddy/memory/MEMORY.md`

### I2. Sidebar 交互
- 三态：固定 / 收起 / hover 悬浮
- 16px 左边缘触发器，拖拽调整宽度 + 吸附 168px
- **设计约定**：sidebar 始终在 flex 流内，不跳出 absolute；面包屑☰按钮控制折叠/展开

### I3. Sidebar Footer 状态指示
- 三态状态灯：🟢 用户使用中 / 🟡 用户编辑中 / 🔴 AI 编辑中（全局统一，基于 `store.systemStatus`）
- 状态灯可点击跳转 `#status` 页，删除了导航区重复的「状态」按钮
- footer 布局：版本号左侧，状态灯右侧，同行两端对齐
- 版本号显示格式「知识库版本 xxxxxxx」，已增强醒目度（font-weight:500, 10px）
- `status-dot--danger` 新增红色圆点 class

### B1. 仪表盘三区布局
- 指标卡片行：项目总数+四色状态圆点 + 文档总数+版本号
- 公共知识区：`file-pen` icon，字段：名称+摘要+日期+作者
- 项目区：`folder-open` icon，字段：名称+摘要+日期+文档数（readme frontmatter 无 author，不展示作者）
- 归档区：`folder-open` icon，字段同项目 + status badge，空时隐藏此分区
- 各区空时显示灰色提示文字（「暂无文档」「暂无子项目」「暂无归档」）
- `projectStats` 前端合并活跃+归档统计
- card-icon 统一 28×28，accent-subtle 底，stroke 1.5
- **设计约定**：头像两级优先（自定义 > 字母首字母）；时间格式 7天内相对、7天以上绝对日期；文件名后缀 .md 不显示

### B2. 项目卡片 hover 面板
- hover 300ms → 卡片内平滑展开面板，内容向下推开其他卡片
- 三区：知识（common-knowledge/ 内文档）/ 子项目（projects/ 内子目录）/ 归档（archive/ 内子项，带 status badge）
- 选项缩进 30px（分区标题 14px），归档项名称+状态 badge 同行 flex 布局
- 点击文档→#doc，点击项目→#project，移出 150ms 收起
- 点击卡片本身跳转 #project/{path}
- **已修复**：数据源按嵌套架构读三个子目录（后端已配合返回文件 `summary` + 测试数据完善）
- **设计约定**：子项目无标签（均为 active），归档保留状态 badge（已完成/已取消/已废弃）
- **测试数据**：知识区 2 篇文档 + 子项目 2 个 + 归档 2 项（用户认证系统/completed，数据迁移工具/cancelled）

### B3. 最近更新
- 已在 B1 中附在仪表盘下方
- **设计约定**：7天及以内相对时间，7天以上绝对日期（yyyy-mm-dd）

### 项目子页面（#project/{path}）
- 头部：page-label 动态显示父项目面包屑（可点击跳转，多级用 / 分割），左箭头 ← 返回上级（hover 加深 `#6366f1` + 淡紫背景）
- 三区布局（类似仪表盘，无指标卡片）：
  - **知识**：`common-knowledge/` 文档卡片，字段：名称+摘要+日期+作者
  - **子项目**：`projects/` 项目卡片，字段：名称+摘要+日期+状态标签（active 不显示）
  - **归档**：`archive/` 卡片，字段：名称+badge+摘要+日期
- 各分区空时显示灰色提示文字
- 所有分区都空时显示统一空状态+「新建文档」按钮
- store 改为三个独立数组：`projectDocs`、`projectSubprojects`、`projectArchived`
- `statusLabel` 提取为全局函数（`utils.js`），`projectComponent` 新增 `goToProject` 方法
- 字段映射修复：`updated_at` → `modified`（后端 API 返回字段名统一）

### 主题防闪
- head 同步 script 设 data-theme + colorScheme + 背景色
- html inline `style="background:#fafafa"` 默认亮色

### 主题切换图标
- 暗色模式 icon 从圆点改为 Lucide 弯月（fill 版本），与浅色太阳 icon 风格统一

---

## 🔄 设计中（决策已定，待实现）

### A1. Setup 页样式
- Raycast 毛玻璃风格全屏居中弹窗，首次进入时默认主题，无需为每套主题做设计

### A2. 服务离线处理（12 场景全覆盖）
- **统一文案**：「服务已断开」
- **三级响应**：
  - 顶部横幅：编辑器打字/浏览列表/只读文档（IndexedDB 兜底）
  - 全屏阻断弹窗：导航到新页面/冷启动离线无草稿/Setup 页
  - toast 提示（3s 消失）：点击操作按钮（新建/删除/保存）
- 场景 5b：冷启动离线 + 有 IndexedDB 草稿 → 不阻断，直接进编辑恢复模式
- 场景 7：网络恢复 → 横幅消失 + 草稿自动同步 + 0.36s 淡出
- 场景 11：关标签页 → beforeunload 写入 IndexedDB + 释放编辑锁，不弹确认窗
- 场景 12：SSE 断开 → 5s 静默重连，3 次失败 → header 小黄点；锁轮询静默吞掉

### A3. 头像展示
- 两级优先：自定义图片（1:1 裁切，Base64 存浏览器）→ 字母默认（昵称首字母，紫色圆底）
- 点击头像弹出下拉：查看信息 / 修改头像 / 设置
- 去掉 Gravatar（本地知识库无意义）

### C3. 空项目处理
- 项目通过 AI/MCP 首次写入时自动创建，不会出现空项目
- 分区内（common-knowledge/projects/archive）可能无子项，空时显示灰色提示文字
- 前端「新建」按钮当前只创建单个 `.md` 文档，不创建完整项目结构

---

## ⏸️ 未开始

### C1. 合并 #view + #edit → #doc/{path} ✅ 已完成
- 路由 `#view/{path}` 和 `#edit/{path}` 已删除，仅保留 `#doc/{path}`
- `editorComponent` + `viewerComponent` → 统一 `docComponent`
- `editingMode` store 状态控制：false→marked 只读 / true→TipTap 编辑
- 编辑切换不再通过路由跳转，改为 `editingMode = true`（点击正文触发）
- 工具栏：只读态显示 [编辑] [删除]，编辑态显示 [放弃] [保存]
- Sidebar `systemStatus` 改用 `editingMode` 判断 🟡 用户编辑中
- 后续增强（拖拽、斜杠命令）留待 Step 2

### C2. 文档卡片 hover 浮出操作按钮
- hover 时右上角浮出「重命名」+「✕ 删除」（0.18s 淡入+上移），删除需二次确认弹窗
- **设计约定**：删除弹窗红边框 + 文档名 + 不可撤销提示 + 取消/确定红色按钮

### D1. Ref 引用浮层
- 默认：标题+摘要+路径+作者日期+「打开文档」链接
- hover 展开：摘要 + 前 200 字预览 + 总字数 + 打开链接
- 设计原则：轻量扫一眼，不点不跳

### D2. 文档操作 header 按钮
- （设计细节见 C1，已在 C1 中合并引用）

### E. 编辑器
- 编辑锁：acquire/release/heartbeat 端点，10 分钟无心跳自动释放
- 自动保存：1s debounce 静默保存，`:is-typing` 标注
- Ctrl+S/Cmd+S 手动保存
- IndexedDB 草稿：DB `MyKnowledgeDrafts`，Store `drafts`，Key=文档 path
- 离线恢复：服务恢复后检测草稿 → 横幅「[立即同步] [忽略]」
- 历史版本：版本列表 + diff 预览 + 「恢复此版本」→ 二次确认
- **设计约定**：E1 ref 链接编辑处理（待讨论），E2 元信息展示时机（待讨论）
- 浏览器崩溃：结合 E3 本地临时存储兜底

### F. 主题系统
- 非 Raycast 主题的暗色（优先级较低）
- 主题切换需过渡动画，越具呼吸感越好

### H2. 系统状态页
- 卡片式布局，两行：
  - 指标卡：项目数（仅根目录 projects/）+ 四色状态圆点 + 全局文档总数 + KB 版本号
  - 卡片：最近更新列表（文档名+摘要+日期+作者）
- 不显示锁状态（header 已有）

### 动态 icon 匹配
- `cardIconSvg()` 函数已写好（关键词→SVG 映射），当前未接入

### G. 响应式 & 移动端（低优先级）
- 暂不考虑移动端

### H3. 快捷键（低优先级）
- 未来考虑

---

## 🐛 已知问题

| 问题 | 现象 | 状态 |
|------|------|:--:|
| 刷新闪黑 | 暗色系统+亮色主题时，刷新瞬间闪黑 | 浏览器级，前端不可控 |
| 刷新一帧旧页面 | 刷新时旧页面内容闪现一帧 | 待研究 bfcache/pageshow |

## ⚠️ 回退记录（2026-07-28 16:48）

因 `git checkout HEAD -- frontend/` 误操作，以下今日完成的修改全部丢失：

| 丢掉的改进 | 状态 |
|-----------|:----:|
| viewer__summary 移入 header、加「摘要」标签 | ❌ 需重做 |
| ref 链接 hover 浮出卡片（向上浮现动画） | ❌ 需重做 |
| 编辑态点击区域外退回只读 | ❌ 需重做 |
| dashboard metric-card 改用 `$store.app.*` 直算 | ❌ 需重做 |
| app.js 拆分为 components/ | ❌ 需重做 |
| build.py 增加 JS 语法检查 + CDN 可达性检查 | ❌ 需重做 |
| utils.js 删除死代码 md5（已恢复） | ❌ 需重做 |

已确认 HEAD 代码可以正常运行，页面可进入。
