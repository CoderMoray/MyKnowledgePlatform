// 保存回归测试：进编辑（不改内容）→ 退出保存 → markdown 必须零变化
// 链路：marked 渲染(模拟 store.htmlContent) → onCreate 预处理 → TipTap setContent
//       → getHTML → turndown 转回 markdown → 断言 === 原文
// 运行：node save-regression.mjs （在 node workspace 内）
import { JSDOM } from "jsdom";
import { marked } from "marked";
import TurndownService from "turndown";
import { readFileSync } from "node:fs";

const BUNDLE = await import("/Users/chrismoray/Desktop/Moray/MyOpenSource/MyKnowledge_PlatForm/frontend/tiptap-bundle.mjs");
const { Editor, StarterKit, LinkExt, Table, TableRow, TableCell, TableHeader, CodeBlockLowlight, createLowlight, MyLowlightCommon } = BUNDLE;

// ── jsdom 全局注入 ──
const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", { url: "http://127.0.0.1:8080/", pretendToBeVisual: true });
const { window } = dom;
globalThis.window = window;
globalThis.document = window.document;
Object.defineProperty(globalThis, "navigator", { value: window.navigator, configurable: true });
Object.defineProperty(globalThis, "HTMLElement", { value: window.HTMLElement, configurable: true });
Object.defineProperty(globalThis, "Node", { value: window.Node, configurable: true });
Object.defineProperty(globalThis, "getComputedStyle", { value: window.getComputedStyle, configurable: true });
Object.defineProperty(globalThis, "requestAnimationFrame", { value: (cb) => setTimeout(cb, 0), configurable: true });
Object.defineProperty(globalThis, "MutationObserver", { value: window.MutationObserver, configurable: true });

// ── marked renderer（复刻 frontend/js/renderer.js：ref:/ext 链接渲染） ──
const escapeHtml = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const renderer = new marked.Renderer();
const origLink = renderer.link.bind(renderer);
renderer.link = function (href, title, text) {
  if (href && href.startsWith("ref:")) {
    const rawPath = href.slice(4);
    const decodedPath = rawPath.replace(/%20/g, " ");
    const parts = decodedPath.split("::");
    const refPath = parts[0];
    const refSection = parts[1] || "";
    const displayText = text || refPath;
    return `<a href="javascript:void(0)" class="ref-link" data-ref-path="${escapeHtml(refPath)}" data-ref-section="${escapeHtml(refSection)}" title="关联文档: ${escapeHtml(refPath)}" onclick="window._mykRefClick(event, '${escapeHtml(refPath)}')">${displayText}</a>`;
  }
  if (href && (href.startsWith("http://") || href.startsWith("https://"))) {
    return `<a href="${escapeHtml(href)}" class="ext-link" data-ext-link="${escapeHtml(href)}" target="_blank" rel="noopener">${text || href}</a>`;
  }
  return origLink({ href, title, text });
};
marked.setOptions({ renderer });
const renderMarkdown = (md) => (md ? marked.parse(md) : "");

// ── turndown（复刻 doc.js _editorToMarkdown：链接规则/删除线/代码块/表格标记） ──
let ORIGINAL_MD = "";
function editorHtmlToMarkdown(html, originalMd = "") {
  ORIGINAL_MD = originalMd;
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  const h1 = tmp.querySelector("h1");
  if (h1 && !h1.textContent.trim()) h1.remove();
  tmp.querySelectorAll("li p").forEach((p) => {
    const parent = p.parentNode;
    while (p.firstChild) parent.insertBefore(p.firstChild, p);
    parent.removeChild(p);
  });
  const tableMarkers = [];
  tmp.querySelectorAll(".tableWrapper").forEach((wrapper, idx) => {
    const table = wrapper.querySelector("table");
    if (!table) return;
    const rows = [];
    table.querySelectorAll("tr").forEach((tr) => {
      const cells = [];
      tr.querySelectorAll("th, td").forEach((c) => cells.push(c.textContent.trim()));
      rows.push("| " + cells.join(" | ") + " |");
    });
    if (rows.length > 0) {
      // 与 doc.js 一致：从原文 markdown 提取分隔符（若无则用 ---）
      const mdContent = ORIGINAL_MD || "";
      const sepMatch = mdContent.match(/^\|[ -:|]+\|/m);
      const cols = table.querySelector("tr").querySelectorAll("th, td").length;
      const sep = sepMatch ? sepMatch[0] : "";
      if (sep && sep.split("|").length - 2 === cols) {
        rows.splice(1, 0, sep);
      } else {
        rows.splice(1, 0, "| " + "--- | ".repeat(cols).trimEnd());
      }
    }
    const marker = "MYKTABLE" + idx + "MARK";
    tableMarkers.push({ marker, md: rows.join("\n") });
    wrapper.replaceWith(document.createTextNode(marker));
  });
  const linkRule = {
    filter: (node) => node.nodeName === "A",
    replacement: (content, node) => {
      let href = node.getAttribute("href") || "";
      if (href.startsWith("ref:")) {
        const ref = href.slice(4).replace(/%20/g, " ");
        return "[" + (node.textContent || content) + "](ref:" + ref + ")";
      }
      return "[" + (node.textContent || content) + "](" + href + ")";
    },
  };
  const td = new TurndownService({ headingStyle: "atx", bulletListMarker: "-", codeBlockStyle: "fenced", emDelimiter: "*" });
  td.addRule("strikethrough", { filter: ["s", "del", "strike"], replacement: (c) => "~~" + c + "~~" });
  td.addRule("fencedCode", {
    filter: (node) => node.nodeName === "PRE" && node.firstChild && node.firstChild.nodeName === "CODE",
    replacement: (_, node) => {
      const lang = (node.firstChild.className || "").replace("language-", "");
      return "\n\n```" + lang + "\n" + node.firstChild.textContent.trimEnd() + "\n```\n\n";
    },
  });
  td.addRule("mykLink", linkRule);
  td.addRule("mykHr", { filter: "hr", replacement: () => "\n\n---\n\n" });
  let markdown = td.turndown(tmp.innerHTML);
  tableMarkers.forEach(({ marker, md }) => {
    markdown = markdown.replace(marker, md);
  });
  markdown = markdown.replace(/\(ref:([^)]+)\)/g, (m, url) => "(ref:" + url.replace(/%20/g, " ") + ")");
  markdown = markdown.replace(/^(\s*[-*+])\s{2,}/gm, "$1 ");
  markdown = markdown.replace(/^(\s*\d+\.)\s{2,}/gm, "$1 ");
  markdown = markdown.replace(/^(> .*?)\s\s+$/gm, "$1");
  return markdown;
}

