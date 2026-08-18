# 前端测试基建提速评估（架构定案）

> 状态：**已定案** — 2026-08-18 架构评估完成（原 `docs/TASK-frontend-test-speed.md` 临时任务单升级为本定案）
> 提出方：前端 agent（全量回归实测） | 归属：前端测试基建（纯提速讨论，与功能改动无关）
> 关联：`testing-plan-edit-switch.md`（S1-S26 + H1-H5 场景）、`testing-plan-paste-markdown.md`（P 系列场景）、`dependency-upgrade-fastapi.md`（后端依赖，独立主题）

## 〇、事实纠偏（原任务单基于过时/不完整快照，以下为实测）

| 原任务单描述 | 实测事实（2026-08-18） | 影响 |
|---|---|---|
| 100 用例 / 18.5 分钟 | **176 用例**（collect-only 实测），8 个测试文件 | 实际规模比任务单大 76%；耗时密度更低（176/1110 ≈ 6.3s/用例，非 11s） |
| 5 个测试文件 | 实际 8 个：`test_health(49)` / `test_stage3(19)` / `test_trash_pagination(8)` 未在任务单列出 | 大块耗时来自未分析的文件 |
| 环境已装 pytest-xdist 3.8.0 | ✅ 确认已装（`python -c "import xdist"` 成功，3.8.0） | B/C 方案的"障碍"前提需重估 |
| 平均约 11s/用例 | 实测约 6.3s/用例 | sleep 占比需按真实分布重算 |

### 真实用例分布（collect-only）

| 文件 | 用例数 | 备注 |
|---|---|---|
| test_health.py | 49 | 含 `TestHealthBrowser`（playwright） |
| test_edit_switch.py | 43 | S1-S26 + 归属 + 创建 |
| test_paste_markdown.py | 24 | P 系列 |
| test_smoke.py | 22 | 静态渲染/路由/主题/垃圾箱 |
| test_stage3.py | 19 | 未在原任务单 |
| test_doc_card_hover.py | 7 | H1-H5 + H5b/H5c |
| test_trash_pagination.py | 8 | 未在原任务单 |
| test_refwarn_toast.py | 4 | — |
| **合计** | **176** | 全量 0 failed |

### Sleep 分布（grep `wait_for_timeout`，160+ 处）

- 中位 600–800ms；长尾 2500ms（test_health / test_stage3 / edit_switch_helpers 的异步退出）
- `test_health.py` 44 处、`test_stage3.py` 26 处、`test_edit_switch.py` 40 处（含 helpers 11 处）
- 时序敏感标注点：`_hover_card_by_title` 的 1300ms（注释"连续 hover 时序敏感"）、`exit_inplace` 的 1200ms（autosave debounce）、`edit_switch_helpers` 的 2500ms（DELETE+toast+倒计时）

## 一、为什么"sleep → 条件等待"能提速（原理）

固定 `wait_for_timeout(N)` **永远等满 N**，且为防批量跑偶发失败，N 通常被设成"历史最慢情况 + 安全余量"（如本地 200ms 加载完，但写 1300ms 防 CI 慢机）。结果：**绝大多数本地运行，每处多等了数百~上千 ms 纯冗余**。

条件等待（`expect(locator).to_be_visible()` / 轮询后端状态）**不等预支余量，元素/状态一就绪即继续**：
- 快环境 → 等 200ms（省掉余量）
- 慢环境 → 等 800ms（和原来一致，但不多等）

**结论**：条件等待不是"比 sleep 快"，而是"不白等余量"——把每用例里为最慢情况预支、但本地用不上的等待全部回收。

⚠️ **诚实边界**：对真正时序敏感的等待（hover 懒加载 1300ms、保存 debounce 1200ms），条件等待**省不了多少**——那一刻它就是需要那么久，等到它就停，时长和 sleep 接近。所以真实收益主要来自下文 A1 类（过渡/动画等待，余量最大），A2 类（时序敏感）收益小、风险高。

## 二、是否值得优化？优先级

**结论：值得优化，但属 P2（非阻塞），且只走方案 A。**

