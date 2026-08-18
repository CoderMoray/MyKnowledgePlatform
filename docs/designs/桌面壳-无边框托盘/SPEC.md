# 桌面壳「无边框标题栏 + 关闭询问 + Tray 后台托管」设计定案

> 状态：**已定案** — 2026-08-19 架构讨论完成（多轮决策全部落地）
> 归属：桌面端（Electron 主进程）为主 + 前端适配（隔离门控）
> 前置条件：**等当前前端视觉优化任务提交后再实施**（改同一批前端文件，避免冲突）
> 关联：`docs/DESKTOP_APP.md`（验收后同步）

---

## 一、背景与目标

桌面 App（`desktop/`，Electron 壳 + PyInstaller 后端）目前是标准 macOS 窗口（系统标题栏 + 红黄绿常驻）。

目标：
1. **无边框沉浸式**：去掉原生标题栏，保留系统红黄绿（`titleBarStyle: 'hidden'`）
2. **关闭询问**：点红点弹自绘 modal，三选「退出 / 后台托管 / 取消」+ 「记住我的选择」
3. **Tray 后台托管**：托管到 macOS 菜单栏（缩小动画 + 图标 + 菜单），进程常驻

## 二、决策记录（2026-08-18/19）

| # | 决策点 | 裁决 | 理由 |
|---|---|---|---|
| 1 | 去 Frame 方式 | **`titleBarStyle: 'hidden'`**（不自绘 traffic lights） | 自绘 hover 显隐代价大且丢失原生行为；hidden 是 macOS App 主流 |
| 2 | hover 显隐按钮 | ❌ 不做 | `customButtonsOnHover` 仅 Windows/Linux；自绘=行为丢失（红点右键菜单/绿点长按等） |
| 3 | 关闭询问 UI | **自绘 modal**（复用 `.guide-modal` 基建，小 modal ~400×260） | 需「记住我的选择」checkbox + 视觉与应用统一；原生 dialog 做不了 |
| 4 | 「记住选择」修改入口 | **设置 modal 加「关闭行为」三选**（询问/退出/后台托管） | 记住后不再弹 modal，必须有入口改回 |
| 5 | loading 期关闭 | **直接 `app.quit()`**（不弹询问） | loading 页是独立 `loading.html`，无 modal 代码，弹询间会无响应 |
| 6 | Tray 菜单 | **三项：显示主窗口 / 关于 / 退出** | macOS 菜单栏图标**左键点击=弹菜单**，无双击语义；「显示主窗口」是唯一恢复入口（必须保留） |
| 7 | 缩小动画 | 简化方案：`setBounds` 逐帧缩（~250ms）+ 透明度渐隐 → hide | macOS 不自带"缩到 Tray"动画（genie 仅 Dock）；真 genie 效果第三方库不稳定，不做 |
| 8 | 托盘图标 | **template image**：纯黑 M + 透明底（16px + 32px@2x） | 菜单栏图标非白底，系统按深浅色自动反色；现有 `icon.svg` 是蓝底白 M 不能用 |
| 9 | 前端隔离 | **`__MYK_APP_MODE__` 门控 + `data-app-mode="desktop"` 作用域，不新建文件夹** | 改动量小且深度耦合 Alpine 结构；`splash.js:16` 已有判断先例 |
| 10 | 拆分阈值 | 桌面专属 JS>300 行 / CSS>150 行时才拆 `js/desktop.js` + `css/desktop.css`（build.py 列表各加一项） | 当前量级撑不起目录复杂度 |

## 三、IPC 契约（主进程 ↔ 渲染进程）

| 方向 | 事件 | payload | 说明 |
|---|---|---|---|
| 主→渲染 | `show-close-choice` | — | 点红点（主窗口）触发，前端弹自绘 modal |
| 渲染→主 | `close-choice` | `{action:'quit'\|'tray', remember:bool}` | 用户在 modal 三选 + 是否记住 |
| 渲染→主 | `close-choice-init` | `{action:'quit'\|'tray'} \| null` | 初始化上报记忆偏好；有记忆则跳过 modal 直接执行 |
| 渲染→主 | `close-choice-pref` | `{action:'quit'\|'tray'\|'ask'}` | 设置页「关闭行为」写入偏好（`'ask'` 清除记忆） |

记忆存储：渲染进程 localStorage（主进程不可读，故由渲染层上报）。

## 四、实施范围与归属

| 部分 | 内容 | 归属 |
|---|---|---|
| 桌面壳主体（~60%） | `main.js`（titleBarStyle/关闭询问/Tray/缩小动画/IPC/菜单）、`preload.js`、托盘图标 template | **桌面端（Electron）** |
| 前端适配（~30%） | 关闭 modal（`__MYK_APP_MODE__` 门控）+ sidebar 28px titlebar 条（`[data-app-mode="desktop"]`）+ 设置页「关闭行为」 | **前端开发 agent** |
| 文档（~10%） | `docs/DESKTOP_APP.md` | 桌面端收尾 |

