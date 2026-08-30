/* ===== FX MOD: glass (เลนส์แก้ว + bgLight) ===== */
/**
 * FX mod id: 'glass' — เอ็นจิน Liquid Glass (ไม่เปลี่ยนจากทุกเวอร์ชัน) ประกอบด้วย:
 *  1) Lens map: สร้าง displacement map ผ่าน canvas ตามรูปทรง .hero-shell
 *     (โค้งขอบตาม border-radius) แล้วฉายลง SVG filter #liquid-distort → เอฟเฟกต์ "เลนส์นูน"
 *     ขนาด scale ปรับตามแสงจ้า (applyLens) — rebuild ใหม่เมื่อ resize/load/font ready.
 *  2) Spotlight on cards: (.liquid-glass/.card/.apple-tile) คำนวณ reflection แบบ Fresnel +
 *     highlight + specular/bloom ตามตำแหน่งเมาส์ → ตั้ง CSS vars (--spec-o/--bloom-o/--mouse-*)
 *     กับ glass glossiness 2 โหมด (GLOSSY ตัว hero / MATTE การ์ดทั่วไป).
 *  3) Text protection: protectionFrom() ลดแสงบนข้อความ (ช่องที่มีตัวอักษรอ่านยาก)
 *  4) BG light: #bgLight (glow ทั้งหน้า) + .liquid-mesh ที่ติดตามเมาส์
 *  ctx ที่ใช้: Motion.reduced() (ปิด tilt เมื่อระบบปิด), InteractionEngine.onMove, ScrollEngine.
 *  Note: tilt โดน gate, แสง/เลนส์ไม่ขึ้นกับ toggle — เป็น core visual ของระบบ.
 */
