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
    var cardPopItems = [];
    function collectCardParallax() {
      cardPopItems = [];
      var sy = window.scrollY || 0;
      document.querySelectorAll("[data-card-parallax]").forEach(function (el) {
        var r = el.getBoundingClientRect();
        cardPopItems.push({
          el: el,
          docTop: r.top + sy,
          docBottom: r.bottom + sy,
          height: r.height,
          py: "",
          pz: ""
        });
      });
    }
    ScrollEngine.subscribe(function (s) {
      if (Motion.reduced()) return;
      var vh = window.innerHeight;
      var band = vh * 0.42;
      var sy = s.y;
      for (var i = 0; i < cardPopItems.length; i++) {
        var item = cardPopItems[i];
        var top = item.docTop - sy;
        var bottom = item.docBottom - sy;
        if (bottom < 0 || top > vh) {
          if (item.py !== "0px" && item.py !== "") {
            item.py = "0px";
            item.pz = "1";
            item.el.style.setProperty("--p-y", "0px");
            item.el.style.setProperty("--p-z", "1");
          }
          continue;
        }
        var center = top + item.height / 2;
        var dCenter = Math.abs(center - vh / 2);
        var f = dCenter > band ? 0 : 1 - dCenter / band;
        f = f * f * (3 - 2 * f);
        var py = (-f * 8).toFixed(1) + "px";
        var pz = (1 + f * 0.012).toFixed(3);
        if (item.py !== py) {
          item.py = py;
          item.el.style.setProperty("--p-y", py);
        }
        if (item.pz !== pz) {
          item.pz = pz;
          item.el.style.setProperty("--p-z", pz);
        }
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
