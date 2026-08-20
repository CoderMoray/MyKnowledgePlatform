"use strict";

/**
 * MyKnowledge macOS 桌面壳 — 主进程
 *
 * 启动流程：
 *   1. 协商空闲端口（8080 被占则依次递增，避免与浏览器版冲突）
 *   2. 创建 loading 窗口（自带 preload，注入 API 地址）→ 显示唯一加载动画
 *   3. spawn PyInstaller 打包的 Python 后端（--port <协商端口>）
 *   4. 后端就绪 且 loading 动画完成 → loadURL 主界面
 *
 * 加载动画策略：桌面 app 只有一套（loading.html 0→100%），前端 splash
 * 通过 preload 注入的 __MYK_APP_MODE__ 隐藏，网页端行为完全不变。
 *
 * 开发模式：设置环境变量 MYKNOWLEDGE_DEV_BACKEND_URL 指向已运行的
 * `myknowledge serve --reload`，跳过 spawn，直接复用开发者后端（热更新）。
 */

const { app, BrowserWindow, dialog, shell, ipcMain, Tray, Menu, nativeImage } = require("electron");
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

// ── 桌面壳状态 ─────────────────────────────────────────────
let tray = null;          // macOS 菜单栏图标（Tray 后台托管）
let hasTrayActive = false; // 是否处于托管状态（窗口隐藏到菜单栏）
let isAppLoaded = false;  // 主界面是否已加载（loading 期关闭 → 直接退出）
let isAnimatingToTray = false; // 缩小动画中（避免 resize 把缩小尺寸写入 window-state）

// 托盘图标文件（template：纯黑 M + 透明底，跟随菜单栏深浅色自动反色）
const TRAY_ICON = path.join(__dirname, "assets", "trayTemplate.png");

// 读取应用版本号（package.json 与 backend/__version__.py 同步维护）
function getAppVersion() {
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, "package.json"), "utf8"));
    return pkg.version || "";
  } catch {
    return "";
  }
}

// ── 窗口状态持久化：记住用户调整的窗口尺寸 ──
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
  // 缩小动画中窗口尺寸在变，不写入（否则会把缩小尺寸存进下次启动）
  if (isAnimatingToTray) return;
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
      // Tray 托管态（窗口隐藏）→ 走恢复流程；否则仅聚焦
      if (hasTrayActive || !mainWindow.isVisible()) {
        restoreFromTray();
      } else {
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.focus();
      }
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

async function findFreePort(start = 2030) {
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
  if (!backendProc || backendProc.killed) return;

  const proc = backendProc;
  backendProc = null;

  // 1. 优雅关闭：SIGTERM，uvicorn timeout_graceful_shutdown=5 会等待进行中的请求完成
  proc.kill("SIGTERM");

  // 2. 兜底：5.5s 后还没退出 → SIGKILL 强杀（5s 超时 + 500ms 缓冲）
  const forceKill = setTimeout(() => {
    if (!proc.killed) {
      proc.kill("SIGKILL");
    }
  }, 5500);

  proc.on("exit", () => clearTimeout(forceKill));
}

// ── Tray 后台托管 ─────────────────────────────────────────

/** 创建菜单栏托盘图标 + 菜单（幂等：已创建则不重复） */
function ensureTray() {
  if (tray) return;
  // Electron 43+ 移除了 Tray.setTemplateImage()；模板图标标记改到 nativeImage 上：
  // 先用 createFromPath 加载，再 setTemplateImage(true)，最后把 NativeImage 传给 Tray。
  const img = nativeImage.createFromPath(TRAY_ICON);
  img.setTemplateImage(true); // template image：跟随菜单栏深浅色自动反色
  tray = new Tray(img);
  const version = getAppVersion();
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "显示主窗口", click: restoreFromTray },
      { type: "separator" },
      {
        label: version ? `关于 MyKnowledge v${version}` : "关于 MyKnowledge",
        click: () => {
          dialog.showMessageBox({
            type: "info",
            title: "关于 MyKnowledge",
            message: `MyKnowledge v${version}`,
            detail:
              "企业私有的知识管理平台\n\n苹果级的知识隐私保护\n\n所有知识仅你授权的 AI 可访问",
          });
        },
      },
      { type: "separator" },
      { label: "退出", click: () => app.quit() },
    ])
  );
}

