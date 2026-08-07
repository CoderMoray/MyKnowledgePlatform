"""API 请求跟踪与重复加载检测（前端 Playwright 测试共用）

用途：检测"某资源被多次加载"这类回归（本项目历史高频 bug）——
每次导航/保存动作后，断言关键文档只被加载预期次数。

用法示例（sync API）：
    from api_tracker import ApiTracker
    tracker = ApiTracker(page)                 # 绑定后自动记录所有 /api/ 请求
    tracker.reset()                            # 动作前清零计数
    ...执行动作（点击导航等）...
    tracker.assert_document_loads(doc_path, max_loads=1, label="切到 C")
    tracker.assert_method_count("PUT", "保存", max_count=1)
    tracker.report()                           # 打印全部请求（可选，调试用）

规则说明：
- "加载一次" = GET /api/document/{path} 主请求（不含 /refs、/meta 后缀）
- 一次导航预期 1 次加载；SSE 事件触发的重载会额外 +1（本端保存会触发 SSE
  重载当前文档——如需保留该行为，测试可传 max_loads=2 并注明原因）
"""
import urllib.parse
from collections import Counter


class ApiTracker:
    def __init__(self, page):
        self._page = page
        self._reqs = []  # (method, path, status)
        page.on("response", self._on_response)

    def _on_response(self, resp):
        try:
            url = urllib.parse.urlparse(resp.url)
        except Exception:
            return
        if "/api/" not in url.path:
            return
        path = url.path.split("/api/", 1)[-1]
        self._reqs.append((resp.request.method, path, resp.status))

    def reset(self):
        """清空已记录请求（动作前调用）"""
        self._reqs = []

    # ── 查询 ──────────────────────────────────────────────
    def all(self):
        return list(self._reqs)

    def method_count(self, method, path_contains=""):
        return sum(1 for m, p, _ in self._reqs
                   if m.upper() == method.upper() and path_contains in p)

    def document_loads(self, doc_path):
        """某文档的主加载次数（GET /api/document/{path}，排除 /refs、/meta）

        注意：前端用 encodeURIComponent 编码整段路径（斜杠也是 %2F），
        因此这里用 quote(safe="") 生成匹配串。
        """
        target = "document/" + urllib.parse.quote(doc_path, safe="")
        n = 0
        for m, p, _ in self._reqs:
            if m.upper() != "GET":
                continue
            if p == target:  # 主加载（精确匹配）
                n += 1
        return n

    # ── 断言 ──────────────────────────────────────────────
    def assert_document_loads(self, doc_path, max_loads=1, label=""):
        """断言某文档主加载次数 <= max_loads（默认 1：一次导航一次加载）"""
        n = self.document_loads(doc_path)
        name = label or doc_path.split("/")[-1]
        assert n <= max_loads, (
            f"[重复加载检测] {name} 被加载了 {n} 次（预期 <= {max_loads}）。"
            f"完整请求：{[ (m, p[:70]) for m, p, _ in self._reqs ]}"
        )
        return n

    def assert_method_count(self, method, max_count, path_contains="", label=""):
        """断言某类请求次数 <= max_count（如保存 PUT 不应重复）"""
        n = self.method_count(method, path_contains)
        assert n <= max_count, (
            f"[请求次数检测] {label or method} {path_contains or ''} 共 {n} 次（预期 <= {max_count}）"
        )
        return n

    def report(self):
        """打印全部请求（调试）"""
        from collections import Counter
        c = Counter((m, p.split("/")[0]) for m, p, _ in self._reqs)
        print("[ApiTracker 请求汇总]")
        for (m, k), v in sorted(c.items()):
            print(f"  {m:4s} {k}: {v}")
        return self
