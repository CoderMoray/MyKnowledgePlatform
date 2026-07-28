document.addEventListener("alpine:init", () => {
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
        window.location.hash = `doc/${encodeURIComponent(store.currentPath)}`;
      } else {
        window.location.hash = "dashboard";
      }
    },
  }))
});


window._mykBindToolbar === "function") {
        window._mykBindToolbar(this.editorInstance);
      }
