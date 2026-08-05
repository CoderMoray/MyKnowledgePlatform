// 冲突弹窗 diff 算法测试：lineDiff（行级 LCS，same/del/add）
// 运行：node diff-logic.mjs （frontend/tests 内）
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";

const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", { url: "http://127.0.0.1:8080/" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
const utilsSrc = readFileSync(new URL("../js/utils.js", import.meta.url), "utf-8");
dom.window.eval(utilsSrc);
const diff = dom.window.lineDiff;

let pass = 0, fail = 0;
const t = (name, cond) => {
  if (cond) { pass++; console.log("  OK " + name); }
  else { fail++; console.log("  XX " + name); }
};
const types = (a, b) => diff(a, b).map(r => r.type).join(",");

console.log("── 基础 ──");
t("空 vs 空 → []", diff("", "").length === 0);
t("空 vs 有内容 → add", diff("", "a")[0].type === "add" && diff("", "a")[0].b === "a");
t("有内容 vs 空 → del", diff("a", "")[0].type === "del" && diff("a", "")[0].a === "a");

console.log("── 相同/不同 ──");
t("全相同 → 全 same", types("a\nb", "a\nb") === "same,same");
t("全不同 → del,add", types("a", "b") === "del,add");
t("追加一行 → same,add", types("a", "a\nb") === "same,add");
t("删除一行 → same,del", types("a\nb", "a") === "same,del");

console.log("── LCS 交错 ──");
t("中间删行 → same,del,same", types("a\nb\nc", "a\nc") === "same,del,same");
t("中间插行 → same,add,same", types("a\nc", "a\nb\nc") === "same,add,same");
t("多行交错 → same,del,add,same", types("a\nx\nc", "a\ny\nc") === "same,del,add,same");

console.log("── 边界 ──");
t("CRLF 归一化: a\\r\\nb vs a\\nb → 2 same", types("a\r\nb", "a\nb") === "same,same");
t("中文内容", diff("技术选型", "技术选型")[0].type === "same");
t("空行删除: a\\n\\nb vs a\\nb → same,del,same", types("a\n\nb", "a\nb") === "same,del,same");
t("null/undefined 输入不报错", diff(null, undefined).length === 0);

console.log("\n结果: " + pass + " 通过, " + fail + " 失败 / " + (pass + fail));
process.exit(fail ? 1 : 0);
