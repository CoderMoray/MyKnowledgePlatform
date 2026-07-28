document.addEventListener("alpine:init", () => {
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
      window.location.hash = "doc/" + encodeURIComponent(path);
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
  }))
});
