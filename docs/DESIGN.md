# MyKnowledge v2 详细设计文档（Design Spec）

> 状态：v0.5 定稿
> 日期：2026-07-29
> 对应实现：backend/ 22 个 MCP 工具 + CLI + 150 项测试

---

## 0. 一句话定位

**MyKnowledge 是一个 local-first、免费、数据归你所有的 AI 知识 + 项目管理平台：以 Markdown 为真相源、版本与协作底座、MCP 为 AI 接入标准，让任意 AI agent 客户端（CodeBuddy / WorkBuddy / Trae 等）「取·存」你的知识并让它越用越厚；可选通过阿里云 OSS 做云同步与分享增强，且云存储仍在你自己的账号下。**

**关键边界：MyKnowledge 自身不内置任何 LLM。** 所有的「智能/推理」都发生在用户的 agent client 侧，MyKnowledge 只负责提供 MCP 工具 + 本地存储 + 可选云同步。

---

## 1. 竞争格局与定位

> 早期版本仅与 ima 单点对比；现补入完整竞品全景（IWE / Logseq / Obsidian / Roam / 腾讯 ima / 飞书知识库 / Notion），以厘清 MyKnowledge 在「本地优先知识库」赛道中的真正空位。v0.5 起维度扩展：新增「离线/无网可用」「结构化数据（数据库/关系）」「内容块粒度」三项，以回应 local-first、文档级所有权与 Notion 结构化能力的对照。

### 1.1 竞品总览矩阵

| 维度 | IWE | Logseq | Obsidian | Roam | 腾讯 ima | 飞书知识库 | Notion | **MyKnowledge** |
|------|-----|--------|----------|------|----------|------------|--------|-----------------|
| 定位/客群 | 开发者+agent | 个人第二大脑 | 个人/爱好者 | 个人深度思考 | 消费级个人 | 企业团队 | 全能工作区·个人/团队/企业 | **业务人员+技术团队+企业** |
| 内容模型 | 文件+包含链接(多父级) | 块大纲 `((块))` | 文件 `[[wiki]]` | 块大纲 `((块))` | 文件/文档 | 页面/层级 | 块页面+数据库(关系/多视图) | 文件+文件夹+自动 readme |
| 存储&本地优先 | 纯 md，本地优先 | md/EDN，本地优先(曾转DB引争议) | 纯 md，本地优先 | 云端 SaaS，非本地 | 腾讯云，非本地 | 飞书云，非本地 | Notion 云，非本地 | **纯 md+Git，本地优先** |
| 双向链接/图谱 | 结构链接(无可视化) | 双向链接+图谱视图 | 双向链接+图谱视图+Canvas | 双向链接+图谱视图 | 弱 | 层级组织，无图谱 | 反向链接(无图谱视图) | 结构链接(无可视化) |
| AI 接入 | 原生 CLI | 第三方 MCP/插件 | 第三方 MCP/插件 | 第三方 MCP+内置AI | 锁定 WorkBuddy | 内置 AI问答/Aily | 内置 Notion AI + REST API/集成 | **原生 MCP(22工具)** |
| 内置 LLM | 否 | 否(插件) | 否(插件) | 是(Roam AI) | 是(腾讯) | 是(飞书) | 是(Notion AI，可接第三方) | **否(外部 client)** |
| 协作 | 无(Git) | 弱 | 弱(无原生实时) | 有(团队图) | 弱 | **强(实时团队)** | **强(实时+评论+权限+发布)** | 弱(Git/分享包) |
| 格式开放/开源 | 开源 | 开源 | 格式开放/App闭源 | 闭源/专有 | 闭源/锁定 | 闭源/锁定 | 闭源/专有(可导出 md/html/csv) | **免费+纯文本** |
| 云同步/分享 | 无 | 官方sync(付费) | Sync/Publish(付费) | 云端自带 | 云自带 | 云自带 | 云自带+分享页/发布 | **OSS自账号+加密.mkpkg** |
| 数据归属/合规 | 你持有 | 你持有 | 你持有 | 厂商云 | 腾讯云 | 飞书云 | Notion 云(企业版有 SOC2/合规) | **你持有+可审计** |
| 用户门槛 | 技术友好 | 技术友好 | 技术友好 | 技术友好 | 零门槛 | 企业开通 | 中低门槛(块编辑易，库/关系需学) | **双入口：技术向 MCP/CLI；业务人员 Web UI(低门槛)** |
| 定价 | 开源免费 | 开源免费 | 个人免费/商业付费 | $15/月 | 免费/订阅 | 企业订阅 | 免费版+Plus $10+Business $18+Enterprise | 免费 |
| 离线/无网可用 | 是(本地) | 是(本地) | 是(本地) | 否(云端) | 否(云端) | 否(云端) | 否(云端，弱离线) | **是(本地 md+Git)** |
| 结构化数据（数据库/关系） | 否(纯文件) | 弱(属性/查询) | 弱(Dataview 插件) | 弱(块查询) | 弱 | 多维表格(Base) | **强(数据库/关系/多视图)** | 否(文档/文件夹，有意不做库) |
| 内容块粒度 | 文档级 | 块级 `((块))` | 块引用(插件) | 块级 `((块))` | 文档级 | 块级(文档) | 块级(任意嵌套) | 文档级(有意不做块级，Git diff 更干净) |

### 1.2 三个集群

