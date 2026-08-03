/* ==========================================================================
   IndexedDB 离线草稿（DB MyKnowledgeDrafts / store drafts / key=文档 path）
   ========================================================================== */
const DRAFT_DB = "MyKnowledgeDrafts";
const DRAFT_STORE = "drafts";

function _openDraftDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DRAFT_DB, 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(DRAFT_STORE)) {
        req.result.createObjectStore(DRAFT_STORE, { keyPath: "path" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function _draftSave(path, value) {
  return _openDraftDB().then((db) => new Promise((resolve, reject) => {
    const tx = db.transaction(DRAFT_STORE, "readwrite");
    tx.objectStore(DRAFT_STORE).put({ path, ...value });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  }));
}

function _draftGet(path) {
  return _openDraftDB().then((db) => new Promise((resolve, reject) => {
    const req = db.transaction(DRAFT_STORE).objectStore(DRAFT_STORE).get(path);
    req.onsuccess = () => resolve(req.result || null);
    req.onerror = () => reject(req.error);
  }));
}

function _draftDelete(path) {
  return _openDraftDB().then((db) => new Promise((resolve, reject) => {
    const tx = db.transaction(DRAFT_STORE, "readwrite");
    tx.objectStore(DRAFT_STORE).delete(path);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  }));
}

document.addEventListener("alpine:init", () => {
// Editor 实例存模块级变量（非 Alpine 响应式数据）：
// Alpine 的 reactive Proxy 会深度包装对象，破坏 ProseMirror 内部引用一致性
// （tr.before !== state、instanceof 失效），导致 mismatched transaction 等诡异问题。
let _editorInstance = null;
Alpine.data("docComponent", () => ({
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
      if (_editorInstance && this._lastDocPath !== path) {
        _editorInstance.destroy();
        _editorInstance = null;
        window.__mykEditor = null;
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
      if (store.isLocked || this._entering) return;
      this._entering = true; // 重入锁：防止 $nextTick 竞态下多次初始化编辑器
      try {
        this._editingPath = store.currentPath; // 记录编辑的文档，返回/导航后仍能正确保存
        let content = store.htmlContent;
        if (!content || !content.trim()) {
          await store.loadDocument(store.currentPath);
          content = store.htmlContent;
        }
        store.setView("edit", store.currentPath);
        await new Promise(r => this.$nextTick(r));
        this.initEditor(content);
      } finally {
        this._entering = false;
      }
    },

    /**
     * 编辑区点击处理：仅当点击真正发生在编辑器容器外部时才退出编辑。
     * 不用 @click.outside —— ProseMirror 在 selection 变化时重建 DOM，
     * click 的 target 可能变成已脱离文档的节点，contains() 误判为外部，
     * 导致拖选文字时误退出编辑。
     */
    onEditorAreaClick(e) {
      if (!e || !e.target) return;
      const shell = this.$el.querySelector(".editor-shell");
      if (!shell) return;
      const inEditor = e.target.isConnected && shell.contains(e.target);
      if (!inEditor) this.exitEdit();
    },

    /** 点击外部 → 退出编辑并保存 */
    async exitEdit() {
      const store = Alpine.store("app");
      if (store.currentView !== "edit" || !_editorInstance) return;
      if (store.isLocked) return; // AI 锁定时禁止退出编辑

      // 保存用进入编辑时记录的路径；导航已离开本文档时不重载、不切 view
      const path = this._editingPath || store.currentPath;
      const stillOnDoc = store.currentPath === path;

      // 从编辑器 DOM 直接取 HTML（getHTML 会丢掉 tableWrapper）
      const html = _editorInstance.view ? _editorInstance.view.dom.innerHTML : _editorInstance.getHTML();
      if (!html || html === "<p></p>" || html.trim() === "") {
        _editorInstance.setEditable(false);
        if (stillOnDoc) store.setView("view", path);
        return;
      }

      const fullMd = this._editorToMarkdown();
      if (fullMd) {
        try {
          await store.saveDocument(path, { content: fullMd, summary: store.document?.summary || "" });
        } catch (e) {}
      }

      // 销毁编辑器，下次进入重新创建（避免 ProseMirror 状态错乱）
      if (_editorInstance) {
        _editorInstance.destroy();
        _editorInstance = null;
      }
      this._editingPath = null;
      // 仅当用户仍停留在本文档时才切回阅读态并重载
      if (stillOnDoc) {
        store.setView("view", path);
        store.loadDocument(path);
      }
    },

    /** 编辑器 DOM → Markdown（exitEdit 与自动保存共用） */
    _editorToMarkdown() {
      const store = Alpine.store("app");
      const ed = _editorInstance;
      if (!ed) return "";
      const html = ed.view ? ed.view.dom.innerHTML : ed.getHTML();
      if (!html || html === "<p></p>" || html.trim() === "") return "";

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
      return firstLine.startsWith("# ") ? markdown : `# ${title}\n\n${markdown}`;
    },

    async initEditor(initialContent) {
      const el = document.getElementById("tiptap-editor");
      if (!el || _editorInstance) return;

      const store = Alpine.store("app");

      await this.waitForTipTap();

      const { Editor, Extension } = window.TipTapCore || {};
      const StarterKit = window.TipTapStarterKit ? window.TipTapStarterKit.StarterKit : null;
      const LinkExt = window.TipTapLink || null;
      const TT = window.TipTapTable || {};
      const TM = window.TipTapMenu || {};
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
        TM.SlashCommand ? TM.SlashCommand.configure(this._buildSlashOptions(TM.SlashCommand)) : null,
      ].filter(Boolean);
      console.log("[doc] extensions count:", extensions.length);

      // 非响应式调试引用（避免 Alpine proxy 包装，供 console/自动化测试）
      window.__mykEditor = null;
      _editorInstance = new Editor({
        element: el,
        extensions,
        editorProps: {
          // 复用 markdown-body 排版，保证阅读态/编辑态视觉一致
          attributes: { class: "ProseMirror markdown-body" },
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
            editor.commands.setContent(tmp.innerHTML);
          }
        },
      });

      window.__mykEditor = _editorInstance;
      this.editorReady = true;

      // 自动保存：update 事件 → debounce（任务 14 实现）
      this._setupAutosave();
      // 浮动格式条：自实现定位（绕开官方 BubbleMenu 的 tippy 依赖）
      this._setupBubbleMenu();
      // 关页面前强制写草稿
      this._bindBeforeUnloadDraft();

      // CMD+S / Ctrl+S 保存（全局监听，只在编辑态生效）
      document.addEventListener("keydown", (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "s" && store.currentView === "edit" && !store.isLocked) {
          e.preventDefault();
          e.stopPropagation();
          this.exitEdit();
        }
      });

      // AI 锁态监听：编辑中被锁 → 只读 + 红框遮罩，解锁 → 绿过渡淡出
      Alpine.effect(() => {
        if (!_editorInstance) return;
        const panel = document.getElementById("content-panel");
        if (store.isLocked && store.currentView === "edit") {
          _editorInstance.setEditable(false);
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
                _editorInstance && _editorInstance.setEditable(true);
                if (panel) panel.classList.remove("content-panel--unlocking");
              }, 480);
            } else {
              _editorInstance && _editorInstance.setEditable(true);
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

    /* --- BubbleMenu / SlashCommand --- */

    /** 自实现浮动格式条：监听 selection，手动定位显示（绕开官方 BubbleMenu 的 tippy） */
    _setupBubbleMenu() {
      const ed = _editorInstance;
      if (!ed || this._bubbleBound) return;
      this._bubbleBound = true;

      // 构建按钮 DOM（一次性）
      const old = document.getElementById("bubble-menu");
      if (old) old.remove();
      const el = document.createElement("div");
      el.id = "bubble-menu";
      el.className = "bubble-menu";
      const shell = document.querySelector(".editor-shell");
      (shell || document.body).appendChild(el);
      const defs = [
        { action: "bold", title: "加粗", label: "<b>B</b>" },
        { action: "italic", title: "斜体", label: "<i>I</i>" },
        { action: "strike", title: "删除线", label: "<s>S</s>" },
        { action: "code", title: "行内代码", label: "&lt;/&gt;" },
        { sep: true },
        { action: "link", title: "添加链接", label: "&#128279;" },
      ];
      defs.forEach(d => {
        if (d.sep) {
          const s = document.createElement("span");
          s.className = "bubble-menu__sep";
          el.appendChild(s);
          return;
        }
        const btn = document.createElement("button");
        btn.className = "bubble-menu__btn";
        btn.title = d.title;
        btn.dataset.bubbleAction = d.action;
        btn.innerHTML = d.label;
        btn.addEventListener("mousedown", (e) => e.preventDefault()); // 防止编辑器失焦丢选区
        btn.addEventListener("click", () => this._bubbleAction(d.action));
        el.appendChild(btn);
      });

      // selection 变化 → 显示/隐藏 + 定位
      const update = () => {
        if (!ed.isFocused && ed.state.selection.empty) { el.classList.remove("is-active"); return; }
        const sel = ed.state.selection;
        const hasSel = !sel.empty;
        const isLink = ed.isActive("link");
        if (!hasSel && !isLink) { el.classList.remove("is-active"); return; }
        // 定位到选区（to 端）
        const coords = ed.view.coordsAtPos(sel.to);
        el.style.left = Math.min(coords.left, window.innerWidth - 200) + "px";
        el.style.top = (coords.top - 44) + "px";
        el.classList.add("is-active");
        el.querySelectorAll("[data-bubble-action]").forEach(b => {
          const act = b.dataset.bubbleAction;
          let active = false;
          if (act === "bold") active = ed.isActive("bold");
          else if (act === "italic") active = ed.isActive("italic");
          else if (act === "strike") active = ed.isActive("strike");
          else if (act === "code") active = ed.isActive("code");
          else if (act === "link") active = isLink;
          b.classList.toggle("is-active", active);
        });
      };
      ed.on("selectionUpdate", update);
      ed.on("transaction", update);
    },

    /** BubbleMenu 按钮点击分发 */
    _bubbleAction(action) {
      const ed = _editorInstance;
      if (!ed) return;
      if (action === "bold") ed.commands.toggleBold();
      else if (action === "italic") ed.commands.toggleItalic();
      else if (action === "strike") ed.commands.toggleStrike();
      else if (action === "code") ed.commands.toggleCode();
      else if (action === "link") this._bubbleLink();
    },

    /** 链接：无链接 → 提示输入；已有链接 → 取消 */
    _bubbleLink() {
      const ed = _editorInstance;
      if (!ed) return;
      if (ed.isActive("link")) {
        ed.commands.unsetLink();
        return;
      }
      const url = window.prompt("输入链接地址（外部 URL 或 ref:知识路径）", "");
      if (!url || !url.trim()) return;
      const href = url.trim().replace(/ /g, "%20");
      ed.chain().focus().setLink({ href }).run();
    },

    /** 构建 SlashCommand 选项（/ 唤出插入菜单，飞书斜杠菜单同款） */
    _buildSlashOptions(SlashCommandCls) {
      this._slashItems = [
        { type: "h1", name: "标题 1", desc: "一级大标题", icon: "H1", run: (ed) => ed.commands.toggleHeading({ level: 1 }) },
        { type: "h2", name: "标题 2", desc: "二级标题", icon: "H2", run: (ed) => ed.commands.toggleHeading({ level: 2 }) },
        { type: "h3", name: "标题 3", desc: "三级标题", icon: "H3", run: (ed) => ed.commands.toggleHeading({ level: 3 }) },
        { type: "bullet", name: "无序列表", desc: "项目符号列表", icon: "&bull;", run: (ed) => ed.commands.toggleBulletList() },
        { type: "ordered", name: "有序列表", desc: "编号列表", icon: "1.", run: (ed) => ed.commands.toggleOrderedList() },
        { type: "quote", name: "引用", desc: "引用一段文字", icon: "&ldquo;", run: (ed) => ed.commands.toggleBlockquote() },
        { type: "code", name: "代码块", desc: "插入代码块", icon: "{ }", run: (ed) => ed.commands.toggleCodeBlock() },
        { type: "hr", name: "分割线", desc: "插入水平分割线", icon: "&mdash;", run: (ed) => ed.commands.setHorizontalRule() },
        { type: "table", name: "表格", desc: "插入 3x3 表格", icon: "&#9646;", run: (ed) => ed.commands.insertTable({ rows: 3, cols: 3, withHeaderRow: true }) },
      ];
      this._slashIndex = 0;
      const menu = document.getElementById("slash-menu");
      const list = menu ? menu.querySelector(".slash-menu__list") : null;

      const render = () => {
        if (!list) return;
        list.innerHTML = "";
        this._slashItems.forEach((item, i) => {
          const div = document.createElement("div");
          div.className = "slash-menu__item" + (i === this._slashIndex ? " slash-menu__item--active" : "");
          div.innerHTML =
            '<span class="slash-menu__icon">' + item.icon + '</span>' +
            '<div class="slash-menu__text">' +
            '<div class="slash-menu__name">' + item.name + '</div>' +
            '<div class="slash-menu__desc">' + item.desc + '</div>' +
            '</div>';
          div.addEventListener("mousedown", (e) => { e.preventDefault(); this._slashSelect(i); });
          div.addEventListener("mouseenter", () => { this._slashIndex = i; this._slashHighlight(list); });
          list.appendChild(div);
        });
      };
      const position = (pos) => {
        if (!menu) return;
        const coords = _editorInstance.view.coordsAtPos(pos);
        menu.style.left = Math.min(coords.left, window.innerWidth - 260) + "px";
        menu.style.top = (coords.bottom + 4) + "px";
      };

      return {
        onOpen: (pos) => {
          this._slashIndex = 0;
          render();
          position(pos);
          menu && menu.classList.add("is-active");
        },
        onClose: () => {
          menu && menu.classList.remove("is-active");
        },
        onKeydown: (event) => {
          const total = this._slashItems.length;
          if (event.key === "ArrowDown") {
            event.preventDefault();
            this._slashIndex = (this._slashIndex + 1) % total;
            this._slashHighlight(list);
            return true;
          }
          if (event.key === "ArrowUp") {
            event.preventDefault();
            this._slashIndex = (this._slashIndex - 1 + total) % total;
            this._slashHighlight(list);
            return true;
          }
          if (event.key === "Enter") {
            event.preventDefault();
            this._slashSelect(this._slashIndex);
            return true;
          }
          return false; // Escape 交给扩展处理
        },
      };
    },

    _slashHighlight(list) {
      if (!list) return;
      Array.from(list.children).forEach((child, i) => {
        child.classList.toggle("slash-menu__item--active", i === this._slashIndex);
      });
    },

    /** 选中斜杠菜单项：先删 "/" 恢复干净段落，再执行命令（避免命令把 "/" 变内容后删除范围错乱/误伤后续块） */
    _slashSelect(idx) {
      const item = this._slashItems[idx];
      const ed = _editorInstance;
      if (!item || !ed) return;
      // 1. 先删除 "/" 及后续 query，恢复空段落
      const sc = ed.extensionManager.extensions.find(e => e.name === "slashCommand");
      if (sc && sc.storage && sc.storage.open) {
        const pos = sc.storage.pos;
        const { state, dispatch } = ed.view;
        const to = state.selection.from;
        if (to > pos) dispatch(state.tr.deleteRange(pos, to));
        sc.storage.open = false;
        sc.storage.pos = null;
        sc.storage.query = "";
      }
      // 2. 再执行命令（作用于干净的空段落）
      item.run(ed);
      const menu = document.getElementById("slash-menu");
      if (menu) menu.classList.remove("is-active");
      ed.commands.focus();
    },

    /* --- 自动保存（debounce + 队列串行） --- */

    _setupAutosave() {
      const ed = _editorInstance;
      if (!ed || this._autosaveBound) return;
      this._autosaveBound = true;
      this._autosaveTimer = null;
      this._saveQueue = Promise.resolve();
      ed.on("update", () => {
        if (this._autosaveTimer) clearTimeout(this._autosaveTimer);
        this._autosaveTimer = setTimeout(() => this._autosave(), 1000);
      });
    },

    /** debounce 到期 → 入队保存 */
    async _autosave() {
      const store = Alpine.store("app");
      if (store.isLocked || store.currentView !== "edit" || !_editorInstance) return;
      this._saveQueue = this._saveQueue.then(() => this._performSave());
    },

    /** 执行一次保存：内容未变跳过；失败 → IndexedDB 草稿兜底 + 横幅 */
    async _performSave() {
      const store = Alpine.store("app");
      if (store.isLocked || store.currentView !== "edit" || !_editorInstance) return;
      const md = this._editorToMarkdown();
      if (!md) return;
      // 内容未变 → 不重复调 API（后端 unchanged 是兜底，前端先自己比对）
      const current = store.document?.content || "";
      if (md === current) return;
      try {
        await store.saveDocumentSilent(store.currentPath, { content: md, summary: store.document?.summary || "" });
        // 保存成功且之前有离线草稿 → 清理
        await this._draftClear(store.currentPath);
        if (store.draftBanner) store.draftBanner = false;
      } catch (e) {
        // 锁冲突/路径错误不是离线：不写草稿（静默，等锁释放或用户操作）
        if (e && (e.isLocked || e.isNotFound || e.isBadRequest)) return;
        // 后端离线/网络失败 → 写本地草稿，不打断输入
        await this._draftToIndexedDB(md);
      }
    },

    /* --- IndexedDB 离线草稿 --- */

    /** 保存失败 → 写入本地草稿 + 顶部横幅 */
    async _draftToIndexedDB(md) {
      const store = Alpine.store("app");
      const path = store.currentPath;
      if (!path || !md) return;
      try {
        await _draftSave(path, {
          content: md,
          title: store.document?.title || "",
          summary: store.document?.summary || "",
          savedAt: new Date().toISOString(),
        });
        store.draftBanner = true;
      } catch (e) {
        // IndexedDB 不可用（无痕模式等）→ 静默丢弃，至少内存里还有
      }
    },

    /** 打开文档时检查：有没有未同步的离线草稿 */
    async _checkDraft() {
      const store = Alpine.store("app");
      const path = store.currentPath;
      if (!path) return;
      try {
        const draft = await _draftGet(path);
        if (draft) {
          store.draftInfo = { path, savedAt: draft.savedAt || "" };
          store.draftBanner = true;
        }
      } catch (e) {
        // 忽略
      }
    },

    /** 关闭页面前：编辑中有未保存内容 → 强制写草稿 */
    _bindBeforeUnloadDraft() {
      if (this._beforeUnloadBound) return;
      this._beforeUnloadBound = true;
      window.addEventListener("beforeunload", () => {
        const store = Alpine.store("app");
        if (store.currentView !== "edit" || !_editorInstance) return;
        const md = this._editorToMarkdown();
        if (md && md !== (store.document?.content || "")) {
          this._draftToIndexedDB(md);
        }
      });
    },

    destroyEditor() {
      if (_editorInstance) {
        _editorInstance.destroy();
        _editorInstance = null;
      }
      const store = Alpine.store("app");
      store.isDirty = false;
    },

    async saveDocument() {
      const store = Alpine.store("app");
      if (store.isLocked) return;

      this.saving = true;
      try {
        const html = _editorInstance
          ? _editorInstance.getHTML()
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
