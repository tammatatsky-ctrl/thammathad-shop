/* ===== FX MOD: halo (แสงเมาส์หลังการ์ด — backlight ให้เรียบ) ===== */
/**
 * FX mod id: 'halo' — ย้าย "ไฟเมาส์" จากบนผิวการ์ด ไปอยู่หลังการ์ด (backlight halo):
 *
 * fx-glass.js เป็น engine ตัวเดิม (UNCHANGED) มันเซ็ต var ลง .style (inline) ของตัวการ์ด
 * --mouse-x/--mouse-y/--spec-o/--bloom-o — mod นี้ "mirror" ค่าเหล่านั้นขึ้นไปวางที่ host
 * (.halo-host: .col ของการ์ด / .hero-shell ของ hero) แล้ว CSS (fx-halo.css) วาด radial
 * blur 26px z:-1 ที่ host → แสงฟุ้งล้นขอบการ์ดที่ pos เดียวกับที่มือชี้.
 *
 * ทำไมไม่แก้ fx-glass.js: มันถูก lock เป็นไฟล์คง (UNCHANGED) และมันคำนวณ Fresnel/rays เต็ม
 * รอบอยู่แล้ว — mirror อ่านค่าสำเร็จมาใช้ ไม่ต้องคำนวณซ้ำ (read style.setProperty = zero-cost).
 * ใครปิดหลอดไฟhero/tile: ลบ mod ที่ basetemplate → ไม่ต้องแตะ core.
 *
 * SMOOTHING (Apple feel): mirror ไม่กระโดดตาม target ทันที — ผ่าน LERP damped (ease ที่ขึ้นกับ
 * dt) ทั้งตำแหน่ง/ความแรง แล้วค่อยเขียนลง CSS เช่นเดียวกับ glass engine ที่ใช้ INERTIA_RATE.
 * rAF ยังวิ่งต่อไปจนทุกค่า settle (กัน "กระตุกตามมือเร็ว") — ตั้ง RATE = 8 หนืดขึ้นนิด.
 *
 * ctx ที่ใช้: ctx.move()/ctx.offMove() (InteractionEngine), ctx.reduced() (ไม่ผูกเมื่อปิด),
 * ctx.onToggle (เปิดกลับ → ผูกใหม่).
 */
