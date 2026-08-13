# 后端评估任务：垃圾箱死链检查性能（临时任务单）

> 状态：📋 待架构评估 | 创建：2026-08-13
> 提出方：前端 agent（实测定位） | 归属：后端（架构决策后由后端 agent 实施）
> 本任务单自包含，无需翻历史会话

## 一、现象（用户可感知）

1. **hover 文档卡片 → 正文预览「加载中」约 3 秒**（此前秒加载）
2. **点击进入含死链引用的文档 → 数秒显示「文档不存在或无法加载」**（实为数据未到时的误显示，非真 404）

## 二、实测数据

对同一后端（8080）直连测 `/api/document/{path}/refs`：

| 文档 | 是否含死链 | /refs 耗时 |
|---|---|---|
| `common-knowledge/refwarn-final.md` | 是（`ref:common-knowledge/no-such-doc.md`） | **2466ms / 1715ms / 1669ms**（持续慢，非预热） |
| `common-knowledge/refwarn-test.md` | 是 | 1823ms |
| `common-knowledge/技术选型.md` | 否（refs 全部正常） | 6ms |

`GET /api/document/{path}`（不含 refs）一律 4~18ms（快）。

## 三、根因（已定位，代码级）

- 前端 hover 预览与文档页打开都调 `getDocumentWithRefs`（`/refs` 端点）。
- `/refs`（`backend/main.py:517`）对每个死链引用调 `ref_status()`（`backend/trash.py:297`）。
- `ref_status` 逻辑：先 `Path.exists()` 检查原始路径（O(1)，快）→ **不存在则调 `list_trash()` 全量扫垃圾箱**。
- `list_trash`（`backend/trash.py`）实现：`glob("trash/documents/*.md")` 枚举 + **对每个文件 `storage.read_document` 读 frontmatter（磁盘 I/O + YAML 解析）** + 再扫 `trash/projects/*/readme.md`。
- 当前测试库垃圾箱 **4939 个文件** → 每次死链检查 = 4939 次文件读 ≈ 1.7~2.5s。
- 正常路径从不扫目录（`_resolve_ref` 最多 2 次单路径读）；**垃圾箱无任何索引，判断「某路径是否在垃圾箱」只能全量枚举比对 `original_path`**——这是唯一慢点，且随垃圾箱膨胀线性恶化。

## 四、方案建议（供架构评估，非定案）

**给垃圾箱加索引**：`trash/trash_index.json`，存 `original_path → trash_path` 映射（documents 与 projects 两类）。

- **索引更新点（后端 4 处，前端零改动）**：
  - `delete_document`（进垃圾箱）
  - `restore_trash`（恢复）
  - `empty_trash`（清空）
  - `gc_trash`（30 天自动清理）
- **`ref_status` 死链分支改为**：查索引 → 命中后 `stat` 对应 `trash_path` 兜底确认（防索引与磁盘不一致）→ `in_trash` / `dead`。
- **一致性兜底**：索引缺失/损坏 → 回退现有 `list_trash` 全扫并重建索引（兼容旧数据/手动改文件）。
- **附带收益**：垃圾箱页面（`list_trash`）同步提速。

## 五、验收方向

- 含死链文档 `/refs` 耗时 < 100ms（由 2.5s 降至毫秒级）。
- trash 增删（删除/恢复/清空/GC）后索引正确，`ref_status` 分类不误判。
- 索引文件缺失/损坏时仍可用（回退重建），不阻塞现有功能。

## 六、前端关联项（独立任务，不阻塞后端）

- `loadDocument` 增加 pending 态：加载中显示「加载中…」，真 404 才显示「文档不存在或无法加载」（现被误显示为后者）。
- hover 预览轻量化（只需「被 N 篇引用」计数，不需要死链详情）——待后端提供轻量端点/列表字段后接入。

## 七、备注

- 垃圾箱膨胀来源：测试（H/S 系列删除文档后仅 `trash/empty` 清理），真实库同样会随时间积累。
- 前端侧不改动任何文件系统/索引逻辑；本任务全部改动预期在后端。
