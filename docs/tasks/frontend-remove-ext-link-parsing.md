---
title: 移除前端外链解析逻辑，改用后端数据
area: frontend
depends_on: docs/tasks/backend-external-links.md
status: todo
---

## 背景

当前 `store.js` 在拿到文档数据后自行从 markdown 正文解析外链：

```javascript
// store.js — 临时外链解析
const extLinks = [];
const re = /\[([^\]]*)\]\((https?:\/\/[^)]+)\)/g;
// ...
this.refs = this.refs.concat(extLinks);
```

## 改法

后端 `api_get_document_refs` 支持返回 `type: "external"` 的条目后，前端移除此解析逻辑。

直接使用后端返回的 refs 数组，根据 `ref.type === "external"` 渲染外部链接样式。其余不变。
