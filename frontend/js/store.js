/* ==========================================================================
   MyKnowledge — Alpine.js 全局状态管理
   设计系统: Raycast · v1.0
   ========================================================================== */

document.addEventListener("alpine:init", () => {
// 目录折叠状态：模块级闭包（不存 Alpine data——proxy set 触发 flush 会重建纯 JS 渲染的目录 DOM）
let _tocCollapsedSet = {};

  Alpine.store("app", {
    /* ── 视图状态 ──────────────────────────────────────────────────────── */

    /** 当前视图: dashboard | project | view | edit | new | status */
    currentView: "dashboard",

    /** 当前文档/项目路径 */
    currentPath: "",

    /** 面包屑片段 */
    breadcrumbs: [],

    /** 是否正在加载 */
    loading: true,

    /** 文档内容加载中（loadDocument 请求在途）：区分「加载中」与「空文档/错误」占位
     *  不并入全局 loading——loading 只用于首次 splash，SPA 内导航触发会误弹 splash */
    docPending: false,

    /** 错误信息 */
    error: null,

    /* ── 锁状态 ────────────────────────────────────────────────────────── */

    /** 是否被锁定 */
    isLocked: false,

    /** 垃圾箱 */
    trashItems: [],
    trashLoading: false,
    /** 垃圾箱条目总数（后端 total，用于「加载中…/全部加载完」提示） */
    trashTotal: 0,
    /** 是否还有更多（后端 has_more，控制滚动加载） */
    trashHasMore: false,
    /** 勾选待精准删除的条目 trash_path 集合（多选删除；只作用于已加载的 trashItems） */
    selectedTrash: [],

    /* ── 知识健康检查（#health） ──────────────────────────────────────── */

    /** 体检数据 { issues, summary }（无 saved/未检查时为空对象） */
    healthData: null,
    /** 体检加载中（首次 / 重新检查） */
    healthLoading: false,
    /** 上次检查时间（UTC ISO 字符串，取自 /api/diagnose/saved 的 generated_at） */
    healthGeneratedAt: "",

    /** 阶段 B：各组勾选项 { groupType: { path: true } } */
    healthSelected: {},
    /** 阶段 B：正在执行修复的分组 type（'' = 未执行；按钮显示「处理中...」防重复点击） */
    healthHealingGroup: "",
    /** 阶段 B：lazy 按钮复制中标记 */
    healthLazyCopying: false,

    /* ── 阶段二：就绪信号（顶部 status-indicator） ──────────────────────── */

    /** 就绪信号数据：{ saved, total_issues, has_high }（saved 表示上次检查是否有结果） */
    readiness: { saved: false, total_issues: 0, has_high: false },

    /* ── 阶段三：AI 客户端配置 + 引导向导 + 配置 modal ─────────────────── */

    /** AI 客户端配置检测状态：{ ClaudeCode: {mcp, hooks, agent}, CodeBuddyIDE: {...} }（bool） */
    clientConfig: null,
    /** 上次成功加载 client-config 的时间戳（refreshClientConfigIfStale 判定旧缓存用） */
    clientConfigAt: 0,
    /** 配置 modal 当前左侧分组：account | general | mcp | hooks | agent */
    settingsGroup: "account",
    /** 引导向导当前步骤：1 身份 | 2 AI 协作 | 3 完成 */
    guideStep: 1,
    /** 是否强制重进引导向导（rerunGuide 设置，绕过身份已配置的 setup 拦截） */
    guideForce: false,
    /** 正在写入的平台/kind（防重复点击）：{ platform, kind } | null */
    clientConfiguring: null,
    /** 配置失败的平台-kind 标记（行内 fallback 文本，5 秒自动消失）："claude-mcp" | null */
    clientFallback: null,
    /** 重新检测 client-config 的加载态（「⟳ 重新检测」按钮禁用 + spinner） */
    clientDetecting: false,

    /** 404 详情：文档被删除时 {deleted_at}（可在垃圾箱恢复） */
    deletedInfo: null,

    /** 锁信息 */
    lockInfo: null,

    /** AI MCP 连接状态: disconnected | reading | writing | connected */
    mcpStatus: "disconnected",

    /** 后端是否离线 */
    backendOffline: false,

    /** 系统三态状态（全局统一） */
    get systemStatus() {
      if (this.isLocked) return { dotClass: "status-dot--danger", label: "AI 编辑中" };
      if (this.currentView === "edit") return { dotClass: "status-dot--warning", label: "用户编辑中" };
      return this.mcpStatusInfo;
    },

    /** 锁状态 tooltip：谁在编辑 + 锁最长剩余（client 名首字母大写）；非锁定时空串 */
    get lockStatusTip() {
      if (!this.isLocked) return "";
      const agent = (this.lockInfo && this.lockInfo.agent) || "";
      const remain = this.lockRemaining;
      const who = agent ? agent.charAt(0).toUpperCase() + agent.slice(1) : "AI";
      const rest = remain != null ? `，预计最长剩余 ${remain} 分钟` : "";
      return `${who} 正在编辑知识中${rest}`;
    },

    /** 锁最长剩余分钟数（新后端 expires_ts = epoch 秒；旧后端仅有 expires_at 本地 ISO，兼容兜底） */
    get lockRemaining() {
      const info = this.lockInfo || {};
      let secs;
      if (info.expires_ts) {
        secs = info.expires_ts - Date.now() / 1000;
      } else if (info.expires_at) {
        secs = new Date(info.expires_at).getTime() / 1000 - Date.now() / 1000;
      } else {
        return null;
      }
      if (secs <= 0) return 0;
      return Math.ceil(secs / 60);
    },

    /** MCP 状态对应的颜色和文字 */
    get mcpStatusInfo() {
      const map = {
        disconnected: { dotClass: "status-dot--danger", label: "AI 未连接" },
        reading:      { dotClass: "status-dot--online", label: "AI 正在读取" },
        writing:      { dotClass: "status-dot--warning", label: "AI 正在写入" },
        connected:    { dotClass: "status-dot--online", label: "AI 已连接" },
      };
      return map[this.mcpStatus] || map.disconnected;
    },

    /* ── 主题 ──────────────────────────────────────────────────────────── */

    /** 当前主题: light | dark | system */
    theme: "system",

    /** 当前设计系统: raycast | intercom | warm-editorial | mistral | resend */
    designTheme: "raycast",

    /** 是否显示亮暗切换（仅 Raycast 有暗色） */
    get showColorMode() { return this.designTheme === "raycast"; },

    /* ── 用户身份 ──────────────────────────────────────────────────────── */

    /** 用户昵称 */
    nickname: "",

    /** 用户邮箱 */
    email: "",

    /** 身份是否已设置 */
    get identitySet() { return !!(this.nickname && this.email); },

    /* ── 文档数据 ──────────────────────────────────────────────────────── */

    /** 侧边栏项目列表 */
    projects: [],

    /** 当前项目下的文档列表（common-knowledge/） */
    projectDocs: [],

    /** 当前项目下的子项目列表（projects/） */
    projectSubprojects: [],

    /** 当前项目下的归档列表（archive/） */
    projectArchived: [],

    /** 当前项目元信息 */
    projectMeta: null,

    /** 当前文档内容 */
    document: null,

    /** 当前文档的引用 */
    refs: [],

    /** 当前文档的 HTML 内容 */
    htmlContent: "",

    /** 当前文档的元信息（作者头像等） */
    documentMeta: null,

    /** 侧边栏是否打开 */
    sidebarOpen: true,
    // 文档目录（TOC）
    tocItems: [],          // [{level, indent, text, hasChildren}]（indent 已按出现顺序缩进修正）
    // （目录折叠状态存模块级闭包 _tocCollapsedSet——避免 Alpine flush 重建纯 JS 目录 DOM）
    tocActiveIdx: -1,      // 当前可见标题索引（滚动跟随高亮）
    tocCollapsed: false,   // 目录区收起
    projectsCollapsed: localStorage.getItem("myknowledge-projects-collapsed") === "1", // 项目区收起
    // 项目展开树（快速索引）：path → 展开状态；树内容懒加载纯 DOM 渲染
    projectExpanded: {},
    projectTree: {},

    /* ── 编辑器状态 ────────────────────────────────────────────────────── */

    /** 编辑器是否已修改 */
    isDirty: false,

    /** 离线草稿横幅是否显示 */
    draftBanner: false,

    /** 离线草稿信息 { path, savedAt } */
    draftInfo: null,

    /** 编辑器自动保存计时器 */
    autoSaveTimer: null,

    /* ── 仪表盘数据 ────────────────────────────────────────────────────── */

    /** 状态摘要 */
    statusSummary: null,

    /** 公共知识区文档列表 */
    commonKnowledge: [],

    /** 仪表盘项目列表（projects/ 目录） */
    dashboardProjects: [],

    /** 归档列表 */
    archived: [],

    /** 最近更新列表 */
    recentUpdates: [],

    /** 系统版本号 */
    systemVersion: "",
    /** 知识库 git commit hash */
    kbVersion: "",

    /* ── 弹窗状态 ──────────────────────────────────────────────────────── */

    /** 弹窗类型: null | 'delete-doc' | 'rename-doc' | 'new-doc' | 'rename-project' | 'share-export' */
    modal: null,

    /** 分享导出：项目列表 */
    shareProjects: [],

    /** 弹窗携带的数据 */
    modalData: null,

    /* ── Ref 浮层 ──────────────────────────────────────────────────────── */

    /** 浮层可见性 */
    popoverVisible: false,

    /** 浮层位置 { top, left } */
    popoverPos: { top: 0, left: 0 },

    /** 浮层中的引用路径 */
    popoverRefPath: "",

    /* ── 方法 ──────────────────────────────────────────────────────────── */

    /**
     * 设置当前视图
     * @param {string} view
     * @param {string} path
     */
    setView(view, path = "") {
      this.currentView = view;
      this.currentPath = path;
      this.error = null;

      if (path) {
        this.breadcrumbs = pathToBreadcrumbs(path);
      } else {
        this.breadcrumbs = [];
      }
      // 路由变化 → 刷新树内高亮（文档行/子项目行当前项）
      if (typeof this._refreshTreeHighlight === "function") this._refreshTreeHighlight();
      // 路由变化 → 自动展开到当前项所在层级（从 doc-card / 外部链接进入时）
      if (typeof this._autoExpandForCurrentPath === "function") this._autoExpandForCurrentPath();
    },

    /**
     * 加载侧边栏项目列表
     */
    /** 从 ProseMirror DOM 提取标题 → 目录（缩进修正：按标题级别首次出现顺序分配缩进级） */
    updateToc() {
      const pm = document.querySelector(".ProseMirror");
      const headings = pm ? pm.querySelectorAll("h1,h2,h3,h4,h5,h6,h7,h8,h9") : [];
      const levelMap = new Map();
      let counter = 0;
      const raw = Array.from(headings).map(h => {
        const level = parseInt(h.tagName.charAt(1), 10);
        if (!levelMap.has(level)) levelMap.set(level, counter++);
        return { level, indent: levelMap.get(level), text: h.textContent.trim() || "（空标题）" };
      });
      this.tocItems = raw.map((it, i) => ({
        ...it,
        hasChildren: i + 1 < raw.length && raw[i + 1].level > it.level,
      }));
      if (this.tocActiveIdx >= this.tocItems.length) this.tocActiveIdx = -1;
      if (this.tocItems.length === 0) this.tocActiveIdx = -1;
      this._renderTocList();
    },

    /** 纯 JS 渲染目录列表（x-for 重建会覆盖折叠 DOM——与项目树同方案） */
    _renderTocList() {
      const list = document.getElementById("sidebar-toc-list");
      if (!list) return;
      const items = this.tocItems;
      if (!items.length) {
        list.innerHTML = '<div class="sidebar-toc__empty">本文档无标题</div>';
        return;
      }
      list.innerHTML = items.map((it, idx) => {
        const cls = [
          "sidebar-toc__item",
          idx === this.tocActiveIdx ? "sidebar-toc__item--active" : "",
          it.indent === 0 ? "sidebar-toc__item--top" : "",
        ].filter(Boolean).join(" ");
        return (
          '<div class="' + cls + '" data-toc-idx="' + idx + '" title="' + escapeHtml(it.text) + '"' +
          ' style="padding-left:' + (it.indent * 16 + 10) + 'px">' +  // base 10px：目录 icon 与项目清单表层项目对齐
          '<button class="sidebar-toc__chev-btn" data-toc-toggle="' + idx + '"' +
          ' style="visibility:' + (it.hasChildren ? "visible" : "hidden") + '"' +
          ' title="' + (it.hasChildren ? "展开/收起子标题" : "") + '">' +
          '<svg class="sidebar-toc__chevron' + (_tocCollapsedSet[idx] ? "" : " is-open") + '"' +
          ' viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor"' +
          ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 4 10 8 6 12"/></svg>' +
          "</button>" +
          // 仅文档标题（第一项）用文件 icon——子标题是章节，不加 icon
          (idx === 0
            ? '<svg class="sidebar-toc__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"' +
              ' stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
              '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>' +
              '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>'
            : "") +
          '<span class="sidebar-toc__item-text" data-toc-jump="' + idx + '">' + escapeHtml(it.text) + "</span>" +
          "</div>"
        );
      }).join("");
      list.querySelectorAll("[data-toc-jump]").forEach(el => {
        el.addEventListener("click", () => this.tocJump(Number(el.dataset.tocJump)));
      });
      list.querySelectorAll("[data-toc-toggle]").forEach(el => {
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          this.toggleTocCollapse(Number(el.dataset.tocToggle));
        });
      });
      // 应用已收起的折叠状态（编辑刷新重建后恢复）
      this._applyTocCollapsed();
    },

    /** 应用 tocCollapsedSet：隐藏所有收起标题的子树（DOM 稳定——纯 JS 渲染） */
    _applyTocCollapsed() {
      const itemEls = Array.from(document.querySelectorAll("#sidebar-toc-list .sidebar-toc__item"));
      Object.keys(_tocCollapsedSet).forEach(k => {
        const j = Number(k);
        if (!_tocCollapsedSet[j]) return;
        const jlvl = this.tocItems[j].level;
        for (let i = j + 1; i < this.tocItems.length && this.tocItems[i].level > jlvl; i++) {
          const el = itemEls[i];
          if (el) el.style.display = "none";
        }
      });
    },

    /** 更新目录项 active 高亮 class */
    _updateTocActiveClass(idx) {
      document.querySelectorAll("#sidebar-toc-list .sidebar-toc__item").forEach(el => {
        el.classList.toggle("sidebar-toc__item--active", Number(el.dataset.tocIdx) === idx);
      });
    },

    /** 点击目录项 → 滚动到对应标题（+ 立即高亮） */
    tocJump(idx) {
      const pm = document.querySelector(".ProseMirror");
      if (!pm) return;
      const headings = pm.querySelectorAll("h1,h2,h3,h4,h5,h6,h7,h8,h9");
      const el = headings[idx];
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      this.tocActiveIdx = idx;
      this._updateTocActiveClass(idx);
    },
    /** 项目区展开/收起（localStorage 持久化） */
    toggleProjects() {
      this.projectsCollapsed = !this.projectsCollapsed;
      localStorage.setItem("myknowledge-projects-collapsed", this.projectsCollapsed ? "1" : "0");
    },

    /** 目录项是否被某收起的祖先覆盖（隐藏） */
    isTocHidden(idx) {
      const items = this.tocItems;
      if (!items || idx >= items.length) return false;
      let cur = items[idx].level;
      for (let j = idx - 1; j >= 0; j--) {
        if (items[j].level >= cur) continue;        // 不是祖先
        if (this.tocCollapsedSet[j]) return true;   // 祖先收起 → 隐藏
        cur = items[j].level;                       // 上溯到更浅层级继续找
      }
      return false;
    },

    /** 切换某标题子级的展开/收起（纯 DOM 操作——x-for 内 x-show 响应式不可靠，与项目树同方案） */
    toggleTocCollapse(idx) {
      const items = this.tocItems;
      if (!items || idx >= items.length) return;
      const lvl = items[idx].level;
      const itemEls = Array.from(document.querySelectorAll(".sidebar-toc__item"));
      // 直接子树范围：idx+1 起，到第一个 level <= lvl 为止
      const subs = [];
      for (let i = idx + 1; i < items.length && items[i].level > lvl; i++) subs.push(i);
      if (!subs.length) return;
      const cur = !!_tocCollapsedSet[idx];
      _tocCollapsedSet = { ..._tocCollapsedSet, [idx]: !cur };
      const nowCollapsed = !cur;
      // chevron 旋转状态
      const chev = itemEls[idx] && itemEls[idx].querySelector(".sidebar-toc__chevron");
      if (chev) chev.classList.toggle("is-open", !nowCollapsed);
      if (nowCollapsed) {
        subs.forEach(si => { const el = itemEls[si]; if (el) el.style.display = "none"; });
      } else {
        // 展开：先恢复子树显示，再重新应用子树内仍收起的标题
        subs.forEach(si => { const el = itemEls[si]; if (el) el.style.display = ""; });
        Object.keys(_tocCollapsedSet).forEach(k => {
          const j = Number(k);
          if (j <= idx || !_tocCollapsedSet[j]) return;
          const jlvl = items[j].level;
          for (let i = j + 1; i < items.length && items[i].level > jlvl; i++) {
            const el = itemEls[i];
            if (el) el.style.display = "none";
          }
        });
      }
    },

    /** 重置目录折叠（进入文档时全部展开；x-for 重建时 DOM 自然全显示） */
    resetTocCollapse() {
      _tocCollapsedSet = {};
    },

    tocJump(idx) {
      const pm = document.querySelector(".ProseMirror");
      if (!pm) return;
      const headings = pm.querySelectorAll("h1,h2,h3,h4,h5,h6,h7,h8,h9");
      const el = headings[idx];
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      this.tocActiveIdx = idx;
    },

    /** 绑定滚动跟随（IntersectionObserver 高亮当前可见标题）；切换文档前调用 _disposeTocScroll 解绑 */
    _bindTocScroll() {
      this._disposeTocScroll();
      const pm = document.querySelector(".ProseMirror");
      if (!pm) return;
      const headings = pm.querySelectorAll("h1,h2,h3,h4,h5,h6,h7,h8,h9");
      if (!headings.length) return;
      // root=null（视口）：文档滚动在 window/body（.editor-content 内容撑开不滚动）
      const self = this;
      this._tocIO = new IntersectionObserver(entries => {
        const visible = entries
          .filter(e => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length) {
          const idx = Array.from(headings).indexOf(visible[0].target);
          if (idx >= 0) {
            self.tocActiveIdx = idx;
            self._updateTocActiveClass(idx);
          }
        }
      }, { root: null, rootMargin: "0px 0px -5% 0px" });
      headings.forEach(h => this._tocIO.observe(h));
    },
    _disposeTocScroll() {
      if (this._tocIO) { this._tocIO.disconnect(); this._tocIO = null; }
    },

    /** sidebar 区块顺序（目录区 vs 项目区）——localStorage 持久化 + 拖动交换 */
    _initSidebarOrder() {
      const toc = document.getElementById("sidebar-toc-section");
      const proj = document.getElementById("sidebar-project-section");
      if (!toc || !proj) return;
      // 目录区在项目区上方（拖动交换结果）
      if (localStorage.getItem("myknowledge-toc-above") === "1") {
        proj.before(toc);
      }
    },
    _bindSidebarDrag() {
      const toc = document.getElementById("sidebar-toc-section");
      const proj = document.getElementById("sidebar-project-section");
      const handle = toc && toc.querySelector(".sidebar-toc__drag");
      if (!toc || !proj || !handle || handle.dataset._dragBound) return;
      handle.dataset._dragBound = "1";
      handle.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("text/plain", "toc");
        e.dataTransfer.effectAllowed = "move";
        toc.classList.add("sidebar-toc--dragging");
      });
      handle.addEventListener("dragend", () => {
        toc.classList.remove("sidebar-toc--dragging");
        proj.classList.remove("sidebar-toc__drop-target");
      });
      proj.addEventListener("dragover", (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        proj.classList.add("sidebar-toc__drop-target");
      });
      proj.addEventListener("dragleave", () => proj.classList.remove("sidebar-toc__drop-target"));
      proj.addEventListener("drop", (e) => {
        e.preventDefault();
        proj.classList.remove("sidebar-toc__drop-target");
        // 交换（双向 toggle）：目录已在项目上方 → 移回下方；否则移到上方
        const tocAbove = (proj.compareDocumentPosition(toc) & Node.DOCUMENT_POSITION_PRECEDING) !== 0;
        if (tocAbove) {
          proj.after(toc);
          localStorage.setItem("myknowledge-toc-above", "0");
          showToast("目录已移回项目下方", "success", 1200);
        } else {
          proj.before(toc);
          localStorage.setItem("myknowledge-toc-above", "1");
          showToast("目录已移到项目上方", "success", 1200);
        }
      });
    },

    /** 项目是否展开 */
    isProjectExpanded(path) { return !!(path && this.projectExpanded[path]); },

    /** 顶层项目是否处于其项目页（淡背景 + 主题色加粗） */
    isProjectActive(path) {
      return this.currentView === "project" && this.currentPath === path;
    },

    /** 树结构直接父级：去掉末尾分类段（/common-knowledge/文件、/projects/子项目、/archive/子项目） */
    _treeParentPath(path) {
      if (!path) return "";
      return path.replace(/(\/common-knowledge\/|\/projects\/|\/archive\/)[^/]+$/, "");
    },

    /** 顶层项目是否处于其项目页（当前项：文本高亮 + 背景） */
    isProjectActive(path) {
      return this.currentView === "project" && this.currentPath === path;
    },

    /** 顶层项目是否为当前路径的树结构直接父级（仅文本高亮，无背景） */
    isProjectParentActive(path) {
      return this._treeParentPath(this.currentPath) === path;
    },

    /** 自动展开 sidebar 树到当前路径所在层级（含项目区收起时）；异步逐级懒加载 */
    async _autoExpandForCurrentPath() {
      const path = this.currentPath;
      if (!path || !path.startsWith("projects/")) return;
      // 提取祖先链：顶层项目 + 各级子项目（按 /projects/ 段）
      const parts = path.split("/");
      const chain = [];
      for (let i = 0; i < parts.length; i++) {
        if (parts[i] === "projects" && i + 1 < parts.length) {
          chain.push(parts.slice(0, i + 2).join("/"));
        }
      }
      if (!chain.length) return;
      // 项目区整体收起 → 自动展开
      if (this.projectsCollapsed) {
        this.projectsCollapsed = false;
        try { localStorage.setItem("myknowledge-projects-collapsed", "0"); } catch (_) {}
      }
      // 逐级展开（当前项是项目页本身时，最后一级不展开）
      for (let idx = 0; idx < chain.length; idx++) {
        const p = chain[idx];
        const isLast = idx === chain.length - 1;
        if (isLast && p === path && this.currentView === "project") break; // 项目页本身
        if (!this.projectExpanded[p]) {
          await this.toggleProjectExpand(p);
        }
      }
      // 展开完成后刷新高亮（当前项 + 直接父级）
      this._refreshTreeHighlight();
    },

    /** 刷新树内高亮：当前项（text+bg）与直接父级（仅文本） */
    _refreshTreeHighlight() {
      const parent = this._treeParentPath(this.currentPath);
      document.querySelectorAll(".sidebar-tree__item").forEach(el => {
        const docPath = el.dataset.docPath;
        const subPath = el.dataset.subPath;
        if (docPath) {
          const active = this.currentView !== "project" && this.currentPath === docPath;
          const isParent = parent === docPath;
          el.classList.toggle("sidebar-tree__item--active", active);
          el.classList.toggle("sidebar-tree__item--parent", isParent && !active);
          el.classList.remove("sidebar-tree__item--active-project");
        } else if (subPath) {
          const active = this.currentView === "project" && this.currentPath === subPath;
          const isParent = parent === subPath;
          el.classList.toggle("sidebar-tree__item--active-project", active);
          el.classList.toggle("sidebar-tree__item--parent", isParent && !active);
          el.classList.remove("sidebar-tree__item--active");
        }
      });
    },

    /** 展开/收起项目（懒加载 + 纯 DOM 渲染子结构） */
    async toggleProjectExpand(path) {
      if (!path) return;
      const chevIcon = this._chevronIcon(path);
      if (this.projectExpanded[path]) {
        this.projectExpanded[path] = false;
        this._persistProjectExpanded();
        if (chevIcon) chevIcon.classList.remove("is-open"); // 旋转动画（收起）
        const container = this._treeContainer(path);
        if (container) container.innerHTML = "";
        return;
      }
      this.projectExpanded[path] = true;
      this._persistProjectExpanded();
      if (chevIcon) chevIcon.classList.add("is-open"); // 旋转动画（展开）
      const container = this._treeContainer(path);
      if (!container) return;
      container.innerHTML = '<div class="sidebar-tree__loading">加载中…</div>';
      try {
        this.projectTree[path] = await this._loadProjectTree(path);
        this._renderProjectTree(container, path);
      } catch (e) {
        container.innerHTML = '<div class="sidebar-tree__error">加载失败</div>';
      }
    },

    /** 懒加载项目结构：知识文档 + 子项目 + 归档项目（归档下只有归档项目，无文档归档） */
    async _loadProjectTree(path) {
      const [docs, subs, arch] = await Promise.all([
        api.list(path + "/common-knowledge").catch(() => ({ items: [] })),
        api.list(path + "/projects").catch(() => ({ items: [] })),
        api.list(path + "/archive").catch(() => ({ items: [] })),
      ]);
      const noReadme = (i) => !/^readme\.md$/i.test(i.name || "");
      return {
        docs: (docs.items || []).filter(i => !i.is_dir && noReadme(i)),
        subs: (subs.items || []).filter(i => i.is_dir),
        archived: (arch.items || []).filter(i => i.is_dir), // 归档项目
      };
    },

    /** 重载并重渲染某顶层项目的侧栏树（重命名/删除/新建文档后调用）。
     *  树未展开或无缓存时静默跳过——下次展开自然加载新数据。
     *  重渲染会重建高亮（_renderProjectTree 按 currentPath 计算 active），无需额外处理。 */
    async refreshProjectTree(projectPath) {
      if (!projectPath) return;
      const container = this._treeContainer(projectPath);
      if (!container || !this.projectTree[projectPath]) return;
      try {
        this.projectTree[projectPath] = await this._loadProjectTree(projectPath);
        this._renderProjectTree(container, projectPath);
        this._refreshTreeHighlight();
      } catch (_) { /* 静默：下次展开自动重载 */ }
    },

    _treeContainer(path) {
      return document.querySelector('[data-tree-path="' + CSS.escape(path) + '"]');
    },

    /** 树内子项目 chevron 的 svg（用于开合旋转动画） */
    _chevronIcon(path) {
      const btn = document.querySelector('[data-expand-path="' + CSS.escape(path) + '"]');
      return btn ? btn.querySelector("svg") : null;
    },

    /** 渲染项目树（纯 DOM，递归嵌套；图标区分：文档 / 文件夹 / 归档箱） */
    _renderProjectTree(container, path) {
      const tree = this.projectTree[path];
      if (!tree) return;
      const groups = [];
      if (tree.docs.length) {
        groups.push(
          '<div class="sidebar-tree__group">' +
          tree.docs.map(d => this._treeRow(d.path, d.name, "doc")).join("") +
          "</div>"
        );
      }
      if (tree.subs.length) {
        groups.push(
          '<div class="sidebar-tree__group">' +
          tree.subs.map(s => this._treeRow(s.path, s.name, "folder")).join("") +
          "</div>"
        );
      }
      if (tree.archived.length) {
        groups.push(
          '<div class="sidebar-tree__group">' +
          tree.archived.map(a => this._treeRow(a.path, a.name, "archive")).join("") +
          "</div>"
        );
      }
      container.innerHTML = groups.join("") || '<div class="sidebar-tree__empty">（无内容）</div>';

      const self = this;
      container.querySelectorAll("[data-doc-path]").forEach(el => {
        el.addEventListener("click", () => {
          window.location.hash = "doc/" + encodeURIComponent(el.dataset.docPath);
        });
      });
      container.querySelectorAll("[data-expand-path]").forEach(el => {
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          self.toggleProjectExpand(el.dataset.expandPath);
        });
      });
      container.querySelectorAll("[data-project-path]").forEach(el => {
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          window.location.hash = "project/" + encodeURIComponent(el.dataset.projectPath);
        });
      });
      // 已展开的子项目/归档项目：恢复其子树
      container.querySelectorAll("[data-sub-path]").forEach(el => {
        const sub = el.dataset.subPath;
        if (self.projectExpanded[sub]) {
          const subContainer = el.parentElement.querySelector('[data-tree-path="' + CSS.escape(sub) + '"]');
          if (subContainer && self.projectTree[sub]) {
            self._renderProjectTree(subContainer, sub);
          } else if (subContainer) {
            self.toggleProjectExpand(sub);
          }
        }
      });
    },

    /** 树行 HTML：文档/文件夹/归档项目（图标区分） */
    _treeRow(path, name, kind) {
      const icon =
        kind === "doc"
          ? '<svg class="sidebar-tree__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>'
          : kind === "archive"
            ? '<svg class="sidebar-tree__icon sidebar-tree__icon--archive" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>'
            : '<svg class="sidebar-tree__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>';
      if (kind === "doc") {
        // 文档名去 .md 后缀（列表不显示后缀）；当前项 text+bg，直接父级仅文本
        const showName = String(name).replace(/\.md$/i, "");
        const activeCls = this.currentView !== "project" && this.currentPath === path
          ? " sidebar-tree__item--active" : "";
        const parentCls = !activeCls && this._treeParentPath(this.currentPath) === path
          ? " sidebar-tree__item--parent" : "";
        return (
          '<div class="sidebar-tree__item' + activeCls + parentCls + '" data-doc-path="' + escapeHtml(path) + '">' +
          icon +
          '<span class="sidebar-tree__name" title="' + escapeHtml(path) + '">' + escapeHtml(showName) + "</span></div>"
        );
      }
      const archCls = kind === "archive" ? " sidebar-tree__item--archive" : "";
      // 子项目 chevron：与顶层项目一致的开合旋转动画（is-open → rotate 90°）
      const openCls = this.isProjectExpanded(path) ? " is-open" : "";
      // 子项目/归档项目：在项目页时淡背景 + 主题色加粗；作为当前项父级时仅文本高亮
      const projActiveCls = this.currentView === "project" && this.currentPath === path
        ? " sidebar-tree__item--active-project" : "";
      const projParentCls = !projActiveCls && this._treeParentPath(this.currentPath) === path
        ? " sidebar-tree__item--parent" : "";
      return (
        '<div class="sidebar-tree__item' + archCls + projActiveCls + projParentCls + '" data-sub-path="' + escapeHtml(path) + '">' +
        '<button class="sidebar-tree__chevron" data-expand-path="' + escapeHtml(path) + '" title="展开">' +
        '<svg class="sidebar-tree__chevron-icon' + openCls + '" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 4 10 8 6 12"/></svg>' +
        "</button>" +
        icon +
        '<span class="sidebar-tree__name" data-project-path="' + escapeHtml(path) + '" title="' + escapeHtml(path) + '">' + escapeHtml(name) + "</span></div>" +
        '<div class="sidebar-project__tree sidebar-project__tree--sub" data-tree-path="' + escapeHtml(path) + '"></div>'
      );
    },

    /** 展开状态持久化（localStorage JSON 数组） */
    _persistProjectExpanded() {
      const arr = Object.keys(this.projectExpanded).filter(k => this.projectExpanded[k]);
      try { localStorage.setItem("myknowledge-project-expanded", JSON.stringify(arr)); } catch (_) {}
    },

    /** 恢复上次展开的项目（loadProjects 后调用） */
    _restoreProjectExpanded() {
      let arr = [];
      try { arr = JSON.parse(localStorage.getItem("myknowledge-project-expanded") || "[]") || []; } catch (_) {}
      arr.forEach(path => { if (this.projectExpanded[path] !== true) this.toggleProjectExpand(path); });
    },

    async loadProjects() {
      try {
        const data = await api.list("projects");
        // 只保留项目目录（排除文件，如 projects/readme.md 总览文档）
        this.projects = data && data.items
          ? data.items.filter(i => i.is_dir && !/^readme\.md$/i.test(i.name || ""))
          : [];
        // 恢复上次展开的项目（懒加载子树）
        setTimeout(() => this._restoreProjectExpanded(), 50);
      } catch (err) {
        console.error("加载项目列表失败:", err);
      }
    },

    /**
     * 加载项目下的文档列表（按嵌套架构分三个子目录）
     * @param {string} projectPath
     */
    async loadProjectDocuments(projectPath) {
      this.error = null;
      try {
        const [docData, subData, archData, projectData] = await Promise.all([
          api.list(projectPath + "/common-knowledge").catch(() => ({ items: [] })),
          api.list(projectPath + "/projects").catch(() => ({ items: [] })),
          api.list(projectPath + "/archive").catch(() => ({ items: [] })),
          api.getProject(projectPath).catch(() => null),
        ]);
        const excludeReadme = (i) => !/^readme\.md$/i.test(i.name || "");
        this.projectDocs = (docData.items || []).filter(i => !i.is_dir && excludeReadme(i));
        this.projectSubprojects = (subData.items || []).filter(i => i.is_dir);
        this.projectArchived = (archData.items || []).filter(i => excludeReadme(i));
        this.projectMeta = projectData || {};
        // 知识卡片预览缓存失效（项目视图文档网格）：编辑保存返回后 hover 重新加载
        Alpine.nextTick(() => this.invalidateDocPreviewCache());
      } catch (err) {
        this.error = err.message || "加载项目数据失败";
        this.projectDocs = [];
        this.projectSubprojects = [];
        this.projectArchived = [];
        this.projectMeta = {};
        // 项目 404 区分：曾存在后被删除（可恢复）vs 从未存在
        const dd = err && err.detail && err.detail.detail;
        this.deletedInfo =
          err && err.status === 404 && err.message === "deleted"
            ? { deleted_at: (dd && dd.deleted_at) || "" }
            : null;
      }
    },

    /**
     * 加载文档内容和引用
     * @param {string} path
     */
    async loadDocument(path) {
      if (!path) return; // 路径为空（如导航中）直接跳过，避免 500
      // 防重：同一文档并发加载去重（router 导航与 doc 组件 init 兜底会双触发，
      // 前者在途时 document 仍为空 → 兜底条件成立 → 一次导航发 2 轮完整请求）
      if (this._loadingDocPath === path) return;
      this._loadingDocPath = path;
      this.docPending = true;
      this.error = null;
      try {
        // 双 API：getDocument 取纯净内容+meta，getDocumentWithRefs 只取 refs
        const [data, refsData] = await Promise.all([
          api.getDocument(path),
          api.getDocumentWithRefs(path).catch(() => ({ refs: [] })),
        ]);

        this.document = {
          ...data,
          meta: data.meta || {},
          // 将 meta 字段拍平到顶层，方便模板直接读取
          ...(data.meta || {}),
          summary: (data.meta && data.meta.summary) || "",
          // 字段名统一：后端 meta 返回 created/updated，模板用 created_at/updated_at
          created_at: (data.meta && data.meta.created) || "",
          updated_at: (data.meta && data.meta.updated) || "",
          // 最后编辑人
          maintainer: (data.meta && data.meta.maintainer) || "",
          // 内容指纹（乐观锁：保存时带回给后端比对，后端提供后生效）
          version: data.version || "",
        };
        this.htmlContent = data.html || (data.content ? marked.parse(
          // 编码 ref: URL 中的空格，防止 marked 截断
          data.content.replace(/\(ref:([^)]+)\)/g, (m, url) => "(ref:" + url.replace(/ /g, "%20") + ")")
        ) : "");
        this.refs = refsData.refs || [];
        // 显式内容同步钩子：doc 组件监听此事件执行 setContent（Alpine.effect 对
        // store.htmlContent 的追踪不可靠——编辑态切文档时可能不重跑 → 新文档显示旧内容）
        document.dispatchEvent(new CustomEvent("myk-doc-html", { detail: this.htmlContent }));

        // 并行加载元信息（不阻塞主内容渲染）
        this.loadDocumentMeta(path).catch(() => {});
        // 检查是否有未同步的离线草稿（不阻塞加载）
        this.checkDraftBanner().catch(() => {});
      } catch (err) {
        const dd = err && err.detail && err.detail.detail;
        // rename 旧路径 404 → 自动跳转新路径（S15，优先于 deleted 处理）。
        // 契约（后端 88183ee）：404 + {"detail":{"detail":"renamed","redirect_to":"<新路径>"}}。
        // location.replace 不污染历史栈：用户 back 不会再次回到旧路径（防死循环）。
        if (err && err.status === 404 && err.message === "renamed" && dd && dd.redirect_to) {
          if (this._loadingDocPath === path) this._loadingDocPath = null; // 防重标记先清
          location.replace("#doc/" + String(dd.redirect_to).replace(/\//g, "%2F"));
          return;
        }
        this.error =
          err && err.status === 404 && err.message !== "deleted"
            ? "文档不存在或无法加载" // 真 404：友好文案（deleted 语义走下方 deletedInfo 分支）
            : (err.message || "加载文档失败");
        this.document = null;
        this.htmlContent = "";
        this.refs = [];
        this.documentMeta = null;
        // 404 区分：文档曾存在后被删除（可恢复）vs 从未存在
        // err.message 已由 apiRequest 解嵌套（"deleted"）；deleted_at 在 err.detail.detail 里
        this.deletedInfo =
          err && err.status === 404 && err.message === "deleted"
            ? { deleted_at: (dd && dd.deleted_at) || "" }
            : null;
      } finally {
        // 仅当没有更新请求覆盖时才清除标记（快速连续切文档：A 在途时切 B → 标记是 B）
        if (this._loadingDocPath === path) this._loadingDocPath = null;
        this.docPending = false;
      }
    },

    /**
     * 加载文档元信息（作者头像等）
     * @param {string} path
     */
    async loadDocumentMeta(path) {
      try {
        const meta = await api.getDocumentMeta(path);
        this.documentMeta = meta;
      } catch {
        this.documentMeta = null;
      }
    },

    /** 切换侧边栏 */
    toggleSidebar() {
      this.sidebarOpen = !this.sidebarOpen;
      localStorage.setItem("myknowledge-sidebar-collapsed", this.sidebarOpen ? "0" : "1");
    },

    /**
     * 保存文档
     * @param {string} path
     * @param {object} body
     */
    async saveDocument(path, body) {
      try {
        const data = await api.updateDocument(path, body);
        // 仅当仍停留在保存的文档时合并（编辑态切文档竞态：保存旧文档的响应返回时
        // document 已切换成新文档——无条件合并会把旧文档 content/version 污染进新文档）
        if (this.currentPath === path) {
          // 后端 PUT 返回不含 summary（只有 status/id/unchanged/version）→ 用 body.summary 补上，
          // 否则原地保存（不切走）后 document.summary 保持旧值 → view 态摘要显示回滚
          this.document = {
            ...this.document,
            ...data,
            summary: body.summary || this.document?.summary || "",
          };
          this.isDirty = false;
        }
        // 记录本端保存（SSE 2s 轮询会推送"文档已更新"→ 前端借此跳过对本端刚保存文档的重载）
        this._localSavedPath = path;
        this._localSavedAt = Date.now();
        if (!data.unchanged) showToast("文档已保存", "success");
        return data;
      } catch (err) {
        // 409 乐观锁冲突：不弹 toast，交由调用方弹 diff 冲突弹窗处理
        if (err.status === 409) throw err;
        if (err.isLocked) {
          showToast("知识库正在整理中，暂时只读", "warning");
        } else {
          showToast(err.message || "保存失败", "error");
        }
        throw err;
      }
    },

    /**
     * 静默保存（自动保存用）：不弹 toast，失败直接抛给调用方处理
     * @param {string} path
     * @param {object} body
     */
    async saveDocumentSilent(path, body) {
      const data = await api.updateDocument(path, body);
      // 仅当仍停留在保存的文档时合并（编辑态切文档竞态：保存旧文档的响应返回时
      // document 已切换成新文档——合并会把旧文档 content 污染进新文档）
      if (this.currentPath === path) {
        // 后端 PUT 返回不含 summary → 用 body.summary 补上（防原地保存后摘要显示回滚）
        this.document = {
          ...this.document,
          ...data,
          summary: body.summary || this.document?.summary || "",
        };
      }
      this.isDirty = false;
      // 记录本端保存（SSE 2s 轮询会推送"文档已更新"→ 前端借此跳过对本端刚保存文档的重载）
      this._localSavedPath = path;
      this._localSavedAt = Date.now();
      return data;
    },

    /** 打开文档后检查：是否有未同步的离线草稿（fire-and-forget） */
    async checkDraftBanner() {
      const path = this.currentPath;
      if (!path) return;
      try {
        const draft = await _draftGet(path);
        if (!draft) return;
        // 草稿内容与后端已同步（内容一致）→ 自动清理，不打扰
        if (draft.content && this.document && draft.content === this.document.content) {
          await _draftDelete(path);
          return;
        }
        this.draftInfo = { path, savedAt: draft.savedAt || "" };
        this.draftBanner = true;
      } catch (e) { /* IndexedDB 不可用则忽略 */ }
    },

    /** 横幅「立即同步」→ 草稿写回后端，成功删除 */
    async syncDraft() {
      const path = this.currentPath;
      try {
        const draft = await _draftGet(path);
        if (!draft) { this.draftBanner = false; return; }
        await this.saveDocumentSilent(path, {
          content: draft.content,
          summary: draft.summary || this.document?.summary || "",
        });
        await _draftDelete(path);
        this.draftBanner = false;
        this.draftInfo = null;
        showToast("离线草稿已同步", "success");
      } catch (e) {
        showToast("同步失败，请稍后重试", "error");
      }
    },

    /** 横幅「忽略」→ 仅隐藏，不删草稿 */
    dismissDraft() {
      this.draftBanner = false;
      this.draftInfo = null;
    },

    /** 横幅「放弃草稿」→ 删除本地草稿并隐藏（内容以线上为准） */
    async discardDraft() {
      const path = this.currentPath;
      try { await _draftDelete(path); } catch (e) { /* 忽略 */ }
      this.draftBanner = false;
      this.draftInfo = null;
    },

    /**
     * 检查锁状态
     */
    async checkLock() {
      try {
        const data = await api.getLock();
        this.isLocked = !!(data && data.locked);
        this.lockInfo = data;
      } catch {
        // 锁状态获取失败不阻塞操作
      }
      // 锁定时加快轮询（剩余时间更跟手、解锁后更快恢复可编辑）；非锁定时低频
      this._startLockPolling();
    },

    /** 启动锁轮询（按 isLocked 动态调整间隔，防重复定时器） */
    _startLockPolling() {
      if (this._lockTimer) clearInterval(this._lockTimer);
      const interval = this.isLocked ? 5000 : 15000;
      this._lockTimer = setInterval(() => this.checkLock(), interval);
    },

    /** 检查 AI MCP 连接状态 */
    async checkMcpStatus() {
      try {
        const data = await api.getMcpStatus();
        this.mcpStatus = (data && data.status) || "disconnected";
      } catch {
        this.mcpStatus = "disconnected";
      }
    },

    /**
     * 加载仪表盘数据
     */
    async loadDashboard() {
      this.error = null;
      try {
        const [knowledgeRes, projectsRes, archiveRes, statusData] = await Promise.all([
          api.list("common-knowledge").catch(() => ({ items: [] })),
          api.list("projects").catch(() => ({ items: [] })),
          api.list("archive").catch(() => ({ items: [] })),
          api.getStatus().catch(() => null),
        ]);

        this.commonKnowledge = (knowledgeRes && knowledgeRes.items || [])
          .filter(item => !item.is_dir);

        this.dashboardProjects = projectsRes && projectsRes.items || [];
        this.archived = archiveRes && archiveRes.items || [];
        this.statusSummary = statusData;
        this.recentUpdates = (statusData && statusData.recent) || [];

        // 存缓存：下次刷新秒出
        try {
          localStorage.setItem("myk-dash", JSON.stringify({
            c: this.commonKnowledge, p: this.dashboardProjects,
            a: this.archived, s: this.statusSummary, r: this.recentUpdates,
            ts: Date.now()
          }));
        } catch(e) {}
        // 知识卡片预览缓存失效：进入文档编辑保存后返回主页，hover 预览需重新加载
        Alpine.nextTick(() => this.invalidateDocPreviewCache());
      } catch (err) {
        this.error = err.message || "加载仪表盘失败";
      }
    },

    /** 知识卡片 hover 预览缓存失效：列表重新加载后文档可能已更新，下次 hover 重新拉取 */
    invalidateDocPreviewCache() {
      document.querySelectorAll(".doc-card__preview").forEach((el) => { el.dataset.loaded = ""; });
    },

    /**
     * 初始化应用
     */
    async init() {
      // 幂等守卫：Alpine 会（部分版本）对 store 的 init 方法自动调用一次，
      // 而 index.html 的 x-init 又显式调用一次 → 双 hashchange 监听 + 双 SSE 订阅
      // → 一次导航/保存触发两轮文档加载（重复加载高频 bug 的根因之一）
      if (this._inited) return;
      this._inited = true;
      const S = window._mykSplash;
      S.init(performance.now());

      // 恢复主题
      const savedTheme = localStorage.getItem("myknowledge-theme") || "system";
      const savedDesign = localStorage.getItem("myknowledge-design") || "raycast";
      this.theme = savedTheme;
      this.designTheme = savedDesign;
      this.applyTheme();

      // 首页 vs 非首页：每步随机间隔不同
      const hash = window.location.hash.replace(/^#/, "");
      const isHome = !hash || hash === "dashboard";
      const homeStep = () => 60 + Math.random() * 30;       // 60~90
      const fastStep = () => Math.random() * 30;            // 0~30
      const slowStep = () => 30 + Math.random() * 30;      // 30~60

      S.set(10);
      // 启动锁轮询（checkLock 内部按 isLocked 动态调整间隔：锁定 5s / 正常 15s）
      await S.step(this.checkLock(), 30, isHome ? homeStep() : fastStep());
      await S.step(this.loadProjects(), 55, isHome ? homeStep() : fastStep());
      await S.step(this.loadIdentity(), 75, isHome ? homeStep() : fastStep());
      await S.step(this.loadVersion(),  90, isHome ? homeStep() : slowStep());

      // 启动 AI 状态轮询
      this.checkMcpStatus();
      setInterval(() => this.checkMcpStatus(), 15000);

      // 订阅 SSE 实时更新
      api.subscribeEvents((raw) => {
        // 事件带 type：{ version, type: "write" | "diagnose" }
        // 阶段二：只对 type="diagnose"（MCP 自检广播）响应 → 重读就绪信号；
        // type="write"（无关写操作）忽略，不被打扰。
        let eventType = "";
        if (typeof raw === "string" && raw.trim()) {
          try { eventType = (JSON.parse(raw).type) || ""; } catch (_) { /* 忽略无法解析的事件 */ }
        }
        if (eventType === "diagnose") {
          this.loadReadiness();
        }
        const view = this.currentView;
        // 本端保存触发的 SSE（后端 2s 轮询 version，事件不带文档路径）：
        // 3s 内本端保存过即视为本次事件的源头 → 跳过重载（内容已在编辑器/缓存为最新），
        // 否则每次保存都把当前文档完整重载一遍（浪费 + 竞态窗口）。
        // 注：单用户本地应用，此窗口内远端变更可能被跳过一次（下次 version 变化会再同步）。
        const selfSaved =
          (view === "view" || view === "edit") &&
          Date.now() - (this._localSavedAt || 0) < 3000;
        if (view === "dashboard") this.loadDashboard();
        else if (view === "project" && this.currentPath) this.loadProjectDocuments(this.currentPath);
        // 仅阅读态重载（实时同步）；编辑态不重载——保护正在编辑的内容，
        // 改为派发事件，由 docComponent 主动检查版本 → 冲突立即弹 diff（不等保存）
        else if (view === "view" && this.currentPath && !selfSaved) this.loadDocument(this.currentPath);
        else if (view === "edit" && this.currentPath && !selfSaved) window.dispatchEvent(new CustomEvent("myk:doc-modified"));
      });

      // 阶段二：初始化就绪信号（读 /api/diagnose/saved，不触发检查）
      this.loadReadiness();

      // 处理初始 hash
      this.handleRoute();
      window.addEventListener("hashchange", () => this.handleRoute());

      if (!this.identitySet) window.location.hash = "setup";

      await S.sprint();
      this.loading = false;
      // sidebar 区块顺序恢复 + 拖动绑定（DOM 已就绪）
      setTimeout(() => { this._initSidebarOrder(); this._bindSidebarDrag(); }, 0);
    },

    /**
     * 处理路由
     */
    handleRoute() {
      // 未设置身份时只允许 setup 页
      const hash = window.location.hash.replace(/^#/, "") || "dashboard";
      if (!this.identitySet && hash !== "setup") {
        window.location.hash = "setup";
        return;
      }

      // setup 特殊处理
      if (hash === "setup") {
        // 身份已配置且非强制重进（rerunGuide）→ 不展示 setup，直接跳仪表盘
        if (this.identitySet && !this.guideForce) {
          window.location.hash = "dashboard";
          return;
        }
        this.guideForce = false; // 放行进入后重置，避免后续导航残留强制标记
        this.currentView = "setup";
        return;
      }

      const router = window._mykRouter;
      if (router) {
        router.navigate(hash);
      } else {
        // Fallback 简单路由
        if (hash === "dashboard") {
          this.setView("dashboard");
          this.loadDashboard();
        } else if (hash.startsWith("project/")) {
          const path = hash.replace("project/", "");
          this.setView("project", path);
          this.loadProjectDocuments(path);
        }
      }
    },

    /**
     * 应用主题
     */
    applyTheme() {
      // 设计系统名 vs 色彩模式：两者用同一个 data-theme 属性
      if (this.designTheme === "raycast") {
        document.documentElement.setAttribute("data-theme", this.theme);
      } else {
        document.documentElement.setAttribute("data-theme", this.designTheme);
      }
      localStorage.setItem("myknowledge-theme", this.theme);
      localStorage.setItem("myknowledge-design", this.designTheme);
    },

    /**
     * 切换色彩模式（仅 Raycast）
     */
    switchTheme(t) {
      this.theme = t;
      this.applyTheme();
    },

    /**
     * 切换设计系统
     */
    switchDesignTheme(dt) {
      this.designTheme = dt;
      if (dt !== "raycast") {
        this.theme = "light"; // 非 Raycast 主题强制亮色
      }
      this.applyTheme();
    },

    /* ── 身份管理 ─────────────────────────────────────────────────── */

    /** 加载用户身份。仅 404 视为未设置。 */
    async loadIdentity() {
      try {
        const id = await api.getIdentity();
        if (id) {
          this.nickname = id.nickname;
          this.email = id.email;
        }
      } catch {
        // 后端不可达 → 标记离线，不阻塞页面
        this.backendOffline = true;
      }
    },

    /**
     * 身份是否已设置。后端离线时暂不判断。
     */
    get identitySet() {
      return !!(this.nickname && this.email);
    },

    /** 保存用户身份 */
    async saveIdentity(nickname, email) {
      await api.setIdentity(email, nickname);
      this.nickname = nickname;
      this.email = email;
    },

    /* ── 阶段三：AI 客户端配置（MCP/hooks/Agent 检测 + 半自动化写入） ── */

    /** AI 平台元信息（key 与后端 client_config.PLATFORMS 严格一致：ClaudeCode/ClaudeDesktop/CodeBuddyIDE/WorkBuddy/Enchante）
     *  key 用 PascalCase（读起来即展示名去空格：CodeBuddyIDE → "CodeBuddy IDE"），URL 无需编码。
     *  kinds: 该平台支持的配置种类（与后端 platforms.json kinds 一致）——
     *         ClaudeCode/CodeBuddyIDE/WorkBuddy/Cursor → mcp+hooks+agent；ClaudeDesktop → 仅 mcp；
     *         Enchante → mcp+agent（无 hooks；MCP 无配置文件，走 deeplink，见 usesDeeplink） */
    clientPlatforms: [
      { key: "ClaudeCode",    label: "Claude Code",   dot: "linear-gradient(135deg,#d97706,#f59e0b)", kinds: ["mcp", "hooks", "agent"] },
      { key: "ClaudeDesktop", label: "Claude Desktop", dot: "linear-gradient(135deg,#b45309,#f59e0b)", kinds: ["mcp"] },
      { key: "CodeBuddyIDE",  label: "CodeBuddy IDE", dot: "linear-gradient(135deg,#6366f1,#818cf8)", kinds: ["mcp", "hooks", "agent"] },
      { key: "WorkBuddy",     label: "WorkBuddy",     dot: "linear-gradient(135deg,#0ea5e9,#22d3ee)", kinds: ["mcp", "hooks", "agent"] },
      { key: "Enchante",      label: "Enchanté",      dot: "linear-gradient(135deg,#9333ea,#a855f7)", kinds: ["mcp", "agent"] },
      { key: "Cursor",        label: "Cursor",        dot: "linear-gradient(135deg,#0891b2,#06b6d4)", kinds: ["mcp", "hooks", "agent"] },
    ],

    /** 加载各平台配置检测状态（GET /api/client-config）；加载中 clientDetecting=true（「重新检测」按钮转 spinner） */
    async loadClientConfig() {
      this.clientDetecting = true;
      try {
        const data = await api.getClientConfig();
        this.clientConfig = data || {};
        this.clientConfigAt = Date.now();
      } catch (e) {
        // 后端离线/异常：置 null，UI 显示「检测失败」并提供复制兜底
        this.clientConfig = null;
      } finally {
        this.clientDetecting = false;
      }
    },

    /**
     * 旧缓存刷新（轻量）：clientConfig 缺失或超过 maxAgeMs 未刷新时才重新拉取，
     * 避免切分组等高频入口反复 GET；打开 Modal 仍走 loadClientConfig 无条件刷新。
     * @param {number} maxAgeMs - 缓存最长存活时间（默认 5s）
     */
    refreshClientConfigIfStale(maxAgeMs = 5000) {
      if (!this.clientConfig || Date.now() - this.clientConfigAt > maxAgeMs) {
        return this.loadClientConfig().catch(() => {});
      }
      return Promise.resolve();
    },

    /**
     * 半自动化配置开关（双向）：开 = POST 写 MyKnowledge 配置；
     * 关 = DELETE 移除 MyKnowledge 配置（只动 MyKnowledge，保留用户其他配置；幂等）。
     * 开关 optimistic：点击立即本地翻转为目标状态；成功 loadClientConfig 刷新真实
     * 状态；失败回弹真实状态 + 行内 fallback 可交互文本（5 秒自动消失）。
     * @param {string} platform - ClaudeCode | ClaudeDesktop | CodeBuddyIDE | WorkBuddy
     * @param {string} kind - mcp | hooks | agent
     */
    async configureClient(platform, kind) {
      if (this.clientConfiguring) return; // 同一时刻只允许一个写入
      this.clientConfiguring = { platform, kind };
      this.clientFallback = null;
      // 开关目标状态：当前未配置 → 开（POST 写）；当前已配置 → 关（DELETE 移除）。
      // optimistic：本地先翻转开关（clientConfig 已加载且非 null 时；null 态开关禁用不会走到这里）
      let target = true;
      if (this.clientConfig && this.clientConfig[platform]) {
        const prev = !!this.clientConfig[platform][kind];
        target = !prev;
        this.clientConfig[platform][kind] = target;
      }
      try {
        // 开 = 写配置（POST）；关 = 移除配置（DELETE，只动 MyKnowledge 条目）
        const res = target
          ? await api.setClientConfig(platform, kind)
          : await api.deleteClientConfig(platform, kind);
        // 写入/移除后重新检测，更新状态显示「已就绪 / 已关闭」
        await this.loadClientConfig();
        const label = this._clientKindLabel(kind);
        if (res && res.status) {
          showToast(`${this._platformLabel(platform)} ${label}${target ? "已就绪" : "已关闭"}`, "success");
        } else {
          showToast(`${this._platformLabel(platform)} ${label}${target ? "配置完成" : "已移除"}`, "success");
        }
      } catch (e) {
        // 失败：loadClientConfig 用真实状态刷新（开关回弹）+ 行内 fallback 文本
        await this.loadClientConfig();
        this.clientFallback = `${platform}-${kind}`;
        setTimeout(() => { this.clientFallback = null; }, 5000);
      } finally {
        this.clientConfiguring = null;
      }
    },

    /** 复制「让 AI 配置」prompt 兜底（失败/非适配时） */
    async copyClientPrompt(platform, kind) {
      const label = this._platformLabel(platform);
      const kindName = this._clientKindName(kind);
      const prompt =
        `请为我的 ${label} 客户端配置 MyKnowledge 的 ${kindName} 协作能力。\n` +
        `目标：让 ${label} 的 AI 能通过 MyKnowledge 的 MCP/hooks/Agent 协作访问我的本地知识库。\n` +
        `请用 MyKnowledge 的 MCP 工具或手动编辑 ${label} 配置文件完成配置，并告诉我配置位置与状态。`;
      const ok = await this._writeClipboard(prompt);
      if (ok) {
        this.clientFallback = null; // 复制成功 → 行内 fallback 自动消失
        showToast(`${label} ${kindName}配置 prompt 已复制 · 粘贴到 AI 对话`, "success");
      } else {
        showToast("复制失败，请手动复制", "error");
      }
    },

    /** 打开配置 modal：跳 account 分组 + 加载 AI 配置状态 */
    openSettings() {
      this.settingsGroup = "account";
      this.openModal("settings");
      // 进入时异步预加载 AI 配置状态（account/general 卡不依赖它）
      this.loadClientConfig().catch(() => {});
    },

    /** 重新运行初始化引导：强制进入 #setup + 重置到 Step1（绕过身份已配置的 setup 拦截） */
    rerunGuide() {
      this.closeModal();
      this.guideStep = 1;
      this.guideForce = true;
      window.location.hash = "setup";
    },

    /** 平台 key → 显示名 */
    _platformLabel(key) {
      const p = this.clientPlatforms.find(p => p.key === key);
      return p ? p.label : key;
    },

    /** kind → 动词标签（用于 toast/按钮） */
    _clientKindLabel(kind) {
      return kind === "mcp" ? "MCP" : kind === "hooks" ? "Hooks" : "Agent";
    },

    /** kind → 中文名（用于 prompt 文案） */
    _clientKindName(kind) {
      return kind === "mcp" ? "MCP" : kind === "hooks" ? "Hooks（PreToolUse）" : "专用 Agent";
    },

    /** AI 协作三类型元信息（mcp/hooks/agent） */
    clientKinds: [
      { key: "mcp",   label: "MCP",       desc: "AI 客户端直连本地知识库工具" },
      { key: "hooks", label: "Hooks",     desc: "PreToolUse 钩子保护裸操作" },
      { key: "agent", label: "Agent",     desc: "专用 Agent 简化知识库操作" },
    ],

    /** 是否正在写入某平台某 kind（按钮转 spinner + disabled） */
    isClientConfiguring(platform, kind) {
      const c = this.clientConfiguring;
      return !!(c && c.platform === platform && c.kind === kind);
    },

    /** 某平台某 kind 的检测状态（已配置=true/未配置=false/无数据=null） */
    clientStatus(platform, kind) {
      const cfg = this.clientConfig;
      if (!cfg || !cfg[platform]) return null;
      return cfg[platform][kind];
    },

    /** 某平台是否已安装（client_installed 平台级 bool；null=检测失败/未返回） */
    clientInstalled(platform) {
      const cfg = this.clientConfig;
      if (!cfg || !cfg[platform]) return null;
      return cfg[platform].client_installed;
    },

    /** 某平台连接态原始值：优先后端 clientConfig[platform].connection（数据驱动）；
     *  后端未返回 connection（mock 阶段/旧后端）时回退本地演示假数据。 */
    connectionValue(platform) {
      const cfg = this.clientConfig && this.clientConfig[platform];
      if (cfg && cfg.connection) return cfg.connection;
      return this._mockConnection(platform);
    },

    /** 连接态样式类：not_connected / connected / inactive / lost / disabled。
     *  置灰唯一依据 = clientInstalled(platform)：!installed（含 null/undefined）→ disabled；
     *  installed 平台无论 configured on/off/null 都显示真实 connection（SPEC §3.5 架构修订）。 */
    connectionClass(platform) {
      if (!this.clientInstalled(platform)) return "disabled";
      const conn = this.connectionValue(platform);
      return ["not_connected", "connected", "inactive", "lost"].includes(conn) ? conn : "not_connected";
    },

    /** 连接态行内文本（四态 + disabled；集中映射，无散落硬编码） */
    connectionLabel(platform) {
      const LABELS = {
        not_connected: "未连接",
        connected: "已连接",
        inactive: "未激活",
        lost: "已断联",
        disabled: "未连接",
      };
      return LABELS[this.connectionClass(platform)] || "未连接";
    },

    /** 连接态 tooltip 文案（精简版，SPEC §2.2 修订；集中映射，无散落硬编码） */
    connectionTooltip(platform) {
      const TIPS = {
        not_connected: "从未连接，配置后显示实时连接状态",
        connected: "已连接，可正常调用知识库工具",
        inactive: "长时间未调用 MCP，可能已停用；到平台用一次 MyKnowledge 确认",
        lost: "已断联；到平台重新使用一次 MyKnowledge 激活",
        disabled: "客户端未安装，安装后显示实时连接状态",
      };
      return TIPS[this.connectionClass(platform)] || TIPS.not_connected;
    },

    /** mock 阶段本地演示连接数据（后端 client_config 返回 connection 后自动被真实值覆盖） */
    _mockConnection(platform) {
      const MOCK = {
        ClaudeCode: "not_connected",
        ClaudeDesktop: "not_connected",
        CodeBuddyIDE: "connected",
        WorkBuddy: "inactive",
        Enchante: "not_connected",
      };
      return MOCK[platform] || "not_connected";
    },

    /** 某平台适用的 kind 列表（按 clientPlatforms[].kinds 数组过滤，与后端 platforms.json 一致） */
    platformKinds(platform) {
      const plat = this.clientPlatforms.find(p => p.key === platform);
      const kinds = plat && Array.isArray(plat.kinds) ? plat.kinds : [];
      return this.clientKinds.filter(k => kinds.includes(k.key));
    },

    /** 某 kind 适用的平台列表（按各平台 kinds 数组过滤，用于 settings 矩阵渲染） */
    platformsForKind(kindKey) {
      return this.clientPlatforms.filter(p =>
        Array.isArray(p.kinds) && p.kinds.includes(kindKey));
    },

    /** 该平台该 kind 是否走 deeplink 安装（当前仅 Enchante MCP：无配置文件，客户端捕获链接） */
    usesDeeplink(platform, kind) {
      return platform === "Enchante" && kind === "mcp";
    },

    /** 正在生成 deeplink（Enchante MCP 按钮 spinner / 防重复点击） */
    deeplinkBusy: false,

    /**
     * Enchante MCP 专属链接流程：GET deeplink → 复制剪贴板 → 隐藏 <a target=_blank> 触发唤起
     * （避免 SPA location.href 跳转中断）→ toast。失败给出可读提示。
     * @param {string} platform - Enchante
     */
    async generateEnchanteDeeplink(platform) {
      if (this.deeplinkBusy || !this.usesDeeplink(platform, "mcp")) return;
      this.deeplinkBusy = true;
      try {
        const data = await api.getClientConfigDeeplink(platform);
        const link = data && data.deeplink;
        if (!link) throw new Error("后端未返回 deeplink");
        const copied = await this._writeClipboard(link);
        if (!copied) showToast("复制失败，请手动复制链接", "error");
        // 隐藏 a 触发打开（用户浏览器对 enchante:// 的注册应用接管；SPA 不跳转）
        const a = document.createElement("a");
        a.href = link;
        a.target = "_blank";
        a.rel = "noopener";
        a.style.display = "none";
        document.body.appendChild(a);
        a.click();
        setTimeout(() => a.remove(), 100);
        showToast("已生成并复制专属链接，若未自动打开 Enchanté，请粘贴到浏览器地址栏", "success");
      } catch (e) {
        showToast(e.message || "生成专属链接失败，请稍后重试", "error");
      } finally {
        this.deeplinkBusy = false;
      }
    },

    /** 引导 Step2：平台×kind 配置项行列表（供 x-for 渲染） */
    get guideConfigItems() {
      const items = [];
      for (const plat of this.clientPlatforms) {
        for (const kind of this.platformKinds(plat.key)) {
          items.push({ platform: plat.key, kind: kind.key });
        }
      }
      return items;
    },

    /** 引导 Step3：总结列表 [{label, done}]（身份 + 各平台 mcp/hooks/agent） */
    get guideSummary() {
      const list = [{ label: "身份信息", done: this.identitySet }];
      for (const plat of this.clientPlatforms) {
        const p = this.clientConfig && this.clientConfig[plat.key];
        list.push({
          label: `${this._platformLabel(plat.key)} 协作`,
          done: !!(p && (p.mcp || p.hooks || p.agent)),
        });
      }
      return list;
    },

    /* ── 版本管理 ─────────────────────────────────────────────────── */

    async loadVersion() {
      try {
        const v = await apiRequest("/api/version");
        this.systemVersion = v.system || "";
        this.kbVersion = v.kb || "";
      } catch {
        // 后端不可达时不阻塞
      }
    },

    /**
     * 打开弹窗
     * @param {string} type
     * @param {any} data
     */
    openModal(type, data = null) {
      this.modal = type;
      this.modalData = data;
    },

    /** 关闭弹窗 */
    closeModal() {
      this.modal = null;
      this.modalData = null;
    },

    /** 打开分享导出弹窗，加载项目列表 */
    async openShareModal() {
      this.shareProjects = [];
      try {
        const data = await api.listProjects();
        const projects = data.items || data || [];
        this.shareProjects = projects.map(p => ({
          path: p.path || p.name,
          name: p.name || fileName(p.path || ""),
          docCount: p.doc_count || p.docCount || "",
          checked: false,
        }));
      } catch (e) {
        this.shareProjects = [];
      }
      this.modal = "share-export";
    },

    /** 全选/取消全选 */
    shareToggleAll() {
      const allChecked = this.shareProjects.every(p => p.checked);
      this.shareProjects.forEach(p => { p.checked = !allChecked; });
    },

    /** 执行导出 */
    async exportShare() {
      const selected = this.shareProjects.filter(p => p.checked);
      if (!selected.length) return;
      try {
        const { blob, filename } = await api.exportProjects(selected.map(p => p.path));
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 100);
        this.closeModal();
        showToast("已导出 " + selected.length + " 个项目", "success");
      } catch (e) {
        showToast("导出失败：" + (e.message || "未知错误"), "error");
      }
    },

    /* ── 垃圾箱 ────────────────────────────────────────────────────────── */

    /** 加载垃圾箱第一页（刷新/恢复/清空后回到首屏）。读 {items,total,has_more} 分页响应。 */
    async loadTrash() {
      this.trashLoading = true;
      try {
        const data = await api.getTrash(0, 50);
        this.trashItems = (data && data.items) || [];
        this.trashTotal = (data && data.total) || this.trashItems.length;
        this.trashHasMore = !!(data && data.has_more);
      } catch (e) {
        showToast(e.message || "加载垃圾箱失败", "error");
      } finally {
        this.trashLoading = false;
      }
    },

    /** 滚动到底自动加载下一页（offset=当前已加载数, limit=50，追加不覆盖）。
     *  防重入（trashLoading）/ 到底（!trashHasMore）时直接返回。 */
    async loadMoreTrash() {
      if (this.trashLoading || !this.trashHasMore) return;
      const offset = this.trashItems.length;
      this.trashLoading = true;
      try {
        const data = await api.getTrash(offset, 50);
        const fresh = (data && data.items) || [];
        // 追加不覆盖；trash_path 唯一天然去重（防滚动竞态重复条目）
        const known = new Set(this.trashItems.map(i => i.trash_path));
        const added = fresh.filter(i => !known.has(i.trash_path));
        this.trashItems = [...this.trashItems, ...added];
        this.trashTotal = (data && data.total) || this.trashTotal;
        this.trashHasMore = !!(data && data.has_more);
      } catch (e) {
        showToast(e.message || "加载更多失败", "error");
      } finally {
        this.trashLoading = false;
      }
    },
    /** 恢复条目（文档所属项目在垃圾箱时后端会拒绝——toast 后端消息提示先恢复项目） */
    async restoreTrashItem(item) {
      try {
        await api.restoreTrash(item.trash_path);
        showToast("已恢复 " + item.name, "success");
        await this.loadTrash();
      } catch (e) {
        showToast(e.message || "恢复失败", "error");
      }
    },
    /** 勾选/取消勾选单条（trash_path 为唯一切片键） */
    toggleTrashSelect(trashPath) {
      const i = this.selectedTrash.indexOf(trashPath);
      if (i >= 0) this.selectedTrash.splice(i, 1);
      else this.selectedTrash.push(trashPath);
    },
    /** 全选/取消全选（只作用于当前已加载的 trashItems，分页未加载的不算；再次点击取消） */
    toggleTrashSelectAll() {
      const allSelected = this.trashItems.length > 0
        && this.trashItems.every(i => this.selectedTrash.includes(i.trash_path));
      if (allSelected) this.clearTrashSelection();
      else this.selectedTrash = this.trashItems.map(i => i.trash_path);
    },
    /** 清空选中 */
    clearTrashSelection() {
      this.selectedTrash = [];
    },
    /** 精准删除选中条目（后端 body trash_paths）：成功 toast「已删除 N 项」→ 清选中 → 刷新第一页 */
    async deleteSelectedTrash() {
      const paths = this.selectedTrash.slice();
      if (paths.length === 0) return;
      try {
        const res = await api.deleteTrashItems(paths);
        const n = (res && typeof res.removed === "number") ? res.removed : paths.length;
        showToast(`已删除 ${n} 项`, "success");
        this.clearTrashSelection();
        await this.loadTrash();
      } catch (e) {
        showToast(e.message || "删除失败", "error");
      }
    },
    /** 清空垃圾箱（不可逆，需确认弹窗；all=true 清全部，与「删除选中」精准删除并存） */
    confirmEmptyTrash() {
      this.openModal("trash-empty", {});
    },
    async emptyTrashAction() {
      try {
        await api.emptyTrash();
        showToast("垃圾箱已清空", "success");
        this.trashItems = [];
        this.trashTotal = 0;
        this.trashHasMore = false;
        this.clearTrashSelection();
      } catch (e) {
        showToast(e.message || "清空失败", "error");
      } finally {
        this.closeModal();
      }
    },

    /* ── 知识健康检查（#health） ──────────────────────────────────────── */

    /**
     * 进 #health 时加载上次体检结果（读/算分离）。
     * saved:true → 渲染上次结果 + 记录 generated_at；saved:false → 空态「尚未检查」。
     */
    async loadHealthSaved() {
      this.healthLoading = true;
      try {
        const data = await api.getDiagnoseSaved();
        if (data && data.saved) {
          this.healthData = { issues: data.issues || [], summary: data.summary || {} };
          this.healthGeneratedAt = data.generated_at || "";
          this.healthSelectAllFixable(); // 进入页面默认全选可修复分组
          this._syncReadinessFromHealth();
        } else {
          this.healthData = null;
          this.healthGeneratedAt = "";
          this.healthSelected = {};
          this.readiness = { saved: false, total_issues: 0, has_high: false };
        }
      } catch (e) {
        // 读上次失败：不弹错误，降级为空态（保留旧数据不适用——此处无旧数据）
        this.healthData = null;
        this.healthGeneratedAt = "";
        this.readiness = { saved: false, total_issues: 0, has_high: false };
        if (e && e.isLocked) showToast("知识库正在整理中，暂时只读", "warning");
      } finally {
        this.healthLoading = false;
      }
    },

    /** 从当前 healthData/healthSummary 同步就绪信号（本地刷新，不依赖 SSE） */
    _syncReadinessFromHealth() {
      const summary = this.healthSummary;
      const total = summary.total_issues || 0;
      const saved = !!this.healthData;
      // has_high：summary.by_type 中 high severity 计数 > 0
      const byType = summary.by_type || {};
      let hasHigh = false;
      // by_type 只统计 type 计数，不含 severity；从 issues 计算 high
      const issues = this.healthIssues;
      hasHigh = issues.some(i => i.severity === "high");
      this.readiness = { saved, total_issues: total, has_high: hasHigh };
    },

    /**
     * 加载就绪信号：读 /api/diagnose/saved（只读，不触发检查）。
     * 成功 → 渲染三态；失败/离线 → 降级 muted（中性，不渲染语义色）。
     */
    async loadReadiness() {
      try {
        const data = await api.getDiagnoseSaved();
        if (data && data.saved) {
          this.healthData = { issues: data.issues || [], summary: data.summary || {} };
          this.healthGeneratedAt = data.generated_at || "";
          this._syncReadinessFromHealth();
        } else {
          this.healthData = null;
          this.readiness = { saved: false, total_issues: 0, has_high: false };
        }
      } catch (e) {
        // 后端离线：降级 muted（中性，不渲染语义色）
        this.readiness = { saved: false, total_issues: 0, has_high: false };
      }
    },

    /**
     * 重新检查：调 /api/diagnose 真算，覆盖结果并渲染新结果。
     * 失败 toast 且保留旧数据（healthLoading 结束、healthData 不变）。
     */
    async runHealthCheck(opts = {}) {
      // 修复进行中禁止用户手动重新检查；内部自动重查（opts.force=true）不受限
      if (this.isHealthHealing && !opts.force) return;
      this.healthLoading = true;
      try {
        const data = await api.getDiagnose();
        this.healthData = { issues: data.issues || [], summary: data.summary || {} };
        this.healthGeneratedAt = data.generated_at || ""; // 后端已补 generated_at
        this.healthSelectAllFixable(); // 重查后默认全选可修复分组
        this._syncReadinessFromHealth(); // 本地刷新就绪信号（不依赖 SSE）
      } catch (e) {
        if (e && e.isLocked) {
          showToast("知识库正在整理中，暂时只读", "warning");
        } else {
          showToast("体检失败 · 请检查后端连接", "error");
        }
        // 保留旧数据：healthData 不变
      } finally {
        this.healthLoading = false;
      }
    },

    /* ── 知识健康检查：派生数据（渲染辅助） ──────────────────────────── */

    /** 当前体检的 summary（为空对象兜底） */
    get healthSummary() {
      return (this.healthData && this.healthData.summary) || {};
    },

    /* ── 阶段二：就绪信号派生（顶部 status-indicator） ────────────────── */

    /** 就绪信号文本（等长三态）：健康 / N 个知识存疑 / 尚未触发检查 */
    get readinessLabel() {
      const r = this.readiness;
      if (!r.saved) return "尚未触发检查";
      if (r.total_issues === 0) return "知识状态健康";
      return `${r.total_issues} 个知识存疑`;
    },

    /** 就绪信号状态点语义类（success/danger/warning/muted） */
    get readinessDotClass() {
      const r = this.readiness;
      if (!r.saved) return "status-indicator__dot--muted";
      if (r.total_issues === 0) return "status-indicator__dot--success";
      return r.has_high
        ? "status-indicator__dot--danger"
        : "status-indicator__dot--warning";
    },

    /** 就绪信号 tooltip：点击进 #health 处理 */
    get readinessTitle() {
      const r = this.readiness;
      if (!r.saved) return "尚未检查知识结构 · 点击进入结构体检";
      if (r.total_issues === 0) return "知识结构健康 · 点击进入结构体检";
      return `${r.total_issues} 个知识存疑 · 点击进入结构体检`;
    },

    /** 当前体检的 issues 列表 */
    get healthIssues() {
      return (this.healthData && this.healthData.issues) || [];
    },

    /** 是否显示「上次检查」时间（有真实 generated_at 时） */
    get hasHealthGeneratedAt() {
      return !!this.healthGeneratedAt;
    },

    /** 上次检查本地时间文案 */
    get healthGeneratedAtLabel() {
      if (!this.healthGeneratedAt) return "";
      try {
        return new Date(this.healthGeneratedAt).toLocaleString();
      } catch (_) {
        return this.healthGeneratedAt;
      }
    },

    /** 高危（high severity）问题数 */
    get healthHighCount() {
      return this.healthIssues.filter(i => i.severity === "high").length;
    },

    /** 顶部「检查」按钮文案：尚未检查→开始检查；已有结果→重新检查 */
    get healthCheckBtnLabel() {
      return this.healthData ? "重新检查" : "开始检查";
    },

    /** 需要 AI 判断（needs_semantic）的 issue 列表 */
    get healthComplexIssues() {
      return this.healthIssues.filter(i => i.needs_semantic);
    },

    /** 按 type 分组的非复杂 issue（只保留有问题的组；顺序按系统 type 顺序） */
    get healthGroups() {
      const order = ["position", "metadata", "index", "ref", "illegal", "system"];
      const labels = {
        position: "位置非法",
        metadata: "缺元数据",
        index: "索引过时",
        ref: "死链",
        illegal: "非法结构",
        system: "系统文件",
      };
      const byType = {};
      this.healthIssues.forEach(i => {
        if (i.needs_semantic) return; // 复杂 issue 进复杂区，不进分组
        (byType[i.type] = byType[i.type] || []).push(i);
      });
      return order
        .filter(t => byType[t] && byType[t].length)
        .map(t => ({ type: t, label: labels[t] || t, issues: byType[t] }));
    },

    /** 分组计数芯片数据：{type, label, count}（全 type，含 0） */
    get healthChips() {
      const order = ["position", "metadata", "index", "ref", "illegal", "system"];
      const labels = {
        position: "position", metadata: "metadata", index: "index",
        ref: "ref", illegal: "illegal", system: "system",
      };
      const byType = (this.healthSummary.by_type) || {};
      return order.map(t => ({ type: t, label: labels[t] || t, count: byType[t] || 0 }));
    },

    /** action → 中文文案映射（issue 行尾部标签） */
    healthActionLabel(action) {
      const map = {
        move_to_peer_ck: "移动",
        add_metadata: "补齐元数据",
        rebuild_index: "重建索引",
        rebuild: "重建索引",
        review: "审查",
      };
      return map[action] || action || "";
    },

    /** issue → 单行 bullet（type · path · [severity] · message · action） */
    _healthIssueLine(i) {
      const sev = i.severity || "low";
      const act = this.healthActionLabel(i.action) || "";
      return `- **${i.type || "?"}** \`${i.path || ""}\` [${sev}] ${i.message || ""}${act ? `（${act}）` : ""}`;
    },

    /**
     * 构造复制 prompt 的 Markdown（不含 KB 根路径）。
     * mode: 'complex' → 仅 needs_semantic（复杂区）；'all' → 全部 issue（lazy 按钮）
     */
    buildHealthPrompt(mode = "complex") {
      const issues = mode === "all"
        ? this.healthIssues
        : this.healthComplexIssues;
      if (!issues.length) return "";
      const lines = issues.map(i => this._healthIssueLine(i));
      return (
        "请用 MyKnowledge 的 MCP 工具（maint__knowledgebase_diagnose 复查 + write__ 系列修复）" +
        "处理以下知识库结构问题。每项请给出处理建议，并按需执行修复：\n" +
        lines.join("\n") +
        "\n---\n" +
        `扫描文件：${(this.healthSummary.total_files) || 0} 个`
      );
    },

    /**
     * 剪贴板写入。
     * 优先在用户手势同步栈里用 document.execCommand("copy")（最可靠，兼容 http/file 环境，
     * 避免 Clipboard API 在非 https/localhost 下 reject 且异步回调丢失用户手势导致降级失败）。
     * execCommand 失败时才回退 Clipboard API。
     */
    _writeClipboard(text) {
      return new Promise((resolve) => {
        // 同步降级：在进入函数的用户手势同步栈内执行 execCommand
        let ok = false;
        try {
          const ta = document.createElement("textarea");
          ta.value = text;
          ta.style.position = "fixed";
          ta.style.left = "-9999px";
          ta.style.opacity = "0";
          document.body.appendChild(ta);
          ta.focus();
          ta.select();
          ta.setSelectionRange(0, text.length);
          ok = document.execCommand("copy");
          ta.remove();
        } catch (_) {
          ok = false;
        }
        if (ok) {
          resolve(true);
          return;
        }
        // 回退：Clipboard API（https/localhost 且有用户权限时）
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard
            .writeText(text)
            .then(() => resolve(true))
            .catch(() => resolve(false));
        } else {
          resolve(false);
        }
      });
    },

    /** 点击「复制 prompt 交 AI」（复杂区）：复制 needs_semantic 子集 + toast */
    async copyHealthPrompt() {
      const prompt = this.buildHealthPrompt("complex");
      const count = this.healthComplexIssues.length;
      if (!count) return;
      const ok = await this._writeClipboard(prompt);
      if (ok) {
        showToast(`已复制 ${count} 条复杂问题 · 粘贴到 AI 对话`, "success");
      } else {
        showToast("复制失败，请手动复制", "error");
      }
    },

    /**
     * lazy 按钮「我懒得看了，交给 AI 吧」：复制全部问题清单（含复杂+非复杂）+ toast。
     * 仅 total_issues>0 时显示。
     */
    async copyLazyHealthPrompt() {
      if (this.isHealthHealing) return; // 修复进行中禁止复制
      const issues = this.healthIssues;
      const total = this.healthSummary.total_issues || issues.length;
      if (!issues.length) return;
      this.healthLazyCopying = true;
      try {
        const header =
          "我知识库的结构体检发现了以下问题（共 " + total + " 项）。" +
          "请用 MyKnowledge 的 MCP 工具处理：\n\n" +
          "复查：maint__knowledgebase_diagnose（先跑一次确认最新状态）\n" +
          "处理：根据每个问题的语义判断该不该修、怎么修，用对应 MCP 工具执行\n" +
          "  - 需移动文档 → write__rename_document 或移动工具\n" +
          "  - 需重建索引 → maint__rebuild_index\n" +
          "  - 需补元数据/内容 → write__update_document（生成 summary 等）\n" +
          "  - 死链/需判断的 → 判断是修复、删除引用还是补充文档，必要时先问我\n" +
          "移动/删除等不可逆操作前先向我确认。\n\n" +
          "问题清单：\n" +
          issues.map(i => this._healthIssueLine(i)).join("\n") +
          "\n\n---\n" +
          `扫描文件：${(this.healthSummary.total_files) || 0} 个`;
        const ok = await this._writeClipboard(header);
        if (ok) {
          showToast("Prompt 已复制，请回到你与 AI 的对话框粘贴。", "success");
        } else {
          showToast("复制失败，请手动复制", "error");
        }
      } finally {
        this.healthLazyCopying = false;
      }
    },

    /* ── 知识健康检查：阶段 B 修复交互 ────────────────────────────────── */

    /** 该 type 是否可勾选修复（非复杂分组：position/index/system） */
    healthIsFixableType(type) {
      return type === "position" || type === "index" || type === "system";
    },

    /** 该 type 的分组组头按钮文案（position→修复知识位置；index/system→重建索引） */
    healthGroupButtonLabel(type) {
      if (type === "position") return "修复知识位置";
      if (type === "index" || type === "system") return "重建索引";
      return "";
    },

    /** 组内已勾选的 path 列表 */
    healthGroupChecked(type) {
      const sel = this.healthSelected[type];
      return sel ? Object.keys(sel) : [];
    },

    /** 组内可勾选 issue 列表（position/index/system 全部 issue） */
    healthGroupCheckableIssues(group) {
      return this.healthIsFixableType(group.type) ? group.issues : [];
    },

    /** 组内全部可勾选项是否都已勾选（全选框 checked） */
    healthGroupAllChecked(group) {
      const issues = this.healthGroupCheckableIssues(group);
      if (!issues.length) return false;
      const sel = this.healthSelected[group.type];
      return issues.every(i => sel && sel[i.path]);
    },

    /** 组内部分勾选（全选框 indeterminate） */
    healthGroupSomeChecked(group) {
      const issues = this.healthGroupCheckableIssues(group);
      const checked = this.healthGroupChecked(group.type).length;
      return checked > 0 && checked < issues.length;
    },

    /** 修复进行中标记：为 true 时禁用所有修复相关操作 */
    get isHealthHealing() {
      return !!this.healthHealingGroup;
    },

    /** 勾选/取消勾选单个 issue（修复进行中忽略） */
    toggleHealthSelect(type, path) {
      if (this.isHealthHealing) return;
      const sel = { ...(this.healthSelected[type] || {}) };
      if (sel[path]) delete sel[path];
      else sel[path] = true;
      this.healthSelected = { ...this.healthSelected, [type]: sel };
    },

    /** 组头全选/取消全选（修复进行中忽略） */
    toggleHealthGroupSelect(group) {
      if (this.isHealthHealing) return;
      const all = this.healthGroupAllChecked(group);
      const sel = { ...(this.healthSelected[group.type] || {}) };
      const issues = this.healthGroupCheckableIssues(group);
      issues.forEach(i => {
        if (all) delete sel[i.path];
        else sel[i.path] = true;
      });
      this.healthSelected = { ...this.healthSelected, [group.type]: sel };
    },

    /** 默认全选所有可勾选分组（position/index/system）的全部 issue */
    healthSelectAllFixable() {
      const sel = {};
      this.healthGroups.forEach(group => {
        if (!this.healthIsFixableType(group.type)) return;
        const groupSel = {};
        this.healthGroupCheckableIssues(group).forEach(i => {
          groupSel[i.path] = true;
        });
        if (Object.keys(groupSel).length) sel[group.type] = groupSel;
      });
      this.healthSelected = sel;
    },

    /** 分组头单按钮：打开修复确认弹窗（只处理勾选项） */
    openHealthFixModal(group) {
      const paths = this.healthGroupChecked(group.type);
      if (!paths.length || this.isLocked || this.healthHealingGroup) return;
      this.openModal("health-fix", {
        groupType: group.type,
        title: this.healthGroupButtonLabel(group.type),
        paths,
      });
    },

    /** 弹窗内勾选项 path 列表（最多显示 5 项，超出折叠） */
    get healthFixPathsPreview() {
      const paths = (this.modalData && this.modalData.paths) || [];
      const max = 5;
      if (paths.length <= max) return { shown: paths, folded: 0 };
      return { shown: paths.slice(0, max), folded: paths.length - max };
    },

    /** 弹窗「复制 prompt」：复制勾选项 prompt + toast */
    async copyHealthFixPrompt() {
      const md = this.modalData || {};
      const groupType = md.groupType || "";
      const paths = md.paths || [];
      if (!paths.length) return;
      const issues = this.healthIssues.filter(i =>
        i.type === groupType && paths.includes(i.path));
      const lines = issues.map(i => this._healthIssueLine(i));
      const prompt =
        "请用 MyKnowledge 的 MCP 工具（maint__knowledgebase_diagnose 复查 + write__ 系列修复）" +
        "处理以下知识库结构问题。每项请给出处理建议，并按需执行修复：\n" +
        lines.join("\n") +
        "\n---\n" +
        `扫描文件：${(this.healthSummary.total_files) || 0} 个`;
      const ok = await this._writeClipboard(prompt);
      if (ok) {
        showToast(`已复制 ${paths.length} 条问题 · 粘贴到 AI 对话`, "success");
      } else {
        showToast("复制失败，请手动复制", "error");
      }
    },

    /**
     * 弹窗「确认执行」：按 groupType 调 REST → toast → 自动重查 → 关闭弹窗。
     * position → /api/heal/move；index/system → /api/heal/rebuild(all:true)
     */
    async execHealthFix() {
      const md = this.modalData || {};
      const groupType = md.groupType || "";
      const paths = md.paths || [];
      if (!paths.length || this.isLocked || this.healthHealingGroup) return;
      this.healthHealingGroup = groupType;
      try {
        if (groupType === "position") {
          const res = await api.healMove(paths);
          const moved = (res && res.moved) || [];
          showToast(`已移动 ${moved.length} 个文档到同级知识区`, "success");
        } else {
          // index / system → 重建受影响层
          const res = await api.healRebuild();
          const count = ((res && res.rebuilt) || []).length;
          showToast(count ? `已重建 ${count} 个层索引` : "已重建索引", "success");
        }
        // 成功：清空该组勾选，关闭弹窗，自动重新检查（内部 force=true，不受修复中守卫限制）
        const sel = { ...(this.healthSelected[groupType] || {}) };
        paths.forEach(p => { delete sel[p]; });
        this.healthSelected = { ...this.healthSelected, [groupType]: sel };
        this.closeModal();
        await this.runHealthCheck({ force: true });
      } catch (e) {
        if (e && e.isLocked) {
          showToast("知识库正在整理中，暂时只读", "warning");
        } else {
          showToast(`修复失败：${(e && e.message) || "请检查后端连接"}`, "error");
        }
        // 失败保留旧数据
      } finally {
        this.healthHealingGroup = "";
      }
    },

    /** 项目页 headbar 删除 → 确认弹窗（移入垃圾箱） */
    confirmDeleteProject() {
      const path = this.currentPath;
      if (!path || this.isLocked) return;
      const name = this.projectMeta && this.projectMeta.name ? this.projectMeta.name : fileName(path);
      this.openModal("delete-project", { path, name });
    },
    async deleteProjectAction() {
      const path = this.modalData && this.modalData.path;
      if (!path || this.isLocked) return;
      try {
        await api.deleteProject(path);
        this.closeModal();
        // 倒计时面板：明确跳转目标（首页）
        showCountdownToast(
          "项目已移入垃圾箱，3 秒后返回首页",
          () => { window.location.hash = "dashboard"; },
          3
        );
      } catch (e) {
        showToast(e.message || "删除失败", "error");
        this.closeModal();
      }
    },

    /** Headbar 删除按钮 → 打开删除确认弹窗 */
    confirmDeleteDocument() {
      const path = this.currentPath;
      if (!path) return;
      const title = (this.document && this.document.meta && this.document.meta.title) || fileName(path);
      this.openModal("delete-doc", { path, title });
    },

    /** 文档卡片右上角删除按钮（hover 出现）→ 复用 delete-doc 确认弹窗（与 top-header 交互一致） */
    confirmDeleteCard(path) {
      if (!path) return;
      this.openModal("delete-doc", { path, title: fileName(path) });
    },

    /** Headbar 面包屑（复刻 page-label 逻辑） */
    get headbarBreadcrumbs() {
      const crumbs = this.breadcrumbs || [];
      return crumbs.slice(1, -1).filter(c => c.label !== "projects");
    },

    /** Headbar 返回上级路径 */
    get headbarParentPath() {
      const crumbs = this.headbarBreadcrumbs;
      if (crumbs.length < 2) return "";
      return crumbs[crumbs.length - 2].path;
    },

    /** Headbar 返回按钮点击 */
    headbarGoBack() {
      const parent = this.headbarParentPath;
      if (parent) {
        const clean = parent.replace(/^projects\//, "");
        window.location.hash = "project/" + clean;
      } else {
        window.location.hash = "dashboard";
      }
    },

    headbarGoToCrumb(path) {
      const clean = (path || "").replace(/^projects\//, "");
      if (path.startsWith("common-knowledge")) {
        window.location.hash = "dashboard";
      } else {
        window.location.hash = "project/" + clean;
      }
    },

    /**
     * 显示 ref 浮层
     * @param {MouseEvent} event
     * @param {string} refPath
     */
    showPopover(event, refPath) {
      this.popoverRefPath = refPath;
      this.popoverVisible = true;
      this.popoverPos = {
        top: event.clientY + 8,
        left: event.clientX,
      };
    },

    /** 关闭 ref 浮层 */
    hidePopover() {
      this.popoverVisible = false;
      this.popoverRefPath = "";
    },
  });
});
