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
      var sy = window.scrollY || 0;
      document
        .querySelectorAll('[data-motion="parallax"]')
        .forEach(function (el) {
          var speed = parseFloat(el.getAttribute("data-speed")) || 0.3;
          var r = el.getBoundingClientRect();
          parallaxItems.push({
            el: el,
            speed: speed,
            docTop: r.top + sy,
            docBottom: r.bottom + sy,
            height: r.height,
            lastT: ""
          });
        });
    }
    ScrollEngine.subscribe(function (s) {
      if (Motion.reduced()) return;
      var vh = window.innerHeight;
      var sy = s.y;
      for (var i = 0; i < parallaxItems.length; i++) {
        var p = parallaxItems[i];
        var top = p.docTop - sy;
        var bottom = p.docBottom - sy;
        if (bottom < -100 || top > vh + 100) continue;
        var center = top + p.height / 2;
        var offset = (center - vh / 2) * p.speed;
        var t = "translate3d(0," + (-offset).toFixed(2) + "px,0)";
        if (p.lastT !== t) {
          p.lastT = t;
          p.el.style.transform = t;
        }
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