FX.register({
  id: "glass",
  boot: function (ctx) {
    /* ==================== 6. LIQUID GLASS ENGINE v3 (UNCHANGED) ==================== */
    try {
      (function () {
        "use strict";
        var MAX_TILT = 2.5;
        var LIGHT_RADIUS = 240;
        var PROT_RADIUS = 140;
        var INERTIA_RATE = 15;
        var TEXT_SEL =
          ".hero-title, .hero-lead, .eyebrow, .hero-actions, h1, h5, .product-name, .product-price, .lead-apple";

        var GLOSSY = {
          specExp: 36,
          specGain: 1.9,
          bloomPow: 4.5,
          bloomGain: 0.75,
        };
        var MATTE = {
          specExp: 16,
          specGain: 1.25,
          bloomPow: 2.8,
          bloomGain: 0.6,
        };

        function clamp(v, lo, hi) {
          return Math.max(lo, Math.min(hi, v));
        }
        function smooth(t) {
          return t * t * (3 - 2 * t);
        }

        var dispEl = document.querySelector(
          "#liquid-distort feDisplacementMap",
        );
        var lensImg = document.getElementById("lensMap");
        var curScale = 8;
        /** applyLens(maxT) — ปรับความแรงเลนส์ (feDisplacementMap scale) ตามแสงจ้าสูงสุดของเฟรม.
         *  @param {number} maxT ความแรง 0..1 ในเฟรมนี้
         */
        function applyLens(maxT) {
          if (!dispEl) return;
          var s = Math.round(8 + maxT * 10);
          if (s !== curScale) {
            curScale = s;
            dispEl.setAttribute("scale", String(s));
          }
        }
        /** buildLensMap() — วาด displacement map (RGB เก็บทิศทาง offset) ตามขนาด/มุมของ .hero-shell
         *  ลง canvas แล้ว convert เป็น dataURL ตั้งให้ SVG image (#lensMap) — โค้งขอบด้วย R.
         */
        function buildLensMap() {
          var hero = document.querySelector(".hero-shell");
          if (!hero || !lensImg) return;
          var rect = hero.getBoundingClientRect();
          var W = Math.max(2, Math.min(1200, Math.ceil(rect.width)));
          var H = Math.max(2, Math.min(800, Math.ceil(rect.height)));
          var cv = document.createElement("canvas");
          cv.width = W;
          cv.height = H;
          var cx = cv.getContext("2d");
          if (!cx || !cx.getImageData) return;
          var R = parseFloat(getComputedStyle(hero).borderRadius) || 28;
          R = Math.min(R, Math.min(W, H) / 2);
          var hw = W / 2 - R,
            hh = H / 2 - R;
          var BAND = Math.min(48, Math.min(W, H) * 0.35);
          var img = cx.createImageData(W, H);
          var d = img.data;
          for (var y = 0; y < H; y++) {
            for (var x = 0; x < W; x++) {
              var qx = Math.abs(x - (W - 1) / 2) - hw;
              var qy = Math.abs(y - (H - 1) / 2) - hh;
              var ax = Math.max(qx, 0),
                ay = Math.max(qy, 0);
              var sd =
                Math.sqrt(ax * ax + ay * ay) +
                Math.min(Math.max(qx, qy), 0) -
                R;
              var i = (y * W + x) * 4;
              var ox = 0.5,
                oy = 0.5;
              if (sd < 0) {
                var band = 1 - -sd / BAND;
                if (band > 0) {
                  var mag = band * band * (3 - 2 * band);
                  var vx = (W - 1) / 2 - x,
                    vy = (H - 1) / 2 - y;
                  var len = Math.sqrt(vx * vx + vy * vy);
                  if (len > 0.001) {
                    ox = 0.5 + 0.5 * (vx / len) * mag;
                    oy = 0.5 + 0.5 * (vy / len) * mag;
                  }
                }
              }
              d[i] = Math.round(ox * 255);
              d[i + 1] = Math.round(oy * 255);
              d[i + 2] = 127;
              d[i + 3] = 255;
            }
          }
          cx.putImageData(img, 0, 0);
          try {
            var url = cv.toDataURL("image/png");
            lensImg.setAttribute("href", url);
            lensImg.setAttribute("xlink:href", url);
            lensImg.setAttribute("width", String(W));
            lensImg.setAttribute("height", String(H));
          } catch (e) {}
        }
        buildLensMap();
        var lensResizeT = null;
        window.addEventListener(
          "resize",
          function () {
            clearTimeout(lensResizeT);
            lensResizeT = setTimeout(buildLensMap, 150);
          },
          { passive: true },
        );
        window.addEventListener("load", buildLensMap);
        if (document.fonts && document.fonts.ready && document.fonts.ready.then)
          document.fonts.ready.then(buildLensMap);

        var entries = Array.prototype.slice
          .call(document.querySelectorAll(".liquid-glass, .card, .apple-tile"))
          .filter(function (c) {
            if (c.dataset.spotlightBound) return false;
            c.dataset.spotlightBound = "1";
            return true;
          })
          .map(function (el) {
            var en = {
              el: el,
              rect: null,
              texts: null,
              textRects: [],
              visible: true,
              vars: {},
              tilt: "",
            };
            el._lightEntry = en;
            return en;
          });

        if ("IntersectionObserver" in window) {
          var io = new IntersectionObserver(
            function (items) {
              items.forEach(function (it) {
                var en = it.target._lightEntry;
                if (en) en.visible = it.isIntersecting;
              });
            },
            { rootMargin: LIGHT_RADIUS + "px" },
          );
          entries.forEach(function (en) {
            io.observe(en.el);
          });
        }

        var rectsDirty = true;
        function invalidateRects() {
          rectsDirty = true;
        }
        window.addEventListener("resize", invalidateRects, { passive: true });
        ScrollEngine.subscribe(function () {
          invalidateRects();
        });
        window.addEventListener("load", invalidateRects);
        if (document.fonts && document.fonts.ready && document.fonts.ready.then)
          document.fonts.ready.then(invalidateRects);

        var bgMesh = document.querySelector(".liquid-mesh");
        var heroShell = document.querySelector(".hero-shell");
        var pageGlow = document.getElementById("bgLight");
        var meshRect = null,
          heroRect = null;
        var heroTextRects = [];
        var heroTexts = heroShell
          ? Array.prototype.slice.call(heroShell.querySelectorAll(TEXT_SEL))
          : [];

        function measure() {
          entries.forEach(function (en) {
            en.rect = en.el.getBoundingClientRect();
            if (!en.texts) en.texts = en.el.querySelectorAll(TEXT_SEL);
            en.textRects.length = 0;
            for (var i = 0; i < en.texts.length; i++)
              en.textRects.push(en.texts[i].getBoundingClientRect());
          });
          meshRect = bgMesh ? bgMesh.getBoundingClientRect() : null;
          heroRect = heroShell ? heroShell.getBoundingClientRect() : null;
          heroTextRects.length = 0;
          for (var j = 0; j < heroTexts.length; j++)
            heroTextRects.push(heroTexts[j].getBoundingClientRect());
        }

        function setVar(en, name, value) {
          if (parseFloat(value) === 0) value = "0";
          if (en.vars[name] === value) return;
          en.vars[name] = value;
          en.el.style.setProperty(name, value);
        }

        function resetCard(en) {
          en.vars = {};
          en.tilt = "";
          var s = en.el.style;
          s.setProperty("--mouse-x", "50%");
          s.setProperty("--mouse-y", "50%");
          s.setProperty("--hi-offset-x", "0px");
          s.setProperty("--hi-offset-y", "1.5px");
          s.setProperty("--shadow-offset-x", "0px");
          s.setProperty("--shadow-offset-y", "-1.5px");
          s.setProperty("--cast-x", "0px");
          s.setProperty("--cast-y", "24px");
          s.setProperty("--cast-i", "0");
          s.setProperty("--spec-o", "0");
          s.setProperty("--bloom-o", "0");
          s.setProperty("--rim-o", "0");
          s.setProperty("--chroma", "0");
          s.setProperty("--ring-angle", "180deg");
          s.transform = "";
        }

        /** protectionFrom(rects, mx, my) — ค่ารัศมีกันแสงบนข้อความ (0..1);
         *  ยิ่งเมาส์ใกล้ช่องข้อความ = แสงบนการ์ดลดลง กันตัวอักษร "จ๋า"
         */
        function protectionFrom(rects, mx, my) {
          var prot = 0;
          for (var i = 0; i < rects.length; i++) {
            var r = rects[i];
            if (!r.width || !r.height) continue;
            var ex = Math.max(
              Math.abs(mx - (r.left + r.width / 2)) - r.width / 2,
              0,
            );
            var ey = Math.max(
              Math.abs(my - (r.top + r.height / 2)) - r.height / 2,
              0,
            );
            prot = Math.max(
              prot,
              smooth(
                clamp(1 - Math.sqrt(ex * ex + ey * ey) / PROT_RADIUS, 0, 1),
              ),
            );
          }
          return prot;
        }

        var _frameMaxT = 0;
        /** applyLight(en, mx, my) — คำนวณแสง/เงาสำหรับการ์ด 1 ใบที่ตำแหน่งเมาส์
         *  (เฉพาะการ์ดที่อยู่จอ visible) แล้วเซ็ต CSS vars + tilt (.liquid-glass เท่านั้น).
         *  setVar() คั่นงานว่า "ค่าเปลี่ยนจริง" กันเขียน style ทุกเฟรมเกินจำเป็น.
         */
        function applyLight(en, mx, my) {
          var r = en.rect;
          if (!r || !r.width || !r.height) return;
          var dx = mx - (r.left + r.width / 2);
          var dy = my - (r.top + r.height / 2);
          var ex = Math.max(Math.abs(dx) - r.width / 2, 0);
          var ey = Math.max(Math.abs(dy) - r.height / 2, 0);
          var t = smooth(
            clamp(1 - Math.sqrt(ex * ex + ey * ey) / LIGHT_RADIUS, 0, 1),
          );
          if (t <= 0 && en.vars["--spec-o"] === "0") return;
          if (t > _frameMaxT) _frameMaxT = t;
          var lx = clamp(dx / (r.width / 2), -1, 1);
          var ly = clamp(dy / (r.height / 2), -1, 1);
          setVar(
            en,
            "--mouse-x",
            (((mx - r.left) / r.width) * 100).toFixed(2) + "%",
          );
          setVar(
            en,
            "--mouse-y",
            (((my - r.top) / r.height) * 100).toFixed(2) + "%",
          );
          setVar(en, "--hi-offset-x", (-lx * 3.5 * t).toFixed(2) + "px");
          setVar(en, "--hi-offset-y", (-ly * 3.5 * t).toFixed(2) + "px");
          setVar(en, "--shadow-offset-x", (lx * 4.0 * t).toFixed(2) + "px");
          setVar(en, "--shadow-offset-y", (ly * 4.0 * t).toFixed(2) + "px");
          setVar(en, "--cast-x", (-lx * 14 * t).toFixed(2) + "px");
          setVar(en, "--cast-y", (24 - ly * 12 * t).toFixed(2) + "px");
          setVar(en, "--cast-i", t.toFixed(3));
          var lz = 1.35,
            lLen = Math.sqrt(lx * lx + ly * ly + lz * lz);
          var ndl = lz / lLen;
          var fres = 0.04 + 0.96 * Math.pow(1 - ndl, 5);
          var rim = Math.min(1, fres * 1.4 * t);
          var vSum = lz + 1;
          var ndh = vSum / Math.sqrt(lx * lx + ly * ly + vSum * vSum);
          var isHero = en.el.classList.contains("liquid-glass");
          var m = isHero ? GLOSSY : MATTE;
          var spec = Math.min(
            1,
            Math.pow(ndh, m.specExp) * m.specGain * t * (0.45 + fres),
          );
          var bloom = Math.min(1, Math.pow(ndh, m.bloomPow) * m.bloomGain * t);
          var over = spec + bloom - 1;
          if (over > 0) {
            bloom = Math.max(0, bloom - over);
          }
          var prot = protectionFrom(en.textRects, mx, my);
          spec *= 1 - 0.85 * prot;
          bloom *= 1 - 0.65 * prot;
          setVar(en, "--spec-o", spec.toFixed(3));
          setVar(en, "--bloom-o", bloom.toFixed(3));
          setVar(en, "--rim-o", rim.toFixed(3));
          setVar(en, "--chroma", isHero ? (rim * 0.8).toFixed(3) : "0");
          var ringDeg =
            (((Math.atan2(lx, -ly) * 57.29578 + 180) % 360) + 360) % 360 || 360;
          setVar(en, "--ring-angle", ringDeg.toFixed(1) + "deg");
          if (!Motion.reduced() && isHero) {
            var tf =
              "perspective(1000px) rotateX(" +
              (-ly * MAX_TILT * t).toFixed(2) +
              "deg) rotateY(" +
              (lx * MAX_TILT * t).toFixed(2) +
              "deg)";
            if (en.tilt !== tf) {
              en.tilt = tf;
              en.el.style.transform = tf;
            }
          } else if (en.tilt) {
            en.tilt = "";
            en.el.style.transform = "";
          }
        }

        function applyBgLights(mx, my) {
          if (heroShell && heroRect) {
            var o = smooth(
              clamp(1 - distOutside(mx, my, heroRect) / LIGHT_RADIUS, 0, 1),
            );
            o *= 1 - 0.75 * protectionFrom(heroTextRects, mx, my);
            if (bgMesh && meshRect && meshRect.width) {
              bgMesh.style.setProperty(
                "--bg-x",
                (((mx - meshRect.left) / meshRect.width) * 100).toFixed(2) +
                  "%",
              );
              bgMesh.style.setProperty(
                "--bg-y",
                (((my - meshRect.top) / meshRect.height) * 100).toFixed(2) +
                  "%",
              );
              bgMesh.style.setProperty("--bg-o", (0.9 * o).toFixed(3));
            }
          }
          if (pageGlow) {
            var vw = window.innerWidth || 1,
              vh = window.innerHeight || 1;
            var lx = (mx / vw) * 2 - 1,
              ly = (my / vh) * 2 - 1;
            var lz = 1.35,
              bvSum = lz + 1;
            var ndh = bvSum / Math.sqrt(lx * lx + ly * ly + bvSum * bvSum);
            var lLen = Math.sqrt(lx * lx + ly * ly + lz * lz);
            var ndl = lz / lLen;
            var fres = 0.04 + 0.96 * Math.pow(1 - ndl, 5);
            var spec =
              Math.min(1, Math.pow(ndh, 30) * 1.6 * (0.5 + fres)) * 0.55;
            var bloom = Math.min(1, Math.pow(ndh, 4) * 0.8) * 0.6;
            pageGlow.style.setProperty(
              "--bg-mx",
              ((mx / vw) * 100).toFixed(2) + "%",
            );
            pageGlow.style.setProperty(
              "--bg-my",
              ((my / vh) * 100).toFixed(2) + "%",
            );
            pageGlow.style.setProperty("--bg-spec", spec.toFixed(3));
            pageGlow.style.setProperty("--bg-bloom", bloom.toFixed(3));
          }
        }

        function distOutside(mx, my, r) {
          var ex = Math.max(
            Math.abs(mx - (r.left + r.width / 2)) - r.width / 2,
            0,
          );
          var ey = Math.max(
            Math.abs(my - (r.top + r.height / 2)) - r.height / 2,
            0,
          );
          return Math.sqrt(ex * ex + ey * ey);
        }

        var ticking = false,
          lastT = 0,
          lastX = 0,
          lastY = 0;
        var px = 0,
          py = 0,
          started = false;

        /** update(now) — เฟรมเดียวของการอินเตอร์โพเลตตำแหน่งเมาส์ (px,py → ตาม mouse ด้วย INERTIA_RATE)
         *  แล้ว applyLight ทุกการ์ดที่ visible + applyBgLights + ปรับเลนส์.
         *  วงรอบ: onMove เริ่ม rAF → ค้างจน mouse ขยับเกิน threshold จึงหยุด (ประหยัด CPU)
         */
        function update(now) {
          ticking = false;
          now = now || performance.now();
          var dt = lastT ? Math.min((now - lastT) / 1000, 0.05) : 0.016;
          lastT = now;
          var ease = 1 - Math.exp(-dt * INERTIA_RATE);
          px += (lastX - px) * ease;
          py += (lastY - py) * ease;
          if (rectsDirty) {
            measure();
            rectsDirty = false;
          }
          _frameMaxT = 0;
          for (var i = 0; i < entries.length; i++) {
            if (entries[i].visible) applyLight(entries[i], px, py);
          }
          applyBgLights(px, py);
          applyLens(_frameMaxT);
          if (Math.abs(lastX - px) > 0.3 || Math.abs(lastY - py) > 0.3) {
            ticking = true;
            requestAnimationFrame(update);
          }
        }

        InteractionEngine.onMove(function (mx, my) {
          lastX = mx;
          lastY = my;
          if (!started) {
            px = lastX;
            py = lastY;
            started = true;
          }
          if (!ticking) {
            ticking = true;
            lastT = performance.now();
            requestAnimationFrame(update);
          }
        });

        document.addEventListener("mouseout", function (e) {
          if (!e.relatedTarget) {
            entries.forEach(resetCard);
            px = lastX;
            py = lastY;
            started = false;
            if (dispEl && curScale !== 8) {
              curScale = 8;
              dispEl.setAttribute("scale", "8");
            }
          }
        });
      })();
    } catch (error) {
      if (window.console && console.error)
        console.error("[shop] glass engine skipped:", error);
    }
    /* ---- Background light ---- */
    var bgLight = document.createElement("div");
    bgLight.id = "bgLight";
    document.body.appendChild(bgLight);
  },
});
