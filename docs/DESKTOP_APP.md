# MyKnowledge macOS 桌面 App

> 状态：可用 | 日期：2026-08-06 | 选型：**Electron**（WKWebView/Tauri 为后续优化路线）

## 1. 一句话架构

**Electron 壳 + Python 后端子进程**。Electron 主进程启动时 spawn 一个 PyInstaller 打包的 FastAPI 后端（`127.0.0.1:<随机空闲端口>`），窗口加载该地址——渲染体验与浏览器 100% 一致。

```
┌────────────────────── MyKnowledge.app ──────────────────────┐
│  Electron 主进程 (desktop/main.js)                          │
│   ├─ 单实例锁（防两个 app 写同一知识库）                     │
│   ├─ 自动协商空闲端口（8080 被占 → 8081/8082…）              │
│   ├─ 先显示 loading 等待页，后端就绪后加载主界面              │
│   ├─ preload 注入 window.__MYK_API_BASE__（前端已有注入点）   │
│   ├─ 外部链接交给系统浏览器                                  │
│   └─ 窗口关闭 → kill 后端子进程                              │
│  ├─ Resources/myknowledge-backend/                          │
│  │    PyInstaller onedir 产物（FastAPI + uvicorn + 前端静态） │
│  │    知识库仍用 ~/.myknowledge/（与 CLI/MCP 完全一致）       │
└─────────────────────────────────────────────────────────────┘
```

## 2. 目录结构

```
desktop/
├── package.json          # electron + electron-builder，npm scripts
├── main.js               # 主进程：spawn 后端 / 端口协商 / 生命周期
├── preload.js            # 注入 window.__MYK_API_BASE__
├── loading.html          # 后端冷启动期间的等待页
├── electron-builder.yml  # 打包配置（.app / zip / dmg）
└── assets/
    ├── icon.svg          # 图标源文件（与前端 favicon 同风格）
    └── icon.icns         # 生成产物（gitignore，用脚本生成）
scripts/
├── build-backend.sh      # 前端构建 + PyInstaller 打包后端
└── make-icon.sh          # icon.svg → icon.icns
```

## 3. 开发模式（日常开发不受影响）

改前端/后端仍用原有流程（浏览器 + `myknowledge serve --reload`）。

需要看桌面壳效果时，先起开发后端，再让 Electron 连它：

```bash
# 终端 1：开发后端（热更新）
python3 -m backend.cli serve --reload

# 终端 2：Electron 壳连开发后端
cd desktop && npm install          # 首次
npm run start:dev                  # MYKNOWLEDGE_DEV_BACKEND_URL=... electron .
```

开发模式下不 spawn 后端、不做端口协商，改完前后端刷新/重启即可。

## 4. 发布流程（发新版时）

```bash
# 一条命令：前端 build → 后端 PyInstaller → .app + zip/dmg
cd desktop && npm run release
```

等价于分步执行：

| 步骤 | 命令 | 产物 | 改动什么后需要重跑 |
|------|------|------|-------------------|
| 1. 前端构建 | `python3 frontend/build.py` | `index.standalone.html` + 资源版本号 | 改前端 JS/CSS |
| 2. 后端打包 | `./scripts/build-backend.sh` | `dist-backend/myknowledge-backend/` | 改后端 Python |
| 3. 壳打包 | `npx electron-builder --mac` | `desktop/dist/MyKnowledge-*.dmg/.zip` | 改 desktop/ 壳代码 |

**版本号**：统一在 `backend/__version__.py`（当前 0.7.5），发版时更新（`desktop/package.json` 的 version 同步）。

**产物**（`desktop/dist/`）：

| 文件 | 说明 |
|------|------|
| `MyKnowledge-0.7.5-arm64.dmg` | 拖入 Applications 安装（Apple Silicon） |
| `MyKnowledge-0.7.5-arm64-mac.zip` | 解压即用，网络受限时用这个分发 |

> DMG 构建工具从 GitHub 下载可能超时，`build:app` 脚本已默认走国内镜像
> （`ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/`，
> 可用环境变量覆盖）；zip 始终是可用的分发替代。

## 5. 体积构成与后端瘦身（2026-08-10 实测）

**.app 357MB**（mac-arm64）构成：

| 组成 | 体积 | 说明 |
|------|------|------|
| Electron 框架 | 275MB | Chromium 内核，**硬成本**，不可砍 |
| Python 后端（PyInstaller onedir） | 81MB | 已瘦身，见下 |
| 壳 + 图标 + 其余 | ~1MB | — |

**分发产物**：`MyKnowledge-0.7.5-arm64-mac.zip` 161MB，`MyKnowledge-0.7.5-arm64.dmg` 148MB。

**瘦身效果：后端 164MB → 71MB（-93MB，57%），.app 446MB → 357MB（-89MB，20%），zip 185MB → 161MB。**

**后端瘦身（`_internal` 140MB → 55MB）**：

三个优化点（`myknowledge-backend.spec` 与 `scripts/build-backend.sh` 同步生效）：

