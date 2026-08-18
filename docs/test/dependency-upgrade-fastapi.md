# 依赖升级专项：fastapi 0.110 → 0.141（联动 starlette / httpx）

> 状态：📋 待架构分析风险 → 通过后由后端 agent 执行升级 + 测试
> 关联：`tests/`（后端 337 用例为质量门禁）

## 背景

- **当前**：fastapi 0.110.0（requirements 锁定 `>=0.100.0,<0.111.0`）、starlette 0.36.3、httpx 0.27.2（锁 `<0.28`）
- **锁定来源**：`<0.111` 在 init 提交（v0.5.0, 2026-07-25）写死，**从未修改**——保守初始选择，非 bug 触发
- **最新**：fastapi 0.141.1（落后 31 个 minor 版本 0.111~0.141）

## 升级动机

1. **TestClient 弃用警告（60 条）**：starlette 0.36.3 的 `TestClient` 内部用 `httpx.Client(app=...)` 旧式构造，
   httpx 0.27 起弃用（0.28 移除）→ 每次后端测试跑都刷 60 条 DeprecationWarning。
   测试代码用 `TestClient(app)` 是**官方标准用法，无需改**——等 starlette 升级（内部换 transport 显式风格）自动消除。
2. **starlette multipart 警告（1 条）**：starlette 内部 `import multipart` → 新版改 `python_multipart`。
3. 0.110 → 0.141 期间的 bug fix / 安全更新（顺带获得）。

## 升级范围（联动，不能单独升）

| 库 | 当前 | 目标 | 说明 |
|---|---|---|---|
| fastapi | 0.110.0 | 最新 0.141.x | 解除 `<0.111` 锁 |
| starlette | 0.36.3 | 随 fastapi 新版绑定 | TestClient 换 transport → 警告消除 |
| httpx | 0.27.2 | 评估放行 `>=0.28` | 当前 `<0.28` 锁是 starlette 0.36.x 兼容需要；新版 starlette TestClient 兼容 0.28+ |

requirements.txt / pyproject.toml 两处锁定同步调整。

## 风险点（供架构分析）

1. **API 破坏性变更**：0.110 → 0.141 跨 31 个版本——需审计 fastapi/starlette/httpx 的 breaking changes
   （重点：路由/依赖注入/响应模型/TestClient 签名/Pydantic 交互）
2. **后端兼容**：backend/ 代码（main.py 路由、mcp_server.py、storage 等）是否用到被变更的 API
3. **httpx 0.28 影响**：`Client(app=)` 移除——项目测试是否还有直接/间接依赖旧式（除 TestClient 内部外）
4. **337 门禁**：升级后全量重验 tests/（337 用例）
5. **前端联动**：前端经 HTTP API 与后端通信——升级后 API 响应格式需与前端兼容（前端 71 用例回归确认）

## 验证要求（升级通过标准）

1. `pytest tests/ -q` 全量 **337 passed**
2. **警告消除**：`pytest tests/ -q -W error::DeprecationWarning` 严格模式无 DeprecationWarning
   （TestClient 60 条 + multipart 1 条 + 已修的 tarfile 不复发）
3. 前端不回归：后端 API 兼容——前端 71 用例（edit_switch 42 + hover 5 + paste 24）通过
4. 手动冒烟：服务启动、文档 CRUD、ref 链接、分享导入（backend 关键路径）

## 执行步骤（架构确认后）

1. 架构：审计 breaking changes + 评估升级策略（直接升最新 / 分段升）
2. 后端 agent：更新 requirements/pyproject 锁定 → 升级安装 → 跑 337 → 修兼容性问题
3. 验证：严格模式警告归零 + 前端 71 回归 + 冒烟

## 已知约束

- fastapi 上限锁 `<0.111` 与 httpx `<0.28` 均为 init 时保守设置，升级时一并评估是否保留
- 升级属后端域（backend agent 执行）；前端 agent 配合验证 API 兼容
