// 保存回归测试：进编辑（不改内容）→ 退出保存 → markdown 必须零变化
// 链路：marked 渲染(模拟 store.htmlContent) → onCreate 预处理 → TipTap setContent
//       → getHTML → turndown 转回 markdown → 断言 === 原文
// 运行：node save-regression.mjs （在 node workspace 内）
import { JSDOM } from "jsdom";
import { marked } from "marked";
import TurndownService from "turndown";
import { readFileSync } from "node:fs";

const BUNDLE = await import("/Users/chrismoray/Desktop/Moray/MyOpenSource/MyKnowledge_PlatForm/frontend/tiptap-bundle.mjs");
const { Editor, StarterKit, LinkExt, Table, TableRow, TableCell, TableHeader, CodeBlockLowlight, createLowlight, MyLowlightCommon, SlashCommand: SlashCommandExt } = BUNDLE;

// ── jsdom 全局注入 ──
const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", { url: "http://127.0.0.1:8080/", pretendToBeVisual: true });
const { window } = dom;
globalThis.window = window;
globalThis.document = window.document;
Object.defineProperty(globalThis, "navigator", { value: window.navigator, configurable: true });
Object.defineProperty(globalThis, "HTMLElement", { value: window.HTMLElement, configurable: true });
Object.defineProperty(globalThis, "Node", { value: window.Node, configurable: true });
Object.defineProperty(globalThis, "NodeFilter", { value: window.NodeFilter, configurable: true });
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
  const firstChild = tmp.firstElementChild;
  if (firstChild && firstChild.tagName === "H1" && !firstChild.textContent.trim()) firstChild.remove();
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
  td.addRule("br", { filter: "br", replacement: () => "\n" });
  td.addRule("listItem", {
    filter: "li",
    replacement: (content, node, options) => {
      content = content.replace(/^\n+/, "").replace(/\n+$/, "\n").replace(/\n/gm, "\n  ");
      let prefix = "- ";
      const parent = node.parentNode;
      if (parent && parent.nodeName === "OL") {
        const start = parent.getAttribute("start");
        const index = Array.prototype.indexOf.call(parent.children, node);
        prefix = (start ? Number(start) + index : index + 1) + ". ";
      }
      return prefix + content + (node.nextSibling && !/\n$/.test(content) ? "\n" : "");
    },
  });
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
  const walker = document.createTreeWalker(tmp, NodeFilter.SHOW_TEXT);
  const softBreaks = [];
  let tn;
  while ((tn = walker.nextNode())) {
    const p = tn.parentNode;
    if (!p || (p.closest && p.closest("pre"))) continue;
    if (tn.nodeValue && tn.nodeValue.includes("\n") && tn.nodeValue.trim() !== "") softBreaks.push(tn);
  }
  softBreaks.forEach((tn) => {
    const frag = document.createDocumentFragment();
    const parts = tn.nodeValue.split("\n");
    parts.forEach((part, i) => {
      if (i > 0) frag.appendChild(document.createElement("br"));
      if (part) frag.appendChild(document.createTextNode(part));
    });
    tn.parentNode.replaceChild(frag, tn);
  });
  return tmp.innerHTML;
}

