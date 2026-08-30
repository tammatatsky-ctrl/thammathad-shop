/* ===== FX MOD: countup (ตัวเลขวิ่งขึ้น) ===== */
/**
 * FX mod id: 'countup' — เลขวิ่งขึ้นจาก 0 ถึงค่าจริงใน element [data-motion="countup"].
 * ctx ที่ใช้: Motion.reduced() (ถ้าปิดระบบ → ข้าม animation เก็บค่าเดิมไว้)
 * ถูกเรียกผ่าน FX.callActor('countup', el):
 *  - โดย EntryEngine (IO) เมื่อ element เข้าจอ
 *  - โดย initial-load hoist (motion-core setTimeout 600) ถ้าอยู่ในจอตอนโหลด
 *  - โดย Motion.toggle ตอนเปิดกลับ (ล้าง hoisted/counted ก่อน)
 * รูปแบบที่อ่าน: "[prefix][number][suffix]" เช่น "฿ 1,234 ฿", decimals คงจากต้นฉบับ.
 */
FX.register({
  id: "countup",
  boot: function (ctx) {
    /* ==================== 5. PRIMITIVES ==================== */
    /** animateCount(el) — เล่นเลขวิ่งขึ้นหนึ่งครั้ง (guard dataset.counted กันเล่นซ้ำ).
     *  @param {HTMLElement} el element ที่มีตัวเลข (textContent จะถูกเขียนทับชั่วคราว)
     */
    function animateCount(el) {
      if (el.dataset.counted) return;
      el.dataset.counted = "1";
      var raw = el.textContent.trim();
      var m = raw.match(/^([^\d]*)([\d,]+(?:\.\d+)?)(.*)$/);
      if (!m) return;
      var pre = m[1],
        val = parseFloat(m[2].replace(/,/g, "")),
        suf = m[3];
      if (isNaN(val) || val <= 0) return;
      if (Motion.reduced()) return;
      var dur = 1200,
        t0 = null;
      var decimals = (m[2].split(".")[1] || "").length;
      function step(ts) {
        if (!t0) t0 = ts;
        var p = Math.min(1, (ts - t0) / dur);
        var e = 1 - Math.pow(1 - p, 3);
        el.textContent =
          pre +
          (val * e).toLocaleString(undefined, {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
          }) +
          suf;
        if (p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    }
    FX.actor("countup", animateCount);
  },
});
