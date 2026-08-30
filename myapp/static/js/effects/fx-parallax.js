/* ===== FX MOD: parallax (พื้นหลังเลื่อนตาม scroll) ===== */
/**
 * FX mod id: 'parallax' — element [data-motion="parallax"][data-speed="N"] ขยับแนวตั้ง
 * แบบ parallax ตามระยะจากกลางจอ (speed=1 → เท่าความเร็ว scroll, default 0.3) — เฉพาะที่
 * ยังอยู่ในช่วงจอ (±100px) เท่านั้น กันคำนวณทั้งหน้า.
 * ctx ที่ใช้: ScrollEngine.subscribe(), Motion.reduced() (ข้ามเมื่อปิด), ctx.onToggle
 * (โทเกิลเปิด → collectParallax ใหม่ เพราะ element อาจเปลี่ยนไปแล้ว).
 */
FX.register({
  id: "parallax",
  boot: function (ctx) {
    /* ---- Scroll parallax ---- */
    var parallaxItems = [];
    function collectParallax() {
      parallaxItems = [];
      document
        .querySelectorAll('[data-motion="parallax"]')
        .forEach(function (el) {
          var speed = parseFloat(el.getAttribute("data-speed")) || 0.3;
          parallaxItems.push({ el: el, speed: speed });
        });
    }
    ScrollEngine.subscribe(function (s) {
      if (Motion.reduced()) return;
      var vh = window.innerHeight;
      for (var i = 0; i < parallaxItems.length; i++) {
        var p = parallaxItems[i];
        var r = p.el.getBoundingClientRect();
        if (r.bottom < -100 || r.top > vh + 100) continue;
        var center = r.top + r.height / 2;
        var offset = (center - vh / 2) * p.speed;
        p.el.style.transform =
          "translate3d(0," + (-offset).toFixed(2) + "px,0)";
      }
    });
    window.addEventListener("resize", collectParallax, { passive: true });
    setTimeout(collectParallax, 700);
    window.addEventListener("load", collectParallax);
    window.__parallaxCollect = collectParallax;
    ctx.onToggle(function (enabled) {
      if (enabled) collectParallax();
    });
  },
});