1. **人本位个人 KB**：Obsidian / Logseq / Roam。人类编辑体验最强（图谱视图、块引用、白板），但 agent 是事后用插件/MCP 接入，企业合规与数据归属讲不清。
2. **agent 可接的本地 KB**：IWE + **MyKnowledge**。文件即真相源、本地优先、agent 一等公民。IWE 有 LSP 编辑器集成；MyKnowledge 有原生 MCP + Git + OSS 分享 + 企业合规叙事。
3. **企业 SaaS**：飞书知识库 / 腾讯 ima / Notion。协作与企业 AI 最强，但数据在厂商云、锁定生态、内置 LLM——恰是 MyKnowledge 明确避开的三件事。其中 **Notion 最「全能」**（块页面 + 数据库 + 内置 AI 一体），是 MyKnowledge 在「人侧易用 + 结构化」上的最强对照，但仍未解决本地优先与数据归属；ima / 飞书更偏企业协作与生态锁定。

### 1.3 MyKnowledge 的唯一空位

横扫七个对手（IWE / Logseq / Obsidian / Roam / ima / 飞书 / Notion），**同时具备以下 5 条的只有 MyKnowledge**：

- 纯 Markdown（人类可读、可手改、可带走）
- 自动版本记录与可审计
- 原生 MCP、agent-first（22 个工具，write-through + 锁/checkpoint 维护机制）
- 企业合规（不内置 LLM，数据不出域，接入可审计）
- OSS 自账号云同步 + 加密分享包（归属仍在企业自己账号）

> 别人要么让人爱用（不管 agent/合规），要么让企业敢用（但数据出域）；MyKnowledge 让企业既敢用、agent 又能用、人还可控、数据永远在你手里。

### 1.4 目标客群（业务人员也是一类，不应只写技术团队）

**不能把客群限定为「技术团队」。**

本项目有前端 Web UI，其存在意义正是让**非技术的业务人员**也能低门槛地录入/查阅知识——否则做前端交互毫无必要。因此目标客群三类并存：

- **业务人员**：经 Web UI 使用，低门槛，是「知识真正被沉淀」的广泛来源，也是企业落地时的主体使用者。
- **技术团队 / 技术向个人**：经 MCP/CLI 使用，最先感知「版本记录 + agent 共享同一份知识 + 数据归自己」的价值，是口碑传播与冷启动楔子。
- **企业客户（更核心）**：合规与采购的落点，飞书/ima 的替代项。

**漏斗关系**：技术向个人（口碑/Star）→ 技术团队（落地验证）→ 企业（合规+采购放大）；业务人员贯穿始终，是企业场景下的主要使用者。

**双入口对应双门槛**：技术向用户走 MCP/CLI（技术友好，需装本地程序 + 配 agent client）；业务人员走 Web UI（低门槛，无需理解 MCP/Git）。两者读写同一批 `.md`，保证「人和 agent 共享真相源」。

### 1.5 关键设计决策：为何不内置 LLM（企业化部署视角）

企业部署 AI 通常有两种路径，这直接决定了 MyKnowledge 的边界：

1. **企业自带模型（自托管）**：能做到这一点的公司技术实力都很强，其技术决策者本身就有能力自研类似 MyKnowledge 的底座。这类客户不是我们的主要目标——他们要么自己造，要么直接基于现有实现扩展。因此我们不需要、也不应该把「内置模型」作为卖点去服务他们。
2. **外部采购企业级 agent client（如 CodeBuddy / WorkBuddy / Trae）**：这是我们的**主要目标客群**，且天然契合合规要求——MCP 对 client 是标准、可控、可审计的接入方式，叠加本地部署，数据不出域。

由此得出边界原则：

- **MyKnowledge 不内置 LLM**；推理发生在外部 agent client（经 MCP）。
- **本地优先 + MCP**：对企业是天然合规（数据本地、接入标准、行为可审计）。
- **OSS 云同步**：仅改配置即可启用，归属仍由企业自己的账号控制；与「不内置模型」不矛盾。
- **双入口不破坏边界**：Web UI 给业务人员用，但底层仍是本地 `.md` + Git，不引入云端模型，合规属性与 MCP 入口一致。
- **可扩展项（后续，非默认）**：平台未来可支持「配置 API Key → 调用外部模型执行定时任务」的能力，但它是**可选、用户自供密钥**的增强，不改变「默认不含模型、核心为零模型成本」的定位。这不等于平台内置模型，而是把「调度外部模型」作为可插拔能力留给需要的企业。

### 1.6 与 ima 的差异化（保留原单点对比，作为子节）

> 早期版本仅与 ima 对比，因彼时 ima 是最直接的「云端 AI 知识库」参照。现 ima 仅是「企业 SaaS 集群」之一员，差异要点保留如下：

| 维度 | ima（腾讯） | MyKnowledge |
|------|------------|-------------|
| 部署形态 | 云端 SaaS，数据在腾讯云 | 本地优先；可选 OSS 云同步（你自己的阿里云账号） |
| 数据所有权 | 平台持有（腾讯云） | 你持有（本地 .md + 你自己的 OSS bucket） |
| 版本控制 | 无真正的版本历史 | 自动版本历史（可 diff/回滚） |
| AI / LLM | 内置腾讯大模型 | **不含 LLM**；智能来自外部 agent client（经 MCP） |
| AI 客户端 | 锁定 WorkBuddy | 任意支持 MCP 的客户端（CodeBuddy/WorkBuddy/Trae/自研…） |
| 可移植性 | 锁定生态，导出受限 | 纯文本 Markdown，随时带走，无厂商锁定 |
| 扩展性 | 封闭 | 免费，连接器以 MCP / 插件扩展 |
| 移动/小程序 | 有 | 暂无（路线图外，可后续加 PWA） |
| 用户门槛 | 零门槛 | 双入口：技术向 MCP/CLI，业务人员 Web UI（低门槛） |

