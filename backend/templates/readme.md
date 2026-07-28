---
id: {layer_id}
type: readme
name: {name}
summary: {summary}
status: {status}
author: {author}
maintainer: {maintainer}
created: {created}
updated: {updated}
generated: {generated}
parent: {parent}
---

# {name}

## 结构说明

本层统一结构：

- `common-knowledge/` — 知识条目（`.md` 文件，含 frontmatter）
- `projects/` — 子项目（递归，以项目名称作为文件夹的形式记录子项目，子项目内的结构与本层相同）
- `archive/` — 已归档子项，包含三个状态：`completed`（已完成）、`cancelled`（已取消）、`abandoned`（已废弃）

## 核心文档

{doc_entries}

## 子项目

{project_entries}

## 归档

{archive_entries}

{archive_footer}
