// 垃圾箱处理 prompt 生成测试：buildTrashPrompt（MCP 精确工具名，后端核对）
// 运行：node trash-prompt-logic.mjs （frontend/tests 内）
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";

const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", { url: "http://127.0.0.1:8080/" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
const utilsSrc = readFileSync(new URL("../js/utils.js", import.meta.url), "utf-8");
dom.window.eval(utilsSrc);
const B = dom.window.buildTrashPrompt;

let pass = 0, fail = 0;
const t = (name, cond) => {
  if (cond) { pass++; console.log("  OK " + name); }
  else { fail++; console.log("  XX " + name); }
};

const item = {
  name: "垃圾箱引用演示.md",
  original_path: "common-knowledge/垃圾箱引用演示.md",
  trash_path: "trash/documents/垃圾箱引用演示.md",
  deleted_at: "2026-08-05 18:30:00 +0800",
  type: "document",
  summary: "演示文档",
};
const ref = { title: "垃圾箱引用演示", path: "common-knowledge/垃圾箱引用演示.md" };

console.log("── 摘要版（默认） ──");
const s = B(ref, item, false, "");
t("含全部 MCP 工具名", s.includes("maint__check_refs") && s.includes("nav__get_document") && s.includes("write__restore_document"));
t("含写锁提示 maint__acquire_lock", s.includes("maint__acquire_lock"));
t("如实反映不能立即永久删除", s.includes("无法立即永久删除"));
t("含原路径/回收站路径", s.includes("common-knowledge/垃圾箱引用演示.md") && s.includes("trash/documents/垃圾箱引用演示.md"));
t("含剩余天数", s.includes("剩余约"));
t("不含全文内容（摘要版）", !s.includes("文档全文"));

console.log("── 全文版 ──");
const f = B(ref, item, true, "这是全文内容ABC");
t("前置敏感提示", f.startsWith("⚠"));
t("含文档全文", f.includes("这是全文内容ABC"));
t("含恢复工具", f.includes("write__restore_document"));

console.log("── 项目类型 ──");
const pItem = Object.assign({}, item, { type: "project", trash_path: "trash/projects/X", original_path: "projects/X" });
t("项目版用 write__restore_project", B(ref, pItem, false, "").includes("write__restore_project"));
t("项目版不含文档恢复工具", !B(ref, pItem, false, "").includes("write__restore_document"));

console.log("── 边界 ──");
t("无 item 时用 ref.title 兜底", B(ref, null, false, "").includes("垃圾箱引用演示"));
t("无 deleted_at 时文案兜底", B(ref, Object.assign({}, item, { deleted_at: "" }), false, "").includes("30 天内可恢复"));
t("摘要缺失兜底", B(ref, Object.assign({}, item, { summary: "" }), false, "").includes("垃圾箱引用演示"));

console.log("\n结果: " + pass + " 通过, " + fail + " 失败 / " + (pass + fail));
process.exit(fail ? 1 : 0);
