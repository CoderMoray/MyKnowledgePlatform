"use strict";

/**
 * MyKnowledge macOS 桌面壳 — 主进程
 *
 * 职责：
 *   1. 启动时 spawn 打包好的 Python 后端（PyInstaller onedir）
 *   2. 自动协商空闲端口（8080 被占则依次递增），避免与浏览器版冲突
 *   3. 先显示启动等待页，后端就绪后 BrowserWindow 加载 http://127.0.0.1:PORT
 *   4. preload 注入 window.__MYK_API_BASE__（前端 api.js 已有此注入点）
 *   5. 单实例锁 + 窗口关闭时杀掉后端子进程
 *
 * 开发模式：设置环境变量 MYKNOWLEDGE_DEV_BACKEND_URL 指向已运行的
 * `myknowledge serve --reload`，则跳过 spawn，直接复用开发者后端（热更新）。
 */

const { app, BrowserWindow, dialog, shell } = require("electron");
const { spawn } = require("child_process");
const net = require("net");
const path = require("path");
const fs = require("fs");

// 开发模式：连开发者自己起的后端（npm run start:dev）
const DEV_BACKEND_URL = process.env.MYKNOWLEDGE_DEV_BACKEND_URL || "";

// 生产模式：打包进 app 的 Resources/ 的后端二进制（PyInstaller onedir 产物）
const BACKEND_BIN =
  process.env.MYKNOWLEDGE_BACKEND_BIN ||
  path.join(process.resourcesPath, "myknowledge-backend", "myknowledge-backend");

let mainWindow = null;
let backendProc = null;
let isQuitting = false;

// ── 窗口状态持久化：加载前后窗口尺寸一致，且记住用户调整 ──
const userDataPath = app.getPath("userData");
const windowStateFile = path.join(userDataPath, "window-state.json");

function loadWindowState() {
  try {
    const d = JSON.parse(fs.readFileSync(windowStateFile, "utf8"));
    if (Number.isFinite(d.width) && Number.isFinite(d.height)) {
      return {
        width: Math.max(Math.round(d.width), 940),
        height: Math.max(Math.round(d.height), 600),
      };
    }
  } catch {
    /* 首次启动或文件损坏 → 使用默认尺寸 */
  }
  // 默认 1080x720（3:2，笔记本友好）；用户调整后以 window-state.json 为准
  return { width: 1080, height: 720 };
}

function saveWindowState() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const [width, height] = mainWindow.getSize();
  try {
    fs.writeFileSync(windowStateFile, JSON.stringify({ width, height }));
  } catch {
    /* 写入失败不影响运行 */
  }
}

let windowState = loadWindowState();

// ── 单实例：防止两个 app 同时写同一个知识库 ──────────────
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

// ── 工具函数 ─────────────────────────────────────────────

function isPortFree(port) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", () => resolve(false));
    srv.listen(port, "127.0.0.1", () => {
      srv.close(() => resolve(true));
    });
  });
}

async function findFreePort(start = 8080) {
  for (let p = start; p < start + 50; p += 1) {
    if (await isPortFree(p)) return p;
  }
  throw new Error(`未找到可用端口（${start}-${start + 49} 全部被占用）`);
}

function checkGitInstalled() {
  return new Promise((resolve) => {
    try {
      const git = spawn("git", ["--version"], { stdio: "ignore" });
      git.on("error", () => resolve(false));
      git.on("exit", (code) => resolve(code === 0));
    } catch {
      resolve(false);
    }
  });
}

function waitForBackend(url, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`${url}/api/status`);
        if (res.ok) {
          clearInterval(timer);
          resolve();
          return;
        }
      } catch {
        /* 后端未就绪，继续轮询 */
      }
      if (Date.now() - started > timeoutMs) {
        clearInterval(timer);
        reject(new Error(`后端启动超时（${timeoutMs / 1000}s）`));
      }
    }, 400);
  });
}

function stopBackend() {
  if (backendProc) {
    backendProc.kill();
    backendProc = null;
  }
}

// ── 启动后端 ─────────────────────────────────────────────

