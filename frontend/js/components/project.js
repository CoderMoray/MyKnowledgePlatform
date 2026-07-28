document.addEventListener("alpine:init", () => {
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
  }))
});
