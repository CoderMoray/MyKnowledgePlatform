/* ==========================================================================
   MyKnowledge — API 客户端
   统一 fetch 封装，处理 423/400/404/500 等状态
   设计系统: Raycast · v1.0
   ========================================================================== */

const API_BASE = window.__MYK_API_BASE__ ||
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://127.0.0.1:8080'
    : window.location.protocol === 'file:'
      ? 'http://127.0.0.1:8080'
      : window.location.origin);

/**
 * 通用 API 请求封装
 * @param {string} path - API 路径（不含 base）
 * @param {object} options - fetch 选项
 * @returns {Promise<any>}
 */
async function apiRequest(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const config = {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  };

  let res;
  try {
    res = await fetch(url, config);
  } catch (err) {
    throw new ApiError(0, "无法连接到服务器，请确认后端已启动", err);
  }

  // 204 No Content — 成功但无响应体
  if (res.status === 204) return null;

  let data;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      data = await res.json();
    } catch {
      data = null;
    }
  } else {
    data = await res.text();
  }

  if (!res.ok) {
    // detail 可能是字符串（"deleted"/"not_found"）或嵌套对象 {detail, deleted_at}
    const dd = data && data.detail;
    const message =
      (typeof dd === "string" && dd) ||
      (dd && dd.detail) ||
      (data && data.message) ||
      `请求失败 (${res.status})`;

    throw new ApiError(res.status, message, data);
  }

  return data;
}

/**
 * API 错误类
 */
