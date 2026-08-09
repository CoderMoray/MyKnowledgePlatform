document.addEventListener("alpine:init", () => {
// 全量项目候选缓存（_ensureProjectTree 递归加载一次）：{label, hierarchy, value}
let _projectCandidates = null;
Alpine.data("modalComponent", () => ({
    newDocName: "",
    newDocSummary: "",
    /** 新建文档归属：内部完整路径（创建用）+ 显示项目名 + 层级描述 */
    newDocParent: "",
    newDocParentName: "",
    parentHierarchy: "",
    parentSuggestions: [],
    parentOpen: false,
    parentIdx: -1,          // 键盘导航高亮索引
    _parentSearchTimer: null,
    _parentSearchSeq: 0,
    _browseAll: [],         // 空输入浏览：全量本地候选
    _browseCount: 0,        // 已加载数量（滚动每次 +8）
    renameValue: "",
    creating: false,
    identityNickname: "",
    identityEmail: "",
    setupNickname: "",
    setupEmail: "",

    isValidEmail(email) {
      return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email || "");
    },

    async createDocument() {
      const store = Alpine.store("app");
      const name = this.newDocName.trim();
      if (!name || store.isLocked) return;

      // 名称预校验（复用 rename 的 titleError + 挡系统保留名 readme）：
      // 避免把非法路径提交给后端等 400，本地立即提示
      const nameErr = (window.MykRename && window.MykRename.titleError(name)) || "";
      if (!nameErr && name.toLowerCase().replace(/\.md$/i, "") === "readme") {
        showToast("readme 是系统索引文档，不能作为新建文档名", "warning");
        return;
      }
      if (nameErr) {
        showToast(nameErr, "warning");
        return;
      }

      this.creating = true;
      try {
        // 归属 = 用户选/输入的归属（显示名 + 完整路径分离）；解析成最终目录
        const parentPath = this._resolveDocParent();
        if (!parentPath) {
          showToast("未找到匹配的项目目录，请从下拉中选择", "warning");
          return;
        }
        const fullPath = `${parentPath}/${name}.md`;

        await api.createDocument(fullPath, {
          // 正文不能为空（后端 empty_body 校验）→ 默认以标题作 H1 起步
          content: `# ${name}\n\n`,
          summary: this.newDocSummary.trim(),
        });

        showToast("文档已创建", "success");
        store.closeModal();
        // 创建后跳转到新文档（编辑态）
        window.location.hash = `edit/${hashEncode(fullPath)}`;
      } catch (err) {
        if (err.isLocked) {
          showToast("知识库正在整理中，暂时只读", "warning");
        } else {
          showToast(err.message || "创建失败", "error");
        }
      } finally {
        this.creating = false;
      }
    },

    /** 解析最终归属目录：显示名与已选路径一致 → 用之；不一致（手改未选）→ 按名称匹配候选 */
    _resolveDocParent() {
      const name = (this.newDocParentName || "").trim();
      const cands = _projectCandidates || [];
      const cur = cands.find((c) => c.value === this.newDocParent);
      if (cur && cur.label === name) return this.newDocParent;
      const hit = cands.find((c) => c.label === name);
      return hit ? hit.value : "";
    },

    async confirmDelete() {
      const store = Alpine.store("app");
      const path = store.modalData?.path;
      if (!path || store.isLocked) return;

      try {
        await api.deleteDocument(path);
        store.closeModal();

        // 倒计时面板：明确跳转目标（项目页 / 首页）
        const projPath = projectName(path);
        showCountdownToast(
          projPath
            ? "已移入垃圾箱，3 秒后返回项目「" + fileName(projPath) + "」"
            : "已移入垃圾箱，3 秒后返回首页",
          () => {
            if (projPath) window.location.hash = "project/" + projPath;
            else window.location.hash = "dashboard";
          },
          3
        );
      } catch (err) {
        showToast(err.message || "删除失败", "error");
      }
    },

    async confirmRename() {
      const store = Alpine.store("app");
      const path = store.modalData?.path;
      const newName = this.renameValue.trim();
      if (!path || !newName || store.isLocked) return;

      try {
        // 判断是项目改名还是文档改名
        if (store.modal === "rename-project") {
          await api.renameProject(path, newName);
        } else {
          await api.renameDocument(path, newName);
        }
        showToast("已改名", "success");
        store.closeModal();

        const parts = path.replace(/\\/g, "/").split("/");
        parts[parts.length - 1] = newName.includes(".") ? newName : newName + ".md";
        const newPath = parts.join("/");
        window.location.hash = `doc/${hashEncode(newPath)}`;
      } catch (err) {
        showToast(err.message || "改名失败", "error");
      }
    },

    async saveIdentity() {
      const store = Alpine.store("app");
      const nick = this.identityNickname.trim();
      const email = this.identityEmail.trim();
      if (!nick || !email || !this.isValidEmail(email)) return;
      try {
        await store.saveIdentity(nick, email);
        showToast("个人信息已保存", "success");
        store.closeModal();
      } catch (err) {
        showToast(err.message || "保存失败", "error");
      }
    },

    async saveSetup() {
      const store = Alpine.store("app");
      const nick = this.setupNickname.trim();
      const email = this.setupEmail.trim();
      if (!nick || !email || !this.isValidEmail(email)) return;
      try {
        await store.saveIdentity(nick, email);
        showToast("欢迎！", "success");
        window.location.hash = "dashboard";
      } catch (err) {
        showToast(err.message || "保存失败", "error");
      }
    },

    init() {
      const store = Alpine.store("app");
      this.$watch("$store.app.modal", (val) => {
        if (val === "edit-identity") {
          this.identityNickname = store.nickname || "";
          this.identityEmail = store.email || "";
        } else if (val === "new-doc") {
          this._initNewDocParent();
        }
      });
    },

    /** 打开新建弹窗：加载全量项目树 → 默认归属 = 当前上下文目录 → 预填候选 */
    async _initNewDocParent() {
      const store = Alpine.store("app");
      await this._ensureProjectTree();
      const target = normalizeDocParentPath(
        (store.modalData && store.modalData.parentPath) || store.currentPath || "");
      const hit = _projectCandidates.find((c) => c.value === target);
      this.newDocParent = hit ? hit.value : target;
      this.newDocParentName = hit ? hit.label : "公共知识";
      this.parentHierarchy = hit ? hit.hierarchy : "";
      this.parentSuggestions = _projectCandidates.slice(0, 8);
      this.parentIdx = -1;
      this.parentOpen = false;
    },

    /** 递归加载全量项目树（顶层 + 所有层级子项目），缓存到模块级 */
    async _ensureProjectTree() {
      if (_projectCandidates) return;
      const allPaths = [];
      // dir = "projects" / "archive"（项目根容器），items = 项目列表（项目本身）
      async function walk(dir) {
        let items = [];
        try {
          const data = await api.list(dir);
          items = (data && data.items) || [];
        } catch (_) { return; }
        for (const proj of items) {
          if (!proj.is_dir || /^\./.test(proj.name || "")) continue; // 跳过 .DS_Store 等
          allPaths.push(proj.path);
          await walkChildren(proj.path); // 递归：项目/projects/子项目/…
        }
      }
      // 子项目容器：项目路径 + "/projects"，items = 子项目列表
      async function walkChildren(projectPath) {
        try {
          const d = await api.list(`${projectPath}/projects`);
          const children = (d && d.items) || [];
          for (const child of children) {
            if (!child.is_dir || /^\./.test(child.name || "")) continue;
            allPaths.push(child.path);
            await walkChildren(child.path);
          }
        } catch (_) { /* 无子项目容器 */ }
      }
      await walk("projects");
      _projectCandidates = [
        { label: "公共知识", hierarchy: "", value: "common-knowledge" },
        ...allPaths.map((p) => makeParentCandidate(`${p}/common-knowledge`)),
      ];
    },

    /** 输入匹配：非空 → 后端项目级搜索（标题/摘要/正文，kind=projects，300ms debounce）；
     *  空输入 → 本地项目树分页浏览（每次 8，滚动到底加载更多）。参考 ref 的搜索交互 */
    onParentInput() {
      const q = (this.newDocParentName || "").trim();
      if (!q) {
        this._browseAll = _projectCandidates || [];
        this._browseCount = 8;
        this.parentSuggestions = this._browseAll.slice(0, this._browseCount);
        this.parentOpen = true;
        this.parentIdx = -1;
        return;
      }
      clearTimeout(this._parentSearchTimer);
      const seq = ++this._parentSearchSeq;
      this._parentSearchTimer = setTimeout(async () => {
        try {
          const data = await api.searchDocuments(q, 20, "projects");
          if (seq !== this._parentSearchSeq) return; // 过期响应丢弃
          // 后端项目级结果 {path: 项目目录, title, summary} → 候选格式
          this.parentSuggestions = ((data && data.results) || []).map((r) => ({
            label: r.title || String(r.path || "").split("/").pop() || "",
            value: `${r.path}/common-knowledge`,
            hierarchy: makeParentHierarchy(r.path),
          }));
          this.parentOpen = true;
          this.parentIdx = -1;
        } catch (_) { /* 搜索失败静默 */ }
      }, 300);
    },

    /** 空输入浏览模式：下拉滚动到底 → 再加载 8 个 */
    onParentScroll(e) {
      if (!this.parentOpen || !this._browseAll || !this._browseAll.length) return;
      const el = e && e.target;
      if (!el) return;
      if (el.scrollTop + el.clientHeight >= el.scrollHeight - 5) {
        if (this._browseCount >= this._browseAll.length) return;
        this._browseCount += 8;
        this.parentSuggestions = this._browseAll.slice(0, this._browseCount);
      }
    },

    /** 选中候选：填显示名 + 完整路径 + 层级，收起下拉 */
    selectParent(item) {
      if (!item) return;
      this.newDocParentName = item.label;
      this.newDocParent = item.value;
      this.parentHierarchy = item.hierarchy;
      this.parentOpen = false;
      this.parentIdx = -1;
    },

    /** 键盘导航：↑↓ 高亮，Enter 选中 */
    onParentKeydown(e) {
      const items = this.parentSuggestions;
      if (!this.parentOpen || !items.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        this.parentIdx = (this.parentIdx + 1) % items.length;
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        this.parentIdx = (this.parentIdx - 1 + items.length) % items.length;
      } else if (e.key === "Enter") {
        if (this.parentIdx >= 0 && this.parentIdx < items.length) {
          e.preventDefault();
          this.selectParent(items[this.parentIdx]);
        }
      } else if (e.key === "Escape") {
        this.parentOpen = false;
        this.parentIdx = -1;
      }
    },
  }))
});

