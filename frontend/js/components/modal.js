document.addEventListener("alpine:init", () => {
Alpine.data("modalComponent", () => ({
    newDocName: "",
    newDocSummary: "",
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
        // parentPath 语义 = "目标目录"，而调用方传的是 currentPath（可能是文档/项目路径）：
        // 统一规整——文档路径 → 所在目录；项目路径 → 其 common-knowledge；空 → 根 common-knowledge
        const raw = store.modalData?.parentPath || "";
        const parentPath = normalizeDocParentPath(raw);
        const fullPath = `${parentPath}/${name}.md`;

        await api.createDocument(fullPath, {
          // 正文不能为空（后端 empty_body 校验）→ 默认以标题作 H1 起步
          content: `# ${name}\n\n`,
          summary: this.newDocSummary.trim(),
        });

        showToast("文档已创建", "success");
        store.closeModal();
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
        }
      });
    },
  }))
});

/** 把"当前文档/项目路径"规整为"新建文档的目标目录"：
 *  文档路径 …/common-knowledge/A.md → …/common-knowledge（所在目录）
 *  项目路径 projects/X（或 archive/X）→ projects/X/common-knowledge
 *  目录（common-knowledge / projects/X/common-knowledge）→ 保持
 *  空 → common-knowledge（根） */
function normalizeDocParentPath(p) {
  if (!p) return "common-knowledge";
  if (p.endsWith(".md")) {
    const i = p.lastIndexOf("/");
    return i > 0 ? p.slice(0, i) : "common-knowledge";
  }
  if (p.startsWith("projects/") || p.startsWith("archive/")) {
    return `${p.replace(/\/+$/, "")}/common-knowledge`;
  }
  return p;
}
