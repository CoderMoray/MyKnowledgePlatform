/**
 * 编辑保存往返测试 — 本地 Node.js 直接跑，不需要浏览器
 * 用法: node frontend/test-save-roundtrip.js
 */
const TurndownService = require("turndown");
const { JSDOM } = require("jsdom");

// ========== 模拟 TipTap 编辑器的 view.dom.innerHTML ==========
// 从浏览器 inspector 中复制的真实 DOM
const tipTapHTML = `<h1>编辑保存测试</h1><h2>内联格式</h2><p><strong>加粗</strong> <em>斜体</em> <s>删除线</s> <code>行内代码</code></p><h2>列表</h2><ul><li><p>无序列表项 1</p></li><li><p>无序列表项 2</p></li></ul><ol><li><p>有序列表项 1</p></li><li><p>有序列表项 2</p></li></ol><h2>引用</h2><blockquote><p>这是一段引用文字<br>引用第二行</p></blockquote><h2>代码块</h2><pre><code>const x = 1;
console.log(x);</code></pre><h2>表格</h2><div class="tableWrapper"><table style="min-width: 300px;"><colgroup><col><col><col></colgroup><tbody><tr><th colspan="1" rowspan="1"><p>列A</p></th><th colspan="1" rowspan="1"><p>列B</p></th><th colspan="1" rowspan="1"><p>列C</p></th></tr><tr><td colspan="1" rowspan="1"><p>a1</p></td><td colspan="1" rowspan="1"><p>b1</p></td><td colspan="1" rowspan="1"><p>c1</p></td></tr><tr><td colspan="1" rowspan="1"><p>a2</p></td><td colspan="1" rowspan="1"><p>b2</p></td><td colspan="1" rowspan="1"><p>c2</p></td></tr></tbody></table></div><h2>链接</h2><p><a target="_blank" rel="noopener noreferrer nofollow" href="https://example.com" data-myk-href="https://example.com">普通链接</a></p><p>参考<a target="_blank" rel="noopener noreferrer nofollow" class="ref-link" href="ref:common-knowledge/技术选型.md::技术栈选型" data-myk-href="ref:common-knowledge/技术选型.md::技术栈选型">技术选型</a></p>`;

// 场景 1b：损坏的链接（无 data-myk-href，模拟真实 bug）
const corruptedHTML = tipTapHTML.replace('data-myk-href="https://example.com"', 'href="%5Bobject%20Object%5D"');

// ========== 期望的 Markdown 输出 ==========
const expected = `# 编辑保存测试

## 内联格式

**加粗** _斜体_ ~~删除线~~ \`行内代码\`

## 列表

- 无序列表项 1
- 无序列表项 2

1. 有序列表项 1
2. 有序列表项 2

## 引用

> 这是一段引用文字
> 引用第二行

## 代码块

\`\`\`
const x = 1;
console.log(x);
\`\`\`

## 表格

| 列A | 列B | 列C |
| --- | --- | --- |
| a1 | b1 | c1 |
| a2 | b2 | c2 |

## 链接

[普通链接](https://example.com)

参考[技术选型](ref:common-knowledge/技术选型.md::技术栈选型)`;

// ========== 转换逻辑（从 doc.js 复制） ==========
function convert(html) {
  const dom = new JSDOM(`<div id="tmp">${html}</div>`);
  const tmp = dom.window.document.getElementById("tmp");

  // 去掉空 h1
  const h1 = tmp.querySelector("h1");
  if (h1 && !h1.textContent.trim()) h1.remove();

  // 恢复 ref 链接
  tmp.querySelectorAll("[data-ref-path]").forEach(a => {
    const section = a.dataset.refSection ? "::" + a.dataset.refSection : "";
    a.setAttribute("href", "ref:" + a.dataset.refPath + section);
  });

  // 清理 <li><p>
  tmp.querySelectorAll("li p").forEach(p => {
    const parent = p.parentNode;
    while (p.firstChild) parent.insertBefore(p.firstChild, p);
    parent.removeChild(p);
  });

  // 表格 → 标记占位
  const tableMarkers = [];
  tmp.querySelectorAll(".tableWrapper").forEach((wrapper, idx) => {
    const table = wrapper.querySelector("table");
    if (!table) return;
    const rows = [];
    table.querySelectorAll("tr").forEach(tr => {
      const cells = [];
      tr.querySelectorAll("th, td").forEach(c => cells.push(c.textContent.trim()));
      rows.push("| " + cells.join(" | ") + " |");
    });
    if (rows.length > 0) {
      const cols = table.querySelector("tr").querySelectorAll("th, td").length;
      rows.splice(1, 0, "|" + " --- |".repeat(cols));
    }
    const marker = "MYKTABLE" + idx + "MARK";
    tableMarkers.push({ marker, md: rows.join("\n") });
    wrapper.replaceWith(dom.window.document.createTextNode(marker));
  });

  // 链接规则
  const linkRule = {
    filter: (node) => node.nodeName === "A",
    replacement: (content, node) => {
      let href = node.getAttribute("data-myk-href") || node.getAttribute("href") || "";
      if (!href || href === "null" || href.startsWith("[object") || href.startsWith("%5B")) return content;
      if (href.startsWith("ref:")) {
        const ref = href.slice(4).replace(/%20/g, " ");
        return "[" + content + "](ref:" + ref + ")";
      }
      return "[" + content + "](" + href + ")";
    }
  };

  const cleanHtml = tmp.innerHTML;

  const td = new TurndownService({ headingStyle: "atx", bulletListMarker: "-", codeBlockStyle: "fenced", emDelimiter: "*" });
  td.addRule("strikethrough", { filter: ["s", "del", "strike"], replacement: (c) => "~~" + c + "~~" });
  td.addRule("fencedCode", {
    filter: (node) => node.nodeName === "PRE" && node.firstChild && node.firstChild.nodeName === "CODE",
    replacement: (_, node) => {
      const lang = (node.firstChild.className || "").replace(/^language-/, "");
      return "\n\n```" + lang + "\n" + node.firstChild.textContent.trimEnd() + "\n```\n\n";
    }
  });
  td.addRule("mykLink", linkRule);
  let markdown = td.turndown(cleanHtml);

  // 还原表格
  tableMarkers.forEach(({ marker, md }) => {
    markdown = markdown.replace(marker, md);
  });

  // 后处理
  markdown = markdown.replace(/\(ref:([^)]+)\)/g, (m, url) => "(ref:" + url.replace(/%20/g, " ") + ")");
  markdown = markdown.replace(/^(\s*[-*+])\s{2,}/gm, "$1 ");
  markdown = markdown.replace(/^(\s*\d+\.)\s{2,}/gm, "$1 ");
  markdown = markdown.replace(/^(> .*?)\s\s+$/gm, "$1");

  return markdown;
}

