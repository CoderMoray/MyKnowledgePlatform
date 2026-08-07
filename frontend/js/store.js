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

    /** 错误信息 */
    error: null,

    /* ── 锁状态 ────────────────────────────────────────────────────────── */

    /** 是否被锁定 */
    isLocked: false,

    /** 垃圾箱 */
    trashItems: [],
    trashLoading: false,

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
        this.error = err.message || "加载文档失败";
        this.document = null;
        this.htmlContent = "";
        this.refs = [];
        this.documentMeta = null;
        // 404 区分：文档曾存在后被删除（可恢复）vs 从未存在
        // err.message 已由 apiRequest 解嵌套（"deleted"）；deleted_at 在 err.detail.detail 里
        const dd = err && err.detail && err.detail.detail;
        this.deletedInfo =
          err && err.status === 404 && err.message === "deleted"
            ? { deleted_at: (dd && dd.deleted_at) || "" }
            : null;
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
        this.document = { ...this.document, ...data };
        this.isDirty = false;
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
        this.document = { ...this.document, ...data };
      }
      this.isDirty = false;
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
      } catch (err) {
        this.error = err.message || "加载仪表盘失败";
      }
    },

    /**
     * 初始化应用
     */
    async init() {
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
      await S.step(this.checkLock(),  30, isHome ? homeStep() : fastStep());
      await S.step(this.loadProjects(), 55, isHome ? homeStep() : fastStep());
      await S.step(this.loadIdentity(), 75, isHome ? homeStep() : fastStep());
      await S.step(this.loadVersion(),  90, isHome ? homeStep() : slowStep());

      // 启动锁轮询
      setInterval(() => this.checkLock(), 15000);

      // 启动 AI 状态轮询
      this.checkMcpStatus();
      setInterval(() => this.checkMcpStatus(), 15000);

      // 订阅 SSE 实时更新
      api.subscribeEvents(() => {
        const view = this.currentView;
        if (view === "dashboard") this.loadDashboard();
        else if (view === "project" && this.currentPath) this.loadProjectDocuments(this.currentPath);
        // 仅阅读态重载（实时同步）；编辑态不重载——保护正在编辑的内容，
        // 改为派发事件，由 docComponent 主动检查版本 → 冲突立即弹 diff（不等保存）
        else if (view === "view" && this.currentPath) this.loadDocument(this.currentPath);
        else if (view === "edit" && this.currentPath) window.dispatchEvent(new CustomEvent("myk:doc-modified"));
      });

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
        // 身份已配置 → 不展示 setup，直接跳仪表盘
        if (this.identitySet) {
          window.location.hash = "dashboard";
          return;
        }
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
    async loadTrash() {
      this.trashLoading = true;
      try {
        const data = await api.getTrash();
        this.trashItems = (data && data.items) || [];
      } catch (e) {
        showToast(e.message || "加载垃圾箱失败", "error");
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
    /** 清空垃圾箱（不可逆，需确认弹窗；后端暂无单条彻底删除 API，只清空全部） */
    confirmEmptyTrash() {
      this.openModal("trash-empty", {});
    },
    async emptyTrashAction() {
      try {
        await api.emptyTrash();
        showToast("垃圾箱已清空", "success");
        this.trashItems = [];
      } catch (e) {
        showToast(e.message || "清空失败", "error");
      } finally {
        this.closeModal();
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
      const name = (this.document && this.document.meta && this.document.meta.title) || fileName(path);
      this.openModal("delete-doc", { path, name });
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
