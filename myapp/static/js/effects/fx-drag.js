/* ===== FX MOD: drag (ลูกเล่นจับลากแบบ Apple — generic ปอย reusable) ===== */
/**
 * FX mod id: 'drag' — จับลากด้วย pointer (เมาส์ + touch) พร้อม inertia / snap / spring
 * กลับอย่างนุ่ม. เป็น "interaction ที่ผู้ใช้เริ่มเอง" — ทำงานแม้ ⚡ off (กฎโปรเจกต์:
 * off หยุดเฉพาะ animation อัตโนมัติ ไม่ตัดปุ่มลากที่ user ต้องการ), แต่ spring กลับ
 * (เกิดหลังปล่อยมือ) ไม่ทำให้ผลลัพธ์กระโดดถ้าปิด motion.
 *
 * ใช้งานได้ 2 เรื่อง (ไม่ต้องพึ่ง plugin ภายนอก):
 *  1. scope แนวตั้ง/แนวนอนลากได้:
 *       - [data-drag-scope]: ภาชนะใหญ่ที่จับได้ ใช้ pointer-drag หมุน transform 3D
 *         (เช่น hero lens pod). attr: data-drag-roll (ส่งต่อยัง rotateX/Y — ไล่ค่า 0..1)
 *  2. track ลาก (element + ตัวตั้งค่าระยะ):
 *       - [data-drag-track]: element ที่มี "แกนไหล" แนวตั้ง/แนวนอนสำหรับสินค้า
 *         (เช่น product rail). attr: data-drag-step (px ต่อ 1 หน่วย), data-drag-min/max
 *         (หน่วยไหลระหว่าง 0..N), data-drag-axis (x|y), data-drag-snap ("cell"|"").
 *
 * ctx ที่ใช้: ctx.reduced() (ค่าสปริงกลับ/การ track เบาบาง), InteractionEngine ไม่จำเป็น
 * เพราะ mod นี้ฟัง pointer events โดยตรง (drag ต้องจับ pointer โดยเฉพาะ ไม่ใช่เมาส์ไหล).
 *
 * รายละเอียด pointer capture: attach pointerdown → setPointerCapture เพื่อให้ drag
 * ไม่ออกจาก element กลางคัน, และใช้ touch-action CSS (fx-drag.css) กันเบราว์เซอร์ scroll
 * เข้าแทรกทิศทางที่เราจัดการเอง.
 */