class ApiError extends Error {
  constructor(status, message, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  get isLocked() {
    return this.status === 423;
  }

  get isNotFound() {
    return this.status === 404;
  }

  get isBadRequest() {
    return this.status === 400;
  }

  get isServerError() {
    return this.status >= 500;
  }
}

/* ── 文档 API ──────────────────────────────────────────────────────────── */

const api = {
  /**
   * 获取目录列表
   * @param {string} path - 目录路径
   */
  async list(path = "") {
    return apiRequest(`/api/list/${path}`);
  },

  /**
   * 获取文档元信息
   * @param {string} path
   */
  async getDocumentMeta(path) {
    return apiRequest(`/api/document/${encodeURIComponent(path)}/meta`);
  },

  /**
   * 获取文档内容
   * @param {string} path - 文档路径
   */
  async getDocument(path) {
    return apiRequest(`/api/document/${encodeURIComponent(path)}`);
  },

  /**
   * 获取文档及其引用
   * @param {string} path - 文档路径
   */
  async getDocumentWithRefs(path) {
    return apiRequest(`/api/document/${encodeURIComponent(path)}/refs`);
  },

  /**
   * 创建文档
   * @param {string} path - 文档路径
   * @param {object} body - { content, summary }
   */
  async createDocument(path, body) {
    return apiRequest(`/api/document/${encodeURIComponent(path)}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /**
   * 更新文档
   * @param {string} path - 文档路径
   * @param {object} body - 部分更新字段
   */
  async updateDocument(path, body) {
    return apiRequest(`/api/document/${encodeURIComponent(path)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  /**
   * 删除文档
   * @param {string} path - 文档路径
   */
  async deleteDocument(path) {
    return apiRequest(`/api/document/${encodeURIComponent(path)}`, {
      method: "DELETE",
    });
  },

  /**
   * 文档改名
   * @param {string} path - 当前路径
   * @param {string} newName - 新名称
   */
  async renameDocument(path, newName) {
    return apiRequest("/api/document/rename", {
      method: "PUT",
      body: JSON.stringify({ path, new_name: newName }),
    });
  },

  /* ── 搜索 API（编辑态引用搜索 / 归属项目选择） ─────────────────────── */
  async searchDocuments(q, limit = 20, kind = "all") {
    // kind: all=文档搜索（标题/摘要/正文组合权重排序）/ projects=项目级搜索（只匹配项目 readme）
    return apiRequest(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}&kind=${encodeURIComponent(kind)}`);
  },

  /* ── 垃圾箱 API ─────────────────────────────────────────────────────── */

  /** 分页拉取垃圾箱条目（半懒加载：首页 50，滚动到底 +50）。
   *  @param {number} offset 偏移
   *  @param {number} limit 页大小（后端默认 50）
   *  @returns {Promise<{items, total, has_more}>} */
  async getTrash(offset = 0, limit = 50) {
    return apiRequest(`/api/trash?offset=${offset}&limit=${limit}`);
  },
  async restoreTrash(trashPath) {
    return apiRequest("/api/trash/restore", {
      method: "POST",
      body: JSON.stringify({ trash_path: trashPath }),
    });
  },
  /** 彻底清空垃圾箱（all=true 清全部；无参后端只 GC 30 天，前端一律彻底清空） */
  async emptyTrash() {
    return apiRequest("/api/trash/empty?all=true", { method: "POST" });
  },
  /** 精准删除选中条目（body trash_paths；后端只删列出的，其余保留）。
   *  @param {string[]} trash_paths 勾选的条目 trash_path 集合
   *  @returns {Promise<{status: "ok", removed: number}>} */
  async deleteTrashItems(trash_paths) {
    return apiRequest("/api/trash/empty", {
      method: "POST",
      body: JSON.stringify({ trash_paths }),
    });
  },

  /* ── 项目 API ────────────────────────────────────────────────────────── */

  /**
   * 获取项目元信息
   * @param {string} path - 项目路径
   */
  async getProject(path) {
    return apiRequest(`/api/project/${encodeURIComponent(path)}`);
  },

  /**
   * 更新项目元信息
   * @param {string} path - 项目路径
   * @param {object} body - 元信息
   */
  async updateProject(path, body) {
    return apiRequest(`/api/project/${encodeURIComponent(path)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  /**
   * 项目改名
   * @param {string} path - 当前路径
   * @param {string} newName - 新名称
   */
  async deleteProject(path) {
    return apiRequest(`/api/project/${encodeURIComponent(path)}`, { method: "DELETE" });
  },
  async renameProject(path, newName) {
    return apiRequest(`/api/project/${encodeURIComponent(path)}/rename`, {
      method: "PUT",
      body: JSON.stringify({ new_name: newName }),
    });
  },

  /* ── 系统 API ────────────────────────────────────────────────────────── */

  /**
   * 获取锁状态
   */
  async getLock() {
    return apiRequest("/api/lock");
  },

  /**
   * 获取结构化状态
   */
  async getStatus() {
    return apiRequest("/api/status/detail");
  },

  /**
   * 完整性检查
   */
  async runCheck() {
    return apiRequest("/api/check", { method: "POST" });
  },

  /* ── 结构体检 API ───────────────────────────────────────────────────── */

  /** 读取上次诊断结果（读/算分离；无结果或损坏返回 {saved:false}） */
  async getDiagnoseSaved() {
    return apiRequest("/api/diagnose/saved");
  },

  /** 重新体检：真算 + 写结果文件，返回 {issues, summary, generated_at} */
  async getDiagnose() {
    return apiRequest("/api/diagnose");
  },

  /* ── 结构体检 · 修复 API（阶段 B） ─────────────────────────────────── */

  /** 移动孤儿文档到同级 common-knowledge；body {paths} → {moved, failed} */
  async healMove(paths) {
    return apiRequest("/api/heal/move", { method: "POST", body: JSON.stringify({ paths }) });
  },

  /** 重建受影响层 readme 索引 + project-status；body {all:true} → {rebuilt, project_status} */
  async healRebuild() {
    return apiRequest("/api/heal/rebuild", { method: "POST", body: JSON.stringify({ all: true }) });
  },

  /* ── 身份 API ────────────────────────────────────────────────────────── */

  /**
   * 获取当前用户身份
   * @returns {Promise<{nickname: string, email: string} | null>}
   *   null = 身份未设置（404），其他错误会 throw
   */
  async getIdentity() {
    try {
      return await apiRequest("/api/identity");
    } catch (err) {
      // 404 = 确实未配置，返回 null；其他错误（后端挂了等）往上抛
      if (err.status === 404) return null;
      throw err;
    }
  },

  /**
   * 更新用户身份
   * @param {string} email
   * @param {string} nickname
   */
  async setIdentity(email, nickname) {
    return apiRequest("/api/identity", {
      method: "PUT",
      body: JSON.stringify({ email, nickname }),
    });
  },

  /* ── AI 客户端配置 API（阶段三：MCP/hooks/Agent 检测与增量写入） ────── */

  /**
   * 检测各 AI 客户端的 MyKnowledge 配置状态
   * @returns {Promise<{ClaudeCode: {mcp, hooks, agent}, CodeBuddyIDE: {mcp, hooks, agent}}>}
   */
  async getClientConfig() {
    return apiRequest("/api/client-config");
  },

  /**
   * 增量写入某平台某 kind 的 MyKnowledge 配置
   * @param {string} platform - ClaudeCode | ClaudeDesktop | CodeBuddyIDE | WorkBuddy
   * @param {string} kind - mcp | hooks | agent
   * @returns {Promise<{platform, kind, file, status, detected}>}
   */
  async setClientConfig(platform, kind) {
    return apiRequest(`/api/client-config/${encodeURIComponent(platform)}/${encodeURIComponent(kind)}`, {
      method: "POST",
    });
  },

  /**
   * 移除某平台某 kind 的 MyKnowledge 配置（只动 MyKnowledge 条目，
   * 保留用户其他配置；幂等）。开=写（setClientConfig），关=移除。
   * @param {string} platform - ClaudeCode | ClaudeDesktop | CodeBuddyIDE | WorkBuddy
   * @param {string} kind - mcp | hooks | agent
   * @returns {Promise<{platform, kind, file, status: "removed"}>}
   */
  async deleteClientConfig(platform, kind) {
    return apiRequest(`/api/client-config/${encodeURIComponent(platform)}/${encodeURIComponent(kind)}`, {
      method: "DELETE",
    });
  },

  /* ── 实时事件 ─────────────────────────────────────────────────────────── */

  /** SSE 事件名 */
  _eventSource: null,
  _eventCallbacks: [],

  /**
   * 订阅 KB 变更事件（Server-Sent Events）
   *
   * 当有写操作（MCP 或 REST API）完成时，后端推送 ``updated`` 事件。
   * 前端收到后自动重新加载当前视图。
   *
   * @param {Function} onUpdated - 收到 "updated" 事件时调用
   * @returns {() => void} 取消订阅函数
   */
  subscribeEvents(onUpdated) {
    this._eventCallbacks.push(onUpdated);

    // 如果已有连接则不复建
    if (this._eventSource) {
      return () => {
        this._eventCallbacks = this._eventCallbacks.filter(cb => cb !== onUpdated);
        if (this._eventCallbacks.length === 0) this._closeEvents();
      };
    }

    const es = new EventSource(`${API_BASE}/api/events`);
    es.addEventListener("updated", (e) => {
      this._eventCallbacks.forEach(cb => cb(e.data));
    });
    es.onerror = () => {
      // 自动重连由浏览器 EventSource 内置处理
    };
    this._eventSource = es;

    return () => {
      this._eventCallbacks = this._eventCallbacks.filter(cb => cb !== onUpdated);
      if (this._eventCallbacks.length === 0) this._closeEvents();
    };
  },

  /** 关闭 SSE 连接 */
  _closeEvents() {
    if (this._eventSource) {
      this._eventSource.close();
      this._eventSource = null;
    }
  },

  /** 获取 AI 连接状态 */
  async getMcpStatus() {
    try {
      const data = await this._request("/api/mcp");
      return data;
    } catch {
      return { status: "disconnected", detail: "" };
    }
  },

  /** 获取项目列表（用于分享导出） */
  async listProjects() {
    return apiRequest("/api/list/projects");
  },

  /** 导出项目为加密知识包 */
  async exportProjects(projectPaths) {
    const res = await fetch(`${API_BASE}/api/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projects: projectPaths }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `导出失败 (${res.status})`);
    }
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    // 优先解析 RFC 5987 编码文件名
    const rfcMatch = disposition.match(/filename\*=UTF-8''([^;]+)/);
    const standardMatch = !rfcMatch && disposition.match(/filename="?([^";]+)"?/);
    const filename = rfcMatch ? decodeURIComponent(rfcMatch[1]) : (standardMatch ? standardMatch[1] : (projectPaths.length === 1 ? "MyKnowledge.mkpkg" : "myknowledge-export.zip"));
    return { blob, filename };
  },
};
