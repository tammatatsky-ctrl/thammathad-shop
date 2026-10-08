/* ===== FX MOD: scene (Depth Hero — tilt ตามเมาส์ + ถอยตาม scroll) ===== */
/**
 * FX mod id: 'scene' — ผสมความลึกให้ hero หน้าแรก (.hero-card-wrap) 2 ชั้น:
 *
 *  1) TILT ตามเมาส์ (±4°) — อ่านเมาส์จาก InteractionEngine (ctx.move) + lerp หนืด
 *     เขียน --scene-rx/--scene-ry ลง .hero-card-wrap.
 *     เป็น "interaction ที่ผู้ใช้เริ่มเอง" → ไม่ถูก gate ด้วย Motion.reduced
 *     (กติกาเดียวกับ morph — animation อัตโนมัติเท่านั้นที่โดน ⚡).
 *
 *  2) DEPTH ตาม scroll — ScrollEngine.subscribe: คำนวณ --scene-scroll (0..1
 *     สัดส่วนความคืบหน้าของ grid) แล้ว CSS ใช้ translateY/scale เบา ๆ —
 *     wrapper ดู "ถอยลึก" ตามการเลื่อน เลเยอร์แสง/แก้วไม่ถูกรบกวน.
 *
 *  ออกแบบให้ไม่ทำงานซ้ำกับ mod อื่น:
 *   - .liquid-glass ยังเป็นของ fx-glass (spotlight/tilt engine / displacement)
 *   - .hero-glass-layer อ่าน vars ที่ fx-glass ตั้งให้เอง (--mouse-x/--spec-o/--bloom-o)
 *     = แสงเมาส์นั้นมีแล้ว — mod นี้ไม่ copy (DRY)
 *   - match: .hero-card-wrap (index หน้าเดียว) — ดู fx-assets.js.
 *
 *  ctx ที่ใช้: ctx.move/offMove, ctx.onToggle, ctx.scroll (ScrollEngine.subscribe).
 */
FX.register({
  id: "scene",
  boot: function (ctx) {
    var wrap = document.querySelector(".hero-card-wrap");
    if (!wrap) return;

    var MAX = 4; // มุมสูงสุด (± องศา)
    var DEPTH_MAX = 26; // px ที่ถอยสูงสุดตาม scroll
    var tx = 0,
      ty = 0; // ตำแหน่งเมาส์ล่าสุด → เป้า tilt
    var cx = 0,
      cy = 0; // ค่า lerp ปัจจุบัน
    var raf = null;

    function tick() {
      raf = null;
      var e = 0.12;
      cx += (tx - cx) * e;
      cy += (ty - cy) * e;
      wrap.style.setProperty("--scene-rx", cy.toFixed(2) + "deg");
      wrap.style.setProperty("--scene-ry", cx.toFixed(2) + "deg");
      if (Math.abs(tx - cx) > 0.05 || Math.abs(ty - cy) > 0.05) {
        raf = requestAnimationFrame(tick);
      }
    }
    function kick() {
      if (!raf) raf = requestAnimationFrame(tick);
    }

    function onMove(mx, my) {
      var vw = window.innerWidth || 1,
        vh = window.innerHeight || 1;
      var nx = ((mx / vw) - 0.5) * 2; // -1..1 แนวนอน
      var ny = ((my / vh) - 0.5) * 2; // -1..1 แนวตั้ง
      tx = nx * MAX;
      ty = -ny * MAX;
      kick();
    }

    ctx.move(onMove);
    ctx.onToggle(function (enabled) {
      if (enabled) ctx.move(onMove);
      else ctx.offMove(onMove);
    });

    /* ออกจากหน้า → กลับตรง */
    document.addEventListener("mouseout", function (e) {
      if (!e.relatedTarget) {
        tx = 0;
        ty = 0;
        kick();
      }
    });

    /* ---- depth ตาม scroll ---- */
    var lastScroll = -1;
    function onScroll(s) {
      var max = Math.max(
        1,
        document.documentElement.scrollHeight - window.innerHeight,
      );
      var v = Math.max(0, Math.min(1, s.y / max));
      if (v !== lastScroll) {
        lastScroll = v;
        wrap.style.setProperty("--scene-scroll", v.toFixed(3));
      }
    }
    ctx.scroll(onScroll);
    onScroll({ y: window.scrollY || 0 });
  },
});
