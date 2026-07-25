/* ==========================================================================
   MyKnowledge — Markdown ↔ HTML 转换
   使用 marked + turndown
   设计系统: Raycast · v1.0
   ========================================================================== */

/* ── Marked 配置 ───────────────────────────────────────────────────────── */

marked.setOptions({
  breaks: true,
  gfm: true,
});

/* ── Turndown 配置 ─────────────────────────────────────────────────────── */

const turndownService = new TurndownService({
  headingStyle: "atx",
  hr: "---",
  bulletListMarker: "-",
  codeBlockStyle: "fenced",
  emDelimiter: "_",
});

/**
 * Markdown → HTML
 * @param {string} md
 * @returns {string}
 */
function mdToHtml(md) {
  if (!md) return "";
  return marked.parse(md);
}

/**
 * HTML → Markdown
 * @param {string} html
 * @returns {string}
 */
function htmlToMd(html) {
  if (!html) return "";
  return turndownService.turndown(html);
}

/**
 * TipTap HTML → Markdown（保存用）
 * 处理 TipTap 的特殊标记
 * @param {string} html - TipTap 编辑器导出的 HTML
 * @returns {string}
 */
function tiptapToMarkdown(html) {
  if (!html) return "";

  // 处理 ref 标记：<span data-ref="path">text</span> → [text](ref:path)
  let processed = html.replace(
    /<span\s+data-ref=["']([^"']+)["'][^>]*>(.*?)<\/span>/g,
    (_, path, text) => `[${text}](ref:${path})`
  );

  return turndownService.turndown(processed);
}

/**
 * Markdown → TipTap HTML（加载用）
 * 处理 ref: 链接的特殊转换
 * @param {string} md
 * @returns {string}
 */
function markdownToTiptapHtml(md) {
  if (!md) return "";

  // 先把 ref: 协议的链接转为 span
  let processed = md.replace(
    /\[([^\]]*)\]\(ref:([^)]+)\)/g,
    (_, text, path) =>
      `<span data-ref="${path}" class="ref-marker">${text || path}</span>`
  );

  return marked.parse(processed);
}

/**
 * 从 Markdown 中提取 ref: 引用列表
 * @param {string} md
 * @returns {string[]}
 */
function extractRefs(md) {
  if (!md) return [];
  const refs = [];
  const regex = /\[([^\]]*)\]\(ref:([^)]+)\)/g;
  let match;
  while ((match = regex.exec(md)) !== null) {
    refs.push(match[2]);
  }
  return refs;
}
