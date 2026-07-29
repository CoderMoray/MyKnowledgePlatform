# 前端依赖

## TipTap 编辑器

| 包 | 版本 | CDN |
|---|------|-----|
| @tiptap/core | 2.1.13 | jsdelivr |
| @tiptap/starter-kit | 2.1.13 | jsdelivr |
| @tiptap/extension-link | 2.1.13 | jsdelivr |
| @tiptap/extension-table | 2.1.13 | jsdelivr |
| @tiptap/extension-table-row | 2.1.13 | jsdelivr |
| @tiptap/extension-table-cell | 2.1.13 | jsdelivr |
| @tiptap/extension-table-header | 2.1.13 | jsdelivr |

> CDN import map 定义在 `frontend/index.html` `<script type="importmap">` 块中。

## 已知 patch

### Link 扩展 href 序列化

**问题**：2.1.13 的 Link 扩展 `parseHTML` 不强制 `href` 为字符串，ProseMirror 属性解析器会把某些 URL 转成 `[object Object]`，导致编辑保存后链接丢失。

**修复**：`frontend/js/components/doc.js` 中 `initEditor()` 覆写 `parseHTML`：

```javascript
href: {
    parseHTML(element) {
        return element.getAttribute('href');
    }
}
```

**移除条件**：升级到 @tiptap/extension-link ≥ 2.6.0 后，官方已修复此问题，可删除自定义扩展，直接用 `LinkExt.configure()`。

## 其他依赖

| 包 | 用途 |
|---|------|
| Alpine.js | 响应式 UI |
| marked | Markdown → HTML |
| turndown | HTML → Markdown |
| highlight.js | 代码高亮 |

> 均通过 CDN 加载，无构建步骤。
