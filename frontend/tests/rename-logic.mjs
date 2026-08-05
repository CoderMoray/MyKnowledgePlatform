// 重命名纯函数测试：MykRename（标题可编辑 = 重命名 的前端逻辑）
// 运行：node rename-logic.mjs （frontend/tests 内）
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";

const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", { url: "http://127.0.0.1:8080/" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;

// 加载 utils.js（含 MykRename）
const utilsSrc = readFileSync(new URL("../js/utils.js", import.meta.url), "utf-8");
dom.window.eval(utilsSrc);
const R = dom.window.MykRename;

let pass = 0, fail = 0;
const t = (name, cond) => {
  if (cond) { pass++; console.log(`  ✅ ${name}`); }
  else { fail++; console.log(`  ❌ ${name}`); }
};

console.log("── buildNewName（标题 → 文件名，自动补 .md） ──");
t('补 .md: "技术选型" → "技术选型.md"', R.buildNewName("技术选型") === "技术选型.md");
t('已带 .md 不重复: "a.md" → "a.md"', R.buildNewName("a.md") === "a.md");
t('带空格标题: "My Doc" → "My Doc.md"', R.buildNewName("My Doc") === "My Doc.md");
t('空标题 → ""', R.buildNewName("") === "" && R.buildNewName("   ") === "");

console.log("── buildNewPath（同目录替换文件名） ──");
t('子目录: "common-knowledge/a.md" + "b.md" → "common-knowledge/b.md"', R.buildNewPath("common-knowledge/a.md", "b.md") === "common-knowledge/b.md");
t('根目录: "a.md" + "b.md" → "b.md"', R.buildNewPath("a.md", "b.md") === "b.md");
t('深层目录: "x/y/z/a.md" + "b.md" → "x/y/z/b.md"', R.buildNewPath("x/y/z/a.md", "b.md") === "x/y/z/b.md");

console.log("── currentTitle（frontmatter title 优先，否则文件名） ──");
t('有 title 字段 → 用 title', R.currentTitle({ title: "自定义标题" }, "a/b.md") === "自定义标题");
t('无 title → 文件名（去 .md）', R.currentTitle({}, "common-knowledge/技术选型.md") === "技术选型");
t('无 title 无路径 → ""', R.currentTitle({}, "") === "");

console.log("── shouldRename（标题变了才 rename） ──");
t('变了 → true', R.shouldRename("旧", "新") === true);
t('没变 → false', R.shouldRename("同", "同") === false);
t('空标题 → false', R.shouldRename("旧", "") === false && R.shouldRename("旧", "  ") === false);

console.log("── titleError（标题合法性） ──");
t('合法标题 → ""', R.titleError("技术选型") === "");
t('空标题 → 报错', R.titleError("") !== "" && R.titleError("  ") !== "");
t('含 / → 报错', R.titleError("a/b") !== "");
t('含非法字符 :*?"<>| → 报错', R.titleError('a:b') !== "" && R.titleError('a|b') !== "" && R.titleError('a<b') !== "");
t('正常中文+空格 → 合法', R.titleError("我的 文档 v2") === "");

console.log(`\n结果: ${pass} 通过, ${fail} 失败 / ${pass + fail}`);
process.exit(fail ? 1 : 0);
