/* ===================================================================== */
/*  THAMMATHAD SHOP — FX MOD: hero-expand                                */
/*  Scroll Expansion Hero Controller                                     */
/*  Translates 21st.dev scroll expansion interaction into Apple Liquid   */
/*  Glass physics via ScrollEngine and pure GPU custom properties.       */
/* ===================================================================== */
FX.register({
  id: "hero-expand",
  boot: function (ctx) {
    var track = document.getElementById("heroExpandTrack") || document.querySelector(".scroll-expand-track");
    var stage = document.getElementById("heroExpandStage") || document.querySelector(".scroll-expand-stage");
    if (!track || !stage) return;

    var card = stage.querySelector(".expand-media-card");
    var promptBtn = stage.querySelector(".expand-scroll-prompt");

    var currentProgress = -1;

    /**
     * คำนวณความคืบหน้า (Progress 0.0 -> 1.0) จากระยะ Scroll ภายใน Track
     * ส่งต่อค่าผ่าน CSS Variable --expand-progress บน GPU Compositor
     */
    function updateProgress() {
      if (ctx.reduced()) {
        if (currentProgress !== 1) {
          stage.style.setProperty("--expand-progress", "1");
          currentProgress = 1;
        }
        return;
      }

      var rect = track.getBoundingClientRect();
      var trackHeight = track.offsetHeight;
      var winHeight = window.innerHeight;
      var scrollDistance = trackHeight - winHeight;

      if (scrollDistance <= 0) {
        stage.style.setProperty("--expand-progress", "1");
        return;
      }

      var scrolled = -rect.top;
      var progress = Math.max(0, Math.min(1, scrolled / scrollDistance));

      // Precision clamp เพื่อไม่ให้ re-render ค่าเดิมซ้ำ
      if (Math.abs(progress - currentProgress) > 0.001) {
        currentProgress = progress;
        stage.style.setProperty("--expand-progress", progress.toFixed(4));
      }
    }

    // ผูกเข้ากับ ScrollEngine ตัวหลักของระบบ (single rAF listener)
    if (ctx.scroll) {
      ctx.scroll(function () {
        updateProgress();
      });
    } else {
      window.addEventListener("scroll", updateProgress, { passive: true });
    }

    // อัปเดตเมื่อปรับขนาดหน้าจอ
    window.addEventListener("resize", function () {
      updateProgress();
    }, { passive: true });

    // ตอบสนองต่อปุ่มเปิด/ปิดอนิเมชั่น (⚡ #motionToggle)
    if (ctx.onToggle) {
      ctx.onToggle(function () {
        updateProgress();
      });
    }

    // คลิกที่ปุ่ม Prompt "เลื่อนลงเพื่อขยาย" เพื่อเลื่อนผ่าน Hero อย่างนุ่มนวล
    if (promptBtn) {
      promptBtn.addEventListener("click", function () {
        var targetY = track.offsetTop + track.offsetHeight - window.innerHeight + 16;
        window.scrollTo({
          top: targetY,
          behavior: "smooth",
        });
      });
    }

    // Interactive Specular Lens Reflection บนการ์ดแก้ว
    if (card) {
      card.addEventListener("mousemove", function (e) {
        var r = card.getBoundingClientRect();
        var mx = ((e.clientX - r.left) / r.width) * 100;
        var my = ((e.clientY - r.top) / r.height) * 100;
        card.style.setProperty("--mouse-x", mx.toFixed(1) + "%");
        card.style.setProperty("--mouse-y", my.toFixed(1) + "%");
        card.style.setProperty("--spec-o", "1");
        card.style.setProperty("--bloom-o", "0.85");
      }, { passive: true });

      card.addEventListener("mouseleave", function () {
        card.style.setProperty("--spec-o", "0.3");
        card.style.setProperty("--bloom-o", "0.2");
      }, { passive: true });
    }

    // เรียกประมวลผลทันทีเมื่อโหลดเสร็จ
    updateProgress();
  },
});
