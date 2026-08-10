# 编辑态切换 · 成体系测试 Plan

> 状态：**进行中** — 2026-08-07 定稿 → 2026-08-09 更新（批 1 已自动化固化）。
> 背景：编辑态 ↔ 导航切换区域连续出现多个 bug（内容残留、误 rename、误删、高亮错乱）。
> 结论（2026-08-09）：**全部场景走 Playwright 自动化**（不再手测），复用同一套完整测试方法。

## 0. 完整测试方法（所有场景统一使用）

```
1. 后端本地 8080 运行中（.myknowledge_test 测试库），浏览器 headless Chrome
2. fixtures（tests/frontend/conftest.py）：static_server / browser / test_docs（隔离创建清理）/ page（toast 捕获）
   ⚠️ static_server 用 index.html（开发版，外部 js 实时加载）——index.standalone.html 被 .gitignore
   忽略且无构建脚本（本地手工内联版），改前端源码不会同步，测试加载会拿到旧版 JS（S19/S20 曾误判）
3. helper（edit_switch_helpers.py）：open_doc → enter_edit(入口) → apply_mod(修改) → navigate(切走)/exit_inplace(原地保存)
   → assert_*(保存/残留/rename/高亮/toast/加载次数)
4. 防重断言（api_tracker.ApiTracker）：一次导航主加载 ≤1 轮（doc/refs/meta 各 ≤1）、一次保存 PUT ≤1
5. 差异校验：API 对比（前端渲染 vs 后端 GET /api/document），不做 git diff 硬校验
6. 竞态注入：page.route 延迟/伪造响应（delay_route / 409 mock / 锁 mock）
7. 测试文档：新建固定成对（test-edit-auto-*，跨项目）+ 子项目 fixture（测试子项目 readme 写文件），测试后清理
```

## 1. 三个维度

### ① 编辑入口 E（进入编辑的方式）
| 代号 | 入口 |
|---|---|
| E1 | 点击文档正文（view 态点击编辑器内部） |
| E2 | 点击标题输入框 |
| E3 | 点击摘要输入框 |

### ② 编辑态修改状态 M
| 代号 | 状态 |
|---|---|
| M0 | 无修改（进入立即切走） |
| M1 | 只改正文 |
| M2 | 只改标题（合法 rename 场景） |
| M3 | 只改摘要 |
| M4 | 改正文 + 标题（组合） |

### ③ 切换目标 T（从编辑态导航到）
| 代号 | 目标 | 方式 |
|---|---|---|
| T1 | 同项目另一文档 | 侧栏项目树文档行 |
| T2 | 跨项目文档 | 侧栏项目树文档行 |
| T3 | 顶层项目页 | 侧栏项目行 |
| T4 | 子项目页 | 侧栏子项目行 |
| T5 | 仪表盘 | 侧栏入口 |
| T6 | 垃圾箱 | 侧栏入口 |
| T7 | 引用链接文档 | 正文 ref 链接点击 |
| T8 | 返回上一文档 | back 按钮 / 面包屑 |
| T9 | 直接改 URL hash | 地址栏/外部链接 |

## 2. 检查点（每场景 6+3 项）

```
① 原文档：编辑模式已关闭？修改内容已保存？（对照 M 状态）
② 原文档：git diff 只有预期修改？文件名未被篡改（rename bug）？
③ 侧栏高亮：当前项 text+bg、直接父级 text-only、更上层恢复正常
④ 当前页：前端渲染内容 = 后端 GET 返回内容（防"只前端变后端没变"）
⑤ 当前页：标题/正文/目录/引用面板渲染符合预期
⑥ 回原文档：渲染正确、已保存的修改保留
⑦ rename 检查：文件名 = 预期（M2 时为新标题，M0/M1/M3 时不变）
⑧ summary 检查：原文档摘要不被新文档污染
⑨ toast 检查：符合预期（已保存/已改名/错误，无异常弹窗）
```

## 2.1 重复加载检测（每个场景必查）

