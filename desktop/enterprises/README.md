# 企业定制配置

每个 JSON 文件代表一个企业的 dmg 定制配置。文件名为企业名（如 `yourcompany.json` → `--enterprise yourcompany`）。

> **配置文件不进代码仓库**：`desktop/enterprises/*.json`（除 `template.json` 外）已被 `.gitignore` 忽略。
> 使用方式：复制 `template.json` 为 `<企业名>.json` 再修改，该文件只存在于本地/分发机，不会提交。

## 打包用法

```bash
# 默认（全平台，不读企业配置）
bash scripts/release.sh

# 企业定制
bash scripts/release.sh --enterprise yourcompany
```

## 配置格式

```json
{
  "name": "yourcompany",
  "default_disabled": false,
  "platforms": {
    "ClaudeCode": { "enabled": true, "display": "Claude Code", "order": 1 },
    "WorkBuddy":  { "enabled": false }
  }
}
```

- `name`：企业名（须与文件名一致，便于排查）
- `default_disabled`：`false`（缺省）→ 未列出的平台沿用 `platforms.json` 默认；`true` → 未列出的平台**全部禁用**（只启用显式列出的，适合"仅开放少数平台"场景）
- `platforms`：只写需要覆盖的平台；未列出的平台行为由 `default_disabled` 决定
- `enabled`：`false` → 该平台不出现在产物（前端列表、检测、配置生成均不含）
- `display`：覆盖该平台的展示名（前端从 `/api/platforms-meta` 读取，无需改前端代码）
- `order`：控制前端展示顺序（数字小的靠前；未配置的平台排在后面保持原序）
- `kinds`：覆盖该平台支持的能力集（如 `["mcp", "agent"]`）；前端 MCP/Hooks/Agent 三页根据它判定"平台原生不支持"置灰
- **平台 key 必须与 `platforms.json` 的 key 严格一致**，否则打包报错

## 常用场景

| 场景 | 配置 |
|---|---|
| 只给某企业开放少数平台 | `"default_disabled": true` + 显式列出要启用的平台 |
| 平台改名（品牌定制） | 指定平台的 `display` |
| 禁用某平台 | 该平台 `enabled: false` |
| 调整展示顺序 | 指定平台的 `order` |
| 声明平台不支持某能力 | 覆盖该平台的 `kinds`（MCP/Hooks/Agent 页置灰显示） |

## 注意

- 企业配置**只影响打包产物**，`backend/AiClientConfig/platforms.json` 源文件不被修改（临时合并，打包后清理）
- 当前是**打包期合并**：一个企业 = 一份配置 + 一次打包 = 一个 dmg
- 平台 key 全集见 `backend/AiClientConfig/platforms.json`：`ClaudeCode` / `ClaudeDesktop` / `CodeBuddyIDE` / `WorkBuddy` / `Enchante` / `Cursor`