### 1.7 待补强（正视短板，列入路线图）

- 消费级精致 UX 与零部署体验（业务人员入口仍需打磨）。
- 移动端 / PWA。
- 可视化知识图谱（Obsidian/Logseq/Roam 的「知识网视图」是人侧最强感知，可作 Phase 9 只读可视化）。
- 块引用粒度（`((块))`，企业场景有意不抄，文档级所有权 + Git diff 更干净）。

### 1.8 与 Notion 的差异化（新增竞品对照）

> Notion 是「万能工作区」标杆，块页面 + 数据库 + 内置 AI 一体，在人侧编辑体验与结构化能力上最强。MyKnowledge 与它的根本分歧如下：

| 维度 | Notion | MyKnowledge |
|------|--------|-------------|
| 运行形态 | 云端 SaaS，数据在 Notion 云 | 本地优先；可选 OSS 云同步（你自己的阿里云账号） |
| 数据所有权 | 厂商云（企业版有 SOC2/合规，但非你持有） | 你持有（本地 .md + 你自己的 OSS bucket） |
| 版本控制 | 页面级历史（有限、不可审计） | 自动版本历史（可 diff/回滚/审计） |
| AI / LLM | 内置 Notion AI（可接第三方模型） | **不含 LLM**；智能来自外部 agent client（经 MCP） |
| AI 接入 | REST API + 第三方集成（非 agent 原生） | 原生 MCP（22 工具，agent 一等公民） |
| 结构化数据 | 强：数据库/关系/多视图 | 否：文档/文件夹，有意不做库（见 1.7） |
| 内容块粒度 | 块级任意嵌套 | 文档级（所有权清晰、Git diff 干净） |
| 离线可用 | 否（云端，弱离线） | 是（本地 md + Git） |
| 可移植性 | 闭源专有，导出受限 | 纯文本 Markdown，随时带走，无厂商锁定 |
| 扩展性 | 封闭 API / 集成 | 免费，连接器以 MCP / 插件扩展 |

> **结论**：Notion 赢在「人侧全能 + 结构化」，MyKnowledge 赢在「agent 原生 + 本地优先 + 数据归你 + 合规可审计」。两者客群都覆盖业务人员/企业，但 MyKnowledge 把 AI 推理留给外部 client、把数据留在用户域——这是 Notion 的结构性不可能三角（云端 + 内置 AI + 数据归属三者不可兼得）。

---

## 2. 核心抽象（Domain Model）

```
知识库                          ← 物理上即一个 .myknowledge/ 目录
 ├─ type: personal | shared | subscribed
 ├─ root: .myknowledge/
 ├─ version: 本地版本库（每次写入自动记录版本，提供可审计的版本历史）
 ├─ oss:  可选，绑定 OSS bucket/前缀（用于云同步与分享）
 ├─ config: .myknowledge/config.yaml（OSS 绑定、加密密钥引用）
 └─ tree:
       Project（项目，递归节点）
        ├─ dir: projects/<name>/
        ├─ readme.md: 项目级索引/routing 表（frontmatter 含 id/name/summary/status）
        ├─ common-knowledge/: 项目级公共知识（.md 文件）
        ├─ projects/: 子项目（结构等同 Project，递归）
        └─ archive/: 已结项内容

Document（文档/知识条目）
 ├─ file: <doc>.md
 ├─ frontmatter: { id, type, summary, source, created, updated,
 │                 project_id?(uuid5), template?(模板名), see_also?[] }
 └─ body: markdown 正文

PublishPackage（分享包）
 ├─ file: publish/<project>.mkpkg（加密压缩包，含各级 readme）
 ├─ manifest: { project_id(uuid5), name, version, exported_by, exported_at, files[], checksums[] }
 └─ 配合 OSS 生成分享链接

Index（索引）—— 默认无独立数据库；索引 = 目录树 + 各级 readme
 └─ 可选 L0: SQLite FTS5（默认关，派生缓存，可从文件重建）
```

> **不设 `project.meta.yaml`**，meta 全部合并到各层 `readme.md` 的 frontmatter 中。

---

## 2.5 知识库目录结构 与索引架构

> 核心结论：**文件系统即索引，readme 即路由表，零独立数据库。**

### 2.5.1 物理结构

```
.myknowledge/
├─ readme.md                    ← 根索引（frontmatter 含 name/summary/updated）
├─ project-status.md            ← 所有项目状态一览
├─ agent-commit.txt             ← 最后一次由 agent 处理的 commit hash
├─ config.yaml                  ← OSS 绑定、加密密钥引用
├─ _templates/                  ← 模板库（init 时从 backend/templates/ 复制）
│   ├─ readme.md                ← readme 生成模板
│   └─ common-knowledge.md      ← 知识条目模板
├─ common-knowledge/            ← 库级公共知识
├─ publish/                     ← 加密分享包暂存
├─ projects/                    ← 进行中项目
│   └─ <项目名>/
│       ├─ readme.md            ← 项目索引（frontmatter 含 id/name/summary/status/...）
│       ├─ project-status.md
│       ├─ common-knowledge/
│       │   └─ *.md
│       ├─ projects/            ← 子项目（递归）
│       ├─ _refs/               ← `--with-context` 导入的外部引用（与原路径一致）
│       └─ archive/
└─ archive/                     ← 已结项整项目
    └─ readme.md
```

