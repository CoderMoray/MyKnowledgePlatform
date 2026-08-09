document.addEventListener("alpine:init", () => {
Alpine.data("modalComponent", () => ({
    newDocName: "",
    newDocSummary: "",
    /** 新建文档归属目录（可编辑，默认当前上下文；输入匹配项目/子项目下拉） */
    newDocParent: "",
    parentSuggestions: [],
    parentOpen: false,
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
        // 归属 = 用户可编辑的 newDocParent（默认当前上下文目录）；normalize 兜底
        const parentPath = normalizeDocParentPath(this.newDocParent || "");
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
          // 默认归属 = 当前上下文的目录（文档所在目录 / 项目 common-knowledge / 根）
          this.newDocParent = normalizeDocParentPath(
            (store.modalData && store.modalData.parentPath) || store.currentPath || "");
          this.parentSuggestions = this.parentCandidates().slice(0, 8);
          this.parentOpen = false;
        }
      });
    },

    /** 归属候选：根 + 顶层项目 + 当前项目页的子项目
     *  每项 { label: 目标项目名, hierarchy: 层级小字, value: 完整目标目录 } */
    parentCandidates() {
      const store = Alpine.store("app");
      const cands = [{ label: "公共知识", hierarchy: "", value: "common-knowledge" }];
      (store.projects || []).forEach((p) => {
        if (p.path) cands.push(makeParentCandidate(`${p.path}/common-knowledge`));
      });
      (store.projectSubprojects || []).forEach((s) => {
        if (s.path) cands.push(makeParentCandidate(`${s.path}/common-knowledge`));
      });
      return cands;
    },

    /** 输入时按名称/路径过滤候选，展示下拉 */
    onParentInput() {
      const q = (this.newDocParent || "").trim().toLowerCase();
      const all = this.parentCandidates();
      this.parentSuggestions = q
        ? all.filter((c) =>
            c.label.toLowerCase().includes(q) || c.value.toLowerCase().includes(q))
        : all.slice(0, 8);
      this.parentOpen = true;
    },

    /** 选中下拉候选 → 填回输入框并收起下拉 */
    selectParent(value) {
      this.newDocParent = value;
      this.parentOpen = false;
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
    hierarchy: chain.length > 1 ? chain.join(" / ") : "主要项目",
    value,
  };
}
