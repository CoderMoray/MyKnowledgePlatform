document.addEventListener("alpine:init", () => {
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
      window.location.hash = `doc/${hashEncode(path)}`;
    },

    goToEdit() {
      const store = Alpine.store("app");
      if (store.currentPath) {
        window.location.hash = `edit/${hashEncode(store.currentPath)}`;
      }
    },

    confirmDelete() {
      const store = Alpine.store("app");
      store.openModal("delete-doc", {
        path: store.currentPath,
        title: store.document?.title || fileName(store.currentPath),
      });
    },
  }))
});
