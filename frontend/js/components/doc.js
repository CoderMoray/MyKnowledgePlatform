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

      // 切文档时销毁旧编辑器，防止内容串台
      if (this.editorInstance && this._lastDocPath !== path) {
        this.editorInstance.destroy();
        this.editorInstance = null;
        this.editorReady = false;
      }
      this._lastDocPath = path;

      if (!store.document && path) {
        store.loadDocument(path);
      }

      this.titleValue = store.document?.title || "";
      this.summaryValue = store.document?.summary || "";
      this.$nextTick(() => this._bindViewerRefLinks(store));
    },

    /* --- 阅读态 --- */

    async openRefPopover(el, refPath) {
      this.refLoading = true;
      this.refPreview = await loadRefPreview(refPath);
      this.refLoading = false;
      if (!this.refPreview) {
        this._showDeadRefCard(el, refPath);
        return;
      }
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
        this._hoverTimer = setTimeout(() => this.closePopover(), 200);
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

    /** 外部链接卡片 — 纯文本，不调 API */
    _showExtCard(linkEl, url) {
      const existing = document.getElementById("ref-card");
      if (existing) existing.remove();

      const card = document.createElement("div");
      card.id = "ref-card";
      card.className = "ref-card";

      card.innerHTML = `
        <div class="ref-card__title">${escapeHtml(linkEl.textContent.trim())}</div>
        <div class="ref-card__source" style="word-break:break-all;font-size:11px;color:var(--text-tertiary)">${escapeHtml(url)}</div>
        <div class="ref-card__divider"></div>
        <div class="ref-card__summary" style="color:var(--text-tertiary)">外部链接，不在知识库内</div>
        <div class="ref-card__footer" style="justify-content:flex-end">
          <span class="ref-card__open">打开链接 ↗</span>
        </div>
      `;

      card.querySelector(".ref-card__open").addEventListener("click", () => {
        window.open(url, "_blank", "noopener");
        this._hideRefCard(true);
      });

      this._attachCardEvents(card, linkEl);
    },

    /** 死链卡片 — ref 文档不存在 */
    _showDeadRefCard(linkEl, refPath) {
      const existing = document.getElementById("ref-card");
      if (existing) existing.remove();

      const card = document.createElement("div");
      card.id = "ref-card";
      card.className = "ref-card";

      card.innerHTML = `
        <div class="ref-card__title">${escapeHtml(linkEl.textContent.trim())}</div>
        <div class="ref-card__source" style="word-break:break-all;font-size:11px;color:var(--text-tertiary)">${escapeHtml(refPath)}</div>
        <div class="ref-card__divider"></div>
        <div class="ref-card__summary" style="color:var(--color-danger)">引用的知识文件不存在或已被删除</div>
        <div class="ref-card__footer" style="justify-content:flex-end;font-size:11px;color:var(--text-tertiary)">ref 链接指向的文档路径无效</div>
      `;

      this._attachCardEvents(card, linkEl);
    },

    /** 卡片共通定位和事件 */
    _attachCardEvents(card, linkEl) {
      card.addEventListener("mouseenter", () => clearTimeout(this._hoverTimer));
      card.addEventListener("mouseleave", () => {
        this._hoverTimer = setTimeout(() => this.closePopover(), 200);
      });
      document.body.appendChild(card);
      const linkRect = linkEl.getBoundingClientRect();
      const cardWidth = 300;
      let left = linkRect.right + 8;
      let top = linkRect.top - 4;
      if (left + cardWidth > window.innerWidth - 16) left = window.innerWidth - cardWidth - 16;
      if (top < 8) top = linkRect.bottom + 4;
      card.style.left = left + "px";
      card.style.top = top + "px";
      card.style.position = "fixed";

      requestAnimationFrame(() => card.classList.add("ref-card--enter"));
    },

    /** 阅读态 ref 链接事件委托（viewer__body 容器） */
    /** 编辑态 AI 锁遮罩：locked = 红框模糊，unlocked = 绿框淡出 */
    _showLockOverlay(state) {
      let el = document.getElementById("editor-lock-overlay");
      if (state === "locked") {
        if (el) return;
        el = document.createElement("div");
        el.id = "editor-lock-overlay";
        el.innerHTML = '<div class="editor-lock-text">AI 编辑中，用户编辑功能暂时锁定。</div>';
        document.getElementById("content-panel").appendChild(el);
        requestAnimationFrame(() => el.classList.add("editor-lock--active"));
      } else if (state === "unlocked" && el) {
        el.classList.add("editor-lock--switch");
        setTimeout(() => {
          el.querySelector(".editor-lock-text").textContent = "AI 编辑结束，已解锁";
          el.classList.remove("editor-lock--switch");
        }, 120);
      }
    },

    _bindViewerRefLinks(store) {
      const viewer = document.getElementById("viewer-content");
      if (!viewer || this._viewerBound) return;
      this._viewerBound = true;
      this._hoverTimer = null;
      const self = this;

      const findLink = (target) => {
        let el = target;
        while (el && el !== viewer) {
          if (el.tagName === "A") {
            if (el.classList.contains("ref-link")) return { el, type: "ref", path: el.dataset.refPath };
            if (el.classList.contains("ext-link")) return { el, type: "ext", url: el.dataset.extLink };
          }
          el = el.parentElement;
        }
        return null;
      };

      viewer.addEventListener("mouseover", (e) => {
        const link = findLink(e.target);
        if (!link) return;
        if (store.editingMode || store.isLocked) return;
        clearTimeout(self._hoverTimer);
        self._hoverTimer = setTimeout(() => {
          if (link.type === "ext") {
            self._showExtCard(link.el, link.url);
          } else if (link.type === "ref") {
            self.openRefPopover(link.el, link.path);
          }
        }, 200);
      });

      viewer.addEventListener("mouseout", (e) => {
        const link = findLink(e.relatedTarget);
        if (link) return;
        clearTimeout(self._hoverTimer);
        self._hoverTimer = setTimeout(() => self.closePopover(), 200);
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
    async enterEdit() {
      const store = Alpine.store("app");
      if (store.isLocked) return;
      let content = store.htmlContent;
      if (!content || !content.trim()) {
        await store.loadDocument(store.currentPath);
        content = store.htmlContent;
      }
      store.setView("edit", store.currentPath);
      this.$nextTick(() => {
        requestAnimationFrame(() => {
          this.initEditor(content);
        });
      });
    },

    /** 点击外部 → 退出编辑并保存 */
    async exitEdit() {
      const store = Alpine.store("app");
      if (store.currentView !== "edit" || !this.editorInstance) return;
      if (store.isLocked) return; // AI 锁定时禁止退出编辑

      // 从编辑器 DOM 直接取 HTML（getHTML 会丢掉 tableWrapper）
      const html = this.editorInstance.view ? this.editorInstance.view.dom.innerHTML : this.editorInstance.getHTML();
      if (!html || html === "<p></p>" || html.trim() === "") {
        this.editorInstance.setEditable(false);
        store.setView("view", store.currentPath);
        return;
      }

      // 预处理 TipTap HTML
      const tmp = document.createElement("div");
      tmp.innerHTML = html;
      // 去掉 ProseMirror 产生的空 h1（标题在 header 显示）
      const h1 = tmp.querySelector("h1");
      if (h1 && !h1.textContent.trim()) h1.remove();
      // 恢复 ref 链接：data-ref-path → href="ref:path"
      tmp.querySelectorAll("[data-ref-path]").forEach(a => {
        a.setAttribute("href", "ref:" + a.dataset.refPath);
      });
      // 清理列表内的多余 <p>
      tmp.querySelectorAll("li p").forEach(p => {
        const parent = p.parentNode;
        while (p.firstChild) parent.insertBefore(p.firstChild, p);
        parent.removeChild(p);
      });
      // TipTap 表格 → 纯文本标记（无特殊字符，turndown 不动）
      const tableMarkers = [];
      tmp.querySelectorAll(".tableWrapper").forEach((wrapper, idx) => {
        const table = wrapper.querySelector("table");
        if (!table) return;
        const rows = [];
        table.querySelectorAll("tr").forEach(tr => {
          const cells = [];
          tr.querySelectorAll("th, td").forEach(c => cells.push(c.textContent.trim()));
          rows.push("| " + cells.join(" | ") + " |");
        });
        if (rows.length > 0) {
          // 保留原始 md 分隔符格式
          const mdContent = store.document?.content || "";
          const sepMatch = mdContent.match(/^\|[ -:|]+\|/m);
          const sep = sepMatch ? sepMatch[0] : "";
          const cols = table.querySelector("tr").querySelectorAll("th, td").length;
          if (sep && sep.split("|").length - 2 === cols) {
            rows.splice(1, 0, sep);
          } else {
            rows.splice(1, 0, "| " + "--- | ".repeat(cols).trimEnd());
          }
        }
        const marker = "MYKTABLE" + idx + "MARK";
        tableMarkers.push({ marker, md: rows.join("\n") });
        wrapper.replaceWith(document.createTextNode(marker));
      });
      // 链接修复：Turndown 自定义规则从 data-myk-href 取值
      const linkRule = {
        filter: (node) => node.nodeName === "A",
        replacement: (content, node) => {
          let href = node.getAttribute("href") || "";
          if (href.startsWith("ref:")) {
            const ref = href.slice(4).replace(/%20/g, " ");
            return "[" + (node.textContent || content) + "](ref:" + ref + ")";
          }
          return "[" + (node.textContent || content) + "](" + href + ")";
        }
      };
      const cleanHtml = tmp.innerHTML;

      // HTML → Markdown（turndown + 自定义规则）
      const td = new TurndownService({ headingStyle: "atx", bulletListMarker: "-", codeBlockStyle: "fenced", emDelimiter: "*" });
      // 删除线
      td.addRule("strikethrough", { filter: ["s", "del", "strike"], replacement: (c) => "~~" + c + "~~" });
      // 代码块：强制用 ``` 围栏式
      td.addRule("fencedCode", {
        filter: (node) => node.nodeName === "PRE" && node.firstChild && node.firstChild.nodeName === "CODE",
        replacement: (_, node) => {
          const lang = (node.firstChild.className || "").replace("language-", "");
          return "\n\n```" + lang + "\n" + node.firstChild.textContent.trimEnd() + "\n```\n\n";
        }
      });
      td.addRule("mykLink", linkRule);
      let markdown = td.turndown(cleanHtml);

      // 还原表格标记
      tableMarkers.forEach(({ marker, md }) => {
        markdown = markdown.replace(marker, md);
      });

      // turndown 后处理
      markdown = markdown.replace(/\(ref:([^)]+)\)/g, (m, url) => "(ref:" + url.replace(/%20/g, " ") + ")");
      markdown = markdown.replace(/^(\s*[-*+])\s{2,}/gm, "$1 ");
      markdown = markdown.replace(/^(\s*\d+\.)\s{2,}/gm, "$1 ");
      markdown = markdown.replace(/^(> .*?)\s\s+$/gm, "$1");

      const title = store.document?.title || "";
      // 如果正文已包含标题 h1，不再重复
      const firstLine = markdown.trim().split("\n")[0];
      const fullMd = firstLine.startsWith("# ") ? markdown : `# ${title}\n\n${markdown}`;
      try {
        await store.saveDocument(store.currentPath, { content: fullMd, summary: store.document?.summary || "" });
      } catch (e) {}

      // 销毁编辑器，下次进入重新创建（避免 ProseMirror 状态错乱）
      if (this.editorInstance) {
        this.editorInstance.destroy();
        this.editorInstance = null;
      }
      store.setView("view", store.currentPath);
      store.loadDocument(store.currentPath);
    },

    async initEditor(initialContent) {
      const el = document.getElementById("tiptap-editor");
      if (!el || this.editorInstance) return;

      const store = Alpine.store("app");

      await this.waitForTipTap();

      const { Editor } = window.TipTapCore || {};
      const StarterKit = window.TipTapStarterKit ? window.TipTapStarterKit.StarterKit : null;
      const LinkExt = window.TipTapLink || null;
      const TT = window.TipTapTable || {};
      console.log("[doc] Editor:", !!Editor, "StarterKit:", !!StarterKit, "LinkExt:", !!LinkExt);
      if (!Editor) return;

      // 自定义 Link 扩展：修复 2.1.13 的 href 序列化 bug
      // ref: https://github.com/ueberdosis/tiptap/issues/4929
      const PatchedLink = LinkExt ? LinkExt.extend({
        addAttributes() {
          return {
            ...this.parent?.(),
            href: {
              default: null,
              parseHTML(element) {
                return element.getAttribute('href');
              },
            }
          };
        },
      }).configure({ openOnClick: false }) : null;

      const extensions = [
        StarterKit ? StarterKit.configure() : null,
        PatchedLink,
        TT.Table ? TT.Table.configure({ resizable: true }) : null,
        TT.TableRow || null,
        TT.TableCell || null,
        TT.TableHeader || null,
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
          const html = initialContent || store.htmlContent || (store.document && store.document.content) || "";
          if (html) {
            const tmp = document.createElement("div");
            tmp.innerHTML = html;
            tmp.querySelectorAll("[data-ref-path]").forEach(a => {
              const section = a.dataset.refSection ? "::" + a.dataset.refSection : "";
              a.setAttribute("href", "ref:" + a.dataset.refPath + section);
            });
            // 延迟设置内容，避免 onCreate 内的事务冲突
            requestAnimationFrame(() => {
              editor.commands.setContent(tmp.innerHTML);
            });
          }
        },
      });

      store.editor = this.editorInstance;
      this.editorReady = true;

      // CMD+S / Ctrl+S 保存（全局监听，只在编辑态生效）
      document.addEventListener("keydown", (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "s" && store.currentView === "edit" && !store.isLocked) {
          e.preventDefault();
          e.stopPropagation();
          this.exitEdit();
        }
      });

      if (typeof window._mykBindToolbar === "function") {
        window._mykBindToolbar(this.editorInstance);
      }

      // AI 锁态监听：编辑中被锁 → 只读 + 红框遮罩，解锁 → 绿过渡淡出
      Alpine.effect(() => {
        if (!this.editorInstance) return;
        const panel = document.getElementById("content-panel");
        if (store.isLocked && store.currentView === "edit") {
          this.editorInstance.setEditable(false);
          if (panel) panel.classList.add("content-panel--locked");
          this._showLockOverlay("locked");
        } else if (!store.isLocked && document.getElementById("editor-lock-overlay")) {
          this._showLockOverlay("unlocked");
          if (panel) {
            panel.classList.remove("content-panel--locked");
            panel.classList.add("content-panel--unlocking");
          }
          setTimeout(() => {
            const el = document.getElementById("editor-lock-overlay");
            if (el) {
              el.classList.add("editor-lock--exit");
              setTimeout(() => {
                el.remove();
                this.editorInstance && this.editorInstance.setEditable(true);
                if (panel) panel.classList.remove("content-panel--unlocking");
              }, 480);
            } else {
              this.editorInstance && this.editorInstance.setEditable(true);
              if (panel) panel.classList.remove("content-panel--unlocking");
            }
          }, 2400);
        }
      });

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
