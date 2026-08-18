# 阶段三前端实施：引导页三步向导 + 配置 modal 3 分组

## 任务概述
实现 MyKnowledge 阶段三前端：
1. **引导页**：扩展现有 setup 视图为三步向导（身份 → AI 协作初始化 → 完成）
2. **配置 modal**：user-menu「设置」入口，左导航 3 分组（账号/通用/AI 协作）+ 右多卡片
3. 半自动化交互：前端按钮 → POST → 刷新 GET → toast；失败走「复制 prompt 给 AI」兜底

后端契约已就绪（commit 42f785e + b6d258a）：GET/POST `/api/client-config`。

## 决策确认（已确认）
- **平台**：硬编码两平台 claude/codebuddy（与后端 `PLATFORMS` 严格一致）
- **引导页**：完整三步向导（SPEC §3.6）
- **配置逻辑**：引导页 Step2 与配置 modal 完全复用同一套 store 方法 + clientConfig 状态

## 步骤分解与状态
1. ✅ api.js：新增 `getClientConfig()` / `setClientConfig(platform, kind)`
2. ✅ store.js：新增 clientConfig 状态 + settingsGroup + guideStep + guideForce + 方法（loadClientConfig/configureClient/copyClientPrompt/openSettings/rerunGuide/isClientConfiguring/clientStatus/guideConfigItems/guideSummary）
3. ✅ modal.js：setup 三步向导逻辑（saveSetup→Step2, guideNext/guidePrev）+ 配置 modal 逻辑（settingsNav/saveSettingsIdentity/configureAi/copyAiPrompt）+ init 监听 settings/setup
4. ✅ index.html：user-menu「设置」入口；setup 三步向导（guide-steps + Step1身份/Step2AI协作/Step3完成）；settings modal（左导航+账号/通用/AI协作卡）
5. ✅ components.css：新增阶段三样式（guide-steps/ai-config-item/settings-modal/settings-nav/settings-body/settings-card/theme-picker/color-mode-seg/ai-platform-row），自包含 .settings-modal 基础视觉避免与既有 .modal 选择器冲突
6. ✅ tests/frontend/ 增改测试：新增 test_stage3.py（14 用例）+ 修正 test_health 2 处复制按钮选择器（用 `复制 prompt(?! 给 AI)` 排除阶段三新增的「复制 prompt 给 AI」）
7. ✅ python3 frontend/build.py 重建 + 浏览器验证（配置 modal 截图 + 引导三步向导截图均确认）
8. ✅ 回归测试：test_health 49 通过 / test_stage3 14 通过 / test_smoke 通过 / test_doc_card_hover 既有 1 失败（stash 验证与本改动无关）/ test_edit_switch 既有 10 失败（stash 验证与本改动无关）

## 执行日志
- 平台契约核对：后端 `client_config.PLATFORMS = ("claude", "codebuddy")` 两平台，cursor 会 raise；前端硬编码两平台与后端严格一致
- rerunGuide 入口：身份已设置时 handleRoute 强制跳 dashboard 阻断 setup → 新增 `guideForce` 标志绕过
- setup 预填：rerunGuide 进入时若身份已设置预填 setupNickname/Email（init 监听 currentView）
- settings-modal 独立样式：自包含 background/border/radius/shadow，不使用 .modal class，避免与 test_health 泛化选择器冲突
- test_health 修正：`has_text="复制 prompt"` 改 `has_text=re.compile(r"复制 prompt(?! 给 AI)")` 精确匹配（排除阶段三新增按钮）
- 既有失败验证：`test_doc_card_hover::test_h5c` 与 `test_edit_switch` 10 个失败均 stash 验证与本改动无关（测试库 health-demo 项目存在 + 偶发时序）

## 输出结果
- 改动文件：
  - `frontend/js/api.js`（+22 行：getClientConfig/setClientConfig）
  - `frontend/js/store.js`（+137 行：clientConfig/settingsGroup/guideStep/guideForce/clientConfiguring + 10 方法 + 派生 getter）
  - `frontend/js/components/modal.js`（+69 行：guideNext/guidePrev/settingsNav/saveSettingsIdentity/configureAi/copyAiPrompt + init 增强）
  - `frontend/index.html`（+159 行：user-menu「设置」+ setup 三步向导 + settings modal）
  - `frontend/css/components.css`（+200 行：阶段三样式区）
  - `tests/frontend/test_stage3.py`（新建，14 用例：静态 10 + 构建 1 + 浏览器 3）
  - `tests/frontend/test_health.py`（+1 行 import re，2 处选择器精确化）
- 构建：python3 frontend/build.py 通过，standalone 522KB
- 浏览器验证：3 张配置 modal 截图 + 3 张引导向导截图全部确认渲染正确
- 测试：test_stage3 14/14、test_health 49/49、test_smoke 通过

## 总结
- 阶段三前端（引导页三步向导 + 配置 modal 3 分组）实施完成
- 严格按 SPEC §3.6/§3.7 + 后端 client_config 契约（claude/codebuddy 两平台）实现
- 半自动化闭环：POST → 刷新 → toast + 复制 prompt 兜底
- 引导页与配置 modal 配置逻辑完全复用同一套 store 方法（决策3）
- 引导页首次身份未设自动触发；rerunGuide 入口处理身份已设置场景
- 用户可手动验证路径：dashboard → 右上 Moray → 设置 → 三分组切换；通用 → 重新运行初始化引导 → 三步向导
- 注意事项：8080 后端需重启以加载 /api/client-config 路由（当前 8080 跑的是旧进程，AI 协作卡显示「检测失败」属正确降级）
