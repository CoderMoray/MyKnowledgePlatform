# 后端提示词：文档乐观锁（冲突检测）

> 用途：粘贴给后端 agent。前端已同步就绪（见"前端约定"），后端按本约定实现即可无缝对接。

---

## 背景

知识库文档被多会话/多端编辑时会互相覆盖。实测事故：A 窗口加载文档后，B 窗口（或后端/MCP 工具）把文档改成新内容；A 退出编辑保存 → 用旧内容覆盖新内容 → 数据丢失。

前端无法单独解决，需要后端提供**基于内容指纹的乐观锁**。

## 关键前提（重要，决定方案）

**前端保存路径（PUT /api/document）目前不产生 git commit**（实测 `git rev-parse HEAD` 不变，文件变未提交状态；git commit 只在 MCP/AI 工具路径产生）。因此：

- ❌ **不能用 git HEAD commit hash 作 version**——前端保存不产生 commit，HEAD 不变 → version 不变 → 乐观锁失效
- ✅ **version = 文档内容的 SHA-256 短 hash（前 12 位）**——每次内容变化必变；内容相同（零 diff 保存）hash 不变 → 不冲突，语义正确
- 后端**不需要存储历史指纹**：每次 GET 现算、PUT 时与请求携带值比对即可

## API 变更

### 1. GET /api/document/{path}

响应 JSON 增加字段：

```json
{
  "content": "...",
  "meta": {...},
  "version": "a1b2c3d4e5f6"   // 新增：sha256(最终 content 字符串)[:12]
}
```

- `version` 每次现算（content 的 SHA-256 前 12 位）
- 计算对象：GET 返回的 `content` 字段的原始字符串（UTF-8）

### 2. PUT /api/document/{path}

请求体增加可选字段：

```json
{
  "content": "...",
  "summary": "...",
  "expected_version": "a1b2c3d4e5f6"   // 可选：前端加载时拿到的指纹
}
```

行为：

- **不带 expected_version**（兼容旧客户端/初始化）→ 照常写盘
- **带 expected_version**：
  - 当前文件内容 hash === expected_version → 正常写盘 + 返回新 version
  - 当前文件内容 hash !== expected_version（文档已被别处修改）→ **不写盘**，返回：

```json
HTTP 409 Conflict
{
  "error": "conflict",
  "message": "文档已被其他会话修改",
  "current_version": "c3d4e5f6a7b8",
  "content": "<服务端当前最新完整内容>"
}
```

- 写盘成功后响应（现有结构）增加 `version` 字段（新内容的 hash），前端用于更新本地指纹

### 3. 其他写接口（新建 /api/document POST）

新建无版本要求（不存在旧版本）。若后续有"更新已有文档"的其他端点，建议同样支持 expected_version 语义。

## 前端约定（已实现，按此对接）

前端保存请求会带 `expected_version`（来自加载时 GET 的 version）；收到 **HTTP 409 + 上述响应体**时：

- 读取 `error` 判断冲突（`=== "conflict"`）
- 读取 `content` 显示"服务端最新版本"（前端做两栏 diff 可视化）
- 提供操作：保留我的修改（再次 PUT，**不带** expected_version 强写）/ 采用最新版本（重新 GET）/ 取消

字段名必须严格一致：`error`、`message`、`current_version`、`content`。

## 验收标准

1. 两个会话（或会话 + 直接改文件）同时编辑同一文档：
   - A 保存成功（200 + version）
   - B 保存 → **409** + `error: "conflict"` + 最新 content，且**文件内容未被 B 覆盖**
2. B 再次保存（不带 expected_version）→ 强制覆盖成功
3. 零 diff 保存（内容未变）→ 不冲突（hash 相同）
4. 不带 expected_version 的旧请求行为不变
5. GET 的 version 与 PUT 保存后返回的 version 逻辑一致（都是内容 hash）

## 注意事项

- 不要动现有 git commit 策略（前端保存不 commit 是另一个议题，另行讨论，本次不做）
- hash 计算放在后端（Python `hashlib.sha256`），确保 GET/PUT 用同一实现
- 409 响应**不要**触发后端现有的"死链 400"等校验冲突（冲突检测优先于内容校验返回 409）

---

## 附：可选第二需求（独立，本次可不做）

**前端保存产生 git commit**：目前前端编辑无 git 版本历史（无法回滚）。建议 PUT 保存时按策略 commit（如：仅"手动保存/退出保存"commit，自动保存不 commit，避免高频刷 commit）。此项独立，需另行确认频率策略。

---

## 后端评审批注（2026-08-05）

### ✅ 确认实施（主需求合理）

乐观锁核心方案正确、应实施：
- `version` = 内容指纹（不用 git HEAD，因为前端保存不 commit）
- 无状态（GET 现算、PUT 比对），`expected_version` 可选向后兼容
- 409 返回最新 content，优先级高于死链 400
- 零 diff 保存 hash 相同 → 不冲突

### ⚠️ 修改：summary 纳入 version

**决定**：`version` 从 content-only 改为 **content + summary** 共同计算，否则 summary 的并发修改无法触发冲突。

> 连锁影响：
> - 前端 PUT 必须携带它持有的 `summary`（即使未改），后端才能正确比对
> - **前端当前未实现 summary 编辑**——这是一个功能缺口，需补上（后端 `api_get_document_meta` 已返回 summary，`PUT /api/document` 已支持改 summary，只是前端没有对应输入框）

### ⚠️ 修改：409 响应补 `current_summary`

summary 纳入后可能出现"content 相同、summary 不同"的冲突。前端两栏 diff 只对比 content 看不出差异，故 409 需额外返回 `current_summary` 供前端展示。

### 🎯 hash 实现基准（已定）

- `version = sha256(f"{summary}\x00{content}")[:12]`，其中：
  - `content` = 纯 body（PUT 传来的正文，不含 frontmatter）
  - `summary` = 显式 summary 字段，用 `summary or ""` 兜底空值
  - `\x00` 分隔符（null 字节，不会出现在正常文本，避免碰撞）
- **前端不计算 hash**——只 GET 存 version → PUT 回传 `expected_version` → 保存后收新 version。分隔符/hash 基准为后端内部实现，前端只需回传语义。
- 后端仅在 `read_document` 返回的精确字符串上算，不做 normalize，保证 GET/PUT 一致。

### ⚠️ 前端需注意：新建文档 summary 空值

后端 REST 已强制 summary 非空（空 summary 保存返回 400）。前端需在**新建文档**时处理：
- 保存前检测 summary 为空 → 弹窗提示补充，或给默认字符串（如文档名）
- 编辑页也应补上 summary 输入框（当前缺失）

### ❌ 驳回：可选第二需求（前端保存产生 git commit）

**理由**：前端保存不 commit 是刻意设计——它留下 dirty working tree，供 AI 在下一次会话的 `maint__read_diff`（checkpoint→HEAD）中审查、校验、commit。若前端自动 commit：
1. `read_diff` 看不到前端变更（已进 HEAD），AI 失去"评估内容是否有问题"的入口
2. 自动保存高频 commit 污染 git 历史
3. 违背 DESIGN.md 场景 2（Web UI 编辑"留 dirty 等 AI 处理"）

前端写操作重新生成的相关文件仅 2 个：父级 `readme.md` + `project-status.md`（加上被编辑文档本身），无其他关联文件。