/**
 * 托管到菜单栏：Dock 隐藏 + 缩小动画（~250ms setBounds 逐帧缩 + 透明度渐隐）→ hide。
 * 进程常驻，后端不退出。
 */
function minimizeToTray() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  hasTrayActive = true;
  isAnimatingToTray = true;
  ensureTray();
  if (app.dock) app.dock.hide();

  const { x, y, width, height } = mainWindow.getBounds();
  const dur = 250;
  const start = Date.now();

  // 主进程无可靠 requestAnimationFrame（窗口隐藏时可能不触发），用 setTimeout 逐帧缩
  const animate = () => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    const t = Math.min(1, (Date.now() - start) / dur);
    const eased = 1 - (1 - t) * (1 - t); // ease-out 渐快
    const cw = Math.max(4, Math.round(width * (1 - eased)));
    const ch = Math.max(4, Math.round(height * (1 - eased)));
    // 锚定原窗口中心缩放
    mainWindow.setBounds({
      x: Math.round(x + (width - cw) / 2),
      y: Math.round(y + (height - ch) / 2),
      width: cw,
      height: ch,
    });
    mainWindow.setOpacity(1 - eased);
    if (t < 1) {
      setTimeout(animate, 16); // ~60fps
    } else {
      mainWindow.hide();
      // 恢复原尺寸/不透明度，等下次 show 时用
      mainWindow.setBounds({ x, y, width, height });
      mainWindow.setOpacity(1);
      isAnimatingToTray = false;
    }
  };
  animate();
}

/** 从菜单栏恢复主窗口：显示 + Dock 显示 */
function restoreFromTray() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.show();
  mainWindow.focus();
  if (app.dock) app.dock.show();
  hasTrayActive = false;
}

// ── 启动后端 ─────────────────────────────────────────────

async function startBackend(port) {
  if (!fs.existsSync(BACKEND_BIN)) {
    throw new Error(
      `未找到后端程序：\n${BACKEND_BIN}\n\n请重新安装应用，或用 npm run build:backend 重新打包。`
    );
  }

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

  await waitForBackend(`http://127.0.0.1:${port}`);
}

// ── 窗口 ─────────────────────────────────────────────────

function createLoadingWindow(backendUrl) {
  // 唯一的加载动画窗口；创建时就带 preload（api-base + app 标志 + IPC 桥）
  mainWindow = new BrowserWindow({
    width: windowState.width,
    height: windowState.height,
    resizable: false,
    title: "MyKnowledge",
    titleBarStyle: "hidden", // 无边框标题栏（系统红黄绿保留），sidebar 顶部 28px 条让位
    backgroundColor: "#fafafa",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      // 后端地址传给 preload → 注入 window.__MYK_API_BASE__ / __MYK_APP_MODE__
      additionalArguments: [`--myk-api-base=${backendUrl}`],
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });
  mainWindow.once("ready-to-show", () => mainWindow.show());
  attachWindowCloseHandler();
  mainWindow.loadFile(path.join(__dirname, "loading.html"));
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

/**
 * 主窗口关闭询问：点红点不直接退出。
 *  - 真正退出流程（app.quit）→ 放行
 *  - loading 期（主界面未加载）→ 直接退出（loading.html 无 modal 代码）
 *  - 主界面 → preventDefault → 通知渲染层弹自绘 modal
 */
function attachWindowCloseHandler() {
  mainWindow.on("close", (e) => {
    if (isQuitting) return; // 真退出流程，放行
    if (!isAppLoaded) {
      // loading 期关闭：直接退出（不弹询问，loading 页无 modal 代码）
      app.quit();
      return;
    }
    e.preventDefault();
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("show-close-choice");
    }
  });
}

