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

  renderer.link = function ({ href, title, text }) {
    // ref: 协议的链接渲染为可点击的关联文档链接
    if (href && href.startsWith("ref:")) {
      const refPath = href.slice(4);
      const displayText = text || refPath;
      return `<a href="javascript:void(0)"
                 class="ref-link"
                 data-ref-path="${escapeHtml(refPath)}"
                 title="关联文档: ${escapeHtml(refPath)}"
                 onclick="window._mykRefClick(event, '${escapeHtml(refPath)}')">${displayText}</a>`;
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
 * 加载引用文档内容到浮层
 * @param {string} refPath
 * @returns {Promise<{title: string, summary: string, path: string}|null>}
 */
async function loadRefPreview(refPath) {
  try {
    const data = await api.getDocument(refPath);
    return {
      title: (data.meta && data.meta.title) || fileName(refPath),
      summary: (data.meta && data.meta.summary) || "",
      path: refPath,
    };
  } catch {
    return null;
  }
}

// 初始化 marked 渲染器
setupMarkedRenderer();