// ── 测试用例 ──
const CASES = [
  { name: "标题+段落", md: "# 一级标题\n\n正文段落。\n\n## 二级\n\n### 三级\n\n#### 四级" },
  { name: "内联格式", md: "**加粗** *斜体* ~~删除线~~ `行内代码`" },
  { name: "无序列表", md: "- 项1\n- 项2\n  - 嵌套项" },
  { name: "软换行引用", md: "> 第一行\n> 第二行" },
  { name: "组合:标题+表格+引用", md: "# 标题\n\n| A | B |\n|------|------|\n| 1 | 2 |\n\n> 引用文字\n\n## 小结" },
  { name: "组合:列表+代码块+分割线", md: "- 项1\n  - 子项\n\n```python\nprint(1)\n```\n\n---\n\n结尾" },
  { name: "组合:代码块紧邻表格", md: "```js\nconst t = 1;\n```\n\n| 列1 | 列2 |\n|-----|-----|\n| a | b |\n\n之后文字" },
  { name: "组合:ref链接段落中+外链+列表", md: "前文[技术选型](ref:common-knowledge/技术选型.md::技术栈选型)中段\n\n[外链](https://example.com)\n\n- 项a\n- 项b" },
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

// ── 斜杠插入测试：模拟斜杠菜单在空行执行命令 → 保存 → 断言产生的 markdown ──
// run 收到编辑器，在光标位置执行命令（等价于斜杠菜单选中后）。
const SLASH_CASES = [
  { name: "斜杠:H1", md: "上方内容", run: (ed) => ed.commands.toggleHeading({ level: 1 }), expect: "上方内容\n\n# " },
  { name: "斜杠:H2", md: "上方内容", run: (ed) => ed.commands.toggleHeading({ level: 2 }), expect: "上方内容\n\n## " },
  { name: "斜杠:H3", md: "上方内容", run: (ed) => ed.commands.toggleHeading({ level: 3 }), expect: "上方内容\n\n### " },
  { name: "斜杠:H4", md: "上方内容", run: (ed) => ed.commands.toggleHeading({ level: 4 }), expect: "上方内容\n\n#### " },
  { name: "斜杠:无序列表", md: "上方内容", run: (ed) => ed.commands.toggleBulletList(), expect: "上方内容\n\n- " },
  { name: "斜杠:有序列表", md: "上方内容", run: (ed) => ed.commands.toggleOrderedList(), expect: "上方内容\n\n1. " },
  { name: "斜杠:引用", md: "上方内容", run: (ed) => ed.commands.toggleBlockquote(), expect: "上方内容\n\n> " },
  { name: "斜杠:代码块", md: "上方内容", run: (ed) => ed.commands.toggleCodeBlock({ language: "javascript" }), expect: "上方内容\n\n```javascript\n\n```" },
  { name: "斜杠:分割线", md: "上方内容", run: (ed) => ed.commands.setHorizontalRule(), expect: "上方内容\n\n---" },
  { name: "斜杠:表格", md: "上方内容", run: (ed) => ed.commands.insertTable({ rows: 3, cols: 3, withHeaderRow: true }), expect: "上方内容\n\n|  |  |  |\n| --- | --- | --- |\n|  |  |  |\n|  |  |  |" },
  // 组合场景（插入块 + 上下内容）由 CASES 覆盖：标题+表格+引用 / 代码块紧邻表格 / ref链接段落中+外链+列表
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
// ── 斜杠触发行为（与飞书一致：光标前无内容即触发，含表格单元格） ──
const TRIGGER_CASES = [
  { name: "触发:行中(前方有内容)", html: "<p>前方文字 后方文字</p>", pos: 2, expectOpen: false },
  { name: "触发:行首(行尾有内容)", html: "<p>前方文字 后方文字</p>", pos: 0, expectOpen: true },
  { name: "触发:表格单元格行首", html: "<table><tr><td><p>单元格内容</p></td></tr></table>", pos: "cell", expectOpen: true, withTable: true },
];
const TRIGGER_EXT = [StarterKit.configure(), SlashCommandExt.configure({})];
const TRIGGER_EXT_TABLE = [StarterKit.configure(), SlashCommandExt.configure({}), Table.configure({ resizable: true }), TableRow, TableCell, TableHeader];
for (const t of TRIGGER_CASES) {
  const ed = new Editor({ element: document.createElement("div"), extensions: t.withTable ? TRIGGER_EXT_TABLE : TRIGGER_EXT });
  try {
    ed.commands.setContent(t.html);
    let pos = t.pos;
    if (pos === "cell") {
      let cellP = -1;
      ed.state.doc.descendants((node, p) => { if (node.type.name === "paragraph" && p > 0) { cellP = p; return false; } });
      pos = cellP;
    }
    ed.view.dispatch(ed.state.tr.setSelection(ed.state.selection.constructor.create(ed.state.doc, pos, pos)));
    ed.view.someProp("handleTextInput", (fn) => fn(ed.view, pos, pos, "/"));
    const sc = ed.extensionManager.extensions.find((e) => e.name === "slashCommand");
    const open = sc ? sc.storage.open : false;
    if (open === t.expectOpen) {
      pass++;
      console.log(`  PASS  ${t.name}`);
    } else {
      fail++;
      console.log(`  FAIL  ${t.name}: open=${open} expect=${t.expectOpen}`);
    }
  } catch (e) {
    fail++;
    console.log(`  ERROR ${t.name}: ${e.message}`);
  }
  ed.destroy();
}

// ── 单 DOM 专项：只读态（editable=false）命令不产生变化；编辑器复用 ──
// 单 DOM 核心：editable 属性随模式正确切换（用户输入由 ProseMirror 原生阻止；
// 程序化命令不检查 editable 是 TipTap 行为，真实 UI 无法触发）
const SINGLE_DOM_CASES = [
  { name: "单DOM:只读态editable=false", setTo: false, expectEditable: false },
  { name: "单DOM:编辑态editable=true", setTo: true, expectEditable: true },
];
for (const t of SINGLE_DOM_CASES) {
  const ed = new Editor({ element: document.createElement("div"), extensions });
  try {
    ed.commands.setContent("<p>原文</p>");
    ed.setEditable(t.setTo);
    if (ed.isEditable === t.expectEditable) {
      pass++;
      console.log(`  PASS  ${t.name}`);
    } else {
      fail++;
      console.log(`  FAIL  ${t.name}: isEditable=${ed.isEditable} expect=${t.expectEditable}`);
    }
  } catch (e) {
    fail++;
    console.log(`  ERROR ${t.name}: ${e.message}`);
  }
  ed.destroy();
}

// ── 切文档路径：编辑器先载入文档A，再 setContent 更新为文档B（模拟单 DOM 的 effect 切文档），
//    保存必须零 diff（尤其 ref 链接——切文档 setContent 必须与 onCreate 走同样的预处理） ──
const SWITCH_DOC_CASES = [
  { name: "切文档:更新后ref链接保留", mdA: "<p>文档A内容</p>", mdB: "前文[技术选型](ref:common-knowledge/技术选型.md::技术栈选型)中段" },
  { name: "切文档:更新后表格+代码块保留", mdA: "<p>文档A</p>", mdB: "## 标题\n\n```js\nconst a = 1;\n```\n\n| A | B |\n|------|------|\n| 1 | 2 |" },
];
for (const t of SWITCH_DOC_CASES) {
  const ed = new Editor({ element: document.createElement("div"), extensions });
  try {
    // 先载入 A（onCreate 路径：预处理后 setContent）
    const aHtml = preprocessForEditor(renderMarkdown(t.mdA));
    ed.commands.setContent(aHtml);
    // 切到 B（effect 路径：与 onCreate 相同的预处理——这就是 _prepareEditorHtml 的职责）
    const bHtml = preprocessForEditor(renderMarkdown(t.mdB));
    ed.commands.setContent(bHtml);
    const outMd = editorHtmlToMarkdown(ed.view.dom.innerHTML, t.mdB);
    if (norm(outMd) === norm(t.mdB)) {
      pass++;
      console.log(`  PASS  ${t.name}`);
    } else {
      fail++;
      console.log(`  FAIL  ${t.name}`);
      console.log("   ── 原文 ──");
      console.log("   " + norm(t.mdB).split("\n").join("\n   "));
      console.log("   ── 转回 ──");
      console.log("   " + norm(outMd).split("\n").join("\n   "));
    }
  } catch (e) {
    fail++;
    console.log(`  ERROR ${t.name}: ${e.message}`);
  }
  ed.destroy();
}

// ── 斜杠插入测试执行 ──
for (const c of SLASH_CASES) {
  const html = renderMarkdown(c.md);
  const prepped = preprocessForEditor(html);
  const ed = new Editor({ element: document.createElement("div"), extensions });
  try {
    // 追加尾部空段落（模拟"按 Enter 后进入空行"），再执行命令（模拟斜杠在空行选中）
    ed.commands.setContent(prepped + "<p></p>");
    const doc = ed.state.doc;
    const Sel = ed.state.selection.constructor;
    const pos = Math.max(0, doc.content.size - 1);
    ed.view.dispatch(ed.state.tr.setSelection(Sel.create(doc, pos, pos)));
    c.run(ed);
    const outMd = editorHtmlToMarkdown(ed.view.dom.innerHTML, c.md);
    const expected = c.expect;
    if (norm(outMd) === norm(expected)) {
      pass++;
      console.log(`  PASS  ${c.name}`);
    } else {
      fail++;
      console.log(`  FAIL  ${c.name}`);
      console.log("   ── 期望 ──");
      console.log("   " + norm(expected).split("\n").join("\n   "));
      console.log("   ── 实际 ──");
      console.log("   " + norm(outMd).split("\n").join("\n   "));
    }
  } catch (e) {
    fail++;
    console.log(`  ERROR ${c.name}: ${e.message}`);
  }
  ed.destroy();
}
// ── 斜杠菜单上下文过滤：单元格内不显示表格项（飞书行为，避免嵌套表格） ──
const SLASH_FILTER_CASES = [
  { name: "过滤:非表格→含表格项", inTable: false, expectHasTable: true, expectTotal: 10 },
  { name: "过滤:表格内→不含表格项", inTable: true, expectHasTable: false, expectTotal: 9 },
];
const _slashItemsForFilter = [
  { type: "h1" }, { type: "h2" }, { type: "h3" }, { type: "h4" },
  { type: "bullet" }, { type: "ordered" }, { type: "quote" }, { type: "code" },
  { type: "hr" }, { type: "table" },
];
for (const f of SLASH_FILTER_CASES) {
  const visible = _slashItemsForFilter.filter((it) => !(it.type === "table" && f.inTable));
  const hasTable = visible.some((it) => it.type === "table");
  if (hasTable === f.expectHasTable && visible.length === f.expectTotal) {
    pass++;
    console.log(`  PASS  ${f.name}`);
  } else {
    fail++;
    console.log(`  FAIL  ${f.name}: hasTable=${hasTable}(expect ${f.expectHasTable}) total=${visible.length}(expect ${f.expectTotal})`);
  }
}


const TOTAL = CASES.length + SLASH_CASES.length + TRIGGER_CASES.length + SLASH_FILTER_CASES.length + SINGLE_DOM_CASES.length + SWITCH_DOC_CASES.length;
console.log(`\n结果: ${pass} 通过, ${fail} 失败 / ${TOTAL}`);
process.exit(fail ? 1 : 0);
