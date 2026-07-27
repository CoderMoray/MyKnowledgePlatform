/* ==========================================================================
   MyKnowledge — Alpine.js 应用入口
   整合所有组件：路由、存储、编辑器、渲染器
   设计系统: Raycast · v2.0
   ========================================================================== */

/**
 * 全局 ref 链接点击处理（供 marked 渲染的 onclick 调用）
 */
window._mykRefClick = function (event, refPath) {
  event.preventDefault();

  const viewerEl = document.querySelector('[x-data="viewerComponent"]');
  if (viewerEl && viewerEl.__x) {
    const data = viewerEl.__x.$data;
    if (typeof data.openRefPopover === "function") {
      data.openRefPopover(event, refPath);
      return;
    }
  }

  try {
    const store = Alpine.store("app");
    store.showPopover(event, refPath);
    loadRefPreview(refPath).then((preview) => {
      if (viewerEl && viewerEl.__x) {
        viewerEl.__x.$data.refPreview = preview;
        viewerEl.__x.$data.refLoading = false;
      }
    });
  } catch {
    // Alpine 可能尚未初始化
  }
};

/** Gravatar URL 辅助 */
window.gravatarUrl = function (email, size) {
  return utils.gravatarUrl(email, size);
};

document.addEventListener("alpine:init", () => {
  /* ── 编辑器组件 ──────────────────────────────────────────────────────── */

  Alpine.data("editorComponent", () => ({
    editorInstance: null,
    titleValue: "",
    summaryValue: "",
    saving: false,

    async init() {
      const store = Alpine.store("app");
      const path = store.currentPath;

      if (!store.document && path) {
        await store.loadDocument(path);
      }

      this.titleValue = store.document?.title || "";
      this.summaryValue = store.document?.summary || "";

      await this.$nextTick();
      const el = document.getElementById("tiptap-editor");
      if (el) {
        await this.waitForTipTap();
        this.initEditor(el);
      }
    },

    async waitForTipTap() {
      for (let i = 0; i < 50; i++) {
        if (window.TipTapCore && window.TipTapStarterKit) return;
        await new Promise((r) => setTimeout(r, 100));
      }
    },

    initEditor(el) {
      if (!el || this.editorInstance) return;

      const store = Alpine.store("app");
      const initialContent = store.htmlContent || "";

      const { Editor } = window.TipTapCore || {};
      const { StarterKit } = window.TipTapStarterKit || {};

      if (!Editor) {
        console.warn("TipTap not available, falling back to textarea");
        return;
      }

      const extensions = [StarterKit ? StarterKit.configure() : null].filter(Boolean);

      this.editorInstance = new Editor({
        element: el,
        extensions,
        content: initialContent,
        editorProps: {
          attributes: {
            class: "ProseMirror",
          },
        },
        onUpdate: ({ editor }) => {
          store.isDirty = true;
        },
      });

      store.editor = this.editorInstance;

      if (typeof window._mykBindToolbar === "function") {
        window._mykBindToolbar(this.editorInstance);
      }
    },

    destroyEditor() {
      if (this.editorInstance) {
        this.editorInstance.destroy();
        this.editorInstance = null;
      }
      const store = Alpine.store("app");
      store.editor = null;
      store.isDirty = false;
    },

    get authorAvatar() {
      const store = Alpine.store("app");
      const meta = store.documentMeta;
      const doc = store.document;
      const author = (meta && meta.author) || (doc && doc.author) || "";
      return authorAvatar(author, 32);
    },

    onAvatarError(event) {
      const img = event.target;
      const fallback = img.nextElementSibling;
      img.style.display = "none";
      if (fallback && fallback.classList.contains("avatar--fallback")) {
        fallback.style.display = "flex";
      }
    },

    async saveDocument() {
      const store = Alpine.store("app");
      if (store.isLocked) return;

      this.saving = true;
      try {
        const html = this.editorInstance
          ? this.editorInstance.getHTML()
          : store.htmlContent;
        const markdown = tiptapToMarkdown(html);

        await store.saveDocument(store.currentPath, {
          content: markdown,
          summary: this.summaryValue,
          title: this.titleValue,
        });
      } catch {
        // 错误已在 store 中处理
      } finally {
        this.saving = false;
      }
    },

    discard() {
      const store = Alpine.store("app");
      if (store.currentPath) {
        window.location.hash = `view/${encodeURIComponent(store.currentPath)}`;
      } else {
        window.location.hash = "dashboard";
      }
    },
  }));

  /* ── 阅读器组件 ──────────────────────────────────────────────────────── */

  Alpine.data("viewerComponent", () => ({
    refPreview: null,
    refLoading: false,

    init() {
      this.$watch("$store.app.htmlContent", () => {
        this.$nextTick(() => {
          this.postRenderViewer();
        });
      });

      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          this.postRenderViewer();
        });
      });
    },

    postRenderViewer() {
      const container = document.getElementById("viewer-content");
      if (!container) return;
      renderToContainer(null, container);
    },

    async openRefPopover(event, refPath) {
      const store = Alpine.store("app");
      this.refLoading = true;
      store.showPopover(event, refPath);
      this.refPreview = await loadRefPreview(refPath);
      this.refLoading = false;
    },

    closePopover() {
      const store = Alpine.store("app");
      store.hidePopover();
      this.refPreview = null;
    },

    get authorAvatar() {
      const store = Alpine.store("app");
      const meta = store.documentMeta;
      const doc = store.document;
      const author = (meta && meta.author) || (doc && doc.author) || "";
      return authorAvatar(author, 32);
    },

    onAvatarError(event) {
      const img = event.target;
      const fallback = img.nextElementSibling;
      img.style.display = "none";
      if (fallback && fallback.classList.contains("avatar--fallback")) {
        fallback.style.display = "flex";
      }
    },

    goToRef(path) {
      this.closePopover();
      window.location.hash = `view/${encodeURIComponent(path)}`;
    },

    goToEdit() {
      const store = Alpine.store("app");
      if (store.currentPath) {
        window.location.hash = `edit/${encodeURIComponent(store.currentPath)}`;
      }
    },

    confirmDelete() {
      const store = Alpine.store("app");
      store.openModal("delete-doc", {
        path: store.currentPath,
        title: store.document?.title || fileName(store.currentPath),
      });
    },
  }));

  /* ── 侧边栏组件 ──────────────────────────────────────────────────────── */

  Alpine.data("sidebarComponent", () => ({
    sidebarWidth: 168,
    resizing: false,
    hovering: false,
    startX: 0,
    startWidth: 0,

    /** 折叠态 = store 的 sidebarOpen 取反 */
    get collapsed() { return !Alpine.store("app").sidebarOpen; },
    get pinned() { return Alpine.store("app").sidebarOpen; },
    get sidebarOpen() { return Alpine.store("app").sidebarOpen; },

    toggle() {
      Alpine.store("app").toggleSidebar();
    },

    /** hover 进入：sidebar 在流内展开，flex 自动收缩内容 */
    onHoverEnter() {
      if (this.pinned) return;
      this.hovering = true;
    },

    /** hover 离开：sidebar 在流内收窄，flex 自动扩展内容 */
    onHoverLeave() {
      if (this.pinned) return;
      this.hovering = false;
    },

    /** 固定：sidebar 已在流内（hover 时），固定操作只切标志位 */
    smoothPin() {
      if (!this.pinned) {
        Alpine.store("app").sidebarOpen = true;
        this.hovering = false;
      } else {
        Alpine.store("app").sidebarOpen = false;
      }
    },

    startResize(e) {
      // 只响应右侧 5px 以内的 mousedown（通过 handle 触发）
      const rect = e.currentTarget.getBoundingClientRect();
      const edgeX = e.clientX - rect.right;
      if (edgeX > 5 || edgeX < -5) return;

      this.resizing = true;
      this.startX = e.clientX;
      this.startWidth = this.sidebarWidth;

      const onMove = (ev) => {
        if (!this.resizing) return;
        const delta = ev.clientX - this.startX;
        const newW = Math.max(120, Math.min(window.innerWidth * 0.5, this.startWidth + delta));
        this.sidebarWidth = newW;
      };

      const onUp = () => {
        this.resizing = false;
        // 吸附到默认宽度（±2px）
        if (Math.abs(this.sidebarWidth - 168) <= 2) {
          this.sidebarWidth = 168;
        }
        localStorage.setItem("myknowledge-sidebar-width", String(this.sidebarWidth));
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };

      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },

    init() {
      // 恢复状态
      const wasCollapsed = localStorage.getItem("myknowledge-sidebar-collapsed") === "1";
      Alpine.store("app").sidebarOpen = !wasCollapsed;
      const saved = parseInt(localStorage.getItem("myknowledge-sidebar-width"));
      if (saved && saved >= 120 && saved <= window.innerWidth * 0.5) {
        this.sidebarWidth = saved;
      }
      // 初始化 CSS 变量
      document.documentElement.style.setProperty("--sidebar-width", this.sidebarWidth + "px");
      this.$watch("sidebarWidth", (v) => {
        document.documentElement.style.setProperty("--sidebar-width", v + "px");
      });
      // 边缘触发器
      const self = this;
      const edge = document.getElementById("sidebarEdge");
      if (edge) {
        edge.addEventListener("mouseenter", () => self.onHoverEnter());
      }
    },

    goToProject(projectPath) {
      window.location.hash = `project/${encodeURIComponent(projectPath)}`;
    },

    goToDocument(docPath) {
      window.location.hash = `view/${encodeURIComponent(docPath)}`;
    },

    newDocument() {
      const store = Alpine.store("app");
      store.openModal("new-doc", {
        parentPath: store.currentPath || "",
      });
    },
  }));

  /* ── 弹窗组件 ────────────────────────────────────────────────────────── */

  Alpine.data("modalComponent", () => ({
    newDocName: "",
    newDocSummary: "",
    renameValue: "",
    creating: false,
    identityNickname: "",
    identityEmail: "",
    setupNickname: "",
    setupEmail: "",

    isValidEmail(email) {
      return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email || "");
    },

    async createDocument() {
      const store = Alpine.store("app");
      if (!this.newDocName.trim() || store.isLocked) return;

      this.creating = true;
      try {
        const parentPath = store.modalData?.parentPath || "";
        const fullPath = parentPath
          ? `${parentPath}/${this.newDocName.trim()}.md`
          : `${this.newDocName.trim()}.md`;

        await api.createDocument(fullPath, {
          content: "",
          summary: this.newDocSummary.trim(),
        });

        showToast("文档已创建", "success");
        store.closeModal();
        window.location.hash = `edit/${encodeURIComponent(fullPath)}`;
      } catch (err) {
        if (err.isLocked) {
          showToast("知识库正在整理中，暂时只读", "warning");
        } else {
          showToast(err.message || "创建失败", "error");
        }
      } finally {
        this.creating = false;
      }
    },

    async confirmDelete() {
      const store = Alpine.store("app");
      const path = store.modalData?.path;
      if (!path || store.isLocked) return;

      try {
        await api.deleteDocument(path);
        showToast("文档已删除", "success");
        store.closeModal();

        const projPath = projectName(path);
        if (projPath) {
          window.location.hash = `project/${encodeURIComponent(projPath)}`;
        } else {
          window.location.hash = "dashboard";
        }
      } catch (err) {
        showToast(err.message || "删除失败", "error");
      }
    },

    async confirmRename() {
      const store = Alpine.store("app");
      const path = store.modalData?.path;
      const newName = this.renameValue.trim();
      if (!path || !newName || store.isLocked) return;

      try {
        // 判断是项目改名还是文档改名
        if (store.modal === "rename-project") {
          await api.renameProject(path, newName);
        } else {
          await api.renameDocument(path, newName);
        }
        showToast("已改名", "success");
        store.closeModal();

        const parts = path.replace(/\\/g, "/").split("/");
        parts[parts.length - 1] = newName.includes(".") ? newName : newName + ".md";
        const newPath = parts.join("/");
        window.location.hash = `view/${encodeURIComponent(newPath)}`;
      } catch (err) {
        showToast(err.message || "改名失败", "error");
      }
    },

    async saveIdentity() {
      const store = Alpine.store("app");
      const nick = this.identityNickname.trim();
      const email = this.identityEmail.trim();
      if (!nick || !email || !this.isValidEmail(email)) return;
      try {
        await store.saveIdentity(nick, email);
        showToast("个人信息已保存", "success");
        store.closeModal();
      } catch (err) {
        showToast(err.message || "保存失败", "error");
      }
    },

    async saveSetup() {
      const store = Alpine.store("app");
      const nick = this.setupNickname.trim();
      const email = this.setupEmail.trim();
      if (!nick || !email || !this.isValidEmail(email)) return;
      try {
        await store.saveIdentity(nick, email);
        showToast("欢迎！", "success");
        window.location.hash = "dashboard";
      } catch (err) {
        showToast(err.message || "保存失败", "error");
      }
    },

    init() {
      const store = Alpine.store("app");
      this.$watch("$store.app.modal", (val) => {
        if (val === "edit-identity") {
          this.identityNickname = store.nickname || "";
          this.identityEmail = store.email || "";
        }
      });
    },
  }));

  /* ── 仪表盘组件 ──────────────────────────────────────────────────────── */

  Alpine.data("dashboardComponent", () => ({
    /** 从 dashboardProjects + archived 合并算出项目统计 */
    get projectStats() {
      const s = Alpine.store("app");
      const active = s.dashboardProjects ? s.dashboardProjects.length : 0;
      const archived = s.archived || [];
      const completed = archived.filter(p => p.status === "completed").length;
      const cancelled = archived.filter(p => p.status === "cancelled").length;
      const abandoned = archived.filter(p => p.status === "abandoned").length;
      return {
        total: active + archived.length,
        active, completed, cancelled, abandoned,
      };
    },

    goToProject(path) {
      window.location.hash = `project/${encodeURIComponent(path)}`;
    },

    goToDocument(path) {
      window.location.hash = `view/${encodeURIComponent(path)}`;
    },

    newDocument() {
      const store = Alpine.store("app");
      store.openModal("new-doc", { parentPath: "" });
    },

    /** B2 hover 面板状态 */
    hoverProject: null,
    hoverTimer: null,
    projectPreview: { docs: [], subprojects: [], archived: [] },

    openPreview(path) {
      clearTimeout(this.hoverTimer);
      this.hoverTimer = setTimeout(() => {
        this.hoverProject = path;
        this.loadProjectPreview(path);
      }, 300);
    },

    closePreview() {
      clearTimeout(this.hoverTimer);
      this.hoverTimer = setTimeout(() => {
        this.hoverProject = null;
      }, 150);
    },

    async loadProjectPreview(path) {
      try {
        // 按 2.5.1 嵌套架构：每个项目下有 common-knowledge/ projects/ archive/ 三个子目录
        const [docData, subData, archData] = await Promise.all([
          api.list(path + "/common-knowledge").catch(() => ({ items: [] })),
          api.list(path + "/projects").catch(() => ({ items: [] })),
          api.list(path + "/archive").catch(() => ({ items: [] })),
        ]);
        const excludeReadme = (i) => !/^readme\.md$/i.test(i.name || "");

        this.projectPreview = {
          docs: (docData.items || []).filter(i => !i.is_dir && excludeReadme(i)),
          subprojects: (subData.items || []).filter(i => i.is_dir),
          archived: (archData.items || []).filter(i => excludeReadme(i)),
        };
      } catch(e) {
        this.projectPreview = { docs: [], subprojects: [], archived: [] };
      }
    },
  }));

  /* ── 项目页组件 ──────────────────────────────────────────────────────── */

  Alpine.data("projectComponent", () => ({
    get projectMeta() {
      return Alpine.store("app").projectMeta || {};
    },

    get projectDisplayName() {
      return this.projectMeta.name || Alpine.store("app").currentPath || "";
    },

    get projectDescription() {
      return this.projectMeta.summary || this.projectMeta.description || "";
    },

    /** 父级面包屑（可点击，不含系统前缀目录） */
    get parentBreadcrumbs() {
      const crumbs = Alpine.store("app").breadcrumbs || [];
      // 跳过首个系统前缀（"projects"），取中间所有层级，过滤掉 "projects" 目录段
      return crumbs.slice(1, -1).filter(c => c.label !== "projects");
    },

    /** 直接父级路径（用于返回按钮） */
    get parentPath() {
      const crumbs = this.parentBreadcrumbs;
      return crumbs.length > 0 ? crumbs[crumbs.length - 1].path : "";
    },

    goToDocument(path) {
      window.location.hash = `view/${encodeURIComponent(path)}`;
    },

    goToProject(path) {
      window.location.hash = `project/${encodeURIComponent(path)}`;
    },

    goToEdit(path) {
      window.location.hash = `edit/${encodeURIComponent(path)}`;
    },

    newDocument() {
      const store = Alpine.store("app");
      store.openModal("new-doc", {
        parentPath: store.currentPath || "",
      });
    },

    renameProject() {
      const store = Alpine.store("app");
      store.openModal("rename-project", {
        path: store.currentPath,
        name: store.currentPath,
      });
    },
  }));
});