- **开发节奏未被阻塞**：176 用例 0 failed，全量是"人在终端手动跑"的收尾动作，非每次改码都等 18 分钟。前端 agent 痛点"hover/编辑切换改动每次都要等"——**局部重跑**即可（只跑 `test_doc_card_hover` 7 例或 `test_edit_switch` 43 例，秒级），不需全量提速。
- **ROI 不正**：18 分钟里浏览器冷启动/Chromium/ProseMirror/tiptap 解析、fixture 建删文档（每次 git commit + readme 重建）是**硬成本，sleep 改条件等待也省不掉**。真实可控 sleep 上限约 1–3 分钟（取决于重叠），方案 A 预估"18.5m→5~8m"**过于乐观**，与实测 sleep 总量不符。
- **但有真实价值**：方案 A 同时是**质量改进**（条件等待本就比固定等待更抗环境波动，减少本地/CI 偶发 flaky），不止提速。

**优先级定级：P2 / 迭代期顺带做，不作阻塞项排期。**

## 三、方案定案：只做 A，不做 B/C/D

### 否决 B（文件级并行 `pytest -n 4 --dist=loadfile`）与 C（真并行）

任务单已列 B/C 致命障碍，实测确认成立：

1. **共享 8080 后端 + 固定 fixture 路径是硬冲突**：`conftest.py` 中 `DOC_MAIN/SAME/TARGET/SUB`、`hover_docs` 的 `hover-ref-a/b/c` 全是**常量绝对路径**。任何并行 worker 会对**同一批文件** POST 覆盖 + `hard_delete_doc` + git commit + readme 重建。两 worker 同时 `git commit` 同一 `.myknowledge_test` 库 → 必冲突/互删文档 → 大批 flaky。非调参能解，是 fixture 架构根因。
2. **C 真并行代价过高**：每 worker 独立后端 + 独立库，需改 `API_BASE`、`conftest` 按 xdist worker id 生成唯一路径/端口、起多进程。conftest 当前是"复用现有 8080、无后端则 skip"极简设计——大改引入新维护面，多 Chromium + 多后端进程开发机资源开销大。**收益（省 1–3 分钟）× 代价（conftest 重写 + 长期维护）= 不划算**。
3. **B 的 `loadfile` 仍共享后端**：除非做到 path 隔离（即 C 的一半工作量），否则 B 等于 C 但更脆弱。

→ **B/C 任何情况下本期不做**；若未来出现"必须分钟级全量"强需求（如接 CI 门禁），直接做 C 的 path/port 隔离版，别做 B。

### 选定 A（sleep → 条件等待）——分两类处理

核心原则：**固定 `wait_for_timeout(N)` 永远等满 N（含为最慢机器预支的余量）；条件等待"等到真实状态就停"，只回收余量、不删必要等待**。改造不是删等待，是把"等 N 毫秒"换成"等某状态出现"。

#### A0. 四类标准改写范式（全测试文件统一套用）

**范式 1 — 等元素/状态出现（替代"过渡等待"）**
```python
# 改造前（过渡等待，永远等满 600ms）
page.wait_for_timeout(600)
assert modal.is_visible()
# 改造后（Playwright expect 自带轮询，默认 5s/100ms，元素一出现即停）
expect(modal).to_be_visible(timeout=5000)   # 注释：等删除确认模态出现
```

**范式 2 — 等 DOM 事件/动画结束（替代"动画/跳转等待"）**
```python
# 改造前
del_btn.click(); page.wait_for_timeout(700)
# 改造后：等模态出现，取消后等它消失
expect(modal).to_be_visible()
page.get_by_role("button", name="取消").first.click()
expect(modal).not_to_be_visible()            # 注释：等模态关闭动画结束
```

**范式 3 — 轮询后端真实状态（替代"异步操作等待"，A2 核心，复用 `wait_for_backend`）**
```python
# edit_switch_helpers.py:115 已有范本
def wait_for_backend(path, expect_status=200, timeout=8.0, interval=0.2):
    """轮询 GET /api/document/{path} 直到返回 expect_status（默认 200）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(f"{API_BASE}/api/document/{path}", headers=AUTH)
        if resp.status_code == expect_status:
            return resp
        time.sleep(interval)                  # 短轮询，不白等
    raise AssertionError(f"后端 {path} 未在 {timeout}s 内达到 {expect_status}")

# 改造前（exit_inplace 后等 autosave 落库）
page.wait_for_timeout(1200)
assert_backend_content(DOC_MAIN, marker)
# 改造后：等保存真正落库
wait_for_backend(DOC_MAIN, 200)              # 注释：等自动保存 debounce 后内容落库
assert_backend_content(DOC_MAIN, marker)
```