### 2.5.2 索引机制：文件系统即索引 + readme 递归路由

- **索引 = 目录树本身**，无需独立 SQLite/FTS 数据库。
- **readme.md = 每层的路由表**：frontmatter 给 agent 一次性拿到 id/name/summary/status，正文列出公共知识与子项的路径+摘要。
- **检索循环（agent 侧）**：从根 readme 起步 → LLM 语义匹配 → 下钻到项目 → 读其 readme → 继续下钻 → 递归直到无更深层相关项。

### 2.5.3 readme 的质量保障与重建

- **铁律**：各级 readme 必须由系统**从目录内容自动生成**，不能靠人手维护，不能由 AI 直接写入正文。
- **重建触发时机**：
  - `create_document` / `update_document` / `delete_document` 写入后 write-through 自动重建父层 readme
  - `update_project_meta` 手动改 readme frontmatter（name/summary/status）后重建
  - `rebuild_index(path)` 手动兜底重建
  - `import_share` 分享包导入后追加父层 readme 条目
- **readme 自检**：生成器输出后检查 section 齐全、路径指向存在的文件、frontmatter 字段完整，不通过则不覆盖。

### 2.5.4 可选的 L0 词法加速器（FTS5，默认关）

同 v0.3 设计。当项目过千或叶子文件巨大时启用，先粗筛再下钻 readme。

### 2.5.5 分享与导入（publish / import_share）

#### 打包格式

`.mkpkg` 文件结构：

```
[4 bytes: manifest JSON length (uint32)]
[N bytes: manifest JSON (UTF-8)]
[remaining: encrypted tar.gz data]
```

manifest（5 个明文字段）：

```json
{
  "project_id": "readme_...",
  "name": "以旧换新",
  "exported_at": "2026-07-24",
  "author_nickname": "张三",
  "author_email_hash": "a1b2c3..."
}
```

#### 加密

密钥由日期驱动的字段池 + `.env` 中的 `KNOWLEDGE_SHARE_CODE` 共同决定。详见 `share.py` 中 `_build_pool` 和 `_derive_key` 的实现。没有 `.env` 时退化为纯 manifest 加密（向后兼容）。

#### 上下文引用（`--with-context`）

`publish --with-context` 扫描项目内所有 `[text](ref:path)` 引用，将指向项目**外部**的文件复制到 `_refs/<原路径>` 下打包：

```
MyKnowledge-以旧换新.mkpkg
└─ 以旧换新/
    ├─ readme.md
    ├─ common-knowledge/...
    └─ _refs/
        └─ common-knowledge/补贴标准.md   ← 外部引用
```

`_refs/` 递归扫描 3 层以捕获传递引用。导入时 `_refs/` 随 copytree 落入。

`get_document_with_refs` 解析优先级：
1. 当前项目 `_refs/<path>`（最高优先级，包快照）
2. `kb_root/<path>`（本地最新版本）
3. 都找不到 → `⚠ 不存在`

#### 导入与合并

详见 2.5.12。

### 2.5.6 项目去重与增量合并（未来增强）

同 v0.3 设计。`project_id`(uuid5) 从 readme frontmatter 读。

### 2.5.7 readme 格式规范

#### 统一模板

```markdown
---
id: root / {uuid5}
type: readme
name: {知识库名 / 项目名}
summary: {一句话描述}
status: active                          # 仅项目级有
updated: {日期}                         # summary 最近一次手动更新
generated: {日期}                       # 正文最近一次自动生成
parent: root / {父级 id}                # 根级没有此字段
---

# {name}

## 结构说明

本层统一结构：

- `common-knowledge/` — 知识条目（`.md` 文件，含 frontmatter）
- `projects/` — 子项目（递归，结构与本层相同）
- `archive/` — 已结项子项

## 核心文档

- `common-knowledge/{文件名}` ({日期}) — {summary}

## 子项目

- `projects/{子项目名}/` — {项目的 summary}

## 归档

- `{归档项目名}` — {项目的 summary}

➡ `archive/` 完整目录见 `archive/readme.md`
```

#### 摘要来源

| readme 区域 | 数据来源 | 字段 |
|------------|---------|------|
| frontmatter `summary` | 本级存储（AI 经 `update_project_meta` 填写） | readme frontmatter `.summary` |
| 「核心文档」条目 | 遍历 `common-knowledge/*.md` 的 frontmatter | `.summary` |
| 「子项目」条目 | 遍历 `projects/*/` 的 readme frontmatter | `.name`, `.summary` |
| 「归档」条目 | 遍历 `archive/*/` 的 readme frontmatter | `.name`, `.summary` |

> **「摘要不从正文提取」**——所有描述性文字全部来自 frontmatter 的 `summary` 字段。创建 doc 时 AI 负责填写，readme 生成器只做拼接不做语义理解。

#### 路径格式

所有路径使用**相对路径**，相对于本 readme 所在目录。

#### 设计原则

| 项 | 结论 |
|----|------|
| tag | 不做独立设计，后续可选脚本级加速 |
| schema | 每层 readme 都有，保持递归一致性和子树自包含 |
| 叶子 doc | 无独立 readme，在父层「核心文档」区列条目 + 日期 + summary |
| archive 指针 | 带条目速览，消除 agent 忽略归档的风险 |
| 独立 yaml | **不设**，全部合并到 readme frontmatter |

### 2.5.8 写入与级联更新流程

#### 写入触发链