> 背景：本项目"某资源被多次加载"是高频 bug 类型——一次导航/保存应只触发
> **1 轮**文档加载（doc+refs+meta 各 1 次），实测历史上有 2-4 轮。

**工具**：`tests/frontend/api_tracker.py` 的 `ApiTracker`（Playwright 共用）

```python
tracker = ApiTracker(page)                    # 绑定后自动记录 /api/ 请求
tracker.reset()                               # 动作前清零
...执行动作（编辑→切换）...
tracker.assert_document_loads(doc_path, max_loads=1, label="切到 C")  # 主加载 ≤1
tracker.assert_method_count("PUT", 1, path_contains="document")       # 保存 ≤1
```

**规则**：
- 一次导航：目标文档主加载 ≤1 次（`doc`/`refs`/`meta` 各 ≤1）
- 一次保存：`PUT /api/document/*` ≤1 次（防双保存）
- 阈值放宽的场景必须注明原因（如远端多客户端同步测试）

## 3. 场景矩阵（执行状态）

### 批 1：核心场景 ✅ 已自动化（test_edit_switch.py::TestBatch1，15/15 通过）

| # | 场景 | 自动化用例 | 状态 |
|---|---|---|---|
| S1 | E1+M0→T1 | test_s1_basic_switch_none | ✅ |
| S2 | E1+M1→T1 | test_s2_body_saved_no_residue | ✅ |
| S3 | E1+M2→T1 | test_s3_rename | ✅ |
| S4 | E1+M3→T1 | test_s4_summary_saved_not_polluted | ✅ |
| S5 | E1+M0→T3 | test_s5_project_highlight | ✅ |
| S6 | E1+M1→T5 | test_s6_dashboard_no_residue | ✅ |
| S7 | E1+M1→T8 | test_s7_back_keeps_changes | ✅ |
| S8 | E1+M0→T2 | test_s8_cross_project | ✅ |
| S9 | E1+M1→T1→T2 | test_s9_quick_switch_no_residue | ✅ |
| S10 | E1+M0→T7 | test_s10_ref_link | ✅ |
| — | 竞态注入（保存晚于加载） | test_s2_race_delayed_save | ✅ |

#### 批 1 补充：原地保存场景 ✅ 已自动化（1920998 手测发现的摘要回滚必现场景）

| # | 场景 | 自动化用例 | 状态 |
|---|---|---|---|
| S4b | 改摘要 → 原地保存 | test_s4b_summary_inplace_no_rollback | ✅ |
| S4c | 连续 3 次原地保存 | test_s4c_summary_multi_inplace | ✅ |
| S4d | 改正文 → 原地保存 | test_s4d_body_inplace | ✅ |
| S4e | 改标题 → 原地保存（rename） | test_s4e_title_inplace_rename | ✅ |

**三类字段更新路径（决定回滚风险）**：
| 修改对象 | 显示数据来源 | 原地保存回滚风险 |
|---|---|---|
| 正文 | `htmlContent`（exitEdit 保存后快照编辑器 DOM） | 无 |
| 标题 | `document.title`（`_maybeRename` 自行更新 + replaceState hash） | 无 |
| 摘要 | `document.summary`（依赖 saveDocument 合并后端返回） | **有**——已用 body.summary 补齐修复 |

### 新建文档：归属选择器 ✅ 已自动化（test_edit_switch.py::TestNewDocParent，8/8 通过）

| 用例 | 覆盖 |
|---|---|
| test_candidates_full_set_no_garbage | 候选全量 7（公共知识+6）、无 archive/common-knowledge/projects 垃圾项 |
| test_candidate_summary_displayed | 下拉项第二行项目摘要（非空）、公共知识=根 readme 摘要 |
| test_search_triggers_on_type | 输入触发 kind=projects 搜索（同长度重输也触发） |
| test_delete_also_triggers_search | 删除文字也触发搜索、删空回浏览 |
| test_no_duplicate_loads_on_reopen | 开关弹窗 0 重复加载（缓存守卫）+ 快速输入合并 1 搜索请求 |
| test_special_chars_no_injection | 特殊字符/HTML 注入无 XSS 无弹窗 |
| test_click_without_change_does_not_search | 点击（内容未变）不触发搜索 |
| test_no_match_shows_placeholder | 无匹配占位 / 有匹配 / 浏览三态切换 |

