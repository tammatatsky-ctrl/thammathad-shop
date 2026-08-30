/* ===== FX MOD: card-pop (การ์ดโผล่กลางจอ) ===== */
/**
 * FX mod id: 'card-pop' — การ์ด [data-card-parallax] ที่อยู่ใกล้กึ่งกลางจอจะลอยขึ้นเล็กน้อย
 * (--p-y) + ขยายนิด (--p-z) แบบ smoothstep ตามระยะจากกลาง — รู้สึกเหมือน "การ์ดเด้งกลางจอ"
 * (testa Apple grid feel; เดิมเคยใช้ data-card-speed แบบ depth-scroll — ถูกลบไปแล้ว ห้ามใส่คืน).
 * ctx ที่ใช้: ScrollEngine.subscribe(), Motion.reduced() (ข้ามเมื่อปิด), ctx.onToggle.
 */
FX.register({
  id: "card-pop",
  boot: function (ctx) {
    /* ---- Card center-pop: การ์ดใกล้กึ่งกลางจอโผล่ขึ้นนิดหน่อย (Apple grid feel) ---- */
    var cardPopEls = [];
    function collectCardParallax() {
      cardPopEls = [];
      document.querySelectorAll("[data-card-parallax]").forEach(function (el) {
        cardPopEls.push(el);
      });
    }
    ScrollEngine.subscribe(function (s) {
      if (Motion.reduced()) return;
      var vh = window.innerHeight;
      var band = vh * 0.42;
      for (var i = 0; i < cardPopEls.length; i++) {
        var el = cardPopEls[i];
        var r = el.getBoundingClientRect();
        if (r.bottom < 0 || r.top > vh) continue;
        var center = r.top + r.height / 2;
        var dCenter = Math.abs(center - vh / 2);
        var f = dCenter > band ? 0 : 1 - dCenter / band;
        f = f * f * (3 - 2 * f);
        el.style.setProperty("--p-y", (-f * 8).toFixed(1) + "px");
        el.style.setProperty("--p-z", (1 + f * 0.012).toFixed(3));
      }
    });
    window.addEventListener("resize", collectCardParallax, { passive: true });
    setTimeout(collectCardParallax, 700);
    window.addEventListener("load", collectCardParallax);
    window.__cardParallaxCollect = collectCardParallax;
    if (!Motion.reduced()) collectCardParallax();
    ctx.onToggle(function (enabled) {
      if (enabled) collectCardParallax();
    });
  },
});