```
create_document / update_document（agent 调 MCP）
  │
  ├── 系统机械层（同步，MCP 返回前完成）
  │     │
  │     ├── ① 写 .md 文件到磁盘
  │     ├── ② git add + commit（"create: 文件名.md"）
  │     ├── ③ rebuild 父层 readme
  │     │     ├── 读 frontmatter → 遍历 common-knowledge/ + projects/ + archive/
  │     │     ├── 从各文档 frontmatter 取出 name/summary/updated
  │     │     ├── 填模板 → 写回父层 readme.md → git add + commit
  │     │     └── 不更新父层 readme 的 frontmatter（summary 保留原样）
  │     └── ④ 返回 MCP 响应，附：{ rebuilt: "路径", summary_changed: false }
  │
  └── Agent 语义层（异步，agent 主动决定）
        │
        ├── ⑤ agent 读新的 readme，判断本级 summary 是否需要更新
        │     → 不需要：流程结束
        │     → 需要：调 MCP update_project_meta(path, summary="新描述")
        │
        ├── ⑥ update_project_meta 触发
        │     ├── 改 readme frontmatter.name/summary/status
        │     ├── 改 readme frontmatter.updated
        │     ├── 不改 body（不触发 rebuild，因为 body 是派生数据）
        │     └── git commit
        │
          └── ⑦ 系统自动触发 rebuild 父层 readme（祖父层 body 重算）
              → 让 agent 再次判断祖父层的 summary 要不要改
              → 递归直到根或某层说「不需要改」

#### 自动归档钩子

写完 + rebuild 完成后，`_write_through()` 和 REST API 写处理器会自动检查项目 readme 的 `status`：

```
⑧ 检查 status（_auto_archive 函数）
    │
    ├── status == "active" → 不动
    └── status != "active" → shutil.move("projects/X", "archive/X")
         ├── 替换已移动文件内的 ref: 路径前缀
         ├── gen.rebuild("") 重建根 readme
         ├── gen.rebuild_project_status()
         └── git commit + SSE broadcast
```

- **`completed`** / **`cancelled`** / **`abandoned`** 都会触发生成目录移动。
- `archive/` 不再只是"导航加速"，而是**非活跃项目的物理归宿**。
- 每个归档项目在 `archive/` 下保持其完整结构（`readme.md` + `common-knowledge/`）。

**MCP 工具清单（完整见 5 节末，共 22 个）**：

> **没有 `write_readme` 工具。** Readme 是派生数据，AI 不应直接写入正文。
>
> **铁律：AI 严禁通过任何方式直接操作 KB 文件系统。** 所有对 MYKNOWLEDGE_ROOT 的文件创建/修改/删除必须通过 MCP 工具完成。如果缺少某工具，AI 应记录需求并告知用户反馈项目开发方。
>
> **已补齐：** `write__move_project`（跨父级移动项目）已实现。现在改名用 `write__rename_project`，换父级用 `write__move_project`。
>
> **新增：** `nav__exists`（路径存在性检查）、`nav__find`（名称模糊搜索）、`nav__list_dir` 的 `recursive` 参数、`write__create_document` 的 `dry_run` 预览与 `if_exists` 策略。

### 2.5.9 会话锁定与维护流程

#### 锁定机制

```
~/.myknowledge/.lock    ← 存在表示 AI（或 Web UI）正在操作
格式：<PID>:<timestamp>  （进程ID:写入时间）
```

- **写操作自动加解锁**（v0.5 改进）：每个 MCP 写工具（`write__*`）在执行开始时自动调 `acquire_lock()`，执行结束后自动调 `release_lock()`。三步在一个工具调用内完成：
  ```
  acquire_lock → 执行写入 → rebuild → commit → broadcast → release_lock
  ```
- `acquire_lock()` 仅在 `.lock` 不存在时创建文件（已持有锁时静默跳过）
- `release_lock()` 总是删除 `.lock` 文件，并在 `agent-commit.txt` 中记录当前 HEAD 作为 checkpoint
- `maint__acquire_lock` / `maint__release_lock` 仍可用于只读流程（如 Review diff 后不想继续写时手动释放）
- Web UI 写接口检查 `.lock`：
  - 存在（5分钟内）→ 只读模式，返回 423 Locked
  - 存在（超过5分钟）→ 视为死锁，清除后继续
  - 不存在 → 正常写入
- 锁不阻止读取，只阻止写入

#### commit 策略

| 场景 | 谁写文件 | 谁 commit | commit 时机 |
|------|---------|-----------|------------|
| AI 经 MCP 修改 | AI | AI | 每次修改后立即 commit（write-through） |
| Web UI 人修改 | 人 | **不做** | 留 dirty 等 AI 处理 |
| 人直接改文件 | 人 | 人（可选） | checkpoint 记录 AI 最后处理点 |

#### AI 工作前检查流程

每次对话开始时，AI 按 `nav__maintenance_procedure` prompt 执行：

1. **调 `maint__read_diff`** 对比 `checkpoint..HEAD`
2. 无差异 → 正常开始
3. 有差异 → 读 diff → 校验 frontmatter → 修复 → 重建索引 → 更新 checkpoint

> **注意**：v0.5 起不再需要手动调 `maint__acquire_lock` / `maint__release_lock` 包裹写操作。写工具自动处理加解锁。
> 只读流程（`maint__read_diff` → review → 确认无写需要）结束时可手动调 `release_lock` 更新 checkpoint。

#### 人工编辑文件后的检修机制（旧版场景保留）

**场景 1 — Agent 经 MCP 写入**（正常路径）
- 同 2.5.8 write-through，自动加解锁 + 索引刷新。

**场景 2 — 用户经 Web UI 编辑**（受控路径）
- 走同一 FastAPI 后端 → 同 write-through 流程，但 Web UI 写操作不自动加解锁（由 AI 的 .lock 保护）。
- Web UI 只提供「保存」，不暴露「commit」功能，从 UI 层消除绕过 write-through 的可能。

**场景 3 — 用户直接改 .md 文件**（非受控路径）
- 绕过 storage 层，write-through 未触发。
- 兜底：`.myknowledge/agent-commit.txt` 记录最后一次 agent 处理的 commit hash。
- agent 复工时调 `maint__read_diff` 检查 `git log <checkpoint>..HEAD -- .myknowledge/`，有变化则：
  - 调 `maint__validate_doc` 修复 frontmatter（破坏格式的情况）
  - 调 `maint__rebuild_index` 重建 readme
  - 做语义级级联更新

**冲突解决（import_share）**：
- 机械层（脚本）：文件名级 + checksum 级识别冲突
- 语义层（agent）：标记冲突后 agent 读两份 diff，向用户提建议或自动 merge

### 2.5.10 待确认 / 待补强的设计点

- **模板自描述**：`_templates/common-knowledge.md` 通过自身 frontmatter 声明 `name` 与 `required_fields`，check 工具扫 `_templates/` 即可发现并查字段完整性。
- ~~archive = 导航加速，非状态管理~~（已废弃）：archive 现在是**非活跃项目的物理归宿**。状态变更（completed/cancelled/abandoned）自动触发 `shutil.move` 移入 archive/，见 2.5.8 自动归档钩子。
- **订阅/只读库落点**：待确认。
- **_refs/ 的生命周期**：发布时带上下文会引入 `_refs/`，但目前没有 GC 清理本地已删除引用源的 `_refs/` 残留。后续可加 `garbage_collect_refs()`。

### 2.5.11 知识引用（Reference）

#### 语法

正文中用标准 Markdown 链接标记引用位置：

```markdown
详情参考[补贴标准](ref:common-knowledge/补贴标准.md)。
精确段落参考[各品牌补贴](ref:common-knowledge/补贴标准.md::各品牌补贴标准)。
```

| 语法 | 含义 |
|------|------|
| `[text](ref:path)` | 引用整篇文档 |
| `[text](ref:path::title)` | 引用文档中 `## title` 标题下的段落 |
| `ref:` 前缀 | 标记为知识引用（浏览器不做跳转） |

