---
title: 支持外链（http/https）的 ref 解析、校验和导出
area: backend
status: todo
---

## 背景

前端已实现三种链接类型的区分展示：

| 链接类型 | 正则 | hover 卡片 | 底部引用列表 |
|---------|------|-----------|------------|
| 知识引用 `[text](ref:path::section)` | `ref:` 前缀 | 文档预览卡片 | 可点击跳转 |
| 外部链接 `[text](https://example.com)` | `http://` / `https://` | 显示 URL + 「打开链接↗」| 「外部」标签 + 新标签页打开 |
| 死链 `[text](ref:path)` 引用失效 | `ref:` 但文件不存在 | 「文件不存在」红色提示 | 「已失效」标签，不可点击 |

**现状**：后端只解析 `ref:` 链接返回给前端。外部链接由前端从原始 markdown 正文里自行提取。

这造成了前后端对「引用列表」的理解不一致，且在知识分享/导出时可能遗漏外链。

## 需要后端改动

### 1. 文档 API refs 返回里加上外链

文件：`backend/main.py` — `api_get_document_refs` 或 `api_get_document_meta`

当前正则只匹配 `ref:`:
```python
refs = re.findall(r'\]\(ref:([^)]+?)(?:::([^)]*))?\)', body)
```

扩展为同时匹配外链：
```python
# 知识引用
ref_refs = re.findall(r'\]\(ref:([^)]+?)(?:::([^)]*))?\)', body)
# 外部链接
ext_refs = re.findall(r'\[([^\]]*)\]\((https?://[^)\s]+)\)', body)
```

返回给前端的 ref 条目需增加 `type` 字段：

```python
# 知识引用（保持现有结构）
{"path": ref_path, "title": section, "resolved": True/False, ...}

# 外部链接（新增）
{"path": url, "title": link_text, "resolved": False, "type": "external"}
```

注：外链的 `path` 存储完整 URL，`title` 存储 markdown 链接文字。

### 2. 校验时跳过外链

文件：`backend/main.py` — `api_check_refs` 或其他校验函数

当前校验逻辑遍历所有 ref 并调用 `_resolve_ref` 检查文件存在性。外链不需要此检查：

```python
for ref_path, section in ref_list:
    if ref_path.startswith("http://") or ref_path.startswith("https://"):
        continue  # 外链，不做本地文件校验
    try:
        _resolve_ref(path, ref_path, storage)
        ...
```

### 3. 分享/导出时保留外链

文件：分享/导出相关逻辑

外联 URL 属于知识内容的一部分，原样保留在 markdown 输出中即可，不需做路径转换或打包处理。确认当前导出逻辑不会截断或丢弃 `http(s)://` 开头的链接。

## 影响范围

- 不影响现有 `ref:` 链接的校验、引用、分享行为
- 前端在拿到后端 `type: "external"` 字段后可移除自身的外链解析逻辑，统一从后端数据渲染
