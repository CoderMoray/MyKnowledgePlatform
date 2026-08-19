# trayTemplate v2 · macOS 菜单栏托盘图标优化 · 设计规格

> 状态：tray 图标优化 ✅ 已落地（方案 A · Bold M，2026-08-19）
> 设计稿：ardot · 页面《托盘图标 (template) 优化 · 2026-08-19》
> 草案日期：2026-08-19
> 设计角色：前端视觉 / 交互设计 agent

> ⚠️ **DMG 范围撤销说明（2026-08-19）**
>
> 本轮原始任务范围**只覆盖 tray 菜单栏图标**。第二轮用户原本列了一份"tray + DMG"补充文档，
> 但用户实际未授权 DMG 改动 —— agent 基于补充文档自行扩展了 DMG 设计稿并改了 PNG / 脚本，
> **已在 2026-08-19 由用户驳回并完整回滚**：
>
> | 项 | 处置 |
> |---|---|
> | `desktop/assets/dmg-background.png` | 已 `git checkout HEAD` 恢复到 v1 原版（86767 B）|
> | `desktop/assets/dmg-background@2x.png` | 已 `git checkout HEAD` 恢复到 v1 原版（212523 B）|
> | `scripts/make-dmg-background.py` | 已 `git checkout HEAD` 恢复到原 4653 B 版本 |
> | `docs/designs/tray-icon-2026-08-19/SPEC-DMG.md` | 已删除 |
> | `docs/designs/tray-icon-2026-08-19/_dmg-v2-*.png` 5 个临时截图 | 已删除 |
> | ardot 画布上残留的 DMG section | 保留作为历史记录，不另行动作 |
> | `desktop/main.js` / `desktop/electron-builder.yml` 锚点 | 未动（DMG 改动前本身就未触及）|
>
> **后续凡是用户没明确说要改 DMG，本 agent 都不应主动触碰 DMG 资源。** 如未来要做 DMG 优化，
> 那是另一轮独立任务，需用户单独下指令。

---

## 0. 优化背景

当前 `desktop/assets/trayTemplate.png` 是把应用主图标 `icon.svg`（512×512，含渐变圆角矩形背景）**直接降采样**到 16×16 后生成的 template image。问题：

| 问题 | 后果 |
|---|---|
| 降采样后 M 字笔画只剩 1–2px | 22pt 菜单栏下远看糊成黑块 |
| 圆角矩形被阶梯像素画 | 与主图标的圆润风格不一致，且失去 M 字识别度 |
| `@2x` 只是简单一倍放大，未做 Retina hint | macOS 视网膜屏幕下抗锯齿发虚 |
| 没有深 / 浅菜单栏的视觉验证 | 设计依据缺失 |

→ 重新设计：在 16×16 像素栅格上手工描线，不依赖主图标降采样。

---

## 1. 推荐方案 · A · Bold M 字形（PRIMARY）

### 1.1 设计意图

沿用项目主图标字根 `M`（MyKnowledge 的 M），但把图形从 512px 主图标的圆角矩形 / 渐变语境中**剥离**出来：
- **不要**：圆角矩形底 / 渐变色 / 装饰元素
- **要**：纯黑 M 字形，Helvetica Bold 风格，笔画几何对称

template image 协议约束（macOS 强约束，**不能破**）：
- 只接受 RGB 灰度通道（实际只剩黑色）+ alpha
- 系统根据菜单栏背景自动反色
- 不需要交付彩色 / 阴影 / 渐变等资源

