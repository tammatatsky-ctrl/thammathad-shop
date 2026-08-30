/* ===== FX MOD: ripple (คลื่นที่จุดคลิก) ===== */
/**
 * FX mod id: 'ripple' — คลื่นกระจายจากจุดคลิกบน selector RIPPLE_SEL (ปุ่ม/ลิงก์…).
 * ctx ที่ใช้: Motion.reduced() — ถ้าปิดระบบ ไม่ผูก listener เลย + doRipple ไม่เล่น.
 * ใช้ object pool (RipplePool) กันการสร้าง DOM ทุกคลิก → คลื่นรีไซเคิลหลัง animationend.
 */
FX.register({
  id: "ripple",
  boot: function (ctx) {
    var RIPPLE_SEL =
      ".btn, .nav-link, .dropdown-item, .lens-btn, .account-chip, .theme-switch, .back-top, .pagination a";
    /** Object pool ของคลื่น (max 8 ชิ้น) — เก็บ wrap+dot ใช้ซ้ำ ลด GC. */
    var RipplePool = {
      _pool: [],
      _max: 8,
      _get: function () {
        var item;
        if (this._pool.length) item = this._pool.pop();
        else {
          var wrap = document.createElement("span");
          wrap.className = "apple-ripple-wrap";
          var dot = document.createElement("span");
          dot.className = "apple-ripple";
          wrap.appendChild(dot);
          item = { wrap: wrap, dot: dot };
        }
        item._released = false;
        return item;
      },
      _release: function (item) {
        if (item._released) return;
        item._released = true;
        if (item.wrap.parentNode) item.wrap.remove();
        item.dot.style.width = "";
        item.dot.style.height = "";
        item.dot.style.left = "";
        item.dot.style.top = "";
        item.dot.style.animation = "none";
        item.dot.offsetHeight;
        item.dot.style.animation = "";
        if (this._pool.length < this._max) this._pool.push(item);
      },
    };
    /** doRipple(e) — เล่นคลื่นที่ (clientX, clientY) บน element ใน RIPPLE_SEL.
     *  ถ้าต้นทางมี position static จะบังคับ relative ก่อน เพื่อให้ span วางได้ถูกที่.
     *  @param {MouseEvent} e event ที่มี clientX/clientY + target.closest
     */
    function doRipple(e) {
      if (Motion.reduced()) return;
      var t = e.target.closest(RIPPLE_SEL);
      if (!t) return;
      var cs = getComputedStyle(t);
      if (cs.position === "static") t.style.position = "relative";
      var r = t.getBoundingClientRect();
      var d = Math.min(Math.max(r.width, r.height) * 1.6, 320);
      var item = RipplePool._get();
      item.dot.style.width = item.dot.style.height = d + "px";
      item.dot.style.left = e.clientX - r.left - d / 2 + "px";
      item.dot.style.top = e.clientY - r.top - d / 2 + "px";
      t.appendChild(item.wrap);
      var pool = RipplePool;
      var rm = function () {
        pool._release(item);
      };
      item.dot.addEventListener("animationend", rm, { once: true });
      setTimeout(rm, 650);
    }
    /* ---- Ripple click ---- */
    if (!Motion.reduced())
      document.addEventListener("click", doRipple, { passive: true });
  },
});
