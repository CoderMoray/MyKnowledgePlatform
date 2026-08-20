"use strict";

/**
 * MyKnowledge 桌面壳 — preload 脚本（loading 窗口与主窗口共用）
 *
 * 通过 additionalArguments 拿到后端地址，注入 window.__MYK_API_BASE__。
 * 前端 frontend/js/api.js 第 7 行已支持该注入点，动态端口场景必需
 * （api.js 的 hostname 分支固定写死 8080）。
 *
 * 同时注入桌面 app 标志与 loading 完成 IPC 桥：
 *   - __MYK_APP_MODE__     : 前端据此隐藏 splash（加载动画由壳的 loading 页承担）
 *   - __mykLoadingDone__() : loading 页动画完成后通知主进程切换主界面
 */

const { contextBridge, ipcRenderer } = require("electron");

const arg = process.argv.find((a) => a.startsWith("--myk-api-base="));
const apiBase = arg ? arg.slice("--myk-api-base=".length) : null;

if (apiBase) {
  contextBridge.exposeInMainWorld("__MYK_API_BASE__", apiBase);
}

// 桌面 app 标志（网页端无此变量 → splash 行为不变）
contextBridge.exposeInMainWorld("__MYK_APP_MODE__", true);

// loading 页动画完成 → 主进程切换主界面
contextBridge.exposeInMainWorld("__mykLoadingDone__", () => {
  ipcRenderer.send("loading-done");
});

// ── 关闭询问 / Tray 托管 IPC 桥（SPEC §三 契约）───────────────────────────
// 点红点（主窗口）触发 → 前端弹自绘关闭询问 modal
contextBridge.exposeInMainWorld("__mykShowCloseChoice__", (cb) => {
  const listener = () => cb();
  ipcRenderer.on("show-close-choice", listener);
  // 返回取消订阅函数
  return () => ipcRenderer.removeListener("show-close-choice", listener);
});

// 用户三选 + 是否记住 → 主进程执行（quit / tray）
contextBridge.exposeInMainWorld("__mykSubmitCloseChoice__", (payload) => {
  ipcRenderer.send("close-choice", payload);
});

// 初始化上报记忆偏好：有记忆则跳过 modal 直接执行（payload: {action} | null）
contextBridge.exposeInMainWorld("__mykInitClosePreference__", (payload) => {
  ipcRenderer.send("close-choice-init", payload);
});

// 设置页「关闭行为」写入偏好（payload: {action:'quit'|'tray'|'ask'}）
contextBridge.exposeInMainWorld("__mykOnCloseChoice__", (payload) => {
  ipcRenderer.send("close-choice-pref", payload);
});

// deeplink 系统级打开（enchante:// 等非 http 协议走主进程 shell.openExternal，
// 避免 setWindowOpenHandler 对非 http(s) 的 deny 拦截）
contextBridge.exposeInMainWorld("__mykOpenExternal__", (url) => {
  return ipcRenderer.invoke("open-external", url);
});
