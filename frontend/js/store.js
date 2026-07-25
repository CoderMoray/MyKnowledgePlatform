/* ==========================================================================
   MyKnowledge — Alpine.js 全局状态管理
   设计系统: Raycast · v1.0
   ========================================================================== */

document.addEventListener("alpine:init", () => {
  Alpine.store("app", {
    /* ── 视图状态 ──────────────────────────────────────────────────────── */

    /** 当前视图: dashboard | project | view | edit | new | status */
    currentView: "dashboard",

    /** 当前文档/项目路径 */
    currentPath: "",

    /** 面包屑片段 */
    breadcrumbs: [],

    /** 是否正在加载 */
    loading: false,

    /** 错误信息 */
    error: null,

    /* ── 锁状态 ────────────────────────────────────────────────────────── */

    /** 是否被锁定 */
    isLocked: false,

    /** 锁信息 */
    lockInfo: null,

    /** 后端是否离线 */
    backendOffline: false,

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

    /** 当前项目下的文档列表 */
    documents: [],

    /** 当前文档内容 */
    document: null,

    /** 当前文档的引用 */
    refs: [],

    /** 当前文档的 HTML 内容 */
    htmlContent: "",

    /** 当前文档的元信息（作者头像等） */
    documentMeta: null,

    /** 侧边栏是否打开（移动端） */
    sidebarOpen: false,

    /* ── 编辑器状态 ────────────────────────────────────────────────────── */

    /** TipTap 编辑器实例 */
    editor: null,

    /** 编辑器是否已修改 */
    isDirty: false,

    /** 编辑器自动保存计时器 */
    autoSaveTimer: null,

    /* ── 仪表盘数据 ────────────────────────────────────────────────────── */

    /** 状态摘要 */
    statusSummary: null,

    /** 最近更新列表 */
    recentUpdates: [],

    /* ── 弹窗状态 ──────────────────────────────────────────────────────── */

    /** 弹窗类型: null | 'delete-doc' | 'rename-doc' | 'new-doc' | 'rename-project' */
    modal: null,

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
    },

    /**
     * 加载侧边栏项目列表
     */
    async loadProjects() {
      try {
        const data = await api.list("projects");
        this.projects = data && data.items ? data.items : [];
      } catch (err) {
        console.error("加载项目列表失败:", err);
      }
    },

    /**
     * 加载项目下的文档列表
     * @param {string} projectPath
     */
    async loadProjectDocuments(projectPath) {
      this.loading = true;
      this.error = null;
      try {
        const data = await api.list(projectPath);
        this.documents = data && data.items ? data.items : [];
      } catch (err) {
        this.error = err.message || "加载文档列表失败";
        this.documents = [];
      } finally {
        this.loading = false;
      }
    },

    /**
     * 加载文档内容和引用
     * @param {string} path
     */
    async loadDocument(path) {
      this.loading = true;
      this.error = null;
      try {
        const data = await api.getDocumentWithRefs(path);
        this.document = data;
        this.htmlContent = data.html || (data.content ? marked.parse(data.content) : "");
        this.refs = data.refs || [];

        // 并行加载元信息（不阻塞主内容渲染）
        this.loadDocumentMeta(path).catch(() => {});
      } catch (err) {
        this.error = err.message || "加载文档失败";
        this.document = null;
        this.htmlContent = "";
        this.refs = [];
        this.documentMeta = null;
      } finally {
        this.loading = false;
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

    /** 切换侧边栏（移动端） */
    toggleSidebar() {
      this.sidebarOpen = !this.sidebarOpen;
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
        showToast("文档已保存", "success");
        return data;
      } catch (err) {
        if (err.isLocked) {
          showToast("知识库正在整理中，暂时只读", "warning");
        } else {
          showToast(err.message || "保存失败", "error");
        }
        throw err;
      }
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

    /**
     * 加载仪表盘数据
     */
    async loadDashboard() {
      this.loading = true;
      this.error = null;
      try {
        const [listData, statusData] = await Promise.all([
          api.list(),
          api.getStatus().catch(() => null),
        ]);
        this.projects = listData && listData.items ? listData.items : [];
        this.statusSummary = statusData;
        this.recentUpdates = (statusData && statusData.recent) || [];
      } catch (err) {
        this.error = err.message || "加载仪表盘失败";
      } finally {
        this.loading = false;
      }
    },

    /**
     * 初始化应用
     */
    async init() {
      // 恢复主题
      const savedTheme = localStorage.getItem("myknowledge-theme") || "system";
      const savedDesign = localStorage.getItem("myknowledge-design") || "raycast";
      this.theme = savedTheme;
      this.designTheme = savedDesign;
      this.applyTheme();

      // 加载锁状态、项目列表和用户身份
      await Promise.all([
        this.checkLock(),
        this.loadProjects(),
        this.loadIdentity(),
      ]);

      // 启动锁轮询
      setInterval(() => this.checkLock(), 15000);

      // 订阅 SSE 实时更新 — KB 有变更时自动重新加载当前视图
      api.subscribeEvents(() => {
        const view = this.currentView;
        if (view === "dashboard") {
          this.loadDashboard();
        } else if (view === "project" && this.currentPath) {
          this.loadProjectDocuments(this.currentPath);
        } else if ((view === "view" || view === "edit") && this.currentPath) {
          this.loadDocument(this.currentPath);
        }
      });

      // 处理初始 hash
      this.handleRoute();
      window.addEventListener("hashchange", () => this.handleRoute());

      // 首次使用：未设置身份时强制到 setup
      if (!this.identitySet) {
        window.location.hash = "setup";
      }
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
