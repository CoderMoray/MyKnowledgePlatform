/* ==========================================================================
   MyKnowledge — Alpine.js 应用入口
   整合所有组件：路由、存储、编辑器、渲染器
   设计系统: Raycast · v2.0
   ========================================================================== */

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
