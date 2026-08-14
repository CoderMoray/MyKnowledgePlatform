# 前端评估任务：前端全量测试耗时过长（18.5 分钟）（临时任务单）

> 状态：📋 待架构评估 | 创建：2026-08-14
> 提出方：前端 agent（全量回归实测） | 归属：前端测试基建（架构评判后决定是否优化、怎么优化）

## 一、现象

前端全量回归 `pytest tests/frontend/` 实测：

- **100 用例，总耗时 1110s（18 分 30 秒），平均约 11s/用例**
- 文件构成：test_doc_card_hover 7 / test_edit_switch 43 / test_paste_markdown 24 / test_refwarn_toast 4 / test_smoke 22
- 结论：0 failed（全量通过），但**单次全量回归接近 20 分钟**，迭代验证成本高

## 二、根因分析（初步，前端侧）

1. **固定 sleep 为主，条件等待为辅**：测试大量使用 `wait_for_timeout(600~1500ms)` 固定等待（如 hover 预览懒加载留 1300ms、dashboard 留 1000ms、模态过渡 600-700ms），不随实际加载速度缩短。历史原因：hover 懒加载/rename 异步/保存 debounce 等时序敏感，曾多次出现「批量跑偶发失败」→ 保守固定等待换取稳定性。
2. **每用例 fixture 建/删文档**：`test_docs`/`hover_docs` 每个用例创建 3 个文档 + 删除 + 清垃圾箱（后端 git commit、readme 重建），几秒/用例。
3. **后端异步操作**：自动保存 1s debounce、rename 的 git 操作、SSE 广播。
4. **浏览器渲染**：Playwright 启动 Chromium、tiptap-bundle（大文件）解析、ProseMirror 渲染。

## 三、候选方案（供架构评判）

| 方案 | 做法 | 预估收益 | 风险 |
|---|---|---|---|
| A. sleep → 条件等待 | 把固定 `wait_for_timeout` 改为 `expect(...)`/轮询等元素/状态出现 | 预计 18.5m → 5~8m | 可能引入新 flaky（hover 懒加载、异步保存等历史坑），需小步验证 + 反复跑 |
| B. 文件级并行 | `pytest -n 4 --dist=loadfile`（环境已装 pytest-xdist 3.8.0） | 3~5m | **所有测试共享 8080 后端 + fixture 固定路径**（`test-edit-auto-*`/`hover-ref-*`），并行 worker 互相删文档 → 大批 flaky；后端单进程锁/乐观锁 409 冲突 |
| C. 真并行 | 每 worker 独立后端 + 独立库（fixture 按 worker 生成唯一路径/端口） | 3~5m | conftest 大改；多后端进程资源开销；复杂 |
| D. 不做 | 维持现状（全量由人在终端手动跑，~20 分钟） | 0 | 迭代验证慢 |

## 四、期望产出

1. 是否值得优化、优先级如何（当前开发节奏是否被测试耗时阻塞）。
2. 方案定案（A/B/C/D 或组合），说明理由与影响面。
3. 若做，建议的推进方式（独立任务？分批小步？如何防 flaky 回归）。

## 五、备注

- 本次全量 100/100 通过，与功能改动无关的纯测试基建提速讨论。
- 相关上下文：hover 测试的固定等待是为「连续 hover 时序敏感」防 flaky 而留（`test_doc_card_hover.py` 注释）；`wait_for_backend` 轮询 helper（836c413）是 rename 异步竞态的既有解法，可作为条件等待改造的参考模式。
