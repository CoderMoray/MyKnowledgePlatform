# MyKnowledge 可视化知识图谱 — 设计文档

> 版本：v0.1 (Draft) · 状态：待后端 AI 实现
> 关联：本项目定位（本地优先、Markdown 真相源、零模型、MCP 原生）
> 对标参考：Tencent/WeKnora `WikiBrowser`（Wiki 可视化图，确定性，非 LLM）

---

## 1. 背景与动机

用户希望为 MyKnowledge 增加「可视化知识图谱」能力，让分散在各项目、各文档之间的关联一目了然。

在调研 WeKnora 后确认：**可视化知识图谱 ≠ 检索增强（GraphRAG）**。WeKnora 内部有两套独立的图：

| 图 | 节点 | 边 | 用途 | 是否 LLM |
|---|---|---|---|---|
| 实体关系图 (`internal/application/service/graph.go`) | LLM 抽取的 Entity | LLM 抽取的 Relation | GraphRAG 多跳检索增强（存 Neo4j） | **是（贵、概率性）** |
| **Wiki 可视化图 (`getWikiGraph`)** | **Wiki 页面** | **页面 `[[wikilink]]`** | **前端可视化导航** | **否（确定性）** |

用户直觉「嵌套索引作图 + node 链接跳转」指的是**第二套**——而这正是 MyKnowledge 已经具备、且能以**零模型成本**确定性产出的部分。

### 战略定位

- MyKnowledge 坚持「推理在外」：图谱是结构化存储的**副产品**，不额外消耗模型算力。
- 节点/边来源于已有的 frontmatter + 显式 `ref:` 链接 + `readme_generator` 的层级索引，确定、即时、可审计、可复现。
- 未来 LLM 增强方向（如跨文档实体抽取）可作为**可选叠加层**，挂在确定性图之上，而非替代它。这与项目「零模型成本」的边界原则一致。

---

## 2. 核心设计原则

1. **确定性优先**：图谱完全由文件扫描生成，不调用任何 LLM。同一份 KB，任何时候生成的图一致。
2. **复用既有原语**：直接复用 `ref:` 链接机制（`renderer.js` 已渲染、`mcp_server.py` 已解析）作为边的唯一来源；复用 `Storage` 的目录/文档枚举作为节点来源。
3. **不强加写作负担**：用户/agent 继续用 `ref:路径` 写关联，**无需学习新的图语法**。图谱只是把隐含结构「画出来」。
4. **与写链路解耦**：图谱是**只读视图**，不参与写事务，不污染 `ref:` 语义。
5. **性能兜底**：大库必须有节点上限（默认 500）与「以某文档为中心展开邻域（ego）」模式，避免浏览器卡死（对齐 WeKnora 的 `overview` / `ego` 双模式）。
6. **实时性**：监听现有 SSE `updated` 事件，KB 变更后前端自动重绘（复用 `api.subscribeEvents`）。

---

## 3. 数据模型

### 3.1 节点（GraphNode）

每个 `.md` 文档（不含 `readme.md`）对应一个节点。可选：`readme.md` 可作为「项目/层级」分组节点。

```jsonc
{
  "id": "doc_20260728_a1b2c3",   // 来自 frontmatter.id（确定性，见 storage.generate_doc_id）
  "path": "projects/以旧换新/common-knowledge/补贴标准.md", // KB 相对路径（图的稳定 key）
  "title": "补贴标准",            // frontmatter.title 或文件名（去 .md）
  "summary": "以旧换新补贴的计算口径", // frontmatter.summary
  "type": "knowledge",           // frontmatter.type：knowledge | artifact | note
  "tags": ["政策", "换算"],        // frontmatter.tags（可选，用于分组/配色）
  "project": "以旧换新",          // 所属项目名（从路径推导）
  "updated": "2026-07-28",       // frontmatter.updated
  "link_count": 12               // 入度 + 出度（见 §3.3）
}
```

**节点颜色/形状建议**（前端自由决定，后端只提供数据）：
- 按 `type` 区分形状（knowledge=圆，artifact=方，note=三角）
- 按 `project` 或 `tags` 区分配色
- 节点尺寸按 `link_count` 缩放（度中心性可视化）

### 3.2 边（GraphEdge）

边只来自文档正文中的 `ref:` 链接。

```jsonc
{
  "source": "projects/以旧换新/common-knowledge/补贴标准.md",
  "target": "common-knowledge/术语表.md",
  "kind": "ref"   // 当前唯一类型；未来可扩展 relation/knowledge
}
```

- `source` = 含链接的文档路径；`target` = 被引用的文档路径（解析 `_refs/` 后如 `mcp_server._resolve_ref`）。
- 单向有向（A 引用 B）。如需无向，前端可双向渲染，但数据保持有向以保留语义。
- **悬空边处理**：若 `target` 解析不到真实文档，`resolved=false`，前端用虚线/灰色渲染，并在详情提示「引用目标不存在」（对齐 `main.py` 中 `refs[].resolved` 的现有行为）。