#### 读取时拼接

`nav__get_document_with_refs(path)` 工具：

1. 读目标文档正文
2. 扫描 `](ref:...)` 模式提取引用列表
3. 去重 + 去循环
4. 对每个引用路径，按优先级查找：
   - **第 1 位**：当前项目 `_refs/<path>`（`--with-context` 导入的快照，最高优先）
   - **第 2 位**：`kb_root/<path>`（本地最新版本）
   - 都找不到 → `⚠ 不存在`
5. 按 `::标题` 截取段落（无标题则返回全文）
6. 拼接在末尾的「参考文献」区

#### 引用段落截取规则

- 匹配 `##` 或 `#` 标题，从标题下一行开始
- 截取到同级或更高级的下一个标题为止
- 找不到标题 → 返回全文 + 行首标记 `⚠ 未找到精确段落`

#### 正文结构规范（给 AI 的写入约定）

知识条目正文建议按 `##` 二级标题划分为独立段落，每个段落可是被 `[ref](path::标题)` 精确引用。

```markdown
---
summary: A 品牌最高 500 元
---

## 各品牌补贴标准
A 品牌最高 500 元，B 品牌最高 300 元。

## 型号兼容清单
| 品牌 | 型号 |
|------|------|
| A   | X100 |
```

#### 为什么不使用前端渲染兼容的 `#` 定位

前端渲染时 Markdown 标题有层级含义（HTML `<h1>`~`<h6>`），不宜与引用定位混合。改用 `::` 作为分隔符，与 `#` 解耦。

### 2.5.12 项目合并（import_share 合并逻辑）

导入 `.mkpkg` 时，如果 `project_id` 匹配本地已有项目，触发文件级合并。

#### 分类与动作

| 条件 | 动作 | 分类 |
|------|------|------|
| 本地无此文件 | 直接复制 | 新增 |
| 字节全等 | 跳过 | 无变化 |
| 字节不等，`maintainer` 相同 | 覆盖为导入版 | 自动更新 |
| 字节不等，`maintainer` 不同 | 本地不动，导入版另存为 `原文件名（来自昵称）.md` | **冲突** |
| 本地有，导入包无 | 不动，收集进报告 | **待确认删除** |

#### 合并工作流

```
脚本机械层（import_share 内部）：
  1. 扫描两边文件 → 按上表分类
  2. 执行自动操作（新增/跳过/自动更新/冲突另存）
  3. rebuild 项目 readme → rebuild 根 readme → rebuild 项目状态 → git commit
  4. 返回结构化报告

Agent 语义层（读取报告后，用户交互）：
  1. 冲突文件 → read_diff / get_document_with_refs 读两份内容
     → 向用户展示 diff → 用户确认后写合并版
  2. 待删除文件 → 用户确认后调 delete_document 工具删除
```

#### 报告格式

