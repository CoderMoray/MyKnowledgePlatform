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
      this._bindDocClick();

      // 编辑态收到 SSE 文档变更（别处保存）→ 主动检查版本，冲突立即弹 diff（不等保存、不覆盖内容）
      window.addEventListener("myk:doc-modified", () => this._checkExternalModification());

      if (!store.document && path) {
        store.loadDocument(path);
      }

      // 任何方式离开编辑态（返回按钮在编辑器外、侧边栏、路由切换）→ 保存并隐藏装饰
      Alpine.effect(() => {
        const v = store.currentView;
        if (this._lastEditView === "edit" && v !== "edit" && _editorInstance) {
          this._saveAndDestroy();
        }
        this._lastEditView = v;
      });

      // 单 DOM 核心：htmlContent 就绪 → 创建编辑器（view 态只读渲染）；切文档 → 更新内容。
      // 统一走 effect，避免 loadDocument 与组件 init 的竞态（document 存在但 html 未就绪时漏创建）。
      Alpine.effect(() => {
        const h = store.htmlContent;
        if (!h || !h.trim()) return;
        // 切文档/重载 → 同步标题/摘要输入框（避免残留上一文档的值）。
        // 仅非编辑态同步：编辑态保护用户正在输入的内容（保存时 htmlContent 快照也会触发本 effect，
        // 若同步会把刚输入的标题覆盖回文件名，导致重命名判断失效）。
        if (store.currentView !== "edit") {
          this.summaryValue = store.document?.summary || "";
          this.titleValue = store.document?.title || fileName(store.currentPath || "");
        }
        if (!_editorInstance) {
          this._ensureEditorForView(); // 内部有 _editorInstance 防重
          return;
        }
        if (store.currentView !== "edit") {
          const cur = _editorInstance.view ? _editorInstance.view.dom.innerHTML : "";
          if (cur !== h) {
            _editorInstance.commands.setContent(this._prepareEditorHtml(h));
            _editorInstance.setEditable(false);
          }
        }
      });

      this.titleValue = store.document?.title || "";
      this.summaryValue = store.document?.summary || "";
    },

    /** 单 DOM：确保编辑器已创建（阅读态也用它渲染，editable=false） */
    async _ensureEditorForView() {
      const store = Alpine.store("app");
      if (_editorInstance || !store.htmlContent || !store.htmlContent.trim()) return;
      await new Promise(r => this.$nextTick(r));
      await this.initEditor(store.htmlContent);
      if (_editorInstance) {
        _editorInstance.setEditable(false);
        this._bindEditorRefLinks(store);
      }
    },

    /**
     * 把阅读态 HTML（marked 渲染）预处理成编辑器可解析的内容：
     * 1. ref 链接 data-ref-path → href="ref:..."（否则 TipTap 解析 javascript:void(0) 时 Link mark 不应用 → 链接变纯文本）
     * 2. 代码块净化（去 hljs span + 转义裸标签）
     * 3. 块内软换行 \n → <br>（ProseMirror 不保留裸 \n，round-trip 零 diff）
     * onCreate 与切文档 setContent 必须共用（否则切文档后 ref 链接丢失）
     */
    _prepareEditorHtml(html) {
      const tmp = document.createElement("div");
      tmp.innerHTML = html;
      tmp.querySelectorAll("[data-ref-path]").forEach(a => {
        const section = a.dataset.refSection ? "::" + a.dataset.refSection : "";
        a.setAttribute("href", "ref:" + a.dataset.refPath + section);
      });
      tmp.querySelectorAll("pre code").forEach(code => {
        const text = code.textContent;
        code.textContent = text;
      });
      const walker = document.createTreeWalker(tmp, NodeFilter.SHOW_TEXT);
      const softBreaks = [];
      let tn;
      while ((tn = walker.nextNode())) {
        const p = tn.parentNode;
        if (!p || (p.closest && p.closest("pre"))) continue;
        if (tn.nodeValue && tn.nodeValue.includes("\n") && tn.nodeValue.trim() !== "") softBreaks.push(tn);
      }
      softBreaks.forEach(tn => {
        const frag = document.createDocumentFragment();
        const parts = tn.nodeValue.split("\n");
        parts.forEach((part, i) => {
          if (i > 0) frag.appendChild(document.createElement("br"));
          if (part) frag.appendChild(document.createTextNode(part));
        });
        tn.parentNode.replaceChild(frag, tn);
      });
      return tmp.innerHTML;
    },

    /** 离开编辑态兜底：保存当前编辑内容并隐藏装饰（不销毁编辑器，单 DOM 复用） */
    async _saveAndDestroy() {
      if (!_editorInstance) return;
      // exitEdit 正常退出已保存（_editingPath 已清空）→ 这里跳过，避免重复保存
      if (!this._editingPath) return;
      const store = Alpine.store("app");
      const path = this._editingPath || store.currentPath;
      let finalPath = path; // rename 后路径可能变化，setView 用新路径
      const fullMd = this._editorToMarkdown();
      if (fullMd) {
        try {
          await store.saveDocumentSilent(path, this._buildSaveBody());
        } catch (e) {
          // 409 冲突：弹可视化 diff（保持编辑态，不打断导航兜底）
          if (this._handleSaveError(e)) return;
          /* 其他失败不打断导航，自动保存/草稿兜底 */
        }
      }
      _editorInstance.setEditable(false);
      this._hideEditDecorations();
      this._editingPath = null;
      this.editorReady = true;
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

    /** 死链卡片 — ref 文档不存在（区分 in_trash 可恢复 / dead 不存在） */
    _showDeadRefCard(linkEl, refPath) {
      const existing = document.getElementById("ref-card");
      if (existing) existing.remove();

      const store = Alpine.store("app");
      const ref = (store.refs || []).find(r => r.path === refPath);
      const status = (ref && ref.ref_status) || "dead";
      const isTrash = status === "in_trash";

      // 剩余可恢复天数（30 天 - 已删除天数）；deleted_at 从垃圾箱条目取
      const trashItem = (store.trashItems || []).find(i => i.original_path === refPath);
      const deletedAt = trashItem && trashItem.deleted_at;
      let remainDays = "";
      if (deletedAt) {
        const deletedMs = new Date(String(deletedAt).replace(" ", "T")).getTime();
        const days = Math.floor((Date.now() - (isNaN(deletedMs) ? Date.now() : deletedMs)) / 86400000);
        remainDays = Math.max(0, 30 - days);
      }

      const card = document.createElement("div");
      card.id = "ref-card";
      card.className = "ref-card";

      card.innerHTML = `
        <div class="ref-card__title">${escapeHtml(linkEl.textContent.trim())}</div>
        <div class="ref-card__source" style="word-break:break-all;font-size:11px;color:var(--text-tertiary)">${escapeHtml(refPath)}</div>
        <div class="ref-card__divider"></div>
        ${isTrash
          ? `<div class="ref-card__summary" style="color:var(--color-warning, #d97706)">该知识已进垃圾箱${remainDays !== "" ? `，剩余 ${remainDays} 天可恢复` : "，可在垃圾箱恢复"}</div>
             <div class="ref-card__footer" style="justify-content:flex-end;gap:8px">
               <button class="ref-card__action ref-card__action--btn" data-copy-prompt>复制给 AI 处理</button>
               <span class="ref-card__sep">|</span>
               <a href="#trash" class="ref-card__action">去垃圾箱恢复</a>
             </div>`
          : `<div class="ref-card__summary" style="color:var(--color-danger)">引用的知识文件不存在</div>
             <div class="ref-card__footer" style="justify-content:flex-end;font-size:11px;color:var(--text-tertiary)">ref 链接指向的文档路径无效</div>`}
      `;

      this._attachCardEvents(card, linkEl);

      // 点击「去垃圾箱恢复」→ 立即缩回卡片（不等鼠标移出）
      const action = card.querySelector("a.ref-card__action");
      if (action) action.addEventListener("click", () => this._hideRefCard());

      // 复制处理 prompt（摘要版 / 含全文版）——点击时不缩回卡片
      const copyBtn = card.querySelector("[data-copy-prompt]");
      if (copyBtn) copyBtn.addEventListener("click", (e) => {
        e.preventDefault(); e.stopPropagation();
        this._copyTrashPrompt(refPath, false);
      });


      // 若还没拿到 deleted_at（trashItems 未加载）→ 异步查一次并重建卡片（动态剩余天数）
      if (isTrash && !deletedAt) {
        api.getTrash().then(data => {
          const item = (data.items || []).find(i => i.original_path === refPath);
          if (item && item.deleted_at) {
            store.trashItems = data.items || [];
            // 重建卡片以显示剩余天数
            const link = document.querySelector("a.ref-link[data-ref-path='" + CSS.escape(refPath) + "']");
            if (link) this._showDeadRefCard(link, refPath);
          }
        }).catch(() => {});
      }
    },

    /** 复制垃圾箱处理 prompt（摘要版：含 MCP 工具名，agent 可 nav__get_document 自取全文） */
    async _copyTrashPrompt(refPath) {
      const store = Alpine.store("app");
      const ref = (store.refs || []).find(r => r.path === refPath);
      let item = (store.trashItems || []).find(i => i.original_path === refPath);
      try {
        if (!item) {
          const data = await api.getTrash();
          store.trashItems = data.items || [];
          item = store.trashItems.find(i => i.original_path === refPath);
        }
        if (!item) { showToast("未找到垃圾箱条目", "error"); return; }
        let summary = "";
        try {
          const data = await api.getDocument(item.trash_path); // trash 路径可直接读（取摘要）
          summary = data.summary || "";
        } catch (_) {
          summary = (ref && ref.title) || "";
        }
        const prompt = buildTrashPrompt(ref, Object.assign({}, item, { summary }), false, "");
        const ok = await copyText(prompt);
        showToast(ok ? "Prompt 已复制，可以发送给你的 AI" : "复制失败", ok ? "success" : "error", 1800);
      } catch (e) {
        showToast(e.message || "复制失败", "error");
      }
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

    /** 单 DOM：在 ProseMirror 容器上委托绑定链接交互（hover 卡片 + 阅读态点击跳转） */
    _bindEditorRefLinks(store) {
      const ed = _editorInstance;
      if (!ed || !ed.view || this._viewerBound) return;
      this._viewerBound = true;
      this._hoverTimer = null;
      const self = this;
      const dom = ed.view.dom;

      // ProseMirror 渲染的链接无 ref-link class，用 href 协议识别
      const findLink = (target) => {
        let el = target;
        while (el && el !== dom && el.nodeType === 1) {
          if (el.tagName === "A") {
            const href = el.getAttribute("href") || "";
            if (href.startsWith("ref:")) return { el, type: "ref", path: href.slice(4).replace(/%20/g, " ").split("::")[0] };
            if (href.startsWith("http")) return { el, type: "ext", url: href };
          }
          el = el.parentElement;
        }
        return null;
      };

      // hover 卡片：仅阅读态（editable=false 且未锁）
      dom.addEventListener("mouseover", (e) => {
        if (store.currentView !== "view" || store.isLocked) return;
        const link = findLink(e.target);
        if (!link) return;
        clearTimeout(self._hoverTimer);
        self._hoverTimer = setTimeout(() => {
          if (link.type === "ext") {
            self._showExtCard(link.el, link.url);
          } else if (link.type === "ref") {
            self.openRefPopover(link.el, link.path);
          }
        }, 200);
      });

      dom.addEventListener("mouseout", (e) => {
        const link = findLink(e.relatedTarget);
        if (link) return;
        clearTimeout(self._hoverTimer);
        self._hoverTimer = setTimeout(() => self.closePopover(), 200);
      });

      // 阅读态点击链接：ref → 跳转目标文档；ext → 新窗口打开
      dom.addEventListener("click", (e) => {
        if (store.currentView !== "view") return;
        const link = findLink(e.target);
        if (!link) return;
        e.preventDefault();
        e.stopPropagation();
        self._hideRefCard(true);
        if (link.type === "ref") {
          const target = link.path.split("::")[0]; // 去掉 section 定位
          window.location.hash = "doc/" + hashEncode(target);
        } else {
          window.open(link.url, "_blank", "noopener");
        }
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
        // 单 DOM：编辑器常驻，首次进入才创建，之后复用（内容/滚动保持）
        if (!_editorInstance) {
          let content = store.htmlContent;
          if (!content || !content.trim()) {
            await store.loadDocument(store.currentPath);
            content = store.htmlContent;
          }
          await new Promise(r => this.$nextTick(r));
          await this.initEditor(content);
          this._bindEditorRefLinks(store);
        }
        _editorInstance.setEditable(true);
        _editorInstance.commands.focus();
        store.setView("edit", store.currentPath);
      } finally {
        this._entering = false;
      }
    },

    /**
     * 全局点击处理（单 DOM，capture 阶段先于 ProseMirror 的 stopPropagation）：
     * - 阅读态（view）：点击编辑器内部（非链接）→ 进入编辑
     * - 编辑态：点击编辑器容器外部 → 退出编辑
     * 不用 @click.outside —— ProseMirror 在 selection 变化时重建 DOM，
     * click 的 target 可能变成已脱离文档的节点，contains() 误判为外部。
     */
    _bindDocClick() {
      if (this._docClickBound) return;
      this._docClickBound = true;
      document.addEventListener("click", (e) => this.onDocClick(e), true);
    },
    async onDocClick(e) {
      if (!e || !e.target) return;
      const shell = this.$el.querySelector(".editor-shell");
      if (!shell) return;
      // summary/标题区在 editor-shell 外，但属于文档编辑区域：点它进编辑（view）/ 不退出（edit）
      const summaryEl = this.$el.querySelector(".viewer__summary");
      const inSummary = summaryEl && e.target.isConnected && summaryEl.contains(e.target);
      const titleEl = this.$el.querySelector(".viewer__title");
      const inTitle = titleEl && e.target.isConnected && titleEl.contains(e.target);
      const inEditor = (e.target.isConnected && shell.contains(e.target)) || inSummary || inTitle;
      const store = Alpine.store("app");
      if (store.currentView !== "edit") {
        // 阅读态：点击编辑器/摘要/标题（且不是链接）→ 进入编辑
        if (inEditor && !e.target.closest("a")) {
          await this.enterEdit();
          // 点击标题进入 → 光标落在标题输入框
          // （setView 后 Alpine 在 nextTick 才显示 input，需等 DOM 更新再 focus）
          if (inTitle) {
            await new Promise(r => this.$nextTick(r));
            setTimeout(() => {
              const ti = document.querySelector(".viewer__title-input");
              if (ti) ti.focus();
            }, 0);
          }
        }
        return;
      }
      if (!inEditor) this.exitEdit();
    },

    /** 点击外部 → 退出编辑并保存（单 DOM：只切只读，不销毁编辑器） */
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
        this._hideEditDecorations();
        if (stillOnDoc) store.setView("view", path);
        this._editingPath = null;
        return;
      }

      let finalPath = path; // rename 后路径可能变化，setView 用新路径
      const fullMd = this._editorToMarkdown();
      if (fullMd) {
        try {
          await store.saveDocument(path, this._buildSaveBody());
          // 保存成功后同步 htmlContent = 编辑器 DOM 快照：
          // 否则退出编辑切回阅读态时，effect 会用"旧 htmlContent"把编辑器内容还原成保存前（内容已保存但显示回滚）
          if (_editorInstance && _editorInstance.view) {
            store.htmlContent = _editorInstance.view.dom.innerHTML;
          }
          // 标题变化 → 重命名文件（先保存内容成功后再 rename；引用链接自动更新）
          const currentTitle = MykRename.currentTitle(store.document, path);
          const newTitle = (this.titleValue || "").trim();
          const titleErr = MykRename.titleError(newTitle);
          if (titleErr) {
            // 非法标题：内容已保存，提示但跳过重命名
            showToast(titleErr + "，未重命名", "warning");
          } else if (MykRename.shouldRename(currentTitle, newTitle)) {
            finalPath = await this._renameCurrentDocument(path, newTitle);
          }
        } catch (e) {
          // 409 冲突：弹可视化 diff，保持编辑态（不切 view、不丢弃内容）
          if (this._handleSaveError(e)) return;
          // 其他失败（含 rename 失败）：toast，不打断退出（内容已保存）
          if (e && e.status !== 409) showToast(e.message || "保存失败", "error");
        }
      }

      // 单 DOM：不销毁编辑器，切只读 + 隐藏编辑装饰；内容就是最新，无需重载
      _editorInstance.setEditable(false);
      this._hideEditDecorations();
      this._editingPath = null;
      if (stillOnDoc) {
        store.setView("view", finalPath);
      }
    },

    /** 隐藏编辑态装饰（浮动条/斜杠菜单/锁遮罩） */
    _hideEditDecorations() {
      const bubble = document.getElementById("bubble-menu");
      if (bubble) bubble.classList.remove("is-active");
      const slash = document.getElementById("slash-menu");
      if (slash) slash.classList.remove("is-active");
      const overlay = document.getElementById("editor-lock-overlay");
      if (overlay) overlay.remove();
      const panel = document.getElementById("content-panel");
      if (panel) panel.classList.remove("content-panel--locked", "content-panel--unlocking");
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
      // 仅去掉"文档开头"的空 h1（标题占位，header 已显示）；斜杠插入的空 H1 保留
      const firstChild = tmp.firstElementChild;
      if (firstChild && firstChild.tagName === "H1" && !firstChild.textContent.trim()) firstChild.remove();
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
      // 分割线统一输出 ---（turndown 默认 * * *，会造成保存时的噪声 diff）
      td.addRule("mykHr", { filter: "hr", replacement: () => "\n\n---\n\n" });
      // 下划线：markdown 无标准语法，用内联 HTML <u> 保留（marked 渲染 raw HTML 也保留）
      td.addRule("underline", { filter: ["u", "ins"], replacement: (content) => "<u>" + content + "</u>" });
      // <br> → 软换行（无行尾空格）：与预处理 \n→<br> 对应，round-trip 零 diff
      td.addRule("br", { filter: "br", replacement: () => "\n" });
      // 嵌套列表缩进用 2 空格（替换 turndown 默认 4 空格，匹配常见手写格式，零 diff）
      td.addRule("listItem", {
        filter: "li",
        replacement: (content, node, options) => {
          content = content.replace(/^\n+/, "").replace(/\n+$/, "\n").replace(/\n/gm, "\n  ");
          let prefix = "- ";
          const parent = node.parentNode;
          if (parent && parent.nodeName === "OL") {
            const start = parent.getAttribute("start");
            const index = Array.prototype.indexOf.call(parent.children, node);
            prefix = (start ? Number(start) + index : index + 1) + ". ";
          }
          return prefix + content + (node.nextSibling && !/\n$/.test(content) ? "\n" : "");
        },
      });
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
      if (!el) return;
      // 保险：编辑器已存在但文档已切换（上一轮保存兜底竞态漏掉）→ 强制重建，防止内容串台
      const store = Alpine.store("app");
      if (_editorInstance) {
        const editing = this._editingPath || store.currentPath;
        if (editing === store.currentPath) return; // 同一文档再次进入 → 保持
        _editorInstance.destroy();
        _editorInstance = null;
        window.__mykEditor = null;
        this.editorReady = false;
      }

      await this.waitForTipTap();

      const { Editor, Extension } = window.TipTapCore || {};
      const StarterKit = window.TipTapStarterKit ? window.TipTapStarterKit.StarterKit : null;
      const LinkExt = window.TipTapLink || null;
      const TT = window.TipTapTable || {};
      const TM = window.TipTapMenu || {};
      const TC = window.TipTapCode || {};
      // lowlight 实例：注册常用语言（js/ts/python/bash/json/markdown/yaml/xml/css 等）
      const _lowlight = TC.createLowlight ? TC.createLowlight(TC.MyLowlightCommon) : null;
      console.log("[doc] Editor:", !!Editor, "StarterKit:", !!StarterKit, "LinkExt:", !!LinkExt);
      if (!Editor) return;

      // 自定义 Link 扩展：修复 2.1.13 的 href 序列化 bug
      // ref: https://github.com/ueberdosis/tiptap/issues/4929
      // 覆写 parseHTML/renderHTML：TipTap Link 的 isAllowedUri 只放行 http/https/mailto/tel，
      // 会拒绝 ref: 协议（parse 时 mark 不应用 → 编辑态成纯文本 → 保存时链接语法丢失）。
      const PatchedLink = LinkExt ? LinkExt.extend({
        parseHTML() {
          return [
            {
              tag: 'a[href]:not([href *= "javascript:" i])',
              getAttrs: (dom) => {
                const href = dom.getAttribute("href");
                if (!href) return false;
                return { href };
              },
            },
          ];
        },
        renderHTML({ HTMLAttributes }) {
          // 不做 isAllowedUri 过滤，ref: 协议原样渲染
          return ["a", { ...HTMLAttributes }, 0];
        },
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
      }).configure({ openOnClick: false, validate: () => true }) : null;

      const extensions = [
        // StarterKit 排除自带 codeBlock，改用 CodeBlockLowlight（Decoration 渲染，编辑态实时高亮）
        StarterKit ? StarterKit.configure({ codeBlock: false }) : null,
        _lowlight && TC.CodeBlockLowlight ? TC.CodeBlockLowlight.configure({ lowlight: _lowlight }) : null,
        PatchedLink,
        TT.Table ? TT.Table.configure({ resizable: true }) : null,
        TT.TableRow || null,
        TT.TableCell || null,
        TT.TableHeader || null,
        window.TipTapUnderline ? window.TipTapUnderline : null,
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
            editor.commands.setContent(this._prepareEditorHtml(html));
          }
        },
      });

      window.__mykEditor = _editorInstance;
      this.editorReady = true;

      // 自动保存：update 事件 → debounce（任务 14 实现）
      this._setupAutosave();
      // 浮动格式条：自实现定位（绕开官方 BubbleMenu 的 tippy 依赖）
      this._setupBubbleMenu();
      this._setupPlusMenu();
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
            const href = link.getAttribute("href") || "";
            // 兼容两种渲染：title="关联文档:..."（前端 renderer）或 href="ref:..."（后端 html）
            const isRef = title.startsWith("关联文档:") || href.startsWith("ref:");
            if (!isRef || link.dataset._refBound) return;
            link.dataset._refBound = "1";

            link.addEventListener("mouseenter", () => {
              if (store.editingMode || store.isLocked) return;
              clearTimeout(self._hoverTimer);
              const refPath = title.startsWith("关联文档:")
                ? title.replace(/^关联文档:\s*/, "").trim()
                : href.slice(4).split("::")[0];
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
      // 注意：编辑态不跑 highlight.js —— hljs 会改写 code 的 innerHTML，
      // 破坏 ProseMirror 的 DOM 同步（引发 mismatch/光标错乱），且对代码内容
      // 做未转义检查会产生安全警告。代码高亮只在阅读态（renderer.js）做。
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
        { dropdown: "block", title: "块类型（正文/标题/列表）", label: "T" },
        { sep: true },
        { action: "bold", title: "加粗", label: "<b>B</b>" },
        { action: "italic", title: "斜体", label: "<i>I</i>" },
        { action: "underline", title: "下划线", label: "<u>U</u>" },
        { action: "strike", title: "删除线", label: "<s>S</s>" },
        { action: "code", title: "行内代码", label: "&lt;/&gt;" },
        { sep: true },
        { action: "indent", title: "增加缩进", label: "&#8594;" },
        { action: "outdent", title: "减少缩进", label: "&#8592;" },
        { sep: true },
        { action: "link", title: "添加链接", label: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>' },
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
        btn.dataset.tip = d.title; // 自定义 tooltip（原生 title 延迟 ~1s 不可控）
        btn.dataset.bubbleAction = d.dropdown ? "dd:" + d.dropdown : d.action;
        btn.dataset.bubbleDropdown = d.dropdown || "";
        btn.innerHTML = d.label;
        btn.addEventListener("mousedown", (e) => e.preventDefault()); // 防止编辑器失焦丢选区
        btn.addEventListener("click", () => {
          if (d.dropdown) this._toggleBlockDropdown(btn, d.dropdown);
          else this._bubbleAction(d.action);
        });
        el.appendChild(btn);
      });

      // selection 变化 → 显示/隐藏 + 定位
      const update = () => {
        // 单 DOM：只读态（阅读态）绝不弹浮动条——选中文字是复制行为，命令会改内容
        if (!ed.isEditable) { el.classList.remove("is-active"); return; }
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
          else if (act === "underline") active = ed.isActive("underline");
          else if (act === "strike") active = ed.isActive("strike");
          else if (act === "code") active = ed.isActive("code");
          else if (act === "link") active = isLink;
          b.classList.toggle("is-active", active);
          // 缩进仅列表项可用：非列表时置灰（避免"点了没反应"的困惑）
          if (act === "indent") b.classList.toggle("is-disabled", !ed.can().sinkListItem("listItem"));
          else if (act === "outdent") b.classList.toggle("is-disabled", !ed.can().liftListItem("listItem"));
        });
        // 选中态变化 → 关闭 T 下拉（保持菜单与内容同步）
        this._closeBlockDropdown();
      };
      ed.on("selectionUpdate", update);
      ed.on("transaction", update);
    },

    /** T 块类型下拉：正文 / 标题 1-4 / 有序 / 无序（飞书同款） */
    _toggleBlockDropdown(btn, kind) {
      const ed = _editorInstance;
      if (!ed) return;
      // 关闭已打开的其他下拉
      if (this._blockDropdownOpen) { this._closeBlockDropdown(); return; }
      const items = [
        { name: "正文", desc: "普通文本", run: () => ed.commands.setParagraph() },
        { name: "标题 1", desc: "一级大标题", run: () => ed.commands.toggleHeading({ level: 1 }) },
        { name: "标题 2", desc: "二级标题", run: () => ed.commands.toggleHeading({ level: 2 }) },
        { name: "标题 3", desc: "三级标题", run: () => ed.commands.toggleHeading({ level: 3 }) },
        { name: "标题 4", desc: "四级标题", run: () => ed.commands.toggleHeading({ level: 4 }) },
        { name: "有序列表", desc: "编号列表", run: () => ed.commands.toggleOrderedList() },
        { name: "无序列表", desc: "项目符号列表", run: () => ed.commands.toggleBulletList() },
      ];
      let dd = document.getElementById("block-dropdown");
      if (!dd) {
        dd = document.createElement("div");
        dd.id = "block-dropdown";
        dd.className = "block-dropdown";
        (document.querySelector(".editor-shell") || document.body).appendChild(dd);
      }
      dd.innerHTML = "";
      items.forEach((it) => {
        const div = document.createElement("div");
        div.className = "block-dropdown__item";
        div.innerHTML = '<span class="block-dropdown__name">' + it.name + '</span><span class="block-dropdown__desc">' + it.desc + '</span>';
        div.addEventListener("mousedown", (e) => e.preventDefault());
        div.addEventListener("click", () => {
          this._closeBlockDropdown();
          it.run();
        });
        dd.appendChild(div);
      });
      const r = btn.getBoundingClientRect();
      dd.style.left = r.left + "px";
      dd.style.top = (r.bottom + 4) + "px";
      dd.classList.add("is-active");
      this._blockDropdownOpen = true;
    },

    _closeBlockDropdown() {
      const dd = document.getElementById("block-dropdown");
      if (dd) dd.classList.remove("is-active");
      this._blockDropdownOpen = false;
    },

    /**
     * 行首 + 插入按钮（飞书同款）：mousemove 检测当前块 → 按钮定位到编辑器左边缘；
     * 点击弹出插入菜单（复用 _slashItems，同款 UI/命令）；选择后在块位置插入。
     */
    _setupPlusMenu() {
      const ed = _editorInstance;
      if (!ed || this._plusBound) return;
      this._plusBound = true;
      const store = Alpine.store("app");
      const dom = ed.view.dom;
      const btn = document.getElementById("plus-btn");
      const menu = document.getElementById("plus-menu");
      if (!btn || !menu) return;
      let currentBlock = null; // 当前鼠标所在块起点 pos

      // 块查找：posAtCoords → resolve → 向上找 block 节点，返回 {start, empty}
      // 边界兜底：pos 落在块边界时 resolve.depth 可能为 0（doc 层），试 pos+1 / pos-1
      const findBlock = (pos) => {
        if (pos == null) return null;
        const tryResolve = (p) => {
          if (p < 0 || p > ed.state.doc.content.size) return null;
          const resolved = ed.state.doc.resolve(p);
          for (let d = resolved.depth; d >= 0; d--) {
            const node = resolved.node(d);
            if (node && node.isBlock && node.type.name !== "doc") {
              return {
                start: Math.max(0, resolved.before(d) + 1),
                // 空块（空行）：无文本且无子内容（飞书：+ 仅出现在空行行首）
                empty: node.textContent === "" && node.content.size === 0,
              };
            }
          }
          return null;
        };
        return tryResolve(pos) || tryResolve(pos + 1) || tryResolve(Math.max(0, pos - 1));
      };

      // mousemove：定位 + 按钮（仅编辑态；菜单打开时保持不动）
      let moveTimer = null;
      dom.addEventListener("mousemove", (e) => {
        if (store.currentView !== "edit" || this._plusMenuOpen) return;
        if (moveTimer) clearTimeout(moveTimer);
        moveTimer = setTimeout(() => {
          const hit = ed.view.posAtCoords({ left: e.clientX, top: e.clientY });
          const pos = hit ? hit.pos : null; // posAtCoords 返回 {pos, inside}
          const block = findBlock(pos);
          // 仅空行显示 + 按钮（飞书行为）
          if (!block || !block.empty) { btn.classList.remove("is-visible"); currentBlock = null; return; }
          currentBlock = block.start;
          const coords = ed.view.coordsAtPos(block.start);
          // 按钮贴近行首（行首 x - 24px；当前 -34 距行首偏远）
          btn.style.left = Math.max(4, coords.left - 24) + "px";
          btn.style.top = ((coords.top + coords.bottom) / 2 - 12) + "px";
          btn.classList.add("is-visible");
        }, 30);
      });
      dom.addEventListener("mouseleave", () => {
        if (!this._plusMenuOpen) { btn.classList.remove("is-visible"); currentBlock = null; }
      });

      // 点击 +：光标移到块，弹出插入菜单
      btn.addEventListener("mousedown", (e) => e.preventDefault());
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (this._plusMenuOpen) { this._closePlusMenu(); return; }
        if (currentBlock != null) ed.commands.setTextSelection(currentBlock);
        this._renderPlusMenu(menu);
        const r = btn.getBoundingClientRect();
        menu.style.left = r.left + "px";
        menu.style.top = (r.bottom + 4) + "px";
        menu.classList.add("is-active");
        btn.classList.add("is-open");
        this._plusMenuOpen = true;
      });

      // 点击菜单外关闭（capture 先于 ProseMirror stopPropagation）
      document.addEventListener("mousedown", (e) => {
        if (!this._plusMenuOpen) return;
        if (e.target && e.target.closest && !e.target.closest("#plus-menu")) this._closePlusMenu();
      }, true);

      // 编辑器更新后若块消失（如删除）→ 隐藏按钮
      ed.on("transaction", () => {
        if (!this._plusMenuOpen) {
          const sel = ed.state.selection;
          if (currentBlock != null && currentBlock > ed.state.doc.content.size) {
            btn.classList.remove("is-visible");
            currentBlock = null;
          }
        }
      });
    },

    /** 渲染加号插入菜单（复用 _slashItems，表格内过滤表格项） */
    _renderPlusMenu(menu) {
      const list = menu.querySelector(".plus-menu__list");
      if (!list) return;
      list.innerHTML = "";
      const inTable = _editorInstance ? _editorInstance.isActive("table") : false;
      const items = this._slashItems.filter((it) => !(it.type === "table" && inTable));
      items.forEach((item) => {
        const div = document.createElement("div");
        div.className = "plus-menu__item";
        div.innerHTML =
          '<span class="plus-menu__icon">' + item.icon + '</span>' +
          '<div class="plus-menu__text">' +
          '<div class="plus-menu__name">' + item.name + '</div>' +
          '<div class="plus-menu__desc">' + item.desc + '</div>' +
          '</div>';
        div.addEventListener("mousedown", (e) => e.preventDefault());
        div.addEventListener("click", () => {
          item.run(_editorInstance);
          this._closePlusMenu();
          _editorInstance && _editorInstance.commands.focus();
        });
        list.appendChild(div);
      });
    },

    _closePlusMenu() {
      const menu = document.getElementById("plus-menu");
      if (menu) menu.classList.remove("is-active");
      const btn = document.getElementById("plus-btn");
      if (btn) btn.classList.remove("is-open");
      this._plusMenuOpen = false;
    },

    /** BubbleMenu 按钮点击分发 */
    _bubbleAction(action) {
      const ed = _editorInstance;
      if (!ed) return;
      if (action === "bold") ed.commands.toggleBold();
      else if (action === "italic") ed.commands.toggleItalic();
      else if (action === "underline") ed.commands.toggleUnderline();
      else if (action === "strike") ed.commands.toggleStrike();
      else if (action === "code") ed.commands.toggleCode();
      else if (action === "indent") ed.commands.sinkListItem("listItem");
      else if (action === "outdent") ed.commands.liftListItem("listItem");
      else if (action === "link") this._bubbleLink();
    },

    /** 链接：无链接 → 提示输入；已有链接 → 取消 */
    /** 链接浮层：主题化小弹窗（替代浏览器 prompt，飞书同款：选中文字作显示名 + URL 输入） */
    _bubbleLink() {
      const ed = _editorInstance;
      if (!ed) return;
      if (ed.isActive("link")) {
        ed.commands.unsetLink();
        return;
      }
      // 已有浮层 → 关闭
      const existing = document.getElementById("link-popover");
      if (existing) { existing.remove(); return; }

      const sel = ed.state.selection;
      const selectedText = sel.empty ? "" : ed.state.doc.textBetween(sel.from, sel.to, " ").slice(0, 60);

      const pop = document.createElement("div");
      pop.id = "link-popover";
      pop.className = "link-popover";
      pop.innerHTML =
        '<div class="link-popover__title">添加链接</div>' +
        '<label class="link-popover__label">显示文本</label>' +
        '<input class="link-popover__input" id="link-popover-text" type="text" value="' + escapeHtml(selectedText) + '" placeholder="链接显示的文字">' +
        '<label class="link-popover__label">链接地址</label>' +
        '<input class="link-popover__input" id="link-popover-url" type="text" placeholder="外部 URL 或 ref:知识路径" spellcheck="false">' +
        '<div class="link-popover__results" id="link-popover-results"></div>' +
        '<div class="link-popover__actions">' +
        '<button class="link-popover__btn link-popover__btn--cancel" id="link-popover-cancel">取消</button>' +
        '<button class="link-popover__btn link-popover__btn--ok" id="link-popover-ok">确定</button>' +
        '</div>';
      (document.querySelector(".editor-shell") || document.body).appendChild(pop);
      // 定位：基于浮动条位置
      const bubble = document.getElementById("bubble-menu");
      const r = bubble ? bubble.getBoundingClientRect() : ed.view.dom.getBoundingClientRect();
      pop.style.left = r.left + "px";
      pop.style.top = (r.top - 140) + "px";
      pop.classList.add("is-active");

      const urlInput = pop.querySelector("#link-popover-url");
      const textInput = pop.querySelector("#link-popover-text");
      urlInput.focus();

      const apply = () => {
        const url = (urlInput.value || "").trim().replace(/ /g, "%20");
        const text = (textInput.value || "").trim() || selectedText || url;
        if (!url) { pop.remove(); return; }
        // 删除选中 → 原地插入带 link mark 的文本（一次事务，避免 selection 漂移导致文本消失/链接不生效）
        const linkMark = { type: "link", attrs: { href: url } };
        if (sel.empty) {
          ed.chain().focus()
            .insertContent([{ type: "text", text: text + " ", marks: [linkMark] }])
            .run();
        } else {
          ed.chain().focus()
            .deleteRange({ from: sel.from, to: sel.to })
            .insertContent([{ type: "text", text: text + " ", marks: [linkMark] }])
            .run();
        }
        pop.remove();
      };
      pop.querySelector("#link-popover-ok").addEventListener("mousedown", (e) => e.preventDefault());
      pop.querySelector("#link-popover-ok").addEventListener("click", apply);
      pop.querySelector("#link-popover-cancel").addEventListener("mousedown", (e) => e.preventDefault());
      pop.querySelector("#link-popover-cancel").addEventListener("click", () => pop.remove());
      urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") apply(); });

      // ── 引用搜索：地址框输入即搜（debounce），点选填入 ref:路径 ──
      const resultsEl = pop.querySelector("#link-popover-results");
      let searchTimer = null;
      let searchSeq = 0;
      const renderResults = (results) => {
        if (!results || results.length === 0) { resultsEl.innerHTML = ""; resultsEl.classList.remove("is-active"); return; }
        resultsEl.innerHTML = results.map(r =>
          '<div class="link-popover__result" data-path="' + escapeHtml(r.path) + '">' +
            '<div class="link-popover__result-title">' + escapeHtml(r.title || fileName(r.path)) + '</div>' +
            '<div class="link-popover__result-path">' + escapeHtml(r.path) + '</div>' +
          '</div>'
        ).join("");
        resultsEl.classList.add("is-active");
        resultsEl.querySelectorAll(".link-popover__result").forEach(item => {
          item.addEventListener("mousedown", (e) => {
            e.preventDefault(); e.stopPropagation();
            urlInput.value = "ref:" + item.dataset.path;
            resultsEl.innerHTML = "";
            resultsEl.classList.remove("is-active");
            urlInput.focus();
          });
        });
      };
      urlInput.addEventListener("input", () => {
        clearTimeout(searchTimer);
        const q = urlInput.value.trim();
        if (!q || /^https?:\/\//i.test(q) || /^ref:/i.test(q)) {
          resultsEl.innerHTML = ""; resultsEl.classList.remove("is-active");
          return;
        }
        searchTimer = setTimeout(async () => {
          const seq = ++searchSeq;
          try {
            const data = await api.searchDocuments(q);
            if (seq !== searchSeq) return; // 过期响应丢弃
            renderResults(data && data.results);
          } catch (_) { /* 搜索失败静默 */ }
        }, 300);
      });
      // 点击浮层外关闭
      setTimeout(() => {
        document.addEventListener("click", (e) => {
          if (pop.isConnected && !pop.contains(e.target)) pop.remove();
        }, { once: true });
      }, 0);
    },

    /** 构建 SlashCommand 选项（/ 唤出插入菜单，飞书斜杠菜单同款） */
    _buildSlashOptions(SlashCommandCls) {
      this._slashItems = [
        { type: "h1", name: "标题 1", desc: "一级大标题", icon: "H1", run: (ed) => ed.commands.toggleHeading({ level: 1 }) },
        { type: "h2", name: "标题 2", desc: "二级标题", icon: "H2", run: (ed) => ed.commands.toggleHeading({ level: 2 }) },
        { type: "h3", name: "标题 3", desc: "三级标题", icon: "H3", run: (ed) => ed.commands.toggleHeading({ level: 3 }) },
        { type: "h4", name: "标题 4", desc: "四级标题", icon: "H4", run: (ed) => ed.commands.toggleHeading({ level: 4 }) },
        { type: "bullet", name: "无序列表", desc: "项目符号列表", icon: "&bull;", run: (ed) => ed.commands.toggleBulletList() },
        { type: "ordered", name: "有序列表", desc: "编号列表", icon: "1.", run: (ed) => ed.commands.toggleOrderedList() },
        { type: "quote", name: "引用", desc: "引用一段文字", icon: "&ldquo;", run: (ed) => ed.commands.toggleBlockquote() },
        // 默认 javascript 语言 → lowlight 编辑态实时高亮（无语言会按纯文本不高亮）
        { type: "code", name: "代码块", desc: "插入代码块（JavaScript）", icon: "{ }", run: (ed) => ed.commands.toggleCodeBlock({ language: "javascript" }) },
        { type: "hr", name: "分割线", desc: "插入水平分割线", icon: "&mdash;", run: (ed) => ed.commands.setHorizontalRule() },
        { type: "table", name: "表格", desc: "插入 3x3 表格", icon: "&#9646;", run: (ed) => ed.commands.insertTable({ rows: 3, cols: 3, withHeaderRow: true }) },
      ];
      this._slashIndex = 0;
      const menu = document.getElementById("slash-menu");
      const list = menu ? menu.querySelector(".slash-menu__list") : null;

      const render = () => {
        if (!list) return;
        list.innerHTML = "";
        // 上下文过滤：单元格内不显示"表格"项（飞书行为：避免嵌套表格）
        const inTable = _editorInstance ? _editorInstance.isActive("table") : false;
        this._slashVisible = this._slashItems.filter((item) => !(item.type === "table" && inTable));
        if (this._slashIndex >= this._slashVisible.length) this._slashIndex = Math.max(0, this._slashVisible.length - 1);
        this._slashVisible.forEach((item, i) => {
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
          // 总数取上下文过滤后的可见项（单元格内隐藏表格项）
          const inTableK = _editorInstance ? _editorInstance.isActive("table") : false;
          const total = this._slashItems.filter((it) => !(it.type === "table" && inTableK)).length;
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
        // 方向键切换时滚动到可见区（菜单可滚动）
        if (i === this._slashIndex) child.scrollIntoView({ block: "nearest" });
      });
    },

    /** 选中斜杠菜单项：先删 "/" 恢复干净段落，再执行命令（避免命令把 "/" 变内容后删除范围错乱/误伤后续块） */
    _slashSelect(idx) {
      const item = this._slashVisible ? this._slashVisible[idx] : this._slashItems[idx];
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
    /** 统一构造保存 body（content + summary + 乐观锁指纹 expected_version） */
    /** 重命名当前文档（标题变化时）：文件 mv + 引用更新（后端），当前会话跟随新路径 */
    async _renameCurrentDocument(oldPath, newTitle) {
      const store = Alpine.store("app");
      const newName = MykRename.buildNewName(newTitle);
      await api.renameDocument(oldPath, newName);
      // 新路径 = 原目录 + 新文件名
      const newPath = MykRename.buildNewPath(oldPath, newName);
      store.currentPath = newPath;
      if (store.document) store.document.title = newTitle;
      // 路由跟随新路径（hash 更新；当前视图无需重载，内容已在编辑器）
      const hash = "doc/" + encodeURIComponent(newPath);
      if (window.location.hash !== "#" + hash) {
        history.replaceState(null, "", "#" + hash);
      }
      showToast("已重命名为 " + newTitle, "success");
      return newPath;
    },

    _buildSaveBody() {
      const store = Alpine.store("app");
      const md = this._editorToMarkdown();
      // summary 纳入乐观锁 version 基准（后端决定）：取编辑态输入框值，空则用文档标题兜底
      // （后端 REST 强制 summary 非空，空保存 400）
      const summary = (this.summaryValue || store.document?.summary || this.titleValue || "").trim();
      const body = { content: md, summary };
      if (store.document && store.document.version) body.expected_version = store.document.version;
      return body;
    },

    /**
     * 处理保存错误：409 冲突 → 弹可视化 diff（暂停自动保存）；其他 → false
     * @returns {boolean} 是否已处理（冲突）
     */
    /** 编辑态收到"文档已在别处修改"事件 → 主动比对版本，冲突立即弹 diff（不覆盖正在编辑的内容） */
    async _checkExternalModification() {
      const store = Alpine.store("app");
      if (store.currentView !== "edit" || !_editorInstance || this._conflictActive) return;
      try {
        const data = await api.getDocument(store.currentPath);
        if (data.version && store.document && data.version !== store.document.version) {
          // 内容被别处修改：用当前编辑器内容作为"我的"，服务端最新作对比
          this._conflictActive = true; // 暂停自动保存，等待用户决策
          const myMd = this._editorToMarkdown() || "";
          this._showConflictModal(
            myMd,
            data.content || "",
            (this.summaryValue || store.document.summary || "").trim(),
            data.summary || ""
          );
        }
      } catch (e) { /* 检查失败不打断编辑 */ }
    },

    _handleSaveError(e) {
      if (e && e.status === 409) {
        const detail = e.detail || {};
        const latestMd = detail.content || "";
        const myMd = this._editorToMarkdown() || "";
        // summary 纳入 version 基准后，可能出现"content 相同、summary 不同"的冲突（后端 409 带 current_summary）
        const latestSummary = detail.current_summary || "";
        const mySummary = (this.summaryValue || Alpine.store("app").document?.summary || "").trim();
        // 内容全等（保存竞态误报）：不弹框，静默同步最新 version 继续编辑
        if (myMd === latestMd && mySummary === latestSummary) {
          const store = Alpine.store("app");
          if (detail.current_version && store.document) {
            store.document.version = detail.current_version;
          }
          return true;
        }
        this._conflictActive = true; // 暂停后续自动保存，避免反复弹窗
        this._showConflictModal(myMd, latestMd, mySummary, latestSummary);
        return true;
      }
      return false;
    },

    /** 冲突可视化弹窗：两栏 diff（我的草稿 vs 服务端最新），行级 LCS 高亮；summary 有差异时单独展示 */
    _showConflictModal(myMd, latestMd, mySummary, latestSummary) {
      const store = Alpine.store("app");
      const existing = document.getElementById("conflict-modal");
      if (existing) existing.remove();

      const rows = lineDiff(myMd, latestMd);
      const esc = escapeHtml;
      // summary 差异区：content 相同但 summary 不同（后端 409 带 current_summary）也能可视化
      // 布局与正文一致：左=服务端，右=我的
      let summaryDiffHtml = "";
      if (String(mySummary || "") !== String(latestSummary || "")) {
        summaryDiffHtml =
          '<div class="conflict-diff conflict-diff--summary">' +
          '<div class="conflict-diff__col"><div class="conflict-diff__header">摘要（服务端）</div><div class="conflict-diff__body"><div class="conflict-diff__line' + (latestSummary ? ' conflict-diff__line--add' : ' conflict-diff__line--gap') + '">' + esc(latestSummary || '（空）') + '</div></div></div>' +
          '<div class="conflict-diff__col"><div class="conflict-diff__header">摘要（我的）</div><div class="conflict-diff__body"><div class="conflict-diff__line' + (mySummary ? ' conflict-diff__line--add' : ' conflict-diff__line--gap') + '">' + esc(mySummary || '（空）') + '</div></div></div>' +
          '</div>';
      }
      // 左列 = 服务端（add 行=服务端有而我没有 → 绿，在左）；右列 = 我的（del 行=我有而服务端没有 → 红，在右）
      // 行号每列独立计数（服务端从 1 计，我的从 1 计），便于对照
      let leftHtml = "", rightHtml = "";
      let leftLine = 1, rightLine = 1;
      rows.forEach(r => {
        const lineHtml = (num, sign, content, cls) =>
          '<div class="conflict-diff__line' + (cls ? " " + cls : "") + '">' +
          '<span class="conflict-diff__num">' + num + '</span>' +
          '<span class="conflict-diff__ln">' + sign + '</span>' + content + '</div>';
        if (r.type === "same") {
          leftHtml += lineHtml(leftLine++, "·", esc(r.a), "");
          rightHtml += lineHtml(rightLine++, "·", esc(r.b), "");
        } else if (r.type === "del") {
          // 我有、服务端无 → 左（服务端）空，右（我的）红（带我的行号）
          leftHtml += '<div class="conflict-diff__line conflict-diff__line--gap"></div>';
          rightHtml += lineHtml(rightLine++, "-", esc(r.a), "conflict-diff__line--del");
        } else {
          // 服务端有、我没有 → 左（服务端）绿（带服务端行号），右（我的）空
          leftHtml += lineHtml(leftLine++, "+", esc(r.b), "conflict-diff__line--add");
          rightHtml += '<div class="conflict-diff__line conflict-diff__line--gap"></div>';
        }
      });

      const modal = document.createElement("div");
      modal.id = "conflict-modal";
      modal.className = "conflict-modal";
      modal.innerHTML =
        '<div class="conflict-modal__backdrop"></div>' +
        '<div class="conflict-modal__card">' +
        '<div class="conflict-modal__title">文档已在别处被修改</div>' +
        '<div class="conflict-modal__desc">你编辑期间，它被其他窗口、设备或 AI 工具更新了。对比下方差异，选择处理方式。<span class="conflict-desc--add">绿色为新增</span>、<span class="conflict-desc--del">红色为删除</span>。</div>' +
        summaryDiffHtml +
        '<div class="conflict-diff">' +
        '<div class="conflict-diff__col conflict-diff__col--left"><div class="conflict-diff__header">服务端最新版本</div><div class="conflict-diff__body">' + leftHtml + '</div></div>' +
        '<div class="conflict-diff__col conflict-diff__col--right"><div class="conflict-diff__header">我的修改（草稿）</div><div class="conflict-diff__body">' + rightHtml + '</div></div>' +
        '</div>' +
        '<div class="conflict-modal__actions">' +
        '<button class="conflict-modal__btn conflict-modal__btn--ghost" id="conflict-cancel">取消（继续编辑）</button>' +
        '<button class="conflict-modal__btn conflict-modal__btn--latest" id="conflict-latest">采用服务端版本</button>' +
        '<button class="conflict-modal__btn conflict-modal__btn--mine" id="conflict-mine">保留我的修改</button>' +
        '</div>' +
        '</div>';
      (document.querySelector(".editor-shell") || document.body).appendChild(modal);

      // 保留我的修改：不带 expected_version 强写
      modal.querySelector("#conflict-mine").addEventListener("click", async () => {
        const path = this._editingPath || store.currentPath;
        try {
          await store.saveDocumentSilent(path, { content: myMd, summary: mySummary || store.document?.summary || "" });
          store.document = { ...store.document, content: myMd, summary: mySummary || "", version: "" };
          this._conflictActive = false;
          modal.remove();
          showToast("已保留你的修改", "success");
        } catch (e2) {
          modal.remove();
          showToast(e2.message || "保存失败", "error");
        }
      });

      // 采用最新版本：重载文档（effect 自动更新编辑器内容），丢弃我的
      modal.querySelector("#conflict-latest").addEventListener("click", async () => {
        const path = this._editingPath || store.currentPath;
        this._conflictActive = false;
        modal.remove();
        try {
          await store.loadDocument(path);
        } catch (e) {}
        // 回到只读（最新内容已加载）
        if (_editorInstance) _editorInstance.setEditable(false);
        this._hideEditDecorations();
        this._editingPath = null;
        if (store.currentPath === path) store.setView("view", path);
        showToast("已加载最新版本", "success");
      });

      modal.querySelector("#conflict-cancel").addEventListener("click", () => {
        modal.remove();
      });
    },

    async _performSave() {
      const store = Alpine.store("app");
      if (store.isLocked || store.currentView !== "edit" || !_editorInstance) return;
      if (this._conflictActive) return; // 冲突未解决前暂停自动保存
      const md = this._editorToMarkdown();
      if (!md) return;
      // 内容未变 → 不重复调 API（后端 unchanged 是兜底，前端先自己比对）
      const current = store.document?.content || "";
      if (md === current) return;
      try {
        await store.saveDocumentSilent(store.currentPath, this._buildSaveBody());
        // 保存成功且之前有离线草稿 → 清理（_draftDelete 为模块级函数）
        await _draftDelete(store.currentPath);
        if (store.draftBanner) store.draftBanner = false;
      } catch (e) {
        // 409 冲突 → 弹可视化 diff（暂停自动保存）
        if (this._handleSaveError(e)) return;
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
