/* ==========================================================================
   MyKnowledge — 工具函数
   设计系统: Raycast · v1.0
   ========================================================================== */

/**
 * 格式化日期为友好的中文显示
 * @param {string|Date} date
 * @returns {string}
 */
function formatDate(date) {
  if (!date) return "—";
  const d = new Date(date);
  if (isNaN(d.getTime())) return "—";
  const now = new Date();
  const diff = now - d;
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  if (days === 0) return "今天";
  if (days === 1) return "昨天";
  if (days <= 14) return `${days} 天前`;

  // 14天以上显示完整日期
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * 格式化日期为完整显示
 * @param {string|Date} date
 * @returns {string}
 */
function formatDateFull(date) {
  if (!date) return "—";
  const d = new Date(date);
  if (isNaN(d.getTime())) return "—";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const h = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${day} ${h}:${min}`;
}

/**
 * HTML 转义
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
  if (!str) return "";
  const map = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };
  return str.replace(/[&<>"']/g, (c) => map[c]);
}

/**
 * 防抖
 * @param {Function} fn
 * @param {number} delay
 * @returns {Function}
 */
function debounce(fn, delay = 300) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

/**
 * 节流
 * @param {Function} fn
 * @param {number} interval
 * @returns {Function}
 */
function throttle(fn, interval = 300) {
  let last = 0;
  return function (...args) {
    const now = Date.now();
    if (now - last >= interval) {
      last = now;
      fn.apply(this, args);
    }
  };
}

/**
 * 从路径中提取文件名（不含后缀）
 * @param {string} path
 * @returns {string}
 */
function fileName(path) {
  if (!path) return "";
  const parts = path.replace(/\\/g, "/").split("/");
  const last = parts[parts.length - 1];
  const dotIdx = last.lastIndexOf(".");
  return dotIdx > 0 ? last.substring(0, dotIdx) : last;
}

/**
 * 状态标签映射
 * @param {string} status
 * @returns {string}
 */
function statusLabel(status) {
  const map = { completed: "已完成", cancelled: "已取消", abandoned: "已废弃" };
  return map[status] || "已废弃";
}

/**
 * 从路径中提取项目名
 * @param {string} path
 * @returns {string}
 */
function projectName(path) {
  if (!path) return "";
  const clean = path.replace(/\\/g, "/").replace(/^\//, "");
  const idx = clean.indexOf("/");
  return idx > 0 ? clean.substring(0, idx) : clean;
}

/**
 * 路径转面包屑片段
 * @param {string} path
 * @returns {{label: string, path: string}[]}
 */
function pathToBreadcrumbs(path) {
  if (!path) return [];
  const clean = path.replace(/\\/g, "/").replace(/^\//, "");
  const parts = clean.split("/");
  const crumbs = [];
  let accumulated = "";

  parts.forEach((part, i) => {
    accumulated += (i === 0 ? "" : "/") + part;
    const label = i === parts.length - 1 ? fileName(part) : part;
    crumbs.push({ label, path: accumulated });
  });

  return crumbs;
}

/**
 * 判断是否为项目路径（无扩展名视为 project）
 * @param {string} path
 * @returns {boolean}
 */
function isProjectPath(path) {
  if (!path) return false;
  const last = path.replace(/\\/g, "/").split("/").pop();
  return !last.includes(".");
}

/**
 * 生成唯一 ID
 * @returns {string}
 */
function uid() {
  return Date.now().toString(36) + Math.random().toString(36).substring(2);
}

/**
 * Toast 通知
 * @param {string} message
 * @param {'success'|'error'|'warning'|'info'} type
 * @param {number} duration - 自动消失时间(ms)
 */
function showToast(message, type = "info", duration = 900) {
  const container =
    document.querySelector(".toast-container") || createToastContainer();
  const toast = document.createElement("div");
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(8px)";
    toast.style.transition = "opacity 0.2s ease, transform 0.2s ease";
    setTimeout(() => toast.remove(), 200);
  }, duration);
}

function createToastContainer() {
  const container = document.createElement("div");
  container.className = "toast-container";
  document.body.appendChild(container);
  return container;
}

/* ── Gravatar / 邮箱 ──────────────────────────────────────────────────── */

/**
 * 从 "昵称 <邮箱>" 格式中提取邮箱地址
 * @param {string} str
 * @returns {string|null}
 */
function extractEmail(str) {
  if (!str) return null;
  const match = str.match(/<([^>]+@[^>]+)>/);
  if (match) return match[1].trim().toLowerCase();
  // Fallback: 如果字符串本身就是邮箱
  if (str.includes("@")) return str.trim().toLowerCase();
  return null;
}

/**
 * 提取显示名称（去掉邮箱部分）
 * @param {string} str
 * @returns {string}
 */
function extractDisplayName(str) {
  if (!str) return "";
  const match = str.match(/^([^<]+)/);
  if (match) return match[1].trim();
  return str.trim();
}

/**
 * 从 author 字符串生成头像信息（纯首字母，无 Gravatar）
 * @param {string} authorStr
 * @param {number} size
 * @returns {{ initial: string, email: string|null }}
 */
function authorAvatar(authorStr, size = 32) {
  const email = extractEmail(authorStr);
  const displayName = extractDisplayName(authorStr);
  const initial = displayName ? displayName.charAt(0).toUpperCase() : "?";
  return { url: "", initial, email };
}

/* ==========================================================================
   card-icon 关键词匹配（v0.1，后续精进）
   ========================================================================== */

/** Lucide icon 原始 SVG path（16×16 viewBox） */
const _ICON_SVGS = {
  folders:    '<path d="M10 4H4a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2V8a2 2 0 00-2-2h-2l-2-2H5"/>',
  "credit-card": '<rect width="14" height="10" x="1" y="3" rx="2"/><path d="M1 7h14"/>',
  "arrow-left-right": '<path d="M8 3L4 7l4 4"/><path d="M8 13l4-4-4-4"/><path d="M4 7h8"/>',
  user:        '<path d="M19 21v-2a4 4 0 00-4-4H9a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  "clipboard-check": '<rect width="8" height="4" x="4" y="2" rx="1"/><path d="M8 2v2"/><rect width="12" height="14" x="2" y="6" rx="2"/><path d="m6 12 3 3 5-5"/>',
  "file-text": '<path d="M15 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V7Z"/><path d="M14 2v4a2 2 0 002 2h2"/><path d="M10 9H8"/><path d="M14 13H8"/><path d="M14 17H8"/>',
};

/** 关键词 → icon 名映射（不区分大小写，匹配到第一个即返回） */
const _ICON_RULES = [
  { kw: ["myknowledge","知识"],        icon: "folders" },
  { kw: ["financing","分期"],           icon: "credit-card" },
  { kw: ["以旧换新","trade in","trade-in"], icon: "arrow-left-right" },
  { kw: ["mycoach","我的私教","私教"],    icon: "user" },
  { kw: ["training","培训","新人评估"],    icon: "clipboard-check" },
];

/**
 * 根据名称匹配 card icon
 * @param {string} name - 文档/项目名称
 * @returns {string} SVG 标签
 */
function cardIconSvg(name) {
  const lower = (name || "").toLowerCase();
  let iconKey = "file-text";
  for (const rule of _ICON_RULES) {
    if (rule.kw.some(k => lower.includes(k.toLowerCase()))) {
      iconKey = rule.icon;
      break;
    }
  }
  const paths = _ICON_SVGS[iconKey] || _ICON_SVGS["file-text"];
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' + paths + '</svg>';
}

/**
 * 行级文本 diff（LCS）：返回对齐行数组，供冲突可视化对比
 * @param {string} aText 版本 A（我的草稿）
 * @param {string} bText 版本 B（服务端最新）
 * @returns {Array<{type:"same"|"del"|"add", a:string, b:string}>}
 */
function lineDiff(aText, bText) {
  // 空文本 → 无行（"" .split("\n") 会返回 [""] 一个空行，空文档不该有行）
  const a = aText ? String(aText).replace(/\r\n/g, "\n").split("\n") : [];
  const b = bText ? String(bText).replace(/\r\n/g, "\n").split("\n") : [];
  const n = a.length, m = b.length;
  // LCS DP（文档几百行内可接受）
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const rows = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { rows.push({ type: "same", a: a[i], b: b[j] }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { rows.push({ type: "del", a: a[i], b: "" }); i++; }
    else { rows.push({ type: "add", a: "", b: b[j] }); j++; }
  }
  while (i < n) { rows.push({ type: "del", a: a[i], b: "" }); i++; }
  while (j < m) { rows.push({ type: "add", a: "", b: b[j] }); j++; }
  return rows;
}
window.lineDiff = lineDiff; // 显式挂载（jsdom eval 不自动挂函数声明；浏览器 script 顶层即 window）

/* ── 重命名（标题可编辑 = 重命名）纯函数 ────────────────────────────────
 * 独立成纯函数便于自动化测试（frontend/tests/rename-logic.mjs）
 */
window.MykRename = {
  /** 标题 → 完整文件名（自动补 .md，已带不重复加） */
  buildNewName(title) {
    const t = (title || "").trim();
    if (!t) return "";
    return t.endsWith(".md") ? t : t + ".md";
  },

  /** 旧路径 + 新文件名 → 新路径（同目录替换文件名） */
  buildNewPath(oldPath, newName) {
    const slash = oldPath.lastIndexOf("/");
    return (slash >= 0 ? oldPath.substring(0, slash + 1) : "") + newName;
  },

  /** 当前显示标题：frontmatter title 优先，否则文件名（去目录 + 去 .md） */
  currentTitle(doc, path) {
    if (doc && doc.title) return doc.title;
    const file = String(path || "").split("/").pop() || "";
    return file.replace(/\.md$/, "");
  },

  /** 标题是否变化（空标题/未变 → 不 rename） */
  shouldRename(currentTitle, newTitle) {
    const nt = (newTitle || "").trim();
    return !!(nt && nt !== currentTitle);
  },

  /** 标题合法性：非空、不含路径分隔符、不含非法文件名字符 */
  titleError(title) {
    const t = (title || "").trim();
    if (!t) return "标题不能为空";
    if (t.includes("/") || t.includes("\\")) return "标题不能包含路径分隔符";
    if (/[:*?"<>|]/.test(t)) return "标题不能包含 : * ? \" < > | 字符";
    return "";
  },
};