```
=== 导入报告 ===
项目: 以旧换新
来源: 张三

✓ 新增 (2): 流程演练.md, 品牌清单.md
= 无变化 (3): readme.md, 补贴标准.md, 机型清单.md
✓ 更新 (1): 费率表.md

⚠ 冲突 (1):
  · 补贴标准.md — 本地维护者: 张三 vs 导入维护者: 李四
  本地版已保留；导入版另存为「补贴标准（来自李四）.md」.
  请用 read_diff 或 get_document 查看两份内容，确认后手动合并。

⚠ 本地有但导入包中无 (1): 旧流程.md
  这些文件在分享方已被删除。确认后请用户用 delete_document 删除。
```

#### 删除的安全策略

删除是敏感操作，脚本**永不自动删除**文件，只报告。agent 得到用户确认后，调 `MCP delete_document` 工具执行删除。

---

## 3. 「取·用·存」闭环

| 阶段 | MyKnowledge 实现 |
|------|------------------|
| 取 | MCP `nav__list_dir`（支持 `recursive`）/ `nav__read_readme` / `nav__get_document` / `nav__exists` / `nav__find`；agent 从根 readme 起语义递归下钻 |
| 用 | **由 agent client 完成** |
| 存 | MCP `write__create_document`（支持 `dry_run` + `if_exists`）/ `write__update_document` / `write__update_project_meta`，自动 write-through + 记录版本 |
| 云 | 可选：OSS 定时同步 / 更新即上传 |

---

## 4. 功能模块

### 4.1 知识库管理
创建/删除/列出知识库；type（个人/共享/订阅）；共享库可绑定 OSS 同步；订阅库为只读副本。

### 4.2 检索
FS + readme 递归为主，可选 FTS5 L0 加速。

### 4.3 写入
`create_document` / `update_document` / `update_project_meta`。自动 write-through 重建 readme + 记录版本。

### 4.4 云同步
OSS 定时同步 / 更新即上传（文件监听或 git hook）。

### 4.5 连接器
统一插件接口，不内置重量连接器。

### 4.6 产物与发布
分享包加密压缩 + OSS 分享链接。

### 4.7 Web UI
调同一后端，保证人和 AI 走同一数据通道。

---

## 5. 技术架构

```
┌────────────────────────────────────────┐
│  外部 agent client                      │  ← 智能在这里
│  (CodeBuddy/WorkBuddy/Trae)            │
└──────────────────┬─────────────────────┘
                   │ MCP 协议 (stdio)
┌──────────────────▼─────────────────────┐
│              mcp_server.py              │ ← 22 个 MCP 工具
│   storage.py  ·  readme_generator.py   │
│   config.py   ·  git_manager.py        │
│   share.py    ·  cli.py                │
└──────┬───────────────────┬─────────────┘
       │                   │
┌──────▼──────┐    ┌──────▼──────┐
│ Storage 层  │    │ SyncJob     │
│ .md IO      │    │ OSS 同步    │
│ readme 生成 │    │ (Phase 5)   │
└──────┬──────┘    └──────┬──────┘
       │                   │
┌──────▼───────────────────▼──────────────┐
│  .myknowledge/ 目录树                   │
│  （真相源，git 跟踪）                    │
│  OSS bucket ← 你自己的账号（可选）       │
└─────────────────────────────────────────┘
```

**当前依赖**：`mcp >=1.0.0`, `pyyaml`, `pytest`, `pytest-asyncio`

**未来依赖（OSS 阶段追加）**：`oss2`, `apscheduler`

> `frontmatter` 解析内联在 `storage.py` 中，没有独立的 `markdown_parser.py`。

> **不引入**：任何 LLM/推理框架、向量数据库。

### MCP 工具清单（共 22 个）

按前缀分组。建议 agent client 显式配置只暴露需要的分组，减少工具干扰。

| 分组 | 工具 | 说明 |
|------|------|------|
| `nav:` (6) | `nav__read_readme` | 读路由索引 |
| | `nav__list_dir` | 列目录（支持 `recursive=True` 递归展开） |
| | `nav__exists` | 一次性确认路径是否存在 |
| | `nav__find` | 按名称模糊搜索（不区分大小写，支持 scope） |
| | `nav__get_document` | 读全文 |
| | `nav__get_document_with_refs` | 读全文 + 拼接引用 |
| `write:` (8) | `write__create_document` | 新建知识（支持 `dry_run` 预览 + `if_exists` 策略） |
| | `write__update_document` | 更新知识 |
| | `write__update_project_meta` | 改项目 frontmatter |
| | `write__delete_document` | 删除文档 |
| | `write__delete_project` | 删除整个项目目录（替换 ref + rebuild） |
| | `write__rename_project` | 改名项目（移动目录 + 替换 ref） |
| | `write__move_project` | 移动项目到不同父级（替换 ref + 重建 readme） |
| | `write__rename_document` | 改名文档（移动文件 + 替换 ref） |
| `maint:` (6) | `maint__acquire_lock` | 获取写锁 |
| | `maint__release_lock` | 释放写锁 |
| | `maint__read_diff` | 读 git diff（对比 checkpoint） |
| | `maint__rebuild_index` | 手动重建 readme |
| | `maint__check_integrity` | GC + 项目状态更新 |
| | `maint__validate_doc` | 检查 frontmatter 完整性 |
| `share:` (2) | `share__publish` | 导出分享包 |
| | `share__import_share` | 导入分享包 |

### 路径校验

所有写工具接受路径后先过 `_validate_path(kind="file"|"dir")` 检查：

| 检查项 | 说明 |
|--------|------|
| 路径穿越 | 禁止 `..` |
| 绝对路径 | 禁止以 `/` 开头 |
| 扩展名 | 文档必须 `.md` |
| 前缀 | 文档路径必须以 `common-knowledge/`、`projects/` 或 `archive/` 开头 |
| 存在性 | 更新/删除/改名操作会检查文件或目录是否存在 |

