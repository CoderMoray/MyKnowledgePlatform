---
name: common-knowledge
required_fields: [summary]
---

# common-knowledge 知识条目模板

## 用途

项目或知识库下的公共知识条目，如业务规则、流程说明、配置标准等。

## 格式约定

正文为自由 Markdown。frontmatter 必须包含以下字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 自动 | 系统生成，格式 `doc_yyyymmdd_xxxx` |
| `type` | 必填 | `knowledge` |
| `summary` | **必填** | 一句话摘要，readme 生成器以此为条目描述 |
| `template` | 自动 | `common-knowledge` |
| `created` | 自动 | 系统生成 |
| `updated` | 自动 | 系统生成 |

### 正文结构建议

正文建议按 `##` 标题划分为独立段落。这样可以被引用工具精确定位：

```markdown
## 各品牌补贴标准
A 品牌最高 500 元，B 品牌最高 300 元。
```

引用时使用：

```markdown
详情参考[补贴标准](ref:common-knowledge/补贴标准.md::各品牌补贴标准)。
```

| 语法 | 含义 |
|------|------|
| `[text](ref:path)` | 引用整篇文档 |
| `[text](ref:path::标题)` | 引用 `## 标题` 段落 |

参考文献区的拼接由 `get_document_with_refs` 工具自动完成。

## 示例

```markdown
---
id: doc_20260723_a1b2
type: knowledge
summary: A 品牌最高 500 元，B 品牌最高 300 元，C 品牌按型号阶梯定价
template: common-knowledge
source: agent创建
created: 2026-07-23
updated: 2026-07-23
---

## 各品牌补贴标准
A 品牌最高 500 元，B 品牌最高 300 元，C 品牌按型号阶梯定价。

### C 品牌明细
- 基础款：200 元
- 旗舰款：600 元
```
