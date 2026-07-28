document.addEventListener("alpine:init", () => {
Alpine.data("docComponent", () => ({
    editorInstance: null,
    titleValue: "",
    summaryValue: "",
    saving: false,
    refPreview: null,
    refLoading: false,

    init() {
      const store = Alpine.store("app");
      const path = store.currentPath;

      // 非阻塞加载：store 可能已有 document（由 router 预先加载）
      if (!store.document && path) {
        store.loadDocument(path);
      }

      this.titleValue = store.document?.title || "";
      this.summaryValue = store.document?.summary || "";
      this.$nextTick(() => this.initEditor());
    },

    /* --- 阅读态 --- */

    async openRefPopover(el, refPath) {
      const store = Alpine.store("app");
      this.refLoading = true;
      const rect = el.getBoundingClientRect();
      store.popoverPos = {
        top: Math.max(4, rect.top - 220),
        left: Math.max(8, rect.left),
      };
      store.popoverVisible = true;
      store.popoverRefPath = refPath;
      this.refPreview = await loadRefPreview(refPath);
      this.refLoading = false;
    },

    closePopover() {
      const store = Alpine.store("app");
      store.hidePopover();
      this.refPreview = null;
    },

    cancelHoverClose() {
      clearTimeout(this._hoverTimer);
    },

    goToRef(path) {
      this.closePopover();
      window.location.hash = "doc/" + encodeURIComponent(path);
    },

    confirmDelete() {
      const store = Alpine.store("app");
      store.openModal("delete-doc", {
        path: store.currentPath,
        title: store.document?.title || fileName(store.currentPath),
      });
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

    /* --- 编辑态 --- */

    enterEdit() {
      const store = Alpine.store("app");
      if (store.isLocked || !this.editorInstance) return;
      if (this.editorInstance.isEditable) return;
      this.editorInstance.setEditable(true);
      store.editingMode = true;
    },

    exitEdit() {
      const store = Alpine.store("app");
      if (!store.editingMode || !this.editorInstance) return;
      this.editorInstance.setEditable(false);
      store.editingMode = false;
    },

    async initEditor() {
      const el = document.getElementById("tiptap-editor");
      if (!el || this.editorInstance) return;

      const store = Alpine.store("app");

      await this.waitForTipTap();

      const { Editor } = window.TipTapCore || {};
      const StarterKit = window.TipTapStarterKit ? window.TipTapStarterKit.StarterKit : null;
      const LinkExt = window.TipTapLink || null;
      console.log("[doc] Editor:", !!Editor, "StarterKit:", !!StarterKit, "LinkExt:", !!LinkExt);
      if (!Editor) return;

      const extensions = [
        StarterKit ? StarterKit.configure() : null,
        LinkExt ? LinkExt.configure({ openOnClick: false }) : null,
      ].filter(Boolean);
      console.log("[doc] extensions count:", extensions.length);

      this.editorInstance = new Editor({
        element: el,
        extensions,
        content: store.htmlContent,
        editable: false,
        editorProps: {
          attributes: { class: "ProseMirror ProseMirror--readonly" },
        },
        onUpdate: () => { store.isDirty = true; },
      });

      store.editor = this.editorInstance;

      if (typeof window._mykBindToolbar === "function") {
        window._mykBindToolbar(this.editorInstance);
      }

      // ref 链接 hover
      this._hoverTimer = null;
      const pmRoot = el.querySelector(".ProseMirror");
      if (pmRoot) {
        const self = this;
        const bindRefLinks = () => {
          pmRoot.querySelectorAll("a").forEach((link) => {
            const title = link.getAttribute("title") || "";
            if (!title.startsWith("关联文档:") || link.dataset._refBound) return;
            link.dataset._refBound = "1";

            link.addEventListener("mouseenter", () => {
              if (store.editingMode || store.isLocked) return;
              clearTimeout(self._hoverTimer);
              const refPath = title.replace(/^关联文档:\s*/, "").trim();
              if (refPath) {
                self._hoverTimer = setTimeout(() => {
                  self.openRefPopover(link, refPath);
                }, 200);
              }
            });

            link.addEventListener("mouseleave", () => {
              clearTimeout(self._hoverTimer);
              self._hoverTimer = setTimeout(() => {
                self.closePopover();
              }, 300);
            });
          });
        };

        bindRefLinks();
        let retries = 0;
        const retryBind = () => {
          if (retries++ < 10) {
            bindRefLinks();
            setTimeout(retryBind, 300);
          }
        };
        setTimeout(retryBind, 500);
      }

      requestAnimationFrame(() => {
        if (typeof hljs !== "undefined") {
          el.querySelectorAll("pre code").forEach((block) => {
            hljs.highlightElement(block);
          });
        }
      });
    },

    async waitForTipTap() {
      for (let i = 0; i < 50; i++) {
        if (window.TipTapCore && window.TipTapStarterKit) return;
        await new Promise((r) => setTimeout(r, 100));
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

        store.editingMode = false;
      } catch {
      } finally {
        this.saving = false;
      }
    },
  }));
});