### 新建文档：创建后跳转编辑态 ✅ 已自动化（test_edit_switch.py::TestNewDocCreate，1f8b15b 三 bug 固化）

| 用例 | 覆盖 |
|---|---|
| test_create_training_enters_edit_with_values | 归属=Training：hash 直达 #edit/ + enterEdit 生效（标题框可见）+ 标题/摘要填充非空 + sidebar 出现新文档行 + 后端 API 对比 |
| test_create_default_parent_root | 默认归属"公共知识"→ 根 common-knowledge 创建，直达编辑态 |

### 批 2：边界场景 ✅ 已自动化（test_edit_switch.py::TestBatch2，9 pass + 1 xfail）

| # | 场景 | 自动化用例 | 状态 |
|---|---|---|---|
| S11 | E2+M0→T1 | test_s11_title_focus_switch_no_rename | ✅ |
| S12 | E3+M0→T1 | test_s12_summary_focus_switch_not_polluted | ✅ |
| S13 | E1+M0→T4 | test_s13_subproject_page_highlight | ✅ |
| S14 | E1+M0→T6 | test_s14_trash_no_residue | ✅ |
| S15 | E1+M2→T8（改标题后 back） | test_s15_rename_then_back | ⚠️ xfail（已知 bug，见下） |
| S16 | E1+M4→T1 | test_s16_body_title_combo | ✅ |
| S17 | E1+M1→T9 | test_s17_url_switch_saves | ✅ |
| S18 | E1+M0→A(再进) | test_s18_reenter_edit_loop | ✅ |
| S19 | 编辑态点目录 TOC | test_s19_toc_click_keeps_edit | ✅（前端已修） |
| S20 | 编辑态点项目树 chevron | test_s20_chevron_keeps_edit | ✅（前端已修） |

**批 2 基建**（helper）：`navigate("subproject")`（树内 data-project-path）、`click_toc`、
`toggle_project_chevron`；conftest 增子项目 fixture（测试子项目 + readme 写文件 + DOC_SUB）。

**S19/S20 前端修复（2026-08-09）**：`onDocClick` 原来"点编辑器外一律退出编辑"，
点 TOC/chevron（文档内辅助操作）也被误伤退出。修复：排除 `.sidebar-toc__list` /
`.sidebar-project__chevron` / `.sidebar-tree__chevron` 内的点击不退出编辑。

**S15 已知 bug（xfail 记录，待修复）**：改标题 rename 成功后，`_maybeRename` 的
replaceState 在 await 后判断 hash 已切走而跳过 → 历史栈仍是旧路径 → back 回
`#doc/旧名`（后端 404）+ bfcache 恢复旧 DOM 显示旧标题。完整修复需后端 rename
映射（old→new 跳转）支持，前端待排期。测试标 `xfail(strict=True)`——修好后自动提示去掉标记。

### 批 3：异常/竞态场景 ✅ 已自动化（test_edit_switch.py::TestBatch3，6/6 通过）

| # | 场景 | 自动化用例 | 状态 |
|---|---|---|---|
| S21 | isLocked 时切换 | test_s21_locked_blocks_switch | ✅（前端已修，见下） |
| S22 | A→B→A 快速往返 | test_s22_quick_roundtrip | ✅ |
| S23 | 编辑态点删除按钮 | test_s23_delete_from_edit | ✅ |
| S24 | 编辑态 + 项目树自动展开 | test_s24_deep_doc_auto_expand | ✅ |
| S25 | 保存 409 冲突时切换 | test_s25_409_conflict_keeps_edit | ✅ |
| S26 | 连续 5 次快速切换 | test_s26_five_rapid_switches | ✅ |