FX.register({
  id: "drag",
  boot: function (ctx) {
    /* ---- state ต่อ pointer ---- */
    var active = null; // กำลังลากอยู่ (pointerId)
    var springing = false;

    /* ---- คลาส helper ---- */
    function addClasses(el, list) {
      for (var i = 0; i < list.length; i++) el.classList.add(list[i]);
    }
    function removeClasses(el, list) {
      for (var i = 0; i < list.length; i++) el.classList.remove(list[i]);
    }

    /* ---- scope: hero lens pod / วัตถุ 3D ที่จับหมุน ได้ 2 แกน ---- */
    var scopes = [];
    function collectScopes() {
      /* ไม่ reset scopes (แท่นเดียวกับ collectTracks — ตัวผูกแล้วข้ามกันรักษา state) */
      document.querySelectorAll("[data-drag-scope]").forEach(function (el) {
        if (el.dataset.dragBound) return;
        el.dataset.dragBound = "1";
        addClasses(el, ["drag-surface"]);
        /* ตัวแปรเป้าหมายการหมุน: --rx/--ry ในช่วง -1..1 และ optional spring กลับ */
        scopes.push({ el: el, rx: 0, ry: 0, vx: 0, vy: 0, active: false });
        /* จุดเริ่มสำหรับค่า 0: ให้ตั้งอยู่ที่ "ตรง" เสมอตอนโหลด (CSS ใช้ --rx/--ry) */
        el.style.setProperty("--rx", "0deg");
        el.style.setProperty("--ry", "0deg");
      });
    }
    collectScopes();
    window.addEventListener("resize", collectScopes, { passive: true });
    window.addEventListener("load", collectScopes);
    setTimeout(collectScopes, 700);

    function applyScopeTransform(s) {
      if (!s || !s.el) return;
      /* ใช้ rx/ry (เป็น "องศา") กับ scale เบา ๆ ตามความลึกมือ */
      var ty = s.ry * 12; // เอียงตามลากแนวตั้ง
      var tx = s.rx * 16; // เอียงตามลากแนวนอน
      s.el.style.transform =
        "rotateX(" + ty.toFixed(2) + "deg) rotateY(" + tx.toFixed(2) + "deg)";
    }

    /* ---- track: rail/carousel — element ตัวไหลเอง (ลูก) จะโดน translate ตาม index ---- */
    var tracks = [];
    function collectTracks() {
      /* สำคัญ: ห้าม reset tracks=[] — ตัวที่ trackBound='1' แล้ว (mount รอบแรก) ถูกข้าม
         ไม่ push ซ้ำ แต่การ reset จะล้าง state ที่ mount ไว้แล้ว → dragSetIndex (ปุ่มกด)
         หาไม่เจอ → rail ไม่เลื่อน (บั๊กที่เพิ่งแก้) */
      document.querySelectorAll("[data-drag-track]").forEach(function (el) {
        if (el.dataset.trackBound) return;
        el.dataset.trackBound = "1";
        var axis = el.getAttribute("data-drag-axis") || "x";
        var step = parseFloat(el.getAttribute("data-drag-step")) || 0;
        var min = parseInt(el.getAttribute("data-drag-min"), 10) || 0;
        var max = parseInt(el.getAttribute("data-drag-max"), 10) || 0;
        var snap = el.getAttribute("data-drag-snap"); // "cell" ถ้าจะ snap ต่อ step
        addClasses(el, axis === "y" ? ["drag-v-track"] : ["drag-h-track"]);
        tracks.push({
          el: el,
          axis: axis,
          step: step,
          min: min,
          max: max,
          index: parseInt(el.getAttribute("data-drag-idx"), 10) || 0,
          snap: snap === "cell",
          /* translate ที่ใช้ (px) — คำนวณจาก index*step */
          render: function () {
            var dx =
              this.axis === "y"
                ? 0
                : -(this.index * this.step);
            var dy = this.axis === "y" ? -(this.index * this.step) : 0;
            el.style.transform =
              "translate3d(" + dx.toFixed(1) + "px," + dy.toFixed(1) + "px,0)";
          },
        });
        el.style.willChange = "transform";
      });
      /* render เริ่มต้น (index 0) */
      tracks.forEach(function (t) {
        t.render();
      });
    }
    collectTracks();
    window.addEventListener("resize", collectTracks, { passive: true });
    window.addEventListener("load", collectTracks);
    setTimeout(collectTracks, 700);

    /* ---- ปุ่ม prev/next/จุด (จากโค้ดรอบตัว template) ต้องสั่งให้ track เลื่อนจริง ๆ ----
       เดิม template เขียนได้แค่ data-drag-idx + class แต่ fx-drag เก็บ index ไว้เป็น
       private ใน tracks[i].index และไม่ฟัง data-drag-idx จากภายนอก → กดปุ่มแล้ว rail
       ไม่เลื่อน (แค่ active เปล่ง). เพิ่ม API ให้โค้ดรอบตัวเรียกเลื่อน + สะท้อนกลับผ่าน
       data-drag-idx (template ฟัง watchAttr ได้อัตโนมัติ). */
    function setTrackIndex(trackEl, target) {
      if (!trackEl) return false;
      var t = tracks.find(function (s) { return s.el === trackEl; });
      if (!t) return false;
      var i = Math.max(t.min, Math.min(t.max, Math.round(Number(target) || 0)));
      t.index = i;
      t.render(); /* เลื่อน .rail-inner จริง ตาม index */
      /* ไม่เขียน data-drag-idx ที่นี่ — ปล่อยให้โค้ดรอบตัว (template) เขียนผ่าน FX.watchAttr.set
         เพื่อตั้ง lastWritten กัน observer วนสะท้อน (recipe #9). ถ้าเรากรwriter attr ตรง ๆ
         + watchAttr ของ template ก็เขียนด้วย จะทำให้ observer ทริกซ้ำ/วนได้. */
      return true;
    }
    if (window.FX) {
      if (!window.FX.api) window.FX.api = {};
      window.FX.api.dragSetIndex = setTrackIndex;
      window.FX.api.dragTrackEl = function (el) {
        return el && el.classList && el.classList.contains("drag-h-track")
          ? el
          : (el && el.querySelector ? el.querySelector("[data-drag-track]") : null);
      };
    }

    /* เก็บ scopes ไปยัง transform ที่อัปเดตเมื่อลาก */
    function updateScope(sp, dx, dy) {
      /* จับเป็น "องศา" ตามการลาก: ใหญ่ขึ้นตามระยะ ลด 0.25 (นุ่ม) */
      var sensX = 0.25 * (sp.el.dataset.dragSenseX ? parseFloat(sp.el.dataset.dragSenseX) : 1);
      var sensY = 0.2;
      sp.rx = Math.max(-28, Math.min(28, dx * sensX));
      sp.ry = Math.max(-22, Math.min(22, -dy * sensY));
      applyScopeTransform(sp);
    }

    /* ---- loop spring กลับ scopes เมื่อปล่อย (ไม่ active) ---- */
    var rafActive = false;
    function springLoop() {
      rafActive = false;
      var alive = false;
      scopes.forEach(function (sp) {
        if (sp.active) return;
        var e = 0.14; // กลับหนืด-นุ่ม
        var nx = sp.rx + (0 - sp.rx) * e;
        var ny = sp.ry + (0 - sp.ry) * e;
        if (Math.abs(sp.rx - 0) > 0.15 || Math.abs(sp.ry - 0) > 0.15) {
          alive = true;
        }
        sp.rx = nx;
        sp.ry = ny;
        applyScopeTransform(sp);
      });
      if (alive) {
        rafActive = true;
        requestAnimationFrame(springLoop);
      } else {
        /* spring จบแล้ว (ทุก scope เข้าใกล้เป้าหมาย) — ปลดล็อก springing ให้ลากครั้งถัดไป
           สปริงกลับได้อีก (เดิม springing=true ค้างไว้ไม่มีโค้ด reset = ลากครั้งแรกแล้วไม่กลับอีกเลย) */
        springing = false;
      }
    }
    function kickSpring() {
      if (!springing && !ctx.reduced()) {
        springing = true;
        if (!rafActive) {
          rafActive = true;
          requestAnimationFrame(springLoop);
        }
      }
    }

    /* ---- pointer handlers (เมาส์ + touch — แบบ pointer events เดียว) ---- */
    function onDown(e) {
      /* ห้ามลากถ้ากำลังคลิกที่ link/ปุ่ม (ให้ click ทำงานปกติ) — ยกเว้น scope (object ใหญ่) */
      var t = e.target;
      var scopeEl = t.closest("[data-drag-scope]");
      var trackEl = t.closest("[data-drag-track]");
      if (!scopeEl && !trackEl) return;
      if (!scopeEl && t.closest("a,button")) return; // ปุ่มใน rail: ปล่อยให้คลิกไหล
      if (active) return;
      active = e.pointerId;
      var target = scopeEl || trackEl;
      target.setPointerCapture && target.setPointerCapture(e.pointerId);
      addClasses(target, ["drag-active"]);
      /* เก็บค่าเริ่มต้น */
      var scopeState = scopeEl ? scopes.find(function (s) { return s.el === scopeEl; }) : null;
      var trackState = trackEl ? tracks.find(function (s) { return s.el === trackEl; }) : null;
      dragStart = {
        id: e.pointerId,
        x: e.clientX,
        y: e.clientY,
        scope: scopeState,
        track: trackState,
        index0: trackState ? trackState.index : 0,
        moved: false,
      };
      if (scopeState) scopeState.active = true;
      if (trackState) {
        trackState.dx0 = 0;
        trackState.dy0 = 0;
      }
    }
    var dragStart = null;

    function onMove(e) {
      if (!active || e.pointerId !== active || !dragStart) return;
      var dx = e.clientX - dragStart.x;
      var dy = e.clientY - dragStart.y;
      if (Math.abs(dx) + Math.abs(dy) < 4) return; // ยังนับเป็นคลิก (ไม่ลาก)
      dragStart.moved = true;
      if (dragStart.scope) {
        updateScope(dragStart.scope, dx, dy);
      }
      if (dragStart.track) {
        var t = dragStart.track;
        var delta = t.axis === "y" ? dy : dx;
        /* สัดส่วน → index (แบบ continuous จริง ๆ ไม่ snap ระหว่างลาก) */
        var idxF = dragStart.index0 + delta / t.step;
        var clamped = Math.max(t.min, Math.min(t.max, idxF));
        t.index = clamped;
        /* ต่อให้ snap ไว้ — ระหว่างลากให้ไหลตามนิ้วได้เต็มที่ */
        t.render();
      }
    }

    function onUp(e) {
      if (!active || e.pointerId !== active) return;
      var start = dragStart;
      active = null;
      dragStart = null;
      /* spring scope กลับ + คลิกไหลถ้าไม่ลาก */
      if (start && start.scope) {
        start.scope.active = false;
        kickSpring();
      }
      if (start && start.track) {
        var t = start.track;
        if (t.snap) {
          /* snap ไป cell ใกล้สุด (คิดจากทศนิยม) + เร็วน้อยหน่อย →
             เรียบเหมือน Apple dock */
          t.index = Math.round(t.index);
          t.index = Math.max(t.min, Math.min(t.max, t.index));
          t.render();
          syncTrackIdx(t);
        } else {
          t.index = Math.max(t.min, Math.min(t.max, t.index));
          t.render();
          syncTrackIdx(t);
        }
      }
      /* ลากเกิน → ถ้าลาก scope (hero) แล้ว moved ใหญ่ → ปิด icon ค้างไว้
         (ไม่ได้ snap index ใหม่ — scope ไม่มีความหมาย index) */

      /* release: remove drag class จากทุก element ที่ active ไว้ (หาใหม่จาก active)
         ง่ายกว่าเพราะมีแค่ 1 pointer — clear ทุก .drag-active */
      document
        .querySelectorAll(".drag-active")
        .forEach(function (el) { removeClasses(el, ["drag-active"]); });

      /* คลิกไหล: ถ้าไม่ moved → ปล่อยให้ browser ทำ click ตามปกติ */
      if (start && start.moved) {
        /* ป้อง link เดิมถูกทริก (เพราะเราจับ pointer ไว้) — คืนให้ได้ด้วย preventDefault
           ในกรณี scope (ลาก hero ไม่ควรพาไปหน้าสินค้า) */
        if (start.scope) e.preventDefault();
      }
    }

    function syncTrackIdx(t) {
      /* แจ้ง template-code ผ่าน data attr เพื่อให้ JS ที่เขียนรอบ (dots/idx) ตามได้ */
      if (t && t.el) t.el.setAttribute("data-drag-idx", String(Math.round(t.index)));
    }

    /* gc: destroy กี่ pointer ผ่าน capture end/leave เพื่อไม่ขาด */
    function onPointerCancel(e) {
      if (active === e.pointerId) onUp(e);
    }
    function onLostCapture(e) {
      if (active === e.pointerId) onUp(e);
    }

    document.addEventListener("pointerdown", onDown, { passive: false });
    document.addEventListener("pointermove", onMove, { passive: false });
    document.addEventListener("pointerup", onUp, { passive: false });
    document.addEventListener("pointercancel", onPointerCancel);
    document.addEventListener("lostpointercapture", onLostCapture);

    /* ---- motion gate: off ไม่ตัด interaction (ลากได้) — แต่หยุด spring loop เพื่อ
       ประหยัด CPU (ผลลัพธ์ตำแหน่งคงที่พอ) ---- */
    ctx.onToggle(function (enabled) {
      if (!enabled) {
        /* ปิด: หยุด spring ค้างตำแหน่งปัจจุบันทันที */
        rafActive = false;
      }
    });
  },
});
