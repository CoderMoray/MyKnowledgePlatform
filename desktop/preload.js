"use strict";

/**
 * MyKnowledge 桌面壳 — preload 脚本
 *
 * 通过 additionalArguments 拿到后端地址，注入 window.__MYK_API_BASE__。
 * 前端 frontend/js/api.js 第 7 行已支持该注入点，用于动态端口场景
 * （api.js 的 hostname 分支固定写死 8080，动态端口必须走这里）。
 */

const { contextBridge } = require("electron");

const arg = process.argv.find((a) => a.startsWith("--myk-api-base="));
const apiBase = arg ? arg.slice("--myk-api-base=".length) : null;

if (apiBase) {
  contextBridge.exposeInMainWorld("__MYK_API_BASE__", apiBase);
}
