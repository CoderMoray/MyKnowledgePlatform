/* ==========================================================================
   MyKnowledge — Hash 路由
   路由: #dashboard | #project/{name} | #view/{path} | #edit/{path} | #new | #status
   设计系统: Raycast · v1.0
   ========================================================================== */

class Router {
  constructor() {
    this.routes = [];
    this.currentRoute = null;
  }

  /**
   * 注册路由
   * @param {string} pattern - 路由模式（支持 :param 参数）
   * @param {Function} handler - 处理函数(params, query)
   */
  on(pattern, handler) {
    const regex = this._patternToRegex(pattern);
    const paramNames = this._extractParamNames(pattern);
    this.routes.push({ pattern, regex, paramNames, handler });
  }

  /**
   * 导航到路由
   * @param {string} hash
   */
  navigate(hash) {
    hash = hash.replace(/^#/, "");

    for (const route of this.routes) {
      const match = hash.match(route.regex);
      if (match) {
        const params = {};
        route.paramNames.forEach((name, i) => {
          params[name] = decodeURIComponent(match[i + 1] || "");
        });

        route.handler(params);
        this.currentRoute = { pattern: route.pattern, params };
        return;
      }
    }

    // 404 fallback → 仪表盘
    window.location.hash = "dashboard";
  }

  /**
   * 将路由模式转为正则
   * @param {string} pattern
   * @returns {RegExp}
   */
  _patternToRegex(pattern) {
    const escaped = pattern
      .replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
      .replace(/:([\w]+)/g, "([^/]+)");
    return new RegExp(`^${escaped}$`);
  }

  /**
   * 提取参数名
   * @param {string} pattern
   * @returns {string[]}
   */
  _extractParamNames(pattern) {
    const names = [];
    const regex = /:([\w]+)/g;
    let match;
    while ((match = regex.exec(pattern)) !== null) {
      names.push(match[1]);
    }
    return names;
  }
}

/* ── 注册路由 ──────────────────────────────────────────────────────────── */

function setupRouter() {
  const router = new Router();
  const store = Alpine.store("app");

  // #dashboard
  router.on("dashboard", () => {
    store.setView("dashboard");
    store.loadDashboard();
  });

  // #project/{name}
  router.on("project/:name", (params) => {
    // URL 中去掉了 projects/ 前缀，这里加回来
    let path = params.name;
    if (!path.startsWith("projects/") && !path.startsWith("archive/") && !path.startsWith("common-knowledge/")) {
      path = "projects/" + path;
    }
    store.setView("project", path);
    store.loadProjectDocuments(path);
  });

  // #doc/{path}（统一文档路由，取代 #view 和 #edit）
  router.on("doc/:path", (params) => {
    const path = decodeURIComponent(params.path);
    store.setView("view", path);
    store.loadDocument(path);
  });

  // #view/{path}（兼容旧链接）
  router.on("view/:path", (params) => {
    const path = decodeURIComponent(params.path);
    store.setView("view", path);
    store.loadDocument(path);
  });

  // #edit/{path}
  router.on("edit/:path", (params) => {
    const path = decodeURIComponent(params.path);
    store.setView("edit", path);
    store.loadDocument(path);
  });

  // #new
  router.on("new", () => {
    store.setView("new");
    store.openModal("new-doc", { parentPath: store.currentPath || "" });
  });

  // #status
  router.on("status", async () => {
    store.setView("status");
    store.loading = true;
    try {
      store.statusSummary = await api.getStatus();
    } catch (err) {
      store.error = err.message;
    } finally {
      store.loading = false;
    }
  });

  // 暴露到全局
  window._mykRouter = router;

  return router;
}