**批 3 注入 helper**（edit_switch_helpers.py）：`inject_lock`/`release_lock`（route mock /api/lock +
checkLock，S21）、`mock_409`（拦截 PUT 返回 409，S25）、`delete_doc_from_edit`（编辑态删除+模态确认，S23）。

**S21 前端 bug 修复（2026-08-10，测试驱动发现）**：锁定语义 = AI 编辑中用户编辑被锁保护。
原来 exitEdit/_autosave 都有 `isLocked` 守卫，但切走时 `Alpine.effect`（currentView 变化）触发
`_saveAndDestroy` 兜底保存——**缺 isLocked 守卫** → 锁定时导航离开仍把用户编辑写入后端，
覆盖 AI 正在编辑的内容。修复：`_saveAndDestroy` 顶部加 `if (store.isLocked) return`。

**测试稳定性经验**：S21 用快速路径（改正文后立即锁注入）而非 apply_mod——全量回归 CPU 忙时
autosave 的 1s 定时器可能先于锁生效触发保存，导致误报。

## 4. 现有测试覆盖（2026-08-09 现状）

| 现有测试 | 覆盖 | 状态 |
|---|---|---|
| tests/frontend/test_edit_switch.py::TestBatch1 | 批 1（S1-S10 + S4b-e + 竞态注入） | ✅ 15/15 通过 |
| tests/frontend/test_edit_switch.py::TestNewDocParent | 归属选择器 8 用例 | ✅ 8/8 通过 |
| tests/frontend/test_edit_switch.py::TestNewDocCreate | 创建后跳转编辑态 2 用例 | ✅ 2/2 通过 |
| tests/frontend/test_edit_switch.py::TestBatch2 | 批 2（S11-S20） | ✅ 9 pass + 1 xfail（S15 已知 bug） |
| tests/frontend/test_edit_switch.py::TestBatch3 | 批 3（S21-S26） | ✅ 6/6 通过 |
| tests/frontend/test_smoke.py（Playwright） | 静态渲染/路由/主题/垃圾箱视图 | ✅ |
| tests/（后端 pytest） | 存储/锁/分享/垃圾箱/MCP 写入等 | ✅ |

**结论**：测试方法已成熟（Playwright E2E + ApiTracker 防重 + API 对比 + helper 库），
批 1/批 2/批 3/归属/创建已全部自动化（42 用例：41 pass + 1 xfail S15）。

## 5. 执行计划（更新版）

```
✅ 阶段 1：测试基建（conftest fixtures + helpers + ApiTracker）——已完成
✅ 阶段 2：批 1（S1-S10 + S4b-e + 竞态）固化为 Playwright 自动化——已完成，15/15
✅ 阶段 3：归属选择器（TestNewDocParent 8 用例）——已完成，8/8
✅ 阶段 4：创建后跳转编辑态（TestNewDocCreate 2 用例）——已完成，2/2
✅ 阶段 5：批 2（S11-S20）自动化——已完成，9 pass + 1 xfail（S15 已知 bug 待修）
✅ 阶段 6：批 3（S21-S26）自动化——已完成，6/6（S21 触发的 _saveAndDestroy 锁守卫 bug 已修）
📋 阶段 7：纳入全量回归（pytest tests/ -q）+ S15 bug 修复（需后端 rename 映射）
```

## 6. 已确认项

- [x] 测试文档：**新建固定成对**（test-edit-auto-*，跨项目），测试后清理
- [x] S23 编辑态删除：删除按钮 **edit 态保留可见**（index.html:392 `x-show` 含 edit），
      点击 → 自动退出编辑（保存）→ 弹删除确认框 → 确认删除进垃圾箱
- [x] 差异校验：**API 对比**（渲染 vs 后端 GET），不做 git diff 硬校验
- [x] 所有场景统一用 Playwright 自动化（2026-08-09 确认，不再手测）