### 1.2 设计 SVG 源

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path d="M1 15 L1 1 L4.5 1 L8 7.6 L11.5 1 L15 1 L15 15 L12.4 15 L12.4 5.6 L9 11.6 L7 11.6 L3.6 5.6 L3.6 15 Z" fill="#000"/>
</svg>
```

设计源已落本机：`docs/designs/tray-icon-2026-08-19/export/trayTemplate-v2-source.svg`

### 1.3 像素栅格规格

坐标系统：`viewBox="0 0 16 16"`，单位 = 1 px。

| 笔画 / STROKE | @1x 坐标 (16 单位) | @2x 栅格 (32 单位) | 占 viewport 比例 |
|---|---|---|---|
| 左竖 Left Stroke | x ∈ [1.0, 3.6] | x ∈ [2, 7] @ 32-grid | 16.3% W · 87.5% H |
| 右竖 Right Stroke | x ∈ [12.4, 15.0] | x ∈ [25, 30] @ 32-grid | 16.3% W · 87.5% H |
| 中央 V Apex | (8, 7.6) → (8, 11.6) | (16, ~15) → (16, 23) | 中央纵向 65% H |

- 笔画厚 ≈ 2.6 px @1x / 5.2 px @2x（垂直 / 水平笔画统一）
- 字形边界：x ∈ [1, 15], y ∈ [1, 15]（周围留 1px 安全边距，防止菜单栏抗锯齿切断笔画尖端）
- 字形中心点：(8, 8)，垂直对称于 y=8

### 1.4 颜色规范（template image 协议）

| Token | 值 | 说明 |
|---|---|---|
| 唯一前景色 | RGB(0, 0, 0) | 仅黑；不接受任何灰色 / 彩色 |
| alpha 范围 | 0 或 255 | 仅两级；不接受中间灰度 |
| 背景 | alpha = 0 | 完全透明，让菜单栏背景穿透 |

> ⚠️ 即使在 Figma / Sketch 设计稿中给图标涂任何颜色，导出 PNG 后必须把**非 (0,0,0) 的像素**全部去除（清除 RGB 通道 + 量化 alpha）。代码层面推荐：
> ```js
> // sharp / PIL 后处理：把 RGB 非黑色像素强制为 RGB(0,0,0)
> // 把 alpha 非 0/255 的中间值向上 / 向下量化（建议 round）
> ```
>
> 验收脚本：
> ```python
> from PIL import Image
> img = Image.open("trayTemplate-v2.png")
> colors = {p[:3] for p in img.getdata()}
> assert colors.issubset({(0,0,0), (255,255,255)}), f"非 template 颜色: {colors}"
> ```

### 1.5 字号 vs viewport

| 实际渲染尺寸 | 推荐视觉行为 | 备注 |
|---|---|---|
| 16 px（@1x PNG，菜单栏 16pt 物理）| 字形居中，笔画 ~2px | 1x retina 显示器对应 |
| 22 px（macOS 菜单栏标准 1x）| 字形居中，笔画 ~3px | macOS 在 1x 屏上把 PNG 缩放到 22px |
| 32 px（@2x PNG，Retina 22pt 物理）| 字形居中，笔画 ~5px | retina 显示器首选 |
| 44 px（@2x 实际 hover / drag 尺寸）| 字形清晰可辨 | 系统自动放大 |
| 88 / 128 px（拖拽 / touch bar）| 字形无失真 | 矢量缩放至大尺寸无压力 |

---

## 2. 其他备选方案（含在画布中）

### 2.1 方案 B · 三条横（备选 ALT）
- 三条不等长横线
- 全几何，16px 下无可读失败点
- 隐喻"知识库层级 / 列表"
- **风险**：与品牌主图标字根（M）脱钩

### 2.2 方案 C · 负空间 · M 框（备选 ALT）
- 圆角方框 + 内部挖空 M 形
- "知识卡片"隐喻
- **风险**：16px 下 M 挖空笔画易糊；菜单栏此造型较为罕见

### 2.3 方案 D · 双卡片叠（实验 EXPLORE）
- 错位双矩形叠影（描边 + 实心）
- "多文档 / 文档库"隐喻，与 macOS Finder 图标家族呼应
- **风险**：与项目品牌 M 字形完全脱钩；学习成本

> 选型建议：选 **A · Bold M**；如团队接受偏离品牌，可换 **C · 负空间 M**。

---

## 3. 交付物清单

### 3.1 设计交付（本目录）

| 文件 | 类型 | 用途 |
|---|---|---|
| `docs/designs/tray-icon-2026-08-19/export/trayTemplate-v2-source.svg` | SVG 矢量 | 设计源头，可重新导出 PNG |
| `docs/designs/tray-icon-2026-08-19/export/trayTemplate-v2-16.png` | PNG 16×16 | @1x 候选（262 B） |
| `docs/designs/tray-icon-2026-08-19/export/trayTemplate-v2-32.png` | PNG 32×32 | @2x 候选（440 B） |
| `docs/designs/tray-icon-2026-08-19/export/124_*.svg` | SVG 矢量 | 画布各 section 矢量稿，前端 agent 可 read_file 解析 |
| `docs/designs/tray-icon-2026-08-19/screenshots/screenshot-*.png` | PNG 截图 | 人工审查参考；前端 agent 不依赖 |

### 3.2 代码层集成

| 改动 | 当前 | 目标 |
|---|---|---|
| `desktop/assets/trayTemplate.png` | 272 B（降采样） | 替换为 `trayTemplate-v2-16.png` 并更名为默认文件名 |
| `desktop/assets/trayTemplate@2x.png` | 简单放大 | 替换为 `trayTemplate-v2-32.png` 并更名为默认文件名 |
| `desktop/main.js` L6-L7 | `loadImage(assetsPath + 'trayTemplate.png')` | 不变（同名替换即可）|
| `desktop/main.js` L7 | `setTemplateImage(true)` | **保持**（不能去掉，去了 macOS 不会自动反色）|

> 集成步骤：
> 1. 确认 `trayTemplate-v2-16.png` 视觉无问题
> 2. `mv desktop/assets/trayTemplate-v2-16.png desktop/assets/trayTemplate.png`
> 3. 同样 for `@2x`
> 4. 重启 Electron 应用，截图 macOS 菜单栏验证深 / 浅两态

---

## 4. macOS 状态行为（系统提供，非 PNG 内容）

下表由 macOS 系统处理，**不需要额外设计资源**：

| 系统状态 | PNG 内容 | 渲染结果 |
|---|---|---|
| 菜单栏浅色背景 | RGB(0,0,0) + alpha | 图标显示为黑色 |
| 菜单栏深色背景 | RGB(0,0,0) + alpha | 图标自动反色为白色 |
| hover / active | 同上 | 背景方块反相（黑↔白），图标色与背景反相 |

→ 不需要为 hover / dark mode 单独交付多张 PNG。

---

## 5. 验收标准（QA Checklist）

| 项 | 期望 |
|---|---|
| 16×16 PNG 文件大小 | < 500 B（实测 262 B） |
| 32×32 PNG 文件大小 | < 800 B（实测 440 B） |
| 像素颜色集合 | ⊆ { RGB(0,0,0), RGB(255,255,255) }（template 协议约束） |
| alpha 通道 | 仅 0 / 255 两级，无中间值 |
| 菜单栏 22pt 物理渲染 | M 字一眼可辨（远距阅读 ≥ 1m） |
| 深色菜单栏呈现 | 自动反色为白色，无手动配色 |
| 矢量缩放 | SVG 缩放到任意尺寸不糊（128px / touch bar 验证） |
| Electron 重启 | `setTemplateImage(true)` 标记保留 |

---

## 6. 风险与遗留

| 风险 | 缓解 |
|---|---|
| 用户拍板前文件命名混淆 | 当前 v2 文件保留 `-v2` 后缀，原文件名不动；定稿后 `mv` 覆盖 |
| 16px 下 M 字与系统 M 图标（Mail / Maps / Messages）撞名 | macOS 菜单栏布局会自动保持距离，撞名概率低；如用户有疑虑可改方案 C |
| Retina hint 缺失 | SVG 路径含小数坐标（1.0, 3.6, 5.6, 11.6），rsvg-convert / macOS 抗锯齿能给出平滑过渡；如出现粗糙可在 `@2x` 手动 hint |
| 颜色漂移风险 | SPEC § 1.4 提供验收脚本，构建期可强制 |

---

## 7. 待用户确认

1. **方案选型**：A（PRIMARY）/ B / C / D 任选其一
2. **是否覆盖原 `trayTemplate.png`**：是 / 否
3. **是否需要 `desktop/main.js` 改动**：仅在引用了非默认文件名时需要
4. **是否需要扩展 dark mode 之外的高亮态配色**：当前由 macOS 自动处理，如需自定义可以约定方向

---

## 附录 A · ardot 设计稿节点索引

| Node ID | 内容 | 用途 |
|---|---|---|
| 124:2 | Root Frame（含全部页面内容） | 整张画布 |
| 124:8 | 方案 A 主推卡 | 评审时优先看 |
| 124:9 | 方案 B 备选卡 | 同上 |
| 124:10 | 方案 C 备选卡 | 同上 |
| 124:11 | 方案 D 实验卡 | 同上 |
| 124:155 | Menu Bar 模拟（浅 + 深） | 验证反色效果 |
| 124:179 | BEFORE 对比卡 | 含 placeholder 当前图 |
| 124:214 | AFTER 推荐卡 | 展示 Bold M + 像素格 |
| 124:231 | SPEC 容器 | 规格说明区 |

## 附录 B · export SVG 文件清单（vector）

- `124_2-*.svg` 整张画布（1.4 MB，前端可不读）
- `124_8-*.svg` A 方案（65 KB，可读）
- `124_9-*.svg` B 方案（78 KB，可读）
- `124_10-*.svg` C 方案（73 KB，可读）
- `124_11-*.svg` D 方案（79 KB，可读）
- `124_155-*.svg` Menu Bar 模拟（55 KB，可读）
- `124_179-*.svg` BEFORE 对比（232 KB，可读）
- `124_214-*.svg` AFTER 对比（240 KB，可读）
- `124_231-*.svg` SPEC 区（271 KB，可读）

> 前端开发 agent 优先 read_file `export/124_8-*.svg`（方案 A）与 `export/trayTemplate-v2-source.svg`（设计 SVG 源）。SPEC.md 的 §1.2 SVG path 直接可作为生成代码的 source of truth。