**范式 4 — 前端状态信号轮询（替代"懒加载/前端内部异步等待"，A2 用）**
```python
def wait_for_preview_update(page, card, expect_text, timeout=5.0):
    """轮询卡片预览 body，直到含预期内容（替代固定 1500ms）。"""
    body = card.locator(".doc-card__preview__body")
    expect(body).to_be_visible(timeout=timeout)   # 先等元素进 DOM
    deadline = time.time() + timeout
    while time.time() < deadline:
        if expect_text in body.inner_text():
            return
        page.wait_for_timeout(100)                # 短轮询间隔
    raise AssertionError(f"预览未更新为 {expect_text!r}")
```

#### (A1) 可安全改的"过渡/动画等待"（低风险，优先做）

不涉"懒加载时序敏感"，改条件等待**只会更稳不会更 flaky**。逐文件清单：

- **`test_doc_card_hover.py`**（PR1）
  - L46 `_open_dashboard` 的 `wait_for_timeout(1000)` → 已有 `wait_for_selector(".doc_card")`；删 sleep，改 `expect(page.locator(".doc-card").first).to_be_visible()`
  - L83 `test_h2` click ref 后 `1000` → `expect(page).to_have_url(re.compile(r"#doc/.*"))` 或等目标文档标题出现
  - L97/L116 `page.mouse.move(5,5)` 后 `400` → 删（`mouse.move` 瞬时；如需等 hover 态消失，改 `expect(hover_preview).not_to_be_visible()`）
  - L140/L144/L152/L159/L168/L173 模态 `600/700` → 范式 2（`to_be_visible()` / `not_to_be_visible()`）
  - **保留** L56 `_hover_card_by_title` 的 `1300`（见 A2①）
- **`edit_switch_helpers.py` + `test_edit_switch.py`**（PR2，已有 `wait_for_backend` 范本）
  - `open_doc` L31 `600` → 已有 `wait_for_selector(".ProseMirror")`；删 sleep
  - `enter_edit` L43 `250` → 已有 `wait_for_selector(".viewer__title-input")`；删 sleep
  - `navigate` L101 `1500` → 按 target 等对应元素（如 `expect(page.locator(".ProseMirror")).to_be_visible()`）
- **`test_smoke` / `test_paste_markdown` / `test_refwarn_toast`**（PR3）
  - 各 transition 类 sleep → 范式 1/2；paste 的 `wait_for_timeout(600)` 等渲染 → `expect(编辑器内容含粘贴标记)`

#### (A2) 时序敏感、暂缓（高风险，需小步验证，每处单独 PR4）

历史"批量跑偶发失败"坑。改造方向是**轮询真实状态 / 串接异步链路**，非简单 `expect`。**必须小步 + 反复跑 3 轮以上验证无 flaky 才合并**。

- **① hover 预览懒加载 `1300ms`（`_hover_card_by_title` L56，注释"连续 hover 时序敏感"）**
  风险：hover 触发异步 fetch，预览元素未进 DOM 就 `expect` 会失败。
  改造：先 `expect(card.locator(".doc-card__preview__body")).to_be_visible()`（等元素出现），再用范式 4 `wait_for_preview_update` 等内容填充。**连续 hover 必须等前一个预览消失再 hover 下一个**（现靠 `400ms + mouse.move(5,5)`）→ 改 `expect(前一个 preview).not_to_be_visible()` 后再 hover 下一个。
- **② 自动保存 debounce `1000/1200ms`（`exit_inplace` L62、`apply_mod` 后）**
  改造：`exit_inplace` 后不 sleep，改 `wait_for_backend(DOC_MAIN, 200)`（等后端 GET 返回 200 + 内容含 marker）。若前端暴露保存态（如 `Alpine.store('app').saving`），可加 `wait_for_saving_done(page)` 双保险；否则只用后端轮询。
