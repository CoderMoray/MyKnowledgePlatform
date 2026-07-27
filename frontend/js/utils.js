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
  if (hours < 24) return `${hours} 小时前`;
  if (days < 7) return `${days} 天前`;

  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  if (y === now.getFullYear()) return `${m}-${day}`;
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
function showToast(message, type = "info", duration = 3000) {
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
 * 纯 JS MD5 实现（兼容 RFC 1321）
 * 基于 Joseph Myers 的实现
 * @param {string} str
 * @returns {string} 32位十六进制 MD5 哈希
 */
function md5(str) {
  function r(n, c) { return (n << c) | (n >>> (32 - c)); }
  function q(n, c) { return (n & c) | (~n & (0xffffffff ^ c)); }
  function p(n, c) { return (n & c) | ((0xffffffff ^ n) & (0xffffffff ^ c)); }
  function o(n, c) { return n ^ c ^ (0xffffffff ^ (n | c)); }
  function l(n, c, t, i, e, u) {
    return r(n + q(c, t, i) + e + u, 7) + c;
  }
  function k(n, c, t, i, e, u) {
    return r(n + p(c, t, i) + e + u, 12) + c;
  }
  function j(n, c, t, i, e, u) {
    return r(n + o(c, t, i) + e + u, 17) + c;
  }

  var a = [], m, g, f, d, c, b,
      h = 0x67452301, v = 0xefcdab89,
      w = 0x98badcfe, x = 0x10325476,
      y = 0, z = str.length;

  for (var i = 0; i < z; i += 8) {
    a.push(
      (str.charCodeAt(i) & 0xff) |
      ((str.charCodeAt(i + 1) || 0) & 0xff) << 8 |
      ((str.charCodeAt(i + 2) || 0) & 0xff) << 16 |
      ((str.charCodeAt(i + 3) || 0) & 0xff) << 24
    );
  }

  a[y >> 2] |= 0x80 << ((y % 4) << 3);
  a[(((z + 8) >> 6) << 4) + 14] = z * 8;

  for (var i = 0; i < a.length; i += 16) {
    m = h; g = v; f = w; d = x;

    for (var u = 0; u < 64; u++) {
      if (u < 16) {
        c = a[i + u];
        b = q(g, f, d);
      } else if (u < 32) {
        c = a[i + ((u * 5) - 15) % 16];
        b = p(g, f, d);
      } else if (u < 48) {
        c = a[i + ((u * 3) + 5) % 16];
        b = o(g, f, d);
      } else {
        c = a[i + (u * 7) % 16];
        b = (f ^ (g | ~d));
      }

      var s = [0xd76aa478, 0xe8c7b756, 0x242070db, 0xc1bdceee,
               0xf57c0faf, 0x4787c62a, 0xa8304613, 0xfd469501,
               0x698098d8, 0x8b44f7af, 0xffff5bb1, 0x895cd7be,
               0x6b901122, 0xfd987193, 0xa679438e, 0x49b40821,
               0xf61e2562, 0xc040b340, 0x265e5a51, 0xe9b6c7aa,
               0xd62f105d, 0x2441453,  0xd8a1e681, 0xe7d3fbc8,
               0x21e1cde6, 0xc33707d6, 0xf4d50d87, 0x455a14ed,
               0xa9e3e905, 0xfcefa3f8, 0x676f02d9, 0x8d2a4c8a,
               0xfffa3942, 0x8771f681, 0x6d9d6122, 0xfde5380c,
               0xa4beea44, 0x4bdecfa9, 0xf6bb4b60, 0xbebfbc70,
               0x289b7ec6, 0xeaa127fa, 0xd4ef3085, 0x4881d05,
               0xd9d4d039, 0xe6db99e5, 0x1fa27cf8, 0xc4ac5665,
               0xf4292244, 0x432aff97, 0xab9423a7, 0xfc93a039,
               0x655b59c3, 0x8f0ccc92, 0xffeff47d, 0x85845dd1,
               0x6fa87e4f, 0xfe2ce6e0, 0xa3014314, 0x4e0811a1,
               0xf7537e82, 0xbd3af235, 0x2ad7d2bb, 0xeb86d391];

      var t = [7,12,17,22,7,12,17,22,7,12,17,22,7,12,17,22,
               5,9,14,20,5,9,14,20,5,9,14,20,5,9,14,20,
               4,11,16,23,4,11,16,23,4,11,16,23,4,11,16,23,
               6,10,15,21,6,10,15,21,6,10,15,21,6,10,15,21];

      c = r(c + b + s[u] + (m || 0), t[u]) + g;
      m = d; d = f; f = g; g = c;
    }

    h += m; v += g; w += f; x += d;
  }

  function toHex(n) {
    var s = "";
    for (var i = 0; i < 4; i++) {
      s += ((n >> (i * 8)) & 0xff).toString(16).padStart(2, "0");
    }
    return s;
  }

  return toHex(h) + toHex(v) + toHex(w) + toHex(x);
}

/**
 * 生成 Gravatar URL
 * @param {string} email - 邮箱地址
 * @param {number} size - 尺寸（默认 32）
 * @returns {string}
 */
function gravatarUrl(email, size = 32) {
  if (!email) return "";
  const hash = md5(email.trim().toLowerCase());
  return `https://www.gravatar.com/avatar/${hash}?s=${size}&d=mp`;
}

/**
 * 从 author 字符串生成头像信息
 * @param {string} authorStr
 * @param {number} size
 * @returns {{ url: string, initial: string, email: string|null }}
 */
function authorAvatar(authorStr, size = 32) {
  const email = extractEmail(authorStr);
  const displayName = extractDisplayName(authorStr);
  const initial = displayName ? displayName.charAt(0).toUpperCase() : "?";

  return {
    url: email ? gravatarUrl(email, size) : "",
    initial,
    email,
  };
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
