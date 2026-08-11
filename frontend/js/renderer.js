/* ==========================================================================
   MyKnowledge — 阅读态渲染器
   marked 配置 + ref: 链接浮层交互
   设计系统: Raycast · v1.0
   ========================================================================== */

/**
 * 设置 marked 渲染器，处理 ref: 协议的链接
 */
function setupMarkedRenderer() {
  const renderer = new marked.Renderer();

  // 保存原始 link 渲染
  const origLink =
    renderer.link.bind(renderer);

  renderer.link = function (href, title, text) {
    // ref: 协议的链接渲染为可点击的关联文档链接
    if (href && href.startsWith("ref:")) {
      const rawPath = href.slice(4);
      // 解码空格编码（避免后续 encodeURIComponent 二次编码）
      const decodedPath = rawPath.replace(/%20/g, " ");
      const parts = decodedPath.split("::");
      const refPath = parts[0];
      const refSection = parts[1] || "";
      const displayText = text || refPath;
      return `<a href="javascript:void(0)"
                 class="ref-link"
                 data-ref-path="${escapeHtml(refPath)}"
                 data-ref-section="${escapeHtml(refSection)}"
                 title="关联文档: ${escapeHtml(refPath)}"
                 onclick="window._mykRefClick(event, '${escapeHtml(refPath)}')">${displayText}</a>`;
    }
    // http/https 外部链接 — 添加标记用于 hover 卡片识别
    if (href && (href.startsWith("http://") || href.startsWith("https://"))) {
      return `<a href="${escapeHtml(href)}"
                 class="ext-link"
                 data-ext-link="${escapeHtml(href)}"
                 target="_blank" rel="noopener">${text || href}</a>`;
    }
    return origLink({ href, title, text });
  };

  marked.setOptions({ renderer });
}

/**
 * 渲染文档 HTML
 * @param {string} markdown
 * @returns {string}
 */
function renderMarkdown(markdown) {
  if (!markdown) return "";
  return marked.parse(markdown);
}

/**
 * 渲染文档内容到容器（后处理：highlight.js 代码高亮）
 * 注意：HTML 内容由 Alpine x-html 设置，此函数仅做后处理
 * @param {string} html - 未使用，保留兼容性
 * @param {HTMLElement} container
 */
function renderToContainer(html, container) {
  if (!container) return;

  // highlight.js 代码高亮（仅处理新增的代码块）
  if (typeof hljs !== "undefined") {
    container.querySelectorAll("pre code:not(.hljs)").forEach((block) => {
      hljs.highlightElement(block);
    });
  }
}

/**
 * 从 refPath 解析来源面包屑
 * "common-knowledge/xxx.md" → [{label:"知识库总览", path:""}]
 * "projects/项目名/common-knowledge/xxx.md" → [{label:"项目名", path:"projects/项目名"}]
 */
function refSourceBreadcrumb(refPath) {
  const clean = refPath.replace(/\\/g, "/");
  const parts = clean.split("/");
  const sysDirs = new Set(["common-knowledge", "projects", "archive", "_templates", "publish"]);
  let seenSys = false;
  const crumbs = [];
  let accumulated = "";
  for (const p of parts) {
    if (!seenSys && sysDirs.has(p)) { seenSys = true; continue; }
    if (sysDirs.has(p)) continue;
    if (p.endsWith(".md")) continue;
    accumulated += (accumulated ? "/" : "") + p;
    const label = fileName(p + ".md");
    crumbs.push({ label, path: accumulated });
  }
  if (crumbs.length === 0) crumbs.push({ label: "知识库总览", path: "" });
  return crumbs;
}

/**
 * 加载项目预览数据（供卡片 x-data 独立调用，避免共享状态）
 */
async function loadProjectPreview(path) {
  try {
    const [docData, subData] = await Promise.all([
      api.list(path + "/common-knowledge").catch(() => ({ items: [] })),
      api.list(path + "/projects").catch(() => ({ items: [] })),
    ]);
    const excludeReadme = (i) => !/^readme\.md$/i.test(i.name || "");
    return {
      docs: (docData.items || []).filter(i => !i.is_dir && excludeReadme(i)),
      subprojects: (subData.items || []).filter(i => i.is_dir),
      archived: [],
    };
  } catch {
    return { docs: [], subprojects: [], archived: [] };
  }
}

/**
 * 生成项目面板 HTML 内容
 */
function renderProjectPanelHTML(data) {
  let html = "";
  const esc = (s) => escapeHtml(s || "");

  if (data.docs.length) {
    html += '<div class="project-panel__section">知识</div>';
    for (const d of data.docs) {
      html += '<div class="project-panel__item" data-doc-path="' + esc(d.path) + '">'
        + '<span class="project-panel__item-name">' + esc(fileName(d.name)) + '</span>'
        + '<span class="project-panel__item-summary">' + esc(d.summary) + '</span>'
        + '</div>';
    }
  }
  if (data.subprojects.length) {
    html += '<div class="project-panel__section">子项目</div>';
    for (const s of data.subprojects) {
      html += '<div class="project-panel__item" data-sub-path="' + esc(s.path) + '">'
        + '<span class="project-panel__item-name">' + esc(fileName(s.name)) + '</span>'
        + '</div>';
    }
  }
  if (!html) {
    html = '<div class="project-panel__empty">暂无内容</div>';
  }
  return html;
}