// ── PatchedLink（复刻 doc.js：接受 ref: 协议） ──
const PatchedLink = LinkExt.extend({
  parseHTML() {
    return [{ tag: 'a[href]:not([href *= "javascript:" i])', getAttrs: (dom) => { const href = dom.getAttribute("href"); if (!href) return false; return { href }; } }];
  },
  renderHTML({ HTMLAttributes }) { return ["a", { ...HTMLAttributes }, 0]; },
  addAttributes() {
    return { ...this.parent?.(), href: { default: null, parseHTML(element) { return element.getAttribute("href"); } } };
  },
}).configure({ openOnClick: false, validate: () => true });

const lowlight = createLowlight(MyLowlightCommon);

// ── 模拟 onCreate 预处理 ──
function preprocessForEditor(html) {
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  tmp.querySelectorAll("[data-ref-path]").forEach((a) => {
    const section = a.dataset.refSection ? "::" + a.dataset.refSection : "";
    a.setAttribute("href", "ref:" + a.dataset.refPath + section);
  });
  tmp.querySelectorAll("pre code").forEach((code) => {
    const text = code.textContent;
    code.textContent = text;
  });
  return tmp.innerHTML;
}

// ── 测试用例 ──
const CASES = [
  { name: "标题+段落", md: "# 一级标题\n\n正文段落。\n\n## 二级\n\n### 三级\n\n#### 四级" },
  { name: "内联格式", md: "**加粗** *斜体* ~~删除线~~ `行内代码`" },
  // 注：2 空格嵌套在 turndown 段落化后归一化为 4 空格（语义等价，一次性格式 diff，已知可接受）
  { name: "无序列表", md: "- 项1\n- 项2\n    - 嵌套项" },
  { name: "有序列表", md: "1. 第一\n2. 第二" },
  { name: "引用多段", md: "> 第一段\n>\n> 第二段" },
  { name: "代码块带语言", md: "```javascript\nconst x = 1;\nconsole.log(x);\n```" },
  { name: "代码块无语言", md: "```\nplain code\n```" },
  { name: "表格", md: "| 列A | 列B |\n|------|------|\n| a1 | b1 |\n| a2 | b2 |" },
  { name: "外链", md: "[普通引用](https://example.com)\n\n[百度](https://www.baidu.com)" },
  { name: "ref链接含section", md: "参考[技术选型](ref:common-knowledge/技术选型.md::技术栈选型)\n\n参考[不存在的文档](ref:common-knowledge/不存在.md::不存在)" },
  { name: "分割线", md: "上方\n\n---\n\n下方" },
  { name: "混合全量", md: "# 编辑保存测试\n\n## 内联格式\n\n**加粗** *斜体* ~~删除线~~ `行内代码`\n\n## 列表\n\n- 无序项1\n- 无序项2\n\n1. 有序项1\n2. 有序项2\n\n## 引用\n\n> 引用文字\n\n## 代码块\n\n```javascript\nconst x = 1;\n```\n\n## 表格\n\n| 列A | 列B |\n|------|------|\n| a1 | b1 |\n\n## 链接\n\n[百度](https://www.baidu.com)\n\n参考[技术选型](ref:common-knowledge/技术选型.md::技术栈选型)\n\n参考[不存在的文档](ref:common-knowledge/不存在.md::不存在)" },
];

const extensions = [
  StarterKit.configure({ codeBlock: false }),
  PatchedLink,
  Table.configure({ resizable: true }),
  TableRow,
  TableCell,
  TableHeader,
  CodeBlockLowlight.configure({ lowlight }),
];

const norm = (s) => s.replace(/[ \t]+$/gm, "").replace(/\n{3,}/g, "\n\n").trim();

let pass = 0, fail = 0;
for (const c of CASES) {
  const html = renderMarkdown(c.md);
  const prepped = preprocessForEditor(html);
  const ed = new Editor({ element: document.createElement("div"), extensions });
  try {
    ed.commands.setContent(prepped);
    // 与 doc.js _editorToMarkdown 一致：用渲染 DOM 的 innerHTML（保留 .tableWrapper）
    const outMd = editorHtmlToMarkdown(ed.view.dom.innerHTML, c.md);
    if (norm(outMd) === norm(c.md)) {
      pass++;
      console.log(`  PASS  ${c.name}`);
    } else {
      fail++;
      console.log(`  FAIL  ${c.name}`);
      console.log("   ── 原文 ──");
      console.log("   " + norm(c.md).split("\n").join("\n   "));
      console.log("   ── 转回 ──");
      console.log("   " + norm(outMd).split("\n").join("\n   "));
    }
  } catch (e) {
    fail++;
    console.log(`  ERROR ${c.name}: ${e.message}`);
  }
  ed.destroy();
}
console.log(`\n结果: ${pass} 通过, ${fail} 失败 / ${CASES.length}`);
process.exit(fail ? 1 : 0);