// ========== 工具函数 ==========
let PASS = 0, FAIL = 0;
function runChecks(result, tests) {
  for (const t of tests) {
    const ok = t.check(result);
    console.log(ok ? "✅" : "❌", t.name);
    ok ? PASS++ : FAIL++;
  }
}

// ========== 运行测试 ==========
console.log("=== 编辑保存往返测试 ===\n");

// ── 场景 1：无修改保存 ──
console.log("场景 1：无修改直接保存");
let result = convert(tipTapHTML);
runChecks(result, [
  { name: "加粗", check: (r) => r.includes("**加粗**") },
  { name: "斜体", check: (r) => r.includes("*斜体*") },
  { name: "删除线", check: (r) => r.includes("~~删除线~~") },
  { name: "行内代码", check: (r) => r.includes("`行内代码`") },
  { name: "无序列表", check: (r) => r.includes("- 无序列表项 1") && r.includes("- 无序列表项 2") },
  { name: "有序列表", check: (r) => r.includes("1. 有序列表项 1") && r.includes("2. 有序列表项 2") },
  { name: "引用", check: (r) => r.includes("> 这是一段引用文字") },
  { name: "代码块", check: (r) => r.includes("```") && r.includes("const x = 1;") },
  { name: "表格列头", check: (r) => r.includes("| 列A | 列B | 列C |") },
  { name: "表格分隔线", check: (r) => r.includes("| --- | --- | --- |") },
  { name: "表格数据", check: (r) => r.includes("| a1 | b1 | c1 |") && r.includes("| a2 | b2 | c2 |") },
  { name: "普通链接", check: (r) => r.includes("[普通链接](https://example.com)") },
  { name: "ref 链接", check: (r) => r.includes("[技术选型](ref:common-knowledge/技术选型.md::技术栈选型)") },
]);

// ── 场景 1b：损坏链接兜底（无 ProseMirror 恢复时） ──
console.log("\n场景 1b：损坏链接回退为纯文本");
result = convert(corruptedHTML);
runChecks(result, [
  { name: "损坏链接降级为文字", check: (r) => !r.includes("[object") && r.includes("普通链接") },
  { name: "ref 链接仍正常", check: (r) => r.includes("ref:common-knowledge/技术选型.md::技术栈选型") },
]);

// ── 场景 2：修改后保存（添加表行、加粗、新列表项） ──
console.log("\n场景 2：修改内容后保存");
const editedHTML = tipTapHTML
  .replace("</tbody></table>", '<tr><td colspan="1" rowspan="1"><p>a3</p></td><td colspan="1" rowspan="1"><p>b3</p></td><td colspan="1" rowspan="1"><p>c3</p></td></tr></tbody></table>')
  .replace("<p><strong>加粗</strong>", "<p><strong>加粗文字修改</strong>")
  .replace("<li><p>无序列表项 2</p></li></ul>", "<li><p>无序列表项 2</p></li><li><p>新增列表项</p></li></ul>");
result = convert(editedHTML);
runChecks(result, [
  { name: "加粗修改生效", check: (r) => r.includes("**加粗文字修改**") },
  { name: "新增列表项", check: (r) => r.includes("- 新增列表项") },
  { name: "表格新增行", check: (r) => r.includes("| a3 | b3 | c3 |") },
  { name: "旧表格数据保留", check: (r) => r.includes("| a1 | b1 | c1 |") },
  { name: "斜体仍保留", check: (r) => r.includes("*斜体*") },
  { name: "链接仍保留", check: (r) => r.includes("[普通链接](https://example.com)") },
]);

// ── 场景 3：空编辑保存 ──
console.log("\n场景 3：空编辑器退出");
const emptyHTML = "<p><br></p>";
result = convert(emptyHTML);
runChecks(result, [
  { name: "空输出", check: (r) => r.trim() === "" || r.trim() === "\\" || r === "<p></p>" },
]);

// ── 汇总 ──
console.log(`\n${PASS}/${PASS + FAIL} 通过`);
if (FAIL > 0) process.exit(1);
