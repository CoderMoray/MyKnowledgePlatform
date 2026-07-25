/* ==========================================================================
   MyKnowledge — Alpine.js 应用入口
   整合所有组件：路由、存储、编辑器、渲染器
   设计系统: Raycast · v1.0
   ========================================================================== */

/**
 * 全局 ref 链接点击处理（供 marked 渲染的 onclick 调用）
 * 在 Alpine x-html 中无法使用 @click 指令，因此使用全局函数桥接
 */
window._mykRefClick = function (event, refPath) {
  event.preventDefault();

  // 找到 viewerComponent 实例并调用其 openRefPopover 方法
  const viewerEl = document.querySelector('[x-data="viewerComponent"]');
  if (viewerEl && viewerEl.__x) {
    const data = viewerEl.__x.$data;
    if (typeof data.openRefPopover === "function") {
      data.openRefPopover(event, refPath);
      return;
    }
  }

  // Fallback: 直接通过 store 打开浮层
  try {
    const store = Alpine.store("app");
    store.showPopover(event, refPath);
    // 异步加载预览
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

/** Gravatar URL 辅助（供 HTML 中 x-bind:src 调用） */
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

      // 加载文档后初始化编辑器
      if (!store.document && path) {
        await store.loadDocument(path);
      }

      this.titleValue = store.document?.title || "";
      this.summaryValue = store.document?.summary || "";

      // 等待 DOM 渲染后初始化编辑器
      await this.$nextTick();
      const el = document.getElementById("tiptap-editor");
      if (el) {
        await this.waitForTipTap();
        this.initEditor(el);
      }
    },

    /**
     * 等待 TipTap ESM 模块加载完成
     */
    async waitForTipTap() {
      for (let i = 0; i < 50; i++) {
        if (window.TipTapCore && window.TipTapStarterKit) return;
        await new Promise((r) => setTimeout(r, 100));
      }
    },

    /**
     * 初始化 TipTap 编辑器
     * @param {HTMLElement} el - 编辑器挂载元素
     */
    initEditor(el) {
      if (!el || this.editorInstance) return;

      const store = Alpine.store("app");
      const initialContent = store.htmlContent || "";

      // 使用 TipTap 扩展
      const { Editor } = window.TipTapCore || {};
      const { StarterKit } = window.TipTapStarterKit || {};

      if (!Editor) {
        console.warn("TipTap not available, falling back to textarea");
        return;
      }

      const extensions = [StarterKit ? StarterKit.configure() : null].filter(
        Boolean
      );

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

      // 绑定工具栏
      if (typeof window._mykBindToolbar === "function") {
        window._mykBindToolbar(this.editorInstance);
      }
    },

    /**
     * 销毁编辑器
     */
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

    get maintainerAvatar() {
      const store = Alpine.store("app");
      const meta = store.documentMeta;
      const doc = store.document;
      const maintainer = (meta && meta.maintainer) || (doc && doc.maintainer) || "";
      return maintainer ? authorAvatar(maintainer, 24) : null;
    },

    onAvatarError(event) {
      const img = event.target;
      const fallback = img.nextElementSibling;
      img.style.display = "none";
      if (fallback && fallback.classList.contains("avatar--fallback")) {
        fallback.style.display = "flex";
      }
    },

    /**
     * 保存文档
     */
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

    /**
     * 放弃编辑
     */
    discard() {
      const store = Alpine.store("app");
      if (store.currentPath) {
        window.location.hash = `view/${encodeURIComponent(store.currentPath)}`;
      } else {
        window.location.hash = "dashboard";
      }
    },

    /**
     * 自动保存
     */
    autoSave() {
      const store = Alpine.store("app");
      if (store.isLocked || !store.isDirty) return;

      clearTimeout(store.autoSaveTimer);
      store.autoSaveTimer = setTimeout(() => {
        this.saveDocument();
      }, 3000);
    },
  }));

  /* ── 阅读器组件 ──────────────────────────────────────────────────────── */

  Alpine.data("viewerComponent", () => ({
    refPreview: null,
    refLoading: false,

    init() {
      // 监听 htmlContent 变化，执行后处理
      this.$watch("$store.app.htmlContent", () => {
        this.$nextTick(() => {
          this.postRenderViewer();
        });
      });

      // 初始渲染（x-html 可能尚未完成，使用 requestAnimationFrame 确保 DOM 就绪）
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          this.postRenderViewer();
        });
      });
    },

    /**
     * 对 x-html 渲染后的内容进行后处理：
     * - 绑定 ref-link 点击事件
     * - highlight.js 代码高亮
     */
    postRenderViewer() {
      const container = document.getElementById("viewer-content");
      if (!container) return;
      renderToContainer(null, container);
    },

    /**
     * 打开 ref 浮层
     * @param {MouseEvent} event
     * @param {string} refPath
     */
    async openRefPopover(event, refPath) {
      const store = Alpine.store("app");
      this.refLoading = true;
      store.showPopover(event, refPath);

      this.refPreview = await loadRefPreview(refPath);
      this.refLoading = false;
    },

    /** 关闭 ref 浮层 */
    closePopover() {
      const store = Alpine.store("app");
      store.hidePopover();
      this.refPreview = null;
    },

    /**
     * 获取当前文档的作者头像信息
     */
    get authorAvatar() {
      const store = Alpine.store("app");
      const meta = store.documentMeta;
      const doc = store.document;
      // 优先使用 meta 中的 author，其次使用 document.author
      const author = (meta && meta.author) || (doc && doc.author) || "";
      return authorAvatar(author, 32);
    },

    /**
     * 获取当前文档的维护者头像信息
     */
    get maintainerAvatar() {
      const store = Alpine.store("app");
      const meta = store.documentMeta;
      const doc = store.document;
      const maintainer = (meta && meta.maintainer) || (doc && doc.maintainer) || "";
      return maintainer ? authorAvatar(maintainer, 24) : null;
    },

    /**
     * Gravatar 头像加载失败时的回退处理
     */
    onAvatarError(event) {
      const img = event.target;
      const fallback = img.nextElementSibling;
      img.style.display = "none";
      if (fallback && fallback.classList.contains("avatar--fallback")) {
        fallback.style.display = "flex";
      }
    },

    /**
     * 导航到引用文档
     * @param {string} path
     */
    goToRef(path) {
      this.closePopover();
      window.location.hash = `view/${encodeURIComponent(path)}`;
    },

    /**
     * 前往编辑
     */
    goToEdit() {
      const store = Alpine.store("app");
      if (store.currentPath) {
        window.location.hash = `edit/${encodeURIComponent(store.currentPath)}`;
      }
    },

    /**
     * 删除文档
     */
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
    collapsedSections: {},

    get sidebarOpen() {
      return Alpine.store("app").sidebarOpen;
    },

    toggleSidebar() {
      Alpine.store("app").toggleSidebar();
    },

    toggleSection(name) {
      this.collapsedSections[name] = !this.collapsedSections[name];
    },

    isCollapsed(name) {
      return !!this.collapsedSections[name];
    },

    /**
     * 导航到项目页
     * @param {string} projectPath
     */
    goToProject(projectPath) {
      window.location.hash = `project/${encodeURIComponent(projectPath)}`;
    },

    /**
     * 导航到文档视图
     * @param {string} docPath
     */
    goToDocument(docPath) {
      window.location.hash = `view/${encodeURIComponent(docPath)}`;
    },

    /**
     * 当前高亮项
     * @param {string} path
     * @returns {boolean}
     */
    isActive(path) {
      const store = Alpine.store("app");
      return store.currentPath === path;
    },

    /**
     * 新建文档
     */
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

    /**
     * 邮箱格式校验
     */
    isValidEmail(email) {
      return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email || "");
    },

    /**
     * 创建文档
     */
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

        // 导航到编辑页
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

    /**
     * 确认删除
     */
    async confirmDelete() {
      const store = Alpine.store("app");
      const path = store.modalData?.path;
      if (!path || store.isLocked) return;

      try {
        await api.deleteDocument(path);
        showToast("文档已删除", "success");
        store.closeModal();

        // 返回上级
        const projectPath = projectName(path);
        if (projectPath) {
          window.location.hash = `project/${encodeURIComponent(projectPath)}`;
        } else {
          window.location.hash = "dashboard";
        }
      } catch (err) {
        showToast(err.message || "删除失败", "error");
      }
    },

    /**
     * 确认改名
     */
    async confirmRename() {
      const store = Alpine.store("app");
      const path = store.modalData?.path;
      const newName = this.renameValue.trim();
      if (!path || !newName || store.isLocked) return;

      try {
        await api.renameDocument(path, newName);
        showToast("已改名", "success");
        store.closeModal();

        // 导航到新路径
        const parts = path.replace(/\\/g, "/").split("/");
        parts[parts.length - 1] = newName.includes(".") ? newName : newName + ".md";
        const newPath = parts.join("/");
        window.location.hash = `view/${encodeURIComponent(newPath)}`;
      } catch (err) {
        showToast(err.message || "改名失败", "error");
      }
    },

    /**
     * 保存用户身份
     */
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

    /**
     * 首次设置身份
     */
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
      // 打开编辑身份弹窗时预填现有信息
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
    get projectCount() {
      const s = Alpine.store("app").statusSummary;
      return s ? s.projects.total : 0;
    },

    get documentCount() {
      const s = Alpine.store("app").statusSummary;
      return s ? s.documents : 0;
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
  }));

  /* ── 项目页组件 ──────────────────────────────────────────────────────── */

  Alpine.data("projectComponent", () => ({
    goToDocument(path) {
      window.location.hash = `view/${encodeURIComponent(path)}`;
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
