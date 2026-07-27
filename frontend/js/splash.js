/* ==========================================================================
   MyKnowledge — 加载动画模块（纯 JS，不依赖 Alpine）
   封装进度条、冲刺、完成动画，供 store.init() 调用
   ========================================================================== */

window._mykSplash = {
  _bar: null,
  _t0: 0,

  /** 初始化：绑定进度条 DOM */
  init(t0) {
    this._bar = document.getElementById("splashBar");
    this._t0 = t0 || performance.now();
  },

  /** 设进度 0-100 */
  set(p) {
    if (this._bar) this._bar.style.width = p + "%";
  },

  /** 加载一步（带最小延时） */
  async step(task, p, minStep) {
    const t = performance.now();
    await task.catch(() => {});
    const d = performance.now() - t;
    if (d < minStep) await new Promise(r => setTimeout(r, minStep - d));
    this.set(p);
  },

  /** 冲刺 + 完成动画 */
  async sprint() {
    const elapsed = performance.now() - this._t0;
    const minDelay = 500 + Math.random() * 700;
    const remaining = Math.max(300, minDelay - elapsed);
    const steps = Math.max(6, Math.floor(remaining / 50));
    const stepMs = remaining / steps;
    this.set(90);
    for (let i = 1; i < steps; i++) {
      await new Promise(r => setTimeout(r, stepMs));
      this.set(90 + Math.round((i / steps) * 10));
    }
    await new Promise(r => setTimeout(r, stepMs));
    this.set(100);
    await new Promise(r => setTimeout(r, 250));
    if (this._bar) {
      this._bar.classList.add("splash__bar-fill--done");
    }
    await new Promise(r => setTimeout(r, 800));
  },
};