### 3.3 link_count 计算

`link_count = 出度(ref 指向他人) + 入度(被他人 ref)`。

- WeKnora 用 `link_count` 做 `overview` 模式 Top-N 排序依据——这是它防卡顿的核心。我们同样采用。

### 3.4 图谱响应包（GraphPayload）

```jsonc
{
  "scope": "overview",          // overview | ego | project
  "stats": { "node_count": 340, "edge_count": 410, "truncated": true },
  "nodes": [ /* GraphNode[] */ ],
  "edges": [ /* GraphEdge[] */ ],
  "generated_at": "2026-07-28T10:00:00"
}
```

---

## 4. 两种视图模式（对齐 WeKnora）

| 模式 | 触发 | 逻辑 | 对应 WeKnora |
|---|---|---|---|
| **overview** | 默认进入图谱 | 枚举全库文档，按 `link_count` 取 **Top 500**（可配）节点 + 其全部边 | `getWikiGraph(overview)` |
| **ego** | 点击节点「展开邻域」 | 以某中心文档为种子，BFS 展开 `depth` 层（默认 1，可 `growFrontier` 逐层加），返回子图 | `getWikiGraph(ego, {center, depth})` |
| **project** | 进入某项目视图的图谱 | 限定 `projects/{rel}/**` 范围 | （本项目扩展，WeKnora 无直接对应） |

- 大库（>500 节点）默认 overview 截断并 `truncated=true`；用户可切到具体项目或 ego 模式深挖。
- ego 模式的「逐层展开」对应 WeKnora 的 `growFrontier`：前端持有当前子图，点「展开」时带 `depth+1` 重新请求并合并。

---

## 5. 与现有系统的关系图

```
                写操作（MCP / REST / agent）
                          │
                          ▼
   ┌───────────────  Storage (kb_root/*.md)  ───────────────┐
   │  frontmatter + body + `ref:` 链接 + 目录层级           │
   └──────────────────────────┬─────────────────────────────┘
                              │  只读扫描
                              ▼
              graph_extractor（新增，纯函数，无 LLM）
               nodes ← 枚举 .md；edges ← 解析 ref:
                              │
              ┌───────────────┴────────────────┐
              ▼                                 ▼
        REST /api/graph                   MCP nav__get_graph
              │                                 │
              ▼                                 ▼
        frontend graph.js (Alpine)      （供外部 AI client 探查结构）
        力导向渲染 + 点击跳转 #doc/{path}
```

- **不改动** `ref:` 语义、`readme_generator`、写事务。
- graph 模块是纯读取 + 转换，可独立测试。

---

## 6. 交互设计（前端草图）

- 主区域为力导向画布（平移/缩放/拖拽节点）。
- 顶部控制条：模式切换（总览 / 项目 / ego）、节点上限、图例开关、搜索框（按 title/tag 过滤）。
- 节点点击：右侧抽屉显示该文档 frontmatter + summary + 其 `ref:` 列表；点列表项 → `window.location.hash = "doc/{path}"` 跳转（即 WeKnora 的「node 链接跳转」）。
- 节点「展开邻域」按钮 → 切换到 ego 模式并 growFrontier。
- 边悬空（resolved=false）用虚线 + 警告色，点击提示修复 `ref:`。
- 接收 SSE `updated` → 防抖后重新 `api.getGraph` 并重绘。

---

## 7. 验收标准（Definition of Done）

1. 后端 `GET /api/graph?scope=overview` 返回含 ≤500 节点 + 全部边的合法 `GraphPayload`。
2. `GET /api/graph?scope=ego&center=<path>&depth=2` 返回以该文档为中心、深度 2 的子图。
3. 边与文档内 `ref:` 链接一一对应；悬空 `ref:` 标记为 `resolved=false`。
4. 前端 `#graph` 路由可渲染力导向图，点击节点跳转对应文档。
5. KB 内容变化（写操作触发的 SSE）后，图谱在 5s 内自动刷新。
6. 零 LLM 调用：图谱生成全程不依赖任何模型接口。
7. （可选）`nav__get_graph` MCP 工具供外部 client 以结构化方式探查 KB 关系。

---

## 8. 未来增强方向（非本期，记录供 roadmap）

- **LLM 实体层（GraphRAG 风格，可选叠加）**：在确定性图之上，用外部 client 抽取跨文档实体/关系，作为额外 `kind=relation` 的边。这与本期确定性图共存，不替换。
- **标签聚类布局**：用 `tags` 做社区检测（如 d3-force `forceCluster`），让同主题文档聚团。
- **时间轴回放**：按 `updated` 字段做图谱随时间的演化动画。
- **项目级 subgraph 缓存**：将 `project` 模式结果落盘（类似 `project-status.md`），减少大库重复扫描。
