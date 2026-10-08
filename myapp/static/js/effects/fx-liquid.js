/* ===== FX MOD: liquid (visionOS Spatial Matrix & Cyber Aurora Engine) ===== */
/**
 * FX mod id: 'liquid' — ขับเคลื่อนสภาพแวดล้อมเชิงมิติมัลติเลเยอร์หลังเลนส์แก้ว
 * - รองรับ Spatial Floating Tech Chips, Cyber Orbs และ Aurora Streams
 * - คำนวณ Multi-depth Spring Parallax บน GPU Compositor Thread (translate3d)
 * - แคช DOM Elements และ Data Depths ตั้งแต่ตอน Boot — ไม่เกิด Layout Thrashing ใน rAF
 * - อัตราตอบสนอง Zero-Lag ที่ 60–144 FPS
 * - ผูกกับปุ่ม ⚡ (Motion Toggle) ตามมาตรฐาน AGENTS.md
 */
FX.register({
  id: "liquid",
  boot: function (ctx) {
    var mesh = document.querySelector(".liquid-mesh");
    if (!mesh || mesh.dataset.liquidBound) return;
    mesh.dataset.liquidBound = "1";

    /* ---- Pre-cache Spatial Elements & Depths (หลีกเลี่ยง query ในลูป rAF) ---- */
    var rawItems = document.querySelectorAll(".spatial-chip, .cyber-orb");
    var spatialItems = [];
    for (var i = 0; i < rawItems.length; i++) {
      var item = rawItems[i];
      spatialItems.push({
        el: item,
        depth: parseFloat(item.dataset.depth) || 0.05,
      });
    }

    /* ---- Critically Damped Multi-Plane Spring Physics ---- */
    var target = { x: 0, y: 0 };
    var cur = { x: 0, y: 0 };
    var ticking = false;
    var lastT = 0;

    function update(now) {
      ticking = false;
      now = now || performance.now();
      var dt = lastT ? Math.min((now - lastT) / 1000, 0.05) : 0.016;
      lastT = now;

      /* สปริงหน่วงแบบนุ่มนวลติดมือ (Critical-Damped Lerp) */
      var ease = 1 - Math.exp(-dt * 12);
      cur.x += (target.x - cur.x) * ease;
      cur.y += (target.y - cur.y) * ease;

      /* 1. เลื่อนคอนเทนเนอร์หลักเบาๆ ให้ทั้งผืนออโรร่าคล้อยตามสายตา */
      var mx = (cur.x * 14).toFixed(1);
      var my = (cur.y * 14).toFixed(1);
      mesh.style.transform = "translate3d(" + mx + "px, " + my + "px, 0)";

      /* 2. เลื่อนแต่ละ Floating Node ตามระดับ Depth เฉพาะตัว */
      for (var j = 0; j < spatialItems.length; j++) {
        var s = spatialItems[j];
        var cx = (cur.x * s.depth * 380).toFixed(1);
        var cy = (cur.y * s.depth * 300).toFixed(1);
        s.el.style.transform = "translate3d(" + cx + "px, " + cy + "px, 0)";
      }

      /* Delta check เพื่อหยุด rAF เมื่อหยุดขยับเมาส์ */
      if (Math.abs(target.x - cur.x) > 0.0008 || Math.abs(target.y - cur.y) > 0.0008) {
        ticking = true;
        requestAnimationFrame(update);
      }
    }

    function onMove(mx, my) {
      var vw = window.innerWidth || 1;
      var vh = window.innerHeight || 1;
      target.x = (mx / vw) * 2 - 1; // สเกลพิกัด -1.0 ถึง +1.0
      target.y = (my / vh) * 2 - 1;
      if (!ticking) {
        ticking = true;
        lastT = performance.now();
        requestAnimationFrame(update);
      }
    }

    /* ---- motion gate: ปิดระบบ → offMove ปลด listener ทันที ---- */
    if (!ctx.reduced()) ctx.move(onMove);
    ctx.onToggle(function (enabled) {
      if (enabled) {
        ctx.move(onMove);
      } else {
        ctx.offMove(onMove);
        mesh.style.transform = "";
        for (var k = 0; k < spatialItems.length; k++) {
          spatialItems[k].el.style.transform = "";
        }
      }
    });
  },
});

