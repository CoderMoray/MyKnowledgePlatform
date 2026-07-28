document.addEventListener("alpine:init", () => {
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
      window.location.hash = "doc/" + encodeURIComponent(docPath);
    },

    newDocument() {
      const store = Alpine.store("app");
      store.openModal("new-doc", {
        parentPath: store.currentPath || "",
      });
    },
  }))
});