/** 把"当前文档/项目路径"规整为"新建文档的目标目录"：
 *  文档路径 …/common-knowledge/A.md → …/common-knowledge（所在目录）
 *  项目路径 projects/X（或 archive/X）→ projects/X/common-knowledge
 *  已是完整目录（common-knowledge / …/common-knowledge）→ 保持（防重复追加）
 *  空 → common-knowledge（根） */
function normalizeDocParentPath(p) {
  if (!p) return "common-knowledge";
  if (p.endsWith(".md")) {
    const i = p.lastIndexOf("/");
    return i > 0 ? p.slice(0, i) : "common-knowledge";
  }
  if (p === "common-knowledge" || p.endsWith("/common-knowledge")) return p;
  if (p.startsWith("projects/") || p.startsWith("archive/")) {
    return `${p.replace(/\/+$/, "")}/common-knowledge`;
  }
  return p;
}

/** 从项目路径（projects/A/B）解析层级小字：表层「主要项目」、多级「A / B」 */
function makeParentHierarchy(projectPath) {
  const chain = (projectPath || "").replace(/^(?:projects|archive)\//, "").split("/");
  if (!chain[0]) return "";
  return chain.length > 1 ? chain.join(" / ") : "主要项目";
}

/** 从完整目标目录构造候选：{ label: 目标项目名, hierarchy: 层级, value }
 *  projects/A/B/common-knowledge → label=B, hierarchy="A / B"
 *  projects/X/common-knowledge   → label=X, hierarchy="主要项目"（表层项目）
 *  common-knowledge              → label=公共知识, hierarchy="" */
function makeParentCandidate(value) {
  const m = value.match(/^(?:projects|archive)\/(.+)\/common-knowledge$/);
  if (!m) return { label: "公共知识", hierarchy: "", value };
  const chain = m[1].split("/");
  return {
    label: chain[chain.length - 1],
    hierarchy: makeParentHierarchy(m[1]),
    value,
  };
}