async function startBackend() {
  if (DEV_BACKEND_URL) {
    // 开发模式：直接连开发者后端，检查其可用
    await waitForBackend(DEV_BACKEND_URL);
    return DEV_BACKEND_URL;
  }

  if (!fs.existsSync(BACKEND_BIN)) {
    throw new Error(
      `未找到后端程序：\n${BACKEND_BIN}\n\n请重新安装应用，或用 npm run build:backend 重新打包。`
    );
  }

  const port = await findFreePort();
  backendProc = spawn(BACKEND_BIN, ["--port", String(port)], {
    env: { ...process.env },
    stdio: ["ignore", "pipe", "pipe"],
  });
  backendProc.stdout.on("data", (d) => process.stdout.write(`[backend] ${d}`));
  backendProc.stderr.on("data", (d) => process.stderr.write(`[backend] ${d}`));
  backendProc.on("exit", (code, signal) => {
    if (!isQuitting) {
      dialog.showErrorBox(
        "MyKnowledge 后端已退出",
        `后端服务意外退出（code=${code} signal=${signal}）。\n请重新打开应用。`
      );
    }
    backendProc = null;
  });

  const url = `http://127.0.0.1:${port}`;
  await waitForBackend(url);
  return url;
}

// ── 窗口 ─────────────────────────────────────────────────

function createLoadingWindow() {
  // 与主窗口同尺寸（记忆的用户状态），避免加载前后窗口跳变
  mainWindow = new BrowserWindow({
    width: windowState.width,
    height: windowState.height,
    resizable: false,
    title: "MyKnowledge",
    backgroundColor: "#fafafa",
    show: false,
  });
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.loadFile(path.join(__dirname, "loading.html"));
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function loadAppWindow(backendUrl) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    // 从 loading 窗口切换：保持同一尺寸（不重新 setSize，避免跳变）
    mainWindow.setResizable(true);
    mainWindow.setMinimumSize(940, 600);
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
      if (url.startsWith("http://") || url.startsWith("https://")) {
        shell.openExternal(url);
      }
      return { action: "deny" };
    });
    mainWindow.webContents.on("will-navigate", (event, url) => {
      if (!url.startsWith(backendUrl)) event.preventDefault();
    });
    mainWindow.loadURL(backendUrl);
    mainWindow.on("resize", saveWindowState);
    return;
  }

  mainWindow = new BrowserWindow({
    width: windowState.width,
    height: windowState.height,
    minWidth: 940,
    minHeight: 600,
    title: "MyKnowledge",
    backgroundColor: "#fafafa", // 与前端 splash 底色一致，避免白闪
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      // 把后端地址传给 preload → 注入 window.__MYK_API_BASE__
      additionalArguments: [`--myk-api-base=${backendUrl}`],
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.on("resize", saveWindowState);

  // 外部链接（ref: 里的 http/https）一律交给系统浏览器
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  // 禁止导航离开后端地址（防止被带到外部页面）
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(backendUrl)) event.preventDefault();
  });

  mainWindow.loadURL(backendUrl);

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ── 生命周期 ─────────────────────────────────────────────

app.whenReady().then(async () => {
  // Git 是后端写操作的外部依赖，先检测并友好提示
  const gitOk = await checkGitInstalled();
  if (!gitOk) {
    dialog.showMessageBoxSync({
      type: "warning",
      message: "未检测到 Git",
      detail:
        "MyKnowledge 依赖 Git 保存每次修改的历史版本。\n\n请安装 Git 后重新打开应用：\nhttps://git-scm.com/downloads\n（macOS 也可在终端运行 xcode-select --install）",
    });
  }

  // 先显示启动等待页，避免后端冷启动（~8s）期间黑屏
  createLoadingWindow();

  try {
    const backendUrl = await startBackend();
    loadAppWindow(backendUrl);
  } catch (err) {
    dialog.showErrorBox(
      "MyKnowledge 启动失败",
      String((err && err.message) || err)
    );
    app.quit();
  }
});

app.on("window-all-closed", () => {
  // 工具类 app：窗口全关即退出（并清理后端进程）
  app.quit();
});

app.on("before-quit", () => {
  isQuitting = true;
  stopBackend();
});
