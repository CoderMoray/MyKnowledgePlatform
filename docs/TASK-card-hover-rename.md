# 前端任务：文档卡片 hover 重命名（临时任务单）

> 状态：📋 待前端 agent 认领 | 创建：2026-08-13
> 主负责：前端 agent（本任务单自包含，无需翻历史会话）

## 一、任务目标

在 **dashboard 公共知识 / 项目视图「知识」的文档卡片** 上提供 **重命名** 交互——
用户在卡片上 hover 后可对文档重命名（复用现有 rename 链路，而非另造一套）。

**背景**：卡片 hover 体系已具备「正文预览 / ref 链接 / 引用行 / 删除按钮（delete-doc 模态）」，
删除已完成（见下方现状），**重命名是缺口**。

## 二、需求（交互设计，待定项见第五节）

1. **入口**：卡片 hover 时出现重命名入口（建议与删除按钮并列，hover 右上角浮出；或复用卡片标题点击进编辑后改标题）
2. **流程**：点重命名 → 输入新标题（建议弹小模态/输入浮层，参考 delete-doc 模态模式）→ 确认 → 调 rename → 卡片/侧栏/路径同步更新
3. **校验**：复用 `MykRename.titleError`（非法字符提示 toast，warning）
4. **失败处理**：rename 失败（后端错误/冲突）→ toast 提示，不破坏卡片状态
5. **成功后**：刷新当前视图的文档列表（卡片标题更新）+ 侧栏树刷新 + 若当前打开的就是该文档则同步 currentPath

## 三、现状知识（必须先读，避免重复造轮子）

### 已有 hover 体系（8-11 完成，提交 d9659f1 同批）
- 卡片结构：摘要常显 + hover 下拉展开正文预览
- `openDocPreview`（renderer.js）：预览渲染（marked 取文本、分行、200 字截断、4 行省略号）
- 预览内 `ref:` 链接可点；底部「被 N 篇引用」行（0 不显示）
- 删除按钮（hover 浮出）→ `delete-doc` 确认模态（modal.js）
- 预览缓存失效：`invalidateDocPreviewCache`（store.js）——编辑/重命名后需调用

### 已有重命名机制（编辑态标题变化触发，doc.js `_maybeRename`）
- 触发：编辑态改标题 → 保存 → `_maybeRename(oldPath, baseTitle, updateStore)`（doc.js:1730）
- 链路：`MykRename.titleError(newTitle)` 校验 → `MykRename.shouldRename` → `api.renameDocument(oldPath, newName)` → `MykRename.buildNewPath` → 刷新
- **卡片重命名应复用这套**（MykRename + api.renameDocument），不新建 rename 逻辑
- 相关：任务 #29 曾做「doc.js _maybeRename 刷新侧栏树 + toast 带文档名」（`refreshProjectTree` 在 store.js）

### 相关文件
| 文件 | 职责 |
|---|---|
| `frontend/js/renderer.js` | `openDocPreview`（预览渲染）、`detectBlockMarkdown` |
| `frontend/js/components/doc.js` | `_maybeRename`（重命名链路）、编辑器 |
| `frontend/js/components/modal.js` | delete-doc 模态（重命名模态可参考此模式）|
| `frontend/js/store.js` | `invalidateDocPreviewCache`、`refreshProjectTree` |
| `frontend/js/api.js` | `renameDocument` API |
| `frontend/js/utils.js` | `MykRename`（titleError/shouldRename/buildNewName/buildNewPath）|

### 测试现状（tests/frontend/test_doc_card_hover.py，H1-H5）
- `hover_docs` fixture（无空格路径根公共知识文档 hover-ref-a/b/c）
- H1 预览渲染 / H2 ref 可点 / H3 引用行 / H4 编辑保存后预览更新 / H5 删除按钮模态
- **重命名应补 H6**（hover 重命名 → 输入新标题 → 确认 → 卡片/侧栏更新 + 后端路径变更）
- 场景矩阵：`doc/test/testing-plan-paste-markdown.md`（粘贴）与 `testing-plan-edit-switch.md`（编辑切换/H1-5）——重命名用例建议加进 hover 测试文件

## 四、验收标准

1. hover 卡片出现重命名入口 → 点击弹输入 → 输入新标题确认 → **后端文档路径变更**（GET 旧路径 404，新路径 200）
2. 卡片标题、侧栏树、`invalidateDocPreviewCache` 同步（重命名后 hover 预览正常）
3. 非法标题（`MykRename.titleError` 命中）→ toast warning，不执行 rename
4. 失败（后端错误）→ toast 提示，卡片状态不破坏
5. 若当前打开文档正是被重命名文档 → currentPath/URL 同步
6. 新增自动化测试（H6 或同风格）通过；全量前端回归（71 用例）不回归

## 五、待定项（实现前需与用户确认或自行选合理方案并说明）

1. **入口形式**：hover 浮出「重命名」文字按钮（与删除按钮并列）vs 标题点击进入重命名态？
2. **输入方式**：弹小模态（参考 delete-doc）vs 卡片标题原地变 input？
3. **与编辑态 rename 的关系**：卡片重命名是否也走 `_maybeRename` 的 titleError/shouldRename 语义
   （建议复用，保持一致）

## 六、约束

- 仅改前端（frontend/ + tests/frontend/）；rename 后端 API 已存在（`api.renameDocument`）
- 复用现有链路（MykRename / modal 模式 / invalidateDocPreviewCache），不另造
- 提交遵循项目规范；测试先行（先写 H6 红色 → 实现 → 转正）
- 完成后更新 `docs/FRONTEND_STATUS.md` 待办（划掉「卡片 hover 重命名」）
