document.addEventListener("alpine:init", () => {
Alpine.data("docComponent", () => ({
    editorInstance: null,
    editorReady: false,
    titleValue: "",
    summaryValue: "",
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
      this.$nextTick(() => {
        this.initEditor();
        this._bindViewerRefLinks(store);  // 立即绑定阅读态 ref 链接
      });
    },

    /* --- 阅读态 --- */

    async openRefPopover(el, refPath) {
      this.refLoading = true;
      this.refPreview = await loadRefPreview(refPath);
      this.refLoading = false;
      if (!this.refPreview) return;
      this._showRefCard(el, this.refPreview, refPath);
    },

    closePopover() {
      this._hideRefCard();
      this.refPreview = null;
    },

    cancelHoverClose() {
      clearTimeout(this._hoverTimer);
    },

    goToRef(path) {
      this._hideRefCard(true);
      window.location.hash = "doc/" + hashEncode(path);
    },

    /** 创建并展示 ref 悬浮卡片（DOM 直接管理） */
    _showRefCard(linkEl, preview, refPath) {
      const existing = document.getElementById("ref-card");
      if (existing) existing.remove();

      const card = document.createElement("div");
      card.id = "ref-card";
      card.className = "ref-card";

      const author = preview.author || "";
      const updated = preview.updated ? formatDate(preview.updated) : "";
      const summary = preview.summary || "";

      // 生成来源面包屑 HTML
      const sourceHtml = (preview.source || []).map((crumb, i) => {
        if (crumb.path) {
          return `<a class="ref-card__crumb" data-crumb="${crumb.path}" href="#project/${encodeURIComponent(crumb.path)}">${escapeHtml(crumb.label)}</a>`;
        }
        return `<span class="ref-card__crumb">${escapeHtml(crumb.label)}</span>`;
      }).join(' <span class="ref-card__sep">/</span> ');
      const sourceBlock = sourceHtml ? `<div class="ref-card__source">${sourceHtml}</div>` : "";

      card.innerHTML = `
        <div class="ref-card__title">${escapeHtml(preview.title)}</div>
        ${sourceBlock}
        <div class="ref-card__meta">${author}${updated ? " · 更新于 " + updated : ""}</div>
        <div class="ref-card__divider"></div>
        <div class="ref-card__summary">${escapeHtml(summary)}</div>
        <div class="ref-card__footer">
          <span class="ref-card__open">打开文档 →</span>
        </div>
      `;

      // 点击面包屑 → 跳转项目
      card.querySelectorAll(".ref-card__crumb[data-crumb]").forEach((el) => {
        el.addEventListener("click", (e) => {
          e.preventDefault();
          this._hideRefCard(true);
          window.location.hash = "project/" + el.dataset.crumb;
        });
      });

      // 点击 "打开文档"
      card.querySelector(".ref-card__open").addEventListener("click", () => {
        this.goToRef(refPath);
      });

      // 鼠标移入卡片 → 取消关闭定时器
      card.addEventListener("mouseenter", () => {
        clearTimeout(this._hoverTimer);
      });
      card.addEventListener("mouseleave", () => {
        this._hoverTimer = setTimeout(() => this.closePopover(), 300);
      });

      document.body.appendChild(card);

      // 定位：链接右下方
      const linkRect = linkEl.getBoundingClientRect();
      const cardWidth = 300;
      let left = linkRect.right + 8;
      let top = linkRect.top - 4;
      // 确保不超出右边界
      if (left + cardWidth > window.innerWidth - 16) {
        left = window.innerWidth - cardWidth - 16;
      }
      // 确保不超出上边界
      if (top < 8) top = linkRect.bottom + 4;

      card.style.left = left + "px";
      card.style.top = top + "px";
      card.style.position = "fixed";

      // 入场动画：从链接位置向右下放大+淡入
      requestAnimationFrame(() => {
        card.classList.add("ref-card--enter");
      });
    },

    /** 隐藏并销毁 ref 卡片 */
    _hideRefCard(instant) {
      const card = document.getElementById("ref-card");
      if (!card) return;
      if (instant) {
        card.remove();
        return;
      }
      card.classList.remove("ref-card--enter");
      card.classList.add("ref-card--exit");
      card.addEventListener("transitionend", () => card.remove(), { once: true });
    },

    /** 阅读态 ref 链接事件委托（viewer__body 容器） */
    _bindViewerRefLinks(store) {
      const viewer = document.getElementById("viewer-content");
      if (!viewer || this._viewerBound) return;
      this._viewerBound = true;
      this._hoverTimer = null;
      const self = this;

      const findRefLink = (target) => {
        let el = target;
        while (el && el !== viewer) {
          if (el.tagName === "A" && el.title.startsWith("关联文档:")) return el;
          el = el.parentElement;
        }
        return null;
      };

      viewer.addEventListener("mouseover", (e) => {
        const link = findRefLink(e.target);
        if (!link) return;
        if (store.editingMode || store.isLocked) return;
        clearTimeout(self._hoverTimer);
        const refPath = link.title.replace(/^关联文档:\s*/, "").trim();
        if (refPath) {
          self._hoverTimer = setTimeout(() => {
            self.openRefPopover(link, refPath);
          }, 200);
        }
      });

      viewer.addEventListener("mouseout", (e) => {
        const link = findRefLink(e.relatedTarget);
        if (link) return;
        clearTimeout(self._hoverTimer);
        self._hoverTimer = setTimeout(() => self.closePopover(), 300);
      });
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

    /** 点击正文 → 进入编辑 */
    enterEdit() {
      const store = Alpine.store("app");
      if (store.isLocked) return;
      store.setView("edit", store.currentPath);
      // TipTap DOM 渲染后才创建编辑器
      this.$nextTick(() => this.initEditor());
    },

    /** 点击外部 → 退出编辑并保存 */
    async exitEdit() {
      const store = Alpine.store("app");
      if (store.currentView !== "edit" || !this.editorInstance) return;

      const html = this.editorInstance.getHTML();
      if (!html || html === "<p></p>" || html.trim() === "") {
        this.editorInstance.destroy();
        this.editorInstance = null;
        this.editorReady = false;
        store.setView("view", store.currentPath);
        store.loadDocument(store.currentPath);
        return;
      }

      // 预处理 TipTap HTML
      const tmp = document.createElement("div");
      tmp.innerHTML = html;
      // 恢复 ref 链接：data-ref-path → href="ref:path"
      tmp.querySelectorAll("[data-ref-path]").forEach(a => {
        a.setAttribute("href", "ref:" + a.dataset.refPath);
      });
      // 清理列表内的多余 <p>，避免 turndown 产生空行
      tmp.querySelectorAll("li p").forEach(p => {
        const parent = p.parentNode;
        while (p.firstChild) parent.insertBefore(p.firstChild, p);
        parent.removeChild(p);
      });
      const cleanHtml = tmp.innerHTML;

      // HTML → Markdown（turndown）
      const td = new TurndownService({ headingStyle: "atx", bulletListMarker: "-" });
      let markdown = td.turndown(cleanHtml);

      // turndown 编码了 ref: 中的空格，还原
      markdown = markdown.replace(/\(ref:([^)]+)\)/g, (m, url) => "(ref:" + url.replace(/%20/g, " ") + ")");

      this.editorInstance.destroy();
      this.editorInstance = null;
      this.editorReady = false;

      const title = store.document?.title || "";
      const fullMd = `# ${title}\n\n${markdown}`;
      try {
        await store.saveDocument(store.currentPath, { content: fullMd, summary: store.document?.summary || "" });
      } catch (e) {}

      store.setView("view", store.currentPath);
      store.loadDocument(store.currentPath);
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
        editorProps: {
          attributes: { class: "ProseMirror" },
        },
        onUpdate: () => { store.isDirty = true; },
        onCreate: ({ editor }) => {
          const content = store.htmlContent || (store.document && store.document.content) || "";
          if (content) {
            editor.commands.setContent(content);
          }
        },
      });

      store.editor = this.editorInstance;
      this.editorReady = true;

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
