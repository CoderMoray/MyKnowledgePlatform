# MyKnowledge 可视化知识图谱 — 工程实现方案

> 面向对象：负责后端 / 前端实现的专用 AI
> 配套文档：`DESIGN.md`（设计原则、数据模型、交互定义）
> 约定：所有改动保持「零 LLM 调用、只读图谱、复用既有原语」。

---

## A. 后端：图提取模块

### A.1 新增 `backend/graph_extractor.py`

纯函数模块，输入 `Storage`，输出 `GraphPayload`。不写文件、不调模型。

**核心函数签名（建议）：**

```python
# backend/graph_extractor.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
import re
from backend.storage import Storage

REF_RE = re.compile(r'\]\(ref:([^\s)]+?)(?:::([^)]*))?\)')

DEFAULT_OVERVIEW_LIMIT = 500

@dataclass
class GraphNode:
    id: str
    path: str
    title: str
    summary: str = ""
    type: str = "knowledge"
    tags: list[str] = field(default_factory=list)
    project: str = ""
    updated: str = ""
    link_count: int = 0

@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str = "ref"
    resolved: bool = True

@dataclass
class GraphPayload:
    scope: str
    stats: dict
    nodes: list
    edges: list
    generated_at: str

def extract_graph(storage: Storage, scope: str = "overview",
                  center: str = "", depth: int = 1,
                  project_rel: str = "", limit: int = DEFAULT_OVERVIEW_LIMIT) -> GraphPayload:
    ...
```

**节点枚举**：遍历 `storage.kb_root`，收集所有 `.md`（排除 `readme.md`、`project-status.md`、隐藏文件、`.codegraph/` 等系统目录）。每个文档：
- `path` = 相对 `kb_root` 的路径（统一正斜杠）
- `id` / `title` / `summary` / `type` / `tags` / `updated` 来自 `storage.read_frontmatter(path)`（字段缺失时用兜底：title=文件名去 `.md`，type=frontmatter 默认或 `"knowledge"`）
- `project` = 路径中 `projects/<name>/...` 段的 `<name>`，否则 `""`（公共知识）
- 解析 `body` 中的 `ref:` 链接（用 `REF_RE`）填入出度；同时全局统计入度

**边解析（关键）**：复用现有 ref 解析逻辑，而非重写。
- 直接在 `graph_extractor` 内对每篇文档 `body` 跑 `REF_RE`，得到 `(ref_path, section)` 列表。
- `target` 解析：复用 `backend.mcp_server._resolve_ref(base_path, ref_path, storage)`（见 `mcp_server.py` 中对 `./`、`../`、`_refs/`、`_common/` 的处理），解析失败 → `resolved=False`，`target=ref_path` 原样保留用于展示。
- 去重：同一 `(source, target)` 只保留一条边（多 ref 合并）。

**模式逻辑：**
- `scope="overview"`：收集全部节点，按 `link_count` 降序取 `limit`；保留这些节点之间的边（含指向被截断节点的边，但 target 节点不在 nodes 列表时仍返回 edge 并 `resolved` 按真实情况）。
- `scope="ego"`：以 `center` 为种子，BFS 展开 `depth` 层（沿出度+入度方向），返回子图节点+边。`depth` 默认 1，前端 `growFrontier` 时递增。
- `scope="project"`：只枚举 `projects/{project_rel}/**` 下的文档（递归子项目）。

**`stats`**：`node_count`、`edge_count`、`truncated`（overview 是否触发上限）。

**`generated_at`**：`datetime.now().isoformat(timespec="seconds")`。

> 复用提示：`storage.read_frontmatter`、`storage.read_document`、`storage.read_dir` 已实现；`storage.kb_root` 是 `Path`。`main.py` 的 `api_status_detail` 里有现成的 `_walk_docs` 遍历范式可直接参考（含 `common-knowledge` / `archive` / `projects/**/common-knowledge` 递归）。

---

## B. 后端：REST 接口

在 `backend/main.py` 注册（放在 `/api/status/detail` 附近，写接口区之前）：

```python
@app.get("/api/graph")
def api_get_graph(scope: str = "overview",
                  center: str = "",
                  depth: int = 1,
                  project: str = "",
                  limit: int = 500):
    """返回 KB 文档关系图谱（确定性，无 LLM）。

    scope: overview | ego | project
    """
    storage, _ = get_storage()
    from backend.graph_extractor import extract_graph
    payload = extract_graph(
        storage, scope=scope, center=center,
        depth=depth, project_rel=project, limit=limit,
    )
    return asdict(payload)
```

- 无需写锁检查（只读）。
- `limit` 上限建议硬截断（如 ≤2000）防滥用。

---

## C. 后端（可选）：MCP 工具

在 `backend/mcp_server.py` 的 `nav__` 工具组新增（与 `nav__get_document` 等一致），供外部 AI client 结构化探查：