无独立桌面端 agent 时整体派前端开发 agent，但须明确 main.js 是 Electron 主进程范畴。

## 五、最终实施 prompt（可复制转交）

```
# 桌面壳「无边框标题栏 + 关闭询问自绘 + Tray 后台托管」实施任务

## 背景
desktop/ 桌面壳。方案已定案（docs/designs/桌面壳-无边框托盘/SPEC.md），
直接实施，无需再确认。前置条件：前端视觉优化任务已提交后方可动前端文件。

## 1. main.js（主进程）
- 主窗口 + loading 窗口均加 titleBarStyle: 'hidden'（系统红黄绿保留）
- 关闭询问（仅主窗口）：
  - 'close' → preventDefault → webContents.send('show-close-choice')
  - 收到 'close-choice' {action, remember}：quit → app.quit()；
    tray → 托管流程；remember → 通知渲染层记忆（渲染层存 localStorage）
  - 收到 'close-choice-init'：有记忆则直接执行对应动作（不再弹 modal）
- loading 窗口关闭：直接 app.quit()（loading.html 无 modal 代码，特判）
- 托盘托管：Tray(trayTemplate.png, setTemplateImage(true)) + app.dock.hide()
  + 窗口缩小动画（~250ms setBounds 逐帧缩 + 透明度渐隐）→ hide()
  恢复：window.show() + app.dock.show()
- Tray 菜单（setContextMenu）：显示主窗口 / 关于 / 退出
  - 显示主窗口 → 恢复流程（macOS 左键=弹菜单，此项是唯一恢复入口）
  - 关于 → dialog.showMessageBox「MyKnowledge v<version>」（读 package.json）
  - 退出 → app.quit()（真退出，Kill 进程，停后端）
- window-all-closed：托管模式下不 quit（区分 hasTrayActive 状态）
- 单实例 second-instance → 恢复窗口（复用现有逻辑）

## 2. preload.js
- 新增 IPC 桥（按 SPEC §三 契约）：
  __mykShowCloseChoice__ / __mykSubmitCloseChoice__ / __mykInitClosePreference__ /
  __mykOnCloseChoice__

## 3. 前端（桌面模式隔离，不影响网页端）
- 隔离机制：桌面模式给 <html> 加 data-app-mode="desktop"（沿用 __MYK_APP_MODE__，
  统一用 class 而非散落 JS 判断）；网页端零变化
- 关闭询问 modal：复用 .guide-modal 基建（小 modal ~400×260，x-show 加
  __MYK_APP_MODE__ 门控）：退出 / 后台托管 / 取消 + checkbox「记住我的选择」；
  ESC=取消；打开期间再点关闭不嵌套；视觉与 design-token 一致
- sidebar 顶部 28px titlebar 条：[data-app-mode="desktop"] 作用域，
  -webkit-app-region: drag、透明、高 28px（traffic lights 让位），
  .sidebar-brand 下移，品牌视觉不变
- 设置 modal 加「关闭行为」三选（询问/退出/后台托管）→ 'close-choice-pref'，
  选「询问」清除记忆
- 不新建文件夹：桌面片段在现有文件内分区 + 命名（desktopClosePref 等）
  （阈值：JS>300 行 / CSS>150 行才拆 js/desktop.js + css/desktop.css）

## 4. 托盘图标（template）
- 从 desktop/assets/icon.svg 的 M 字形制作：纯黑 M + 透明底，
  16px(trayTemplate.png) + 32px(trayTemplate@2x.png)（工具任选）
- setTemplateImage(true)，跟随菜单栏深浅色自动反色

## 5. 验收
- 开发模式/打包手动验证：
  - 标题栏无边框、红黄绿常驻、sidebar 顶部不被遮挡
  - 主窗口点红点弹自绘 modal；三选 + 记住选择生效（二次关闭跳过弹窗）；
    设置页可改回「询问」
  - loading 期点红点直接退出（无弹窗）
  - 托管：缩小动画 + 菜单栏图标 + Dock 消失；菜单三项各生效；
    「显示主窗口」恢复；「退出」杀进程（后端确认退出）
  - 网页端（浏览器）显示与现在完全一致（隔离生效）
- 不动后端/业务逻辑；验证后同步 docs/DESKTOP_APP.md
```

## 六、验收清单（架构师侧）

- [ ] 桌面壳三处 IPC 与 SPEC §三 契约一致
- [ ] 前端三改动均 `data-app-mode`/`__MYK_APP_MODE__` 门控，网页端零变化（浏览器实测）
- [ ] 设置页「关闭行为」三选可往返修改（含清除记忆）
- [ ] loading 期关闭直接退出
- [ ] 托盘菜单三项 + template 图标反色正常
- [ ] 缩小动画 ≤300ms 不卡顿
- [ ] 文档同步 `docs/DESKTOP_APP.md`