- **③ 异步退出编辑 `2500ms`（`edit_switch_helpers` L239 DELETE + toast + 倒计时跳转）**
  改造：DELETE 后 `expect(toast).to_contain_text(...)`（等 toast 出现）→ `expect(page).to_have_url("#dashboard")` 或等目标视图出现（替代"等倒计时跳转完成"的固定 2500ms）。

#### 新增 helper 建议（放 `edit_switch_helpers.py`，不新建文件）

- `wait_for_preview_update(page, card, text, timeout=5)` — 范式 4，轮询预览内容
- `wait_for_view(page, hash_or_locator, timeout=5)` — 等视图切换完成（dashboard/doc 互跳）
- （可选）`wait_for_saving_done(page, timeout=5)` — 等前端保存态结束（需确认 `Alpine.store('app').saving` 可用）

#### 防 flaky 规则（写入 conftest / helpers 约定，纳入 code review）

1. **禁止新增裸 `wait_for_timeout` 防竞态**：任何"等异步"必须用语义化等待（expect / `wait_for_backend` / 自定义 `wait_for_*`）。
2. **新增等待必须注释"等什么状态"**：如 `expect(modal).to_be_visible()  # 等删除确认模态出现`。
3. **选对信号**：等"内容/状态"而非"元素存在"；懒加载先等元素出现再等内容（范式 4）。
4. **异步链路按顺序串条件**：A2 的 fetch→填充→消失必须逐步 `expect`，不可只等一步。
5. **`wait_for_backend` 为唯一后端轮询入口**，各处不得重写轮询逻辑。
6. **每 PR 合并前连跑 3 次**该文件（或全量），任一次失败即退回。

### 否决 D（不做）

现状每次 18 分钟虽不阻塞，但 A1 类改造零风险且顺带提质，无理由不做。D 排除。

## 四、推进方式

1. **独立任务，按文件拆小 PR**，勿一次性改 160 处：
   - PR1：`test_doc_card_hover.py` 的 A1 类（模态/跳转，不动 1300ms 懒加载）→ 跑 5 轮验证
   - PR2：`edit_switch_helpers.py` + `test_edit_switch.py` 的 A1 类（已有 `wait_for_backend` 范本）→ 跑 5 轮
   - PR3：`test_smoke` / `test_paste_markdown` / `test_refwarn_toast` 的 A1 类
   - PR4（可选、高谨慎）：A2 类 hover 懒加载/保存 debounce，用 `wait_for_backend`/轮询替代，每处单独验证
2. **防 flaky 回归**：
   - 每 PR 合并前**连跑 3 次全量 `tests/frontend/`**（或至少该文件 3 次），任一次失败即退回
   - 保留 `wait_for_backend` 轮询范式作标准；**禁止新增"裸 `wait_for_timeout` 防竞态"**——新增等待必须用条件等待，注释说明等什么状态
3. **不碰 conftest 并行化**：保持"复用 8080 + 固定路径"现状，B/C 不在本期范围。
4. **重新基准**：优化后以 176 用例实测耗时为准更新本文件，预期从 18.5m 降到 ~14–16m（保守，主要来自 A1）；若 A2 也做且稳，可能到 ~12m。**不承诺 5–8m**。

## 五、裁决摘要

| 项 | 裁决 |
|---|---|
| 是否优化 | **是**，但 P2（非阻塞，迭代顺带） |
| 方案 | **只做 A（条件等待），B/C 否决，D 否决** |
| 优先级 | A1（过渡/动画等待，低风险）先 > A2（懒加载/debounce，高谨慎小步） |
| 并行化 | **本期不做**；若未来需 CI 分钟级门禁，直接做 C 的 path/port 隔离版 |
| 防回归 | 每 PR 连跑 3 轮；新增等待必须用条件等待 + 注释 |
| 基准修正 | 以 176 用例实测为基准，预期 ~14–16m，不承诺 5–8m |

## 六、与 docs/test/ 其他文件的关系

- `testing-plan-edit-switch.md` / `testing-plan-paste-markdown.md`：本文件优化的是"它们定义的测试**怎么跑更快**"，不改动其场景矩阵（测什么）。互相引用，不合并。
- `dependency-upgrade-fastapi.md`：后端依赖主题，独立。注意其验证要求提到"前端 71 用例回归"（当时口径），与本文件 176 用例基准不同——fastapi 升级验证时应以当前 176 用例全量为准。