FX.register({
  id: "halo",
  boot: function (ctx) {
    function clamp(v, lo, hi) {
      return Math.max(lo, Math.min(hi, v));
    }

    /* ---- เตรียม host map: card -> host (.halo-host) ---- */
    var hosts = [];
    function addHost(el) {
      if (!el || el.dataset.haloBound) return;
      if (el.closest(".card-expand-wrap")) return; // กล่อง morph ไม่มีคู่
      var host = el.classList.contains("liquid-glass") ||
        el.classList.contains("hero-card") ||
        el.classList.contains("hero-shell")
        ? el.closest(".hero-shell")
        : el.parentElement.closest(".col") || el.parentElement;
      if (!host || host.dataset.haloBound) return;
      host.dataset.haloBound = "1";
      host.classList.add("halo-host");
      /* state ต่อ host: เก็บ "ค่าเป้า" (target) กับ "ค่าปัจจุบัน" (cur) เพื่อ lerp */
      hosts.push({
        card: el,
        host: host,
        t: { x: 50, y: 50, ho: 0 },
        c: { x: 50, y: 50, ho: 0 },
        lastWrite: "",
      });
    }
    function collect() {
      document
        .querySelectorAll(".liquid-glass, .card, .apple-tile")
        .forEach(function (el) {
          if (el.classList.contains("liquid-glass")) {
            addHost(el);
          } else if (!el.closest(".halo-host")) {
            addHost(el);
          }
        });
    }
    collect();
    window.addEventListener("resize", collect, { passive: true });
    window.addEventListener("load", collect);
    setTimeout(collect, 800);
    window.__haloCollect = collect;

    /* ---- mirror: คัดค่า vars สำเร็จจาก card ขึ้น host (อ่าน .style = inline ที่ fx-glass เขียน) ---- */
    function mirrorHost(h) {
      var s = h.card.style;
      var spec = parseFloat(s.getPropertyValue("--spec-o") || "0") || 0;
      var bloom = parseFloat(s.getPropertyValue("--bloom-o") || "0") || 0;
      var mx = s.getPropertyValue("--mouse-x") || "50%";
      var my = s.getPropertyValue("--mouse-y") || "50%";
      /* --ho: แรงรวม = แสงหลัก + ประกายปลาย — ลดแรงลงที่ 0.8 (ภาพนุ่ม ไม่แข็ง) */
      h.t.ho = clamp(spec + bloom * 0.5, 0, 1) * 0.8;
      h.t.x = parseFloat(mx) || 50;
      h.t.y = parseFloat(my) || 50;
    }

    /* ---- lerp damped: ไล่ค่าปัจจุบันเข้าหาเป้าด้วย ease ขึ้นกับ dt (Apple feel) ---- */
    var RATE = 8; // 8 < INERTIA_RATE(15) ของ glass — ดูหนืด/ลื่นกว่า
    function lerpTo(cur, target, ease) {
      return cur + (target - cur) * ease;
    }

    var ticking = false;
    var lastT = 0;
    var lastX = 0,
      lastY = 0;

    /* state เพิ่มตัวสำหรับ page light (ตำแหน่ง + ความแรง) */
    var pl = { tx: 50, ty: 50, ts: 0, tb: 0, cx: 50, cy: 50, cs: 0, cb: 0 };
    var plLastWrite = ""; /* guard: เขียน --bg-* เฉพาะเมื่อค่าเปลี่ยนจริงเท่านั้น
        (เดิมเขียนทุกเฟรม = style write + full-screen repaint ต่อเฟรมตลอดที่เมาส์วิ่ง) */

    /* ---- page light: แสงฟุ้งทั้งหน้า (#bgLight) — บั๊กเดิมใน fx-glass: pageGlow ถูกจับก่อน
       element ถูก append เข้า DOM → null → applyBgLights ไม่เคยเขียน --bg-spec/--bg-bloom
       เลยแม้แต่เดียว (พื้นหลังไม่ตอบสนอง) — mod นี้เขียนแทน โดยใช้สูตร Fresnel เดียวกับ core. ---- */
    var pageLight = document.getElementById("bgLight");

    function computePageLight() {
      var vw = window.innerWidth || 1;
      var vh = window.innerHeight || 1;
      var lx = clamp((lastX / vw) * 2 - 1, -1, 1);
      var ly = clamp((lastY / vh) * 2 - 1, -1, 1);
      var lz = 1.35,
        vSum = lz + 1;
      var ndh = vSum / Math.sqrt(lx * lx + ly * ly + vSum * vSum);
      var lLen = Math.sqrt(lx * lx + ly * ly + lz * lz);
      var ndl = lz / lLen;
      var fres = 0.04 + 0.96 * Math.pow(1 - ndl, 5);
      /* ทำนุ่ม: ลด exponent/ความแรงของ spec ลง (30→22, 1.6→1.2) — ไฟหน้าไม่เด้งรุนแรง */
      var spec = Math.min(1, Math.pow(ndh, 22) * 1.2 * (0.5 + fres)) * 0.55;
      var bloom = Math.min(1, Math.pow(ndh, 4) * 0.8) * 0.6;
      pl.tx = (lastX / vw) * 100;
      pl.ty = (lastY / vh) * 100;
      pl.ts = spec;
      pl.tb = bloom;
    }

    function update(now) {
      ticking = false;
      now = now || performance.now();
      var dt = lastT ? Math.min((now - lastT) / 1000, 0.05) : 0.016;
      lastT = now;
      var ease = 1 - Math.exp(-dt * RATE);
      var alive = false;

      /* 1) อัปเดตเป้าจาก card (mirror) ทุกเฟรม */
      for (var i = 0; i < hosts.length; i++) mirrorHost(hosts[i]);

      /* 2) lerp + เขียน CSS เมื่อค่าเปลี่ยนพอสมควร */
      for (var j = 0; j < hosts.length; j++) {
        var h = hosts[j];
        h.c.x = lerpTo(h.c.x, h.t.x, ease);
        h.c.y = lerpTo(h.c.y, h.t.y, ease);
        h.c.ho = lerpTo(h.c.ho, h.t.ho, ease);
        if (
          Math.abs(h.c.x - h.t.x) > 0.05 ||
          Math.abs(h.c.y - h.t.y) > 0.05 ||
          Math.abs(h.c.ho - h.t.ho) > 0.003
        ) {
          alive = true;
        }
        var write =
          h.c.x.toFixed(2) + "|" + h.c.y.toFixed(2) + "|" + h.c.ho.toFixed(3);
        if (write !== h.lastWrite) {
          h.lastWrite = write;
          var hs = h.host.style;
          hs.setProperty("--hx", h.c.x.toFixed(2) + "%");
          hs.setProperty("--hy", h.c.y.toFixed(2) + "%");
          /* แรงรวม compress นิด: ho ล่างสุดของพลัง 0.95 (คงไม่ถึง sec ให้ให้ค่านุ่ม) */
          hs.setProperty("--ho", clamp(h.c.ho, 0, 1).toFixed(3));
        }
      }

      /* 3) page light พร้อม lerp */
      computePageLight();
      pl.cx = lerpTo(pl.cx, pl.tx, ease);
      pl.cy = lerpTo(pl.cy, pl.ty, ease);
      pl.cs = lerpTo(pl.cs, pl.ts, ease);
      pl.cb = lerpTo(pl.cb, pl.tb, ease);
      if (
        Math.abs(pl.cx - pl.tx) > 0.05 ||
        Math.abs(pl.cy - pl.ty) > 0.05 ||
        Math.abs(pl.cs - pl.ts) > 0.002 ||
        Math.abs(pl.cb - pl.tb) > 0.002
      ) {
        alive = true;
      }
      if (pageLight) {
        /* guard string — เขียนตัวแปรตามเมาส์เฉพาะค่าเปลี่ยน (reduce full-screen repaint) */
        var pw =
          pl.cx.toFixed(2) +
          "|" +
          pl.cy.toFixed(2) +
          "|" +
          pl.cs.toFixed(3) +
          "|" +
          pl.cb.toFixed(3);
        if (pw !== plLastWrite) {
          plLastWrite = pw;
          pageLight.style.setProperty("--bg-mx", pl.cx.toFixed(2) + "%");
          pageLight.style.setProperty("--bg-my", pl.cy.toFixed(2) + "%");
          pageLight.style.setProperty("--bg-spec", pl.cs.toFixed(3));
          pageLight.style.setProperty("--bg-bloom", pl.cb.toFixed(3));
        }
      }

      if (alive) {
        ticking = true;
        requestAnimationFrame(update);
      }
    }

    function onMove(mx, my) {
      lastX = mx;
      lastY = my;
      if (!ticking) {
        ticking = true;
        lastT = performance.now();
        requestAnimationFrame(update);
      }
    }

    /* ---- reset เมื่อเมาส์ออกจากจอ (fx-glass reset จริงที่ card — mirror ต้องตาม) ---- */
    document.addEventListener("mouseout", function (e) {
      if (!e.relatedTarget) {
        for (var i = 0; i < hosts.length; i++) {
          hosts[i].t.ho = 0;
        }
        pl.ts = 0;
        pl.tb = 0;
        if (!ticking) {
          ticking = true;
          lastT = performance.now();
          requestAnimationFrame(update);
        }
      }
    });

    /* ---- motion gate: ปิด → offMove ปลด listener (CSS not gate — แสงอยู่หลังเสมอ แต่ CPU หยุด) ---- */
    if (!ctx.reduced()) ctx.move(onMove);
    ctx.onToggle(function (enabled) {
      if (enabled) ctx.move(onMove);
      else ctx.offMove(onMove);
    });
  },
});