1. **前端只拷运行时文件**：原 `datas=[('frontend','frontend')]` 整目录拷贝，把 node_modules（24MB 构建期依赖，jsdom/turndown 供测试用）也打进包；改为精确拷贝 6 项（index.html / index.standalone.html / js / css / vendor / tiptap-bundle.mjs），前端共 2.4MB
2. **excludes 排除无关大库**：matplotlib(12M) / PIL(12M) / lxml(8.8M) / jedi(8.1M) / numpy(6.6M) / gevent(3.6M) / pandas / scipy——backend/ 源码 grep 零引用，PyInstaller 依赖收集过宽收进来的，约 50MB
3. **strip=True**：EXE 与 COLLECT 去符号表

> ⚠️ **两处配置必须同步维护**：PyInstaller 命令行参数（`scripts/build-backend.sh`）与 spec 文件（`myknowledge-backend.spec`）。改动任一处的 datas/excludes/strip，另一处必须同步，否则体积会回弹。构建时 `python3 -m PyInstaller myknowledge-backend.spec` 会自动重写 spec，注意检查是否覆盖了手动修改。

## 6. 关键工程决策

| 决策 | 原因 |
|------|------|
| **后端用 PyInstaller onedir 而非 onefile** | onefile 每次启动解包 ~10s，onedir 就绪时间更短；`backend/main.py` 的 `_frontend_dir()` 支持 `sys._MEIPASS` 定位打进包的前端资源 |
| **动态端口 + `__MYK_API_BASE__` 注入** | 8080 可能与浏览器版 `myknowledge serve` 冲突；前端 `api.js` 的 hostname 分支写死 8080，动态端口必须走 preload 注入 |
| **前端由后端托管**（`http://127.0.0.1:PORT`） | 与浏览器完全一致；`file://` 加载 ES Module（tiptap-bundle.mjs）会被 CORS 拦截 |
| **单实例锁** | 两个 app 同时写一个知识库会互相清锁 |
| **窗口关闭即退出** | 工具类 app 语义；同时确保后端子进程被 kill |

## 7. 已知限制

- **Git 是外部依赖**：后端写操作依赖系统 `git`（GitPython / trash 恢复等）。app 启动时检测，缺失会弹窗引导安装。
- **未签名/公证**：本地构建的 `.app` 首次打开需右键→打开（Gatekeeper 提示）。对外分发需 Apple Developer ID 签名 + notarization（electron-builder 已配置 `hardenedRuntime`，补齐证书后自动签名）。
- **仅 macOS 14+ 验证**：Electron 自带 Chromium，与浏览器一致，无系统 WebKit 兼容性问题。

## 8. 打包 App 待办清单

状态标记：✅ 已完成 · ⏳ 进行中 · ⬜ 待执行

### P0 — 近期（体验与分发核心）

- ⏳ **标题栏一体化（hiddenInset）+ 前端顶栏重构**：`titleBarStyle: 'hiddenInset'` 隐藏标题栏，红绿灯融入 UI；M logo + sidebar 折叠按钮上移顶栏，theme 收进用户菜单；顶栏设 `-webkit-app-region: drag` 拖拽区（交互元素 `no-drag`）；loading 页同步适配。*待与前端 agent 讨论布局后实施*
- ⬜ **启动动画最终化**：当前 loading 页方案已可用；后续把进度条与后端真实启动进度挂钩、显示阶段文案（检查 Git/初始化知识库/启动服务）
- ⬜ **自动更新（electron-updater）**：构建产出 `latest-mac.yml`；更新源托管 **OSS**（国内速度，项目已有 oss2 能力，`.env` 配置）；app 内「检查更新」菜单项；差分更新依赖 **zip 产物保留**

### P1 — 内部分发完善

- ⬜ **Intel（x64）或 universal 包**：当前只构建 arm64（Apple Silicon）；`npx electron-builder --mac --x64` 可出 x64，universal 需 `--universal`
- ⬜ **后端启动提速（~8s → ≤3s）**：冷启动主要耗时在 FastAPI/uvicorn/mcp 全量 import；探索延迟 import mcp 框架、按需加载
- ⬜ **后端日志落盘**：当前 stdout 直通终端，排查线上问题困难；落地到 `~/Library/Logs/MyKnowledge/`
- ⬜ **应用内「关于/设置」**：显示版本、知识库位置、按钮「打开数据目录」「查看日志」

### P2 — 对外发布准备

- ⬜ **GitHub Actions 自动构建发布**：`macos-14` runner（arm64），打 tag 触发 → PyInstaller + electron-builder → 产物上传 GitHub Release
- ⬜ **Developer ID 签名 + 公证**：对外分发硬前提（electron-builder 已配 `hardenedRuntime`，补齐证书自动签名）
- ⬜ **正式品牌图标**：当前 `assets/icon.svg` 为占位 M 图标，待品牌定稿后替换
- ⬜ **Tauri/WKWebView 优化路线**：体积 ~357MB → ~70MB（省 Chromium），需适配 WKWebView 差异（TipTap 编辑器/中文输入法、`backdrop-filter`、自定义滚动条）；已确认用户 macOS ≥ 14，importmap 无风险
