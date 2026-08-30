/* ===== FX MOD: magnetic (ปุ่มดูดเมาส์) ===== */
/**
 * FX mod id: 'magnetic' — ปุ่ม .btn-primary ค่อยๆ "ดูด" เข้าหาเมาส์เล็กน้อยในรัศมี 110px
 * (lerp แบบนุ่ม กันกระตุก) แล้วคืนตำแหน่งเมื่อเมาส์ออก.
 * - InteractionEngine.onMove → เก็บ target offset ต่อปุ่มใน magState
 * - magTick (rAF หนึ่งวง) lerp current→target แล้วเขียน transform — ใช้ cache magRects
 *   และ invalidateMagRects ตอน scroll/resize (DOM เลื่อนแล้ว rect เดิมเพี้ยน)
 * ctx ที่ใช้: Motion.reduced() (ถ้าปิด → ไม่นับ offset), InteractionEngine.
 */
FX.register({
  id: "magnetic",
  boot: function (ctx) {
    /* ---- Magnetic buttons (จำกัดรัศมี + lerp แบบนุ่ม ไม่กระตุก) ---- */
    var magBtns = document.querySelectorAll(".btn-primary");
    var magRects = [];
    var magState = [];
    var magRaf = null;
    var MAG_R = 110,
      MAG_KX = 0.07,
      MAG_KY = 0.05,
      MAG_LERP = 0.14;
    /** cacheMagRects() — จับคู่ปุ่มปัจจุบัน + reset state offset (เรียกตอนเริ่ม/resize/load). */
    function cacheMagRects() {
      magBtns = document.querySelectorAll(".btn-primary");
      magRects = [];
      magState = [];
      for (var i = 0; i < magBtns.length; i++) {
        magRects.push(null);
        magState.push({ tx: 0, ty: 0, cx: 0, cy: 0 });
      }
    }
    function invalidateMagRects() {
      magRects = magRects.map(function () {
        return null;
      });
    }
    function magTick() {
      magRaf = null;
      var done = true;
      for (var i = 0; i < magBtns.length; i++) {
        var st = magState[i];
        if (!st) continue;
        st.cx += (st.tx - st.cx) * MAG_LERP;
        st.cy += (st.ty - st.cy) * MAG_LERP;
        if (Math.abs(st.tx - st.cx) > 0.05 || Math.abs(st.ty - st.cy) > 0.05)
          done = false;
        magBtns[i].style.transform =
          "translate(" + st.cx.toFixed(1) + "px," + st.cy.toFixed(1) + "px)";
      }
      if (!done) magRaf = requestAnimationFrame(magTick);
    }
    InteractionEngine.onMove(function (mx, my) {
      if (Motion.reduced()) return;
      for (var i = 0; i < magBtns.length; i++) {
        if (!magRects[i]) magRects[i] = magBtns[i].getBoundingClientRect();
        var r = magRects[i];
        var cx = r.left + r.width / 2,
          cy = r.top + r.height / 2;
        var dist = Math.sqrt((mx - cx) * (mx - cx) + (my - cy) * (my - cy));
        var st = magState[i];
        if (!st) continue;
        if (dist > MAG_R) {
          st.tx = 0;
          st.ty = 0;
        } else {
          var f = 1 - dist / MAG_R;
          st.tx = (mx - cx) * f * MAG_KX;
          st.ty = (my - cy) * f * MAG_KY;
        }
      }
      if (!magRaf) magRaf = requestAnimationFrame(magTick);
    });
    document.querySelectorAll(".btn-primary").forEach(function (btn) {
      btn.addEventListener("mouseleave", function () {
        for (var i = 0; i < magBtns.length; i++) {
          if (magBtns[i] === btn && magState[i]) {
            magState[i].tx = 0;
            magState[i].ty = 0;
          }
        }
      });
    });
    cacheMagRects();
    ScrollEngine.subscribe(invalidateMagRects);
    window.addEventListener("resize", invalidateMagRects, { passive: true });
  },
});