/**
 * 打开卡片面板（纯 DOM 操作，不触发 Alpine 响应式）
 */
function openCardPanel(cardEl, path) {
  const panel = cardEl.querySelector(".project-panel");
  if (!panel) return;
  const inner = panel.querySelector(".project-panel__inner");
  panel.classList.add("project-panel--open");
  // 懒加载
  if (!inner.dataset.loaded) {
    inner.innerHTML = '<div class="project-panel__empty">加载中...</div>';
    loadProjectPreview(path).then(data => {
      if (!panel.classList.contains("project-panel--open")) return;
      inner.innerHTML = renderProjectPanelHTML(data);
      inner.dataset.loaded = "1";
      // 绑定点击事件
      inner.querySelectorAll("[data-doc-path]").forEach(el => {
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          window.location.hash = "doc/" + hashEncode(el.dataset.docPath);
        });
      });
      inner.querySelectorAll("[data-sub-path]").forEach(el => {
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          const clean = (el.dataset.subPath || "").replace(/^projects\//, "");
          window.location.hash = "project/" + clean;
        });
      });
    });
  }
}

/**
 * 关闭卡片面板
 */
function closeCardPanel(cardEl) {
  const panel = cardEl.querySelector(".project-panel");
  if (panel) panel.classList.remove("project-panel--open");
}

/**
 * 知识卡片 hover：懒加载正文预览 + 引用数（0 引用不显示引用行）。
 * 摘要已常显在卡片上；hover 下拉区展示正文预览（纯文本截断，防 XSS）+ 被引用数。
 * dataset.loaded 防重：同一卡片只拉一次（hover 多次不重复请求）。
 */
async function openDocPreview(cardEl, path) {
  const inner = cardEl.querySelector(".doc-card__preview");
  if (!inner || inner.dataset.loaded) return;
  inner.dataset.loaded = "1";
  inner.innerHTML = '<div class="doc-card__preview__loading">加载中…</div>';
  try {
    const data = await api.getDocumentWithRefs(path);
    const md = (data && data.content) || "";
    const body = document.createElement("div");
    body.className = "doc-card__preview__body";
    // marked 渲染 → textContent 提取纯文本（解析准确：表格/代码块/嵌套列表都正确处理，
    // 优于手写正则剥符号）。只用 textContent（不插 HTML）→ 无 XSS；先剥离 frontmatter
    // （marked 不会自动跳过 YAML 头）+ script/style 噪音。
    const mdBody = md.replace(/^---[\s\S]*?---\s*/m, "");
    const tmp = document.createElement("div");
    tmp.innerHTML = renderMarkdown(mdBody);
    tmp.querySelectorAll("script, style").forEach((el) => el.remove());
    // 保留分行：块级元素后补换行再取文本（marked 输出的块级标签在 textContent 里会被挤成一行）
    tmp.querySelectorAll("h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,tr,div").forEach((el) => {
      el.appendChild(document.createTextNode("\n"));
    });
    const text = (tmp.textContent || "")
      .replace(/[ \t]+/g, " ")       // 行内多空格压成单空格（保留换行）
      .replace(/\n{3,}/g, "\n\n")    // 连续空行收敛
      .trim();
    body.textContent = (text || "（无正文）").slice(0, 200);
    inner.textContent = "";
    inner.appendChild(body);
    const refs = (data && data.refs) || [];
    const refCount = Array.isArray(refs) ? refs.length : 0;
    if (refCount > 0) {
      const refsRow = document.createElement("div");
      refsRow.className = "doc-card__preview__refs";
      refsRow.textContent = "被 " + refCount + " 篇文档引用";
      inner.appendChild(refsRow);
    }
  } catch (e) {
    inner.textContent = "";              // 加载失败不阻塞（hover 区留空）
    inner.dataset.loaded = "";           // 失败不毒化防重缓存：下次 hover 允许重试
  }
}

/**
 * 从 ref 对象生成来源路径字符串（用于 viewer__refs 列表）
 * @param {{ path: string }} ref
 * @returns {string}
 */
function refSourcePath(ref) {
  if (!ref || !ref.path) return "";
  const crumbs = refSourceBreadcrumb(ref.path);
  return crumbs.map((c) => c.label).join(" / ");
}

/**
 * 加载引用文档内容到浮层
 * @param {string} refPath
 * @returns {Promise<{title: string, summary: string, path: string}|null>}
 */
async function loadRefPreview(refPath) {
  try {
    const data = await api.getDocument(refPath);
    const meta = data.meta || {};
    return {
      title: meta.title || fileName(refPath),
      summary: meta.summary || "",
      author: meta.author ? extractDisplayName(meta.author) : "",
      updated: meta.updated || "",
      body: data.content || "",
      path: refPath,
      source: refSourceBreadcrumb(refPath),
    };
  } catch {
    return null;
  }
}

// 初始化 marked 渲染器
setupMarkedRenderer();
