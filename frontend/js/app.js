/* ==========================================================================
  MyKnowledge — Alpine.js 应用入口
  整合所有组件：路由、存储、编辑器、渲染器
  设计系统: Raycast · v2.0
  ========================================================================== */

// 桌面模式隔离：给 <html> 加 data-app-mode="desktop"，桌面专属样式/片段用
// [data-app-mode="desktop"] 作用域。网页端无 __MYK_APP_MODE__，零变化。
if (window.__MYK_APP_MODE__) {
  document.documentElement.setAttribute("data-app-mode", "desktop");
}

/**
 * 全局 ref 链接点击处理（供 marked 渲染的 onclick 调用）
 */
window._mykRefClick = function (event, refPath) {
  event.preventDefault();

  const docEl = document.querySelector('[x-data="docComponent"]');
  if (docEl && docEl.__x) {
    const data = docEl.__x.$data;
    if (typeof data.openRefPopover === "function") {
      data.openRefPopover(event, refPath);
      return;
    }
  }

  try {
    const store = Alpine.store("app");
    store.showPopover(event, refPath);
    loadRefPreview(refPath).then((preview) => {
      if (docEl && docEl.__x) {
        docEl.__x.$data.refPreview = preview;
        docEl.__x.$data.refLoading = false;
      }
    });
  } catch {
    // Alpine 可能尚未初始化
  }
};