function loadAppWindow(backendUrl) {
  isAppLoaded = true; // 主界面已加载 → 此后关闭走询问流程
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
    titleBarStyle: "hidden", // 无边框标题栏（系统红黄绿保留），sidebar 顶部 28px 条让位
    backgroundColor: "#fafafa", // 与前端 splash 底色一致，避免白闪
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      additionalArguments: [`--myk-api-base=${backendUrl}`],
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.on("resize", saveWindowState);

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
  attachWindowCloseHandler();

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ── 生命周期 ─────────────────────────────────────────────

app.whenReady().then(async () => {
  // 启动即创建托盘图标（幂等），用户随时可从菜单栏「显示主窗口 / 退出」
  ensureTray();

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

  let backendUrl = "";
  let backendReady = false;
  let loadingDone = false;

  // 后端就绪 且 loading 动画完成 → 切换主界面
  const maybeLoad = () => {
    if (backendReady && loadingDone && mainWindow && !mainWindow.isDestroyed()) {
      loadAppWindow(backendUrl);
    }
  };

  ipcMain.on("loading-done", () => {
    loadingDone = true;
    maybeLoad();
  });

  // ── 关闭询问 / Tray 托管 IPC ──────────────────────────────
  // 渲染层 modal 三选：退出 / 后台托管
  ipcMain.on("close-choice", (_e, payload) => {
    const action = payload && payload.action;
    if (action === "quit") app.quit();
    else if (action === "tray") minimizeToTray();
    // remember 由渲染层存 localStorage，主进程无需持久化
  });

  // 渲染层初始化上报记忆偏好：有记忆则跳过 modal 直接执行
  ipcMain.on("close-choice-init", (_e, payload) => {
    const action = payload && payload.action;
    if (action === "quit") app.quit();
    else if (action === "tray") minimizeToTray();
    // null → 无记忆，忽略（等用户点红点再询问）
  });

  // 设置页「关闭行为」偏好：'ask' 表示清除记忆。渲染层已持久化，此处仅确认通道。
  ipcMain.on("close-choice-pref", () => {
    /* 无需主进程处理 */
  });

  // ── deeplink 系统级打开（IPC）────────────────────────────
  // Enchante 的 enchante:// protocol 不是 http/https，主窗口的
  // setWindowOpenHandler 只放行 http/https，其余被 deny → 需走 shell.openExternal
  // 在系统层路由到注册的 Enchante 应用。
  ipcMain.handle("open-external", (_e, url) => {
    if (typeof url !== "string" || !url) return { ok: false, error: "empty url" };
    // 仅放行协议链接（enchante://...），避免渲染层任意打开本地文件/命令
    if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(url) || url.startsWith("file:")) {
      return { ok: false, error: "blocked url" };
    }
    try {
      shell.openExternal(url);
      return { ok: true };
    } catch (err) {
      return { ok: false, error: String(err) };
    }
  });

  try {
    if (DEV_BACKEND_URL) {
      // 开发模式：直接连开发者后端
      backendUrl = DEV_BACKEND_URL;
      createLoadingWindow(backendUrl);
      await waitForBackend(backendUrl);
      backendReady = true;
    } else {
      // 先协商端口，让 loading 窗口从一开始就带正确的 API 地址
      const port = await findFreePort();
      backendUrl = `http://127.0.0.1:${port}`;
      createLoadingWindow(backendUrl);
      await startBackend(port);
      backendReady = true;
    }

    // loading 动画兜底：后端就绪后最多再等 3s（loading 页进度慢或 IPC 异常时）
    setTimeout(() => {
      if (!loadingDone) {
        loadingDone = true;
        maybeLoad();
      }
    }, 3000);

    maybeLoad();
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
  // 但 Tray 托管模式下（进程常驻菜单栏）不退出
  if (!hasTrayActive) app.quit();
});

app.on("before-quit", () => {
  isQuitting = true;
  stopBackend();
});