```
tool: nav__get_graph
args: { scope: str, center?: str, depth?: int, project?: str, limit?: int }
returns: GraphPayload (同 REST)
```

实现直接调用 `graph_extractor.extract_graph`，复用 `create_mcp_app` 的 storage。这样外部 client 能在「零模型」前提下理解 KB 拓扑，再决定是否补充链接。

---

## D. 前端：API 客户端

`frontend/js/api.js` 的 `api` 对象新增：

```js
async getGraph({ scope = "overview", center = "", depth = 1, project = "", limit = 500 } = {}) {
  const qs = new URLSearchParams({ scope, depth, limit });
  if (center) qs.set("center", center);
  if (project) qs.set("project", project);
  return apiRequest(`/api/graph?${qs.toString()}`);
},
```

---

## E. 前端：路由

`frontend/js/router.js` 的 `setupRouter()` 中新增 hash 解析：

- `#graph` → `currentView="graph"`，scope=overview
- `#graph/project/{rel}` → `currentView="graph"`，scope=project，记录 projectRel
- 点击节点跳转文档仍用既有 `goToDocument(path)`（`#doc/{path}`）。

在 `$store.app` 的 view 白名单里加入 `"graph"`（参考 dashboard/project/view/edit/status 的现有注册方式）。

---

## F. 前端：图谱组件

新增 `frontend/js/graph.js`，导出 `graphComponent`（Alpine `x-data`），由 `index.html` 的 graph 视图容器引用：

```html
<div x-show="$store.app.currentView === 'graph'" x-data="graphComponent" x-cloak>
  <!-- 控制条 + SVG/Canvas 画布 + 节点详情抽屉 -->
</div>
```

**渲染库选型（二选一，推荐 cytoscape）：**
- **cytoscape.js**（推荐）：CDN 引入即带平移/缩放/点击/布局（cose/force-directed），社区成熟，对接 Alpine 简单。
  - CDN：`https://cdn.jsdelivr.net/npm/cytoscape@3.30.2/dist/cytoscape.min.js`，在 `index.html` 的 `<script>` 区追加。
- **d3-force**：更可控但需手写 pan/zoom（WeKnora 即手写）。除非要高度定制视觉，否则不推荐。

**组件职责：**
1. `init()`：调用 `api.getGraph(...)` 拉数据 → 转换为 cytoscape `elements`（nodes/edges）。
2. 节点样式：`background-color` 按 `type`/`project` 映射（复用 `design-tokens.css` 的 `--accent` 等变量以适配明暗主题）；`width/height` 按 `link_count` 缩放；`label` = title。
3. 边：`target-arrow-shape: triangle`；`resolved=false` 时 `line-style: dashed` + 警告色。
4. 点击节点：右侧抽屉展示 `summary` + `tags` + `ref:` 列表；列表项点击 → `goToDocument(path)`。
5. 「展开邻域」按钮：ego 模式 `depth+1` 重新请求并合并到当前图（`growFrontier`）。
6. 搜索框：按 title/tag 过滤 `display:none` 节点。
7. 订阅 SSE：`api.subscribeEvents(() => debounce(reload, 2000))`。

**明暗主题**：cytoscape 样式需读取 `document.documentElement` 的 `data-theme`，或监听 MutationObserver 切换调色板（参考 `index.html` 中现有 `updateHljsTheme` 的 MutationObserver 范式）。

---

## G. 前端：侧边栏入口

`frontend/index.html` 的 `sidebar-nav` 中「仪表盘」下方新增「知识图谱」项（图标用 network/share-2 SVG），点击 `window.location.hash='graph'`，`:class` 绑定 `currentView === 'graph'` 高亮。

---

## H. 测试

- 新增 `tests/backend/test_graph_extractor.py`：
  - 用临时 KB（`tmp_path` + 若干 `.md` + `ref:` 链接）验证 nodes/edges 数量与 `link_count`。
  - overview 触发 `truncated` 的边界（构造 >500 节点或 mock limit）。
  - ego BFS 深度正确。
  - 悬空 `ref:` → `resolved=false`。
- 新增 `tests/frontend/test_graph.py`（沿用 `tests/frontend/test_smoke.py` 的 pytest+playwright 范式）：访问 `#graph` 断言画布渲染、点击节点跳转文档。

---

## I. 实施顺序（建议提交粒度）

1. `backend/graph_extractor.py` + 单元测试（核心逻辑，无前端依赖）。
2. `backend/main.py` 的 `/api/graph` + 手动 curl 验证。
3. （可选）`mcp_server.py` 的 `nav__get_graph`。
4. `api.js` 的 `getGraph`。
5. `router.js` 路由 + `index.html` 侧边栏入口 + 占位视图。
6. `graph.js` + cytoscape 渲染 + 抽屉交互 + SSE 刷新。
7. 前端测试 + `FRONTEND_STATUS.md` 更新。

每步独立可验证，便于分 PR review。
