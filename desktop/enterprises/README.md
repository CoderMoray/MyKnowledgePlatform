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
  "platforms": {
    "ClaudeCode": { "enabled": true, "display": "Claude Code" },
    "WorkBuddy":  { "enabled": false }
  }
}
```

- `name`：企业名（须与文件名一致，便于排查）
- `platforms`：只写需要覆盖的平台；**未列出的平台沿用 `backend/AiClientConfig/platforms.json` 默认值**
- `enabled: false`：该平台不会出现在产物（前端列表、检测、配置生成均不含）
- `display`：覆盖该平台的展示名（前端从 `/api/platforms-meta` 读取，无需改前端代码）
- **平台 key 必须与 `platforms.json` 的 key 严格一致**，否则打包报错

## 常用场景

| 场景 | 配置 |
|---|---|
| 只给某企业开放少数平台 | 其余平台 `enabled: false` |
| 平台改名（品牌定制） | 指定平台的 `display` |
| 禁用某平台 | 该平台 `enabled: false` |

## 注意

- 企业配置**只影响打包产物**，`backend/AiClientConfig/platforms.json` 源文件不被修改（临时合并，打包后清理）
- 当前是**打包期合并**：一个企业 = 一份配置 + 一次打包 = 一个 dmg
- 平台 key 全集见 `backend/AiClientConfig/platforms.json`：`ClaudeCode` / `ClaudeDesktop` / `CodeBuddyIDE` / `WorkBuddy` / `Enchante` / `Cursor`
