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
    loading: true,

    /** 错误信息 */
    error: null,

    /* ── 锁状态 ────────────────────────────────────────────────────────── */

    /** 是否被锁定 */
    isLocked: false,

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
      this.document = { ...this.document, ...data };
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
