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
    _parentHintRestore: null, // hover 前 hint 状态（离开下拉时恢复）
    _browseAll: [],         // 空输入浏览：全量本地候选
    _browseCount: 0,        // 已加载数量（滚动每次 +8）
    renameValue: "",
    creating: false,
    identityNickname: "",
    identityEmail: "",
    setupNickname: "",
    setupEmail: "",
    setupCompany: "",
    setupOrgCode: "",

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
        // 刷新目标项目侧栏树（树未展开/无缓存时静默，下次展开自然加载）
        store.refreshProjectTree(projectName(parentPath)).catch(() => {});
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

        const view = store.currentView;
        if (view === "dashboard" || view === "project") {
          // 卡片删除（dashboard 公共知识 / 项目视图）：原地不跳、无倒计时。
          // SSE updated 事件已按当前视图自动刷新列表，这里显式刷新双保险（不依赖 SSE 时序）；
          // 侧栏树同步（项目文档，公共知识 parent 为空自动跳过）。
          if (view === "dashboard") store.loadDashboard().catch(() => {});
          else store.loadProjectDocuments(store.currentPath).catch(() => {});
          store.refreshProjectTree(store._treeParentPath(path)).catch(() => {});
          showToast("已移入垃圾箱，30 天内可恢复", "success");
        } else {
          // 文档页删除（view/edit）：保留 3 秒倒计时跳转（hash 必变 → 触发刷新）
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
        }
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

    /** Step1：保存身份 + 企业名称/组织代码（POST /api/config/share，失败 toast 不阻断）。
     *  @returns {boolean} 保存是否成功（身份失败返回 false 留页；share 配置失败不阻断返回 true） */
    async saveSetup() {
      const store = Alpine.store("app");
      const nick = this.setupNickname.trim();
      const email = this.setupEmail.trim();
      const company = store.setupCompany.trim();
      const orgCode = store.setupOrgCode.trim();
      if (!nick || !email || !this.isValidEmail(email)) return false;
      try {
        await store.saveIdentity(nick, email);
        showToast("身份已保存", "success");
      } catch (err) {
        showToast(err.message || "保存失败", "error");
        return false;
      }
      // 企业名称 + 组织代码 → 分享配置（部分更新幂等）；失败 toast 不阻断进入下一步
      if (company && orgCode) {
        try {
          await api.setConfigShare(company, orgCode);
        } catch (err) {
          showToast(err.message || "分享配置保存失败，可稍后在设置中重试", "error");
        }
      }
      return true;
    },

    /** 引导向导：下一步（4 页 3 步：1 身份 → 2 平台多选 → 3 执行+结论 → 4 完成） */
    async guideNext() {
      const store = Alpine.store("app");
      if (store.guideStep === 1) {
        // Step1：4 字段全有效 + 保存身份/分享配置 → 进入 2.1 平台多选
        if (!store.guideStep1Valid(this.setupNickname, this.setupEmail)) return;
        if (!store.identitySet) {
          const ok = await this.saveSetup();
          if (!ok) return; // 身份保存失败留在 Step1
        } else if (store.setupCompany || store.setupOrgCode) {
          // 已设身份（rerunGuide 场景）：企业名称/组织代码已填则补写分享配置，失败不阻断
          try {
            if (store.setupCompany.trim() && store.setupOrgCode.trim()) {
              await api.setConfigShare(store.setupCompany.trim(), store.setupOrgCode.trim());
            }
          } catch (err) {
            showToast(err.message || "分享配置保存失败，可稍后在设置中重试", "error");
          }
        }
        store.guideStep = 2;
      } else if (store.guideStep === 2) {
        // Step2.1：至少选 1 平台 → 进入 2.2 执行+结论，自动执行
        if (!store.guideStep2Valid()) return;
        store.guideStep = 3;
        store.guideExecute();
      } else if (store.guideStep === 3) {
        // Step2.2：执行完成后才可进入 Step3 完成
        if (!store.guideExecDone) return;
        store.guideStep = 4;
      } else {
        // Step4 完成 → 开始使用
        window.location.hash = "dashboard";
      }
    },

    /** 引导向导：上一步（4 页：4→3→2→1；2.2 执行中不可回退） */
    guidePrev() {
      const store = Alpine.store("app");
      if (store.guideExecuting) return; // 执行中禁止回退
      if (store.guideStep === 2) store.guideStep = 1;
      else if (store.guideStep === 3) store.guideStep = 2;
      else if (store.guideStep === 4) store.guideStep = 3;
    },

    /** 配置 modal：切换左侧分组 */
    settingsNav(group) {
      const store = Alpine.store("app");
      store.settingsGroup = group;
      // 切到 MCP 分组时若 clientConfig 是旧缓存则轻量刷新 connection（避免显示过期连接态）
      if (group === "mcp") store.refreshClientConfigIfStale();
    },

    /** 配置 modal · 账号卡：保存昵称/邮箱 */
    async saveSettingsIdentity() {
      const store = Alpine.store("app");
      const nick = this.identityNickname.trim();
      const email = this.identityEmail.trim();
      if (!nick || !email || !this.isValidEmail(email)) return;
      try {
        await store.saveIdentity(nick, email);
        showToast("个人信息已保存", "success");
      } catch (err) {
        showToast(err.message || "保存失败", "error");
      }
    },

    /** 配置 modal / 引导 Step2 · AI 协作：写入配置 */
    configureAi(platform, kind) {
      return Alpine.store("app").configureClient(platform, kind);
    },

    /** 配置 modal / 引导 Step2 · AI 协作：复制 prompt 兜底 */
    copyAiPrompt(platform, kind) {
      return Alpine.store("app").copyClientPrompt(platform, kind);
    },

    init() {
      const store = Alpine.store("app");
      this.$watch("$store.app.modal", (val) => {
        if (val === "edit-identity" || val === "settings") {
          // 身份卡共用 identityNickname/Email（edit-identity 与 settings 账号卡）
          this.identityNickname = store.nickname || "";
          this.identityEmail = store.email || "";
          if (val === "settings") {
            store.settingsGroup = "account";
            store.loadClientConfig().catch(() => {});
          }
        } else if (val === "new-doc") {
          this._initNewDocParent();
        }
      });
      // 引导向导视图：进入 setup 重置 Step1（首次自动触发 / 重新运行引导）
      this.$watch("$store.app.currentView", (val) => {
        if (val === "setup") {
          store.guideStep = 1;
          // 重置 Step2（2.1 选择集 / 2.2 执行态 / Enchante 按钮态）
          store.resetGuideExec();
          // 身份已设置时预填（rerunGuide 进入场景；首次进入 setup 身份未设留空待填）
          if (store.identitySet) {
            this.setupNickname = store.nickname || "";
            this.setupEmail = store.email || "";
          }
          store.loadClientConfig().catch(() => {});
          // 预填分享配置（企业名称/组织代码）：.env 已有值则回显到 Step1（本机用户自己配置）
          api.getConfigStatus()
            .then((cs) => {
              if (cs && cs.share_code) store.setupCompany = cs.share_code;
              if (cs && cs.share_map && cs.share_map !== "000") store.setupOrgCode = cs.share_map;
            })
            .catch(() => {});
        }
      });
      // 高度柔和动画：候选/展开状态变化时，先定格当前高度再过渡到目标高度
      // （候选数变化 5↔1 时下拉高度平滑缩放，而非突变；0.3s 匹配 CSS transition）
      this.$watch("parentSuggestions", () => {
        if (this.parentOpen) requestAnimationFrame(() => this._animateListHeight());
      });
      this.$watch("parentOpen", (val) => {
        requestAnimationFrame(() => this._animateListHeight());
      });
    },

    /** 两段式高度动画：定格当前高度 → 下一帧（DOM 更新完成）读目标高度并过渡。
     *  候选数变化（5↔1）或展开/收起时高度平滑缩放，0.3s 匹配 CSS transition。
     *  注意：外层 overflow:hidden → 其 scrollHeight 下限=clientHeight（读不到真实内容），
     *  必须读内层 .parent-picker__scroll 的内容高度（≤210px 滚动上限） */
    _animateListHeight() {
      const el = this.$refs.parentList;
      if (!el) return;
      const current = el.getBoundingClientRect().height;
      el.style.transition = "none";            // 1. 关过渡，定格
      el.style.height = current + "px";
      requestAnimationFrame(() => {            // 2. 下一帧：DOM 已更新，读真实目标
        const inner = el.querySelector(".parent-picker__scroll");
        const contentH = inner ? inner.scrollHeight : el.scrollHeight;
        const target = this.parentOpen ? Math.min(contentH, 210) : 0;
        if (Math.abs(target - el.getBoundingClientRect().height) < 1) {
          el.style.transition = "";
          el.style.height = target + "px";     // 无变化也落定
          return;
        }
        el.style.transition = "";              // 3. 恢复 CSS 过渡（0.3s ease）
        el.style.height = target + "px";       // 4. 过渡到目标
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
      this.parentHierarchy = hit ? hit.hierarchy : "所有项目";
      this._browseAll = _projectCandidates || [];
      this._browseCount = 5;
      this.parentSuggestions = this._browseSuggestions();
      this.parentIdx = -1;
      this.parentOpen = false;
    },

    /** 浏览候选：全量项目列表按分页切片，候选 q = 当前输入值（默认归属高亮，与搜索模式一致） */
    _browseSuggestions() {
      const q = this.newDocParentName || "";
      return (this._browseAll || []).slice(0, this._browseCount).map((c) => ({
        ...c,
        q, // 高亮词 = 当前输入框内容（浏览模式也高亮默认归属；搜索模式由后端结果带 q）
      }));
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
      // 防御：过滤容器保留名（archive/common-knowledge/projects/readme.md）——
      // 后端校验禁止项目用这些名字，但历史数据/迁移可能残留（如 Training/projects 混入）
      const RESERVED = new Set(["archive", "common-knowledge", "projects", "readme.md"]);
      async function walkChildren(projectPath) {
        try {
          const d = await api.list(`${projectPath}/projects`);
          const children = (d && d.items) || [];
          for (const child of children) {
            if (!child.is_dir || /^\./.test(child.name || "")) continue;
            if (RESERVED.has(child.name)) continue; // 容器目录不是子项目
            allPaths.push(child.path);
            await walkChildren(child.path);
          }
        } catch (_) { /* 无子项目容器 */ }
      }
      await walk("projects");
      // 并发拉各项目 readme 摘要（供下拉项第二行展示；失败静默为空）
      const summaries = await Promise.all(allPaths.map(async (p) => {
        try {
          const d = await api.getDocument(`${p}/readme.md`);
          return (d && d.summary) || "";
        } catch (_) { return ""; }
      }));
      // 根 readme（公共知识）摘要
      let rootSummary = "";
      try {
        const d = await api.getDocument("readme.md");
        rootSummary = (d && d.summary) || "";
      } catch (_) { /* 根 readme 缺失则用默认文案 */ }
      _projectCandidates = [
        { label: "公共知识", hierarchy: "所有项目", summary: rootSummary || "所有项目", value: "common-knowledge", q: "" },
        ...allPaths.map((p, i) => makeParentCandidate(`${p}/common-knowledge`, summaries[i])),
      ];
    },

    /** 点击归属输入框：全选当前值（用户输入即替换，避免追加成"默认值+新输入"搜不到）
     *  + 打开下拉；内容未变化 → 不搜索（保持当前候选/浏览） */
    onParentClick() {
      const inp = this.$refs.parentInput;
      if (inp) inp.select();
      if (!this.parentSuggestions.length) this._refreshBrowse();
      this.parentOpen = true;
      this.parentIdx = -1;
    },

    /** 输入事件（触发 = 用户打字；点击 select 不触发 input，走 onParentClick）：
     *  任何 input 都搜索（新增/删除/替换/重输同内容，用户要求"文本变动都触发"）；
     *  删空 → 本地浏览。300ms debounce + seq 丢弃过期响应（同 ref 搜索）。
     *  输入时 hint 显示"检索中..."（占位文本，保持布局稳定不跳动） */
    onParentInput() {
      const raw = this.newDocParentName || "";
      if (raw.trim()) {
        this.parentHierarchy = "检索中..."; // 占位：正在搜索，保持 hint 区域高度
        this._doParentSearch(raw.trim());
      } else {
        this.parentHierarchy = "选择归属项目"; // 浏览模式占位
        this._refreshBrowse();
      }
      this.parentOpen = true;
      this.parentIdx = -1;
    },

    /** 空输入浏览：本地项目树分页（每次 5，滚动到底加载更多）；候选高亮词 = 当前输入值 */
    _refreshBrowse() {
      this._browseAll = _projectCandidates || [];
      this._browseCount = 5;
      this.parentSuggestions = this._browseSuggestions();
    },

    /** 后端项目级搜索（参考 ref：debounce + seq 过期丢弃） */
    _doParentSearch(q) {
      if (!q) { this._refreshBrowse(); return; }
      clearTimeout(this._parentSearchTimer);
      const seq = ++this._parentSearchSeq;
      this._parentSearchTimer = setTimeout(async () => {
        try {
          const data = await api.searchDocuments(q, 20, "projects");
          if (seq !== this._parentSearchSeq) return; // 过期响应丢弃
          const results = (data && data.results) || [];
          // hint 从"检索中..."更新为结果数（保持区域高度，布局不跳动）
          this.parentHierarchy = results.length
            ? `找到 ${results.length} 个匹配项目`
            : "未找到匹配项目";
          // 后端项目级结果 {path: 项目目录或空(根readme), title, summary} → 候选格式
          this.parentSuggestions = results.map((r) => ({
            label: r.title || String(r.path || "").split("/").pop() || "公共知识",
            // path 空 = 根 readme（公共知识归属）
            value: r.path ? `${r.path}/common-knowledge` : "common-knowledge",
            hierarchy: r.path ? makeParentHierarchy(r.path) : "所有项目",
            summary: r.summary || "",
            q, // 高亮词（浏览模式为空 → 不高亮）
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
        this._browseCount += 5;
        this.parentSuggestions = this._browseSuggestions();
      }
    },

    /** 匹配高亮：文本中命中 q 的子串包上主题色 span（大小写不敏感，HTML 转义防注入） */
    highlightMatch(text, q) {
      const t = String(text || "");
      if (!q) return escapeHtml(t);
      const lower = t.toLowerCase();
      const ql = q.toLowerCase();
      let out = "";
      let i = 0;
      let idx = lower.indexOf(ql);
      if (idx === -1) return escapeHtml(t);
      while (idx !== -1) {
        out += escapeHtml(t.slice(i, idx));
        out += `<span class="parent-picker__match">${escapeHtml(t.slice(idx, idx + q.length))}</span>`;
        i = idx + q.length;
        idx = lower.indexOf(ql, i);
      }
      out += escapeHtml(t.slice(i));
      return out;
    },

    /** 选中候选：填显示名 + 完整路径 + 层级，收起下拉 */
    selectParent(item) {
      if (!item) return;
      this.newDocParentName = item.label;
      this.newDocParent = item.value;
      this.parentHierarchy = item.hierarchy;
      this._parentHintRestore = null; // 选中即确定，清掉 hover 恢复标记
      this.parentOpen = false;
      this.parentIdx = -1;
    },

    /** hover/键盘高亮候选：hint 显示该候选的层级（主要项目/父/子）；
     *  首次进入记录 hover 前的 hint（离开时恢复，避免覆盖搜索/浏览状态文本） */
    onParentHover(item, i) {
      if (this._parentHintRestore === null) {
        this._parentHintRestore = this.parentHierarchy; // 记录进入前的状态
      }
      this.parentIdx = i;
      if (item && item.hierarchy) this.parentHierarchy = item.hierarchy;
    },

    /** 离开下拉：恢复 hover 前的 hint（搜索"找到 N 个"/浏览"选择归属项目"） */
    onParentLeave() {
      if (this._parentHintRestore !== null) {
        this.parentHierarchy = this._parentHintRestore;
        this._parentHintRestore = null;
      }
      this.parentIdx = -1;
    },

    /** 键盘导航：↑↓ 高亮（自动滚动跟随 + 浏览模式到底先加载更多再循环），Enter 选中 */
    onParentKeydown(e) {
      const items = this.parentSuggestions;
      if (!this.parentOpen || !items.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        let next = this.parentIdx + 1;
        const canLoadMore = next >= items.length
          && this._browseAll && this._browseCount < this._browseAll.length;
        if (canLoadMore) {
          // 浏览模式分页：到达已加载末尾且还有更多 → 先加载更多，next 指向新窗口下一项
          this._browseCount = Math.min(this._browseCount + 5, this._browseAll.length);
          this.parentSuggestions = this._browseSuggestions();
        } else {
          next = next % this.parentSuggestions.length; // 越界 → 循环回第一项
        }
        this.onParentHover(this.parentSuggestions[next], next);
        this._scrollActiveIntoView();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        // ↑ 在当前已加载窗口内循环；回退加载仅发生在 ↓ 到底时（分页只从头部扩展）
        const prev = (this.parentIdx - 1 + this.parentSuggestions.length) % this.parentSuggestions.length;
        this.onParentHover(this.parentSuggestions[prev], prev);
        this._scrollActiveIntoView();
      } else if (e.key === "Enter") {
        if (this.parentIdx >= 0 && this.parentIdx < items.length) {
          e.preventDefault();
          this.selectParent(items[this.parentIdx]);
        }
      } else if (e.key === "Escape") {
        this.parentOpen = false;
        this.onParentLeave();
      }
    },

    /** 键盘高亮项滚入可视区（下拉自动跟随；scrollIntoView nearest 部分可见时不滚，
     *  手动精确滚动：超出底部滚到可见、超出顶部滚回可见。
     *  用 parentIdx 直接取项（不依赖 .is-active class——Alpine 响应式 class 更新是异步的，
     *  键盘事件同步调用时 class 可能未应用） */
    _scrollActiveIntoView() {
      const el = this.$refs.parentList;
      if (!el) return;
      const sc = el.querySelector(".parent-picker__scroll");
      if (!sc) return;
      const active = el.querySelectorAll(".parent-picker__item")[this.parentIdx];
      if (!active) return;
      const aTop = active.offsetTop;
      const aBottom = aTop + active.offsetHeight;
      const cTop = sc.scrollTop;
      const cBottom = cTop + sc.clientHeight;
      if (aBottom > cBottom) {
        sc.scrollTop = aBottom - sc.clientHeight; // 向下滚到项底部可见
      } else if (aTop < cTop) {
        sc.scrollTop = aTop; // 向上滚到项顶部可见
      }
    },
  }))

  /* 垃圾箱视图组件：滚动到底自动加载下一页（scroll 监听 content-panel）。
     滚动容器为 .content-panel（overflow-y:auto），滚动到底（距底 ≤40px）且
     还有更多时触发 store.loadMoreTrash()。哨兵仅作「加载中…」提示，非触发源。
     用 scroll 事件而非 IntersectionObserver——headless 下 IntersectionObserver
     对内部滚动容器触发不稳定，scroll 事件在真实/无头浏览器一致可靠。 */
  Alpine.data("trashComponent", () => ({
    _onScroll: null,
    _contentPanel: null,

    init() {
      const store = Alpine.store("app");
      this._contentPanel = document.querySelector("#content-panel");
      if (!this._contentPanel) return;
      this._onScroll = () => {
        const cp = this._contentPanel;
        if (!cp) return;
        // 距底 ≤40px（阈值 ≥40）→ 加载下一页（loadMoreTrash 内部防重入/到底）
        if (cp.scrollTop + cp.clientHeight >= cp.scrollHeight - 40) {
          store.loadMoreTrash();
        }
      };
      this._contentPanel.addEventListener("scroll", this._onScroll, { passive: true });
    },

    destroy() {
      if (this._contentPanel && this._onScroll) {
        this._contentPanel.removeEventListener("scroll", this._onScroll);
      }
      this._contentPanel = null;
      this._onScroll = null;
    },
  }));
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

/** 从完整目标目录构造候选：{ label: 目标项目名, hierarchy: 层级, summary, value, q }
 *  projects/A/B/common-knowledge → label=B, hierarchy="A / B"
 *  projects/X/common-knowledge   → label=X, hierarchy="主要项目"（表层项目）
 *  common-knowledge              → label=公共知识, hierarchy="" */
function makeParentCandidate(value, summary = "") {
  const m = value.match(/^(?:projects|archive)\/(.+)\/common-knowledge$/);
  if (!m) return { label: "公共知识", hierarchy: "所有项目", summary, value, q: "" };
  const chain = m[1].split("/");
  return {
    label: chain[chain.length - 1],
    hierarchy: makeParentHierarchy(m[1]),
    summary,
    value,
    q: "",
  };
}