校验失败的报错包含**恢复指引**（什么工具能列出正确路径），AI 可自助恢复。

### 版本

系统版本号在 `backend/__version__.py`，硬编码 `0.5.0`。`GET /api/version` 返回 `{system, kb}`：
- `system` — 系统版本（手动更新）
- `kb` — 知识库版本（从 `agent-commit.txt` checkpoint 读取，无则空）

### 自动项目骨架

`ReadmeGenerator.rebuild()` 首次为项目建立 readme 时，自动创建 `common-knowledge/`、`projects/`、`archive/` 子目录。无需手动初始化。

> **当前**：MCP 协议无原生工具分组，当前用前缀命名（`nav__` / `write__` / `maint__` / `share__`）模拟分组。如后续协议支持分组暴露，可按组分别注册。

---

## 6. 数据格式约定

### readme.md frontmatter

```yaml
---
id: root / {uuid5}
type: readme
name: MyKnowledge / 以旧换新
summary: 一句话描述
status: active                          # 仅项目级
updated: 2026-07-23
generated: 2026-07-23
parent: root / {父级 id}
---
```

### 知识条目 frontmatter

```yaml
---
id: doc_20260723_a1b2
type: knowledge                        # knowledge | artifact | profile | note
summary: A 品牌最高 500 元              # readme 生成器以此为条目描述
template: common-knowledge             # 所用模板名
author: 张三 <user@example.com>         # 创建者（自动注入，首次写入后不变）
maintainer: 张三 <user@example.com>     # 最后维护者（每次更新自动更新）
source: agent创建                       # 来源说明
source_client: CodeBuddy               # 产生者
created: 2026-07-23
updated: 2026-07-23
---
```

> 引用不再使用 `see_also` frontmatter 字段，改用正文内 `[text](ref:path::title)` 语法（详见 2.5.11）。

---

## 6. 部署与配置总览

### 6.1 三个配置点

| 配置点 | 用途 | 配置位置 | 设置方式 |
|--------|------|----------|----------|
| **后端 → 知识库目录** | 决定 REST API/MCP 读写哪个 KB | `backend/config.py` `resolve_root()` | `MYKNOWLEDGE_ROOT` 环境变量 或 `--root` CLI 参数 |
| **前端 → 后端地址** | 决定浏览器请求哪个 API 服务器 | `frontend/js/api.js` `API_BASE` | 代码硬编码 `127.0.0.1:8080`，或 `window.__MYK_API_BASE__` 覆写 |
| **CodeBuddy → MCP 服务器** | 决定 AI agent 连接哪个 MCP 进程 | `.codebuddy/mcp.json` | json 配置 `command` + `args` + `env` |

**关键区分**：前端只需要知道"API 在哪个端口"，不关心后端读的是 `.myknowledge` 还是 `.myknowledge_test`。知识库目录选择是后端的事。

### 6.2 启动命令

```bash
# 开发（测试知识库）
MYKNOWLEDGE_ROOT=.myknowledge_test uvicorn backend.main:app --port 8080
cd frontend && python3 -m http.server 8081
# 浏览器访问 http://127.0.0.1:8081/index.standalone.html

# 生产（全局知识库）
myknowledge serve    # 不需要 --root，默认 ~/.myknowledge/
```

### 6.3 实时事件（SSE）

当 MCP 或 REST API 写入知识库时，前端需要及时刷新展示。采用 **SSE（Server-Sent Events）** 方案：

```
写路径（MCP _write_through / REST API handlers）
  ↓ broadcast(kb_root)
  ↓
.events/version.json          ← 文件级版本计数器（本地）
  ↓ 可插拔，云上换 Redis/DB   ← 接口不变
SSE /api/events                ← 纯 HTTP
  ↓ 浏览器 EventSource 自动连接
前端自动重新加载当前视图
```

架构优势：
- **本地**：MCP 和 FastAPI 是两个独立进程，通过文件桥接版本变化
- **云上**：只需把 `broadcast()`/`poll_version()` 实现从文件换成 Redis pub/sub，SSE 端点和前端代码完全不变
- **不依赖 WebSocket**，浏览器原生 `EventSource` API 自动处理重连

轮询间隔：每 2 秒检查版本文件，每 15 秒发 keepalive 防止代理断开连接。

---

## 7. 分阶段实现路线图

- **Phase 0（已完成）**：PRD + 设计文档
- **Phase 1（已完成）**：`storage.py`, `git_manager.py`, `readme_generator.py`, `_templates/`
- **Phase 2（已完成）**：22 个 MCP 工具 + `cli.py`（init/mcp/check/login/whoami）
- **Phase 4（已完成）**：`share.py`（publish / import_share / 加密 / 合并 / --with-context）
- **Phase 7（已完成）**：按 `maintainer` + 字节对比的文件级合并
- **Phase 3** — Web UI 最小闭环（`main.py` FastAPI）
- **Phase 5** — 云同步 OSS（SyncJob + `.env`）
- **Phase 6** — 连接器体系（插件接口）

---

## 8. 与全竞品差异化一句话总结

> 个人知识管理有 Obsidian / Logseq / Roam，企业知识 SaaS 有飞书知识库 / ima，agent 可读的本地 KB 有 IWE——但「企业敢用（数据归你、不内置 LLM、合规可审计）、agent 能用（原生 MCP）、人可控（Web UI + 纯 Markdown + Git）」这个交集，目前只有 MyKnowledge。
