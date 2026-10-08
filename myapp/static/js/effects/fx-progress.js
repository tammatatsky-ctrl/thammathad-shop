/* ===== FX MOD: progress (แถบความคืบหน้า) ===== */
/**
 * FX mod id: 'progress' — สร้าง #scrollProgress (แถบบอกตำแหน่งอ่านหน้า)
 * - เบราว์เซอร์มาตรฐาน (Chrome, Edge, Safari 18+): รองรับ Native CSS Scroll-Driven Animations
 *   (animation-timeline: scroll()) → ทำงานบน GPU Compositor Thread 100% ไม่ใช้ JS
 * - เบราว์เซอร์รุ่นเก่า: Fallback เป็น ScrollEngine subscriber หนึ่งเดียว แล้ว lerp ใน rAF
 * ctx ที่ใช้: ScrollEngine.subscribe().
 */
FX.register({
  id: "progress",
  boot: function (ctx) {
    /* ---- Progress bar (single rAF via ScrollEngine) ---- */
    var progress = document.createElement("div");
    progress.id = "scrollProgress";
    document.body.appendChild(progress);

    /* ตรวจสอบว่าเบราว์เซอร์รองรับ Native CSS Scroll-Driven Animations หรือไม่
       หากรองรับ CSS @supports (animation-timeline: scroll()) จะขับเคลื่อนแถบเองบน GPU Compositor
       จึงไม่ต้องผูก JS Scroll Listener เลยแม้แต่ตัวเดียว (Zero-JS Overhead) */
    if (window.CSS && CSS.supports && CSS.supports("animation-timeline", "scroll()")) {
      return;
    }

    var progTarget = 0,
      progCur = 0;
    ScrollEngine.subscribe(
      function (s) {
        progTarget = Math.max(
          0,
          Math.min(
            1,
            s.y /
              Math.max(
                1,
                document.documentElement.scrollHeight - window.innerHeight,
              ),
          ),
        );
      },
      FXBus.PRIORITY.HIGH,
    );
    var progRaf = null;
    /** tickProgress() — lerp ค่าปัจจุบันเข้าหาเป้าหมาย (progress 0..1)
     *  แล้วเขียน transform; หยุด rAF เมื่อเข้าใกล้เป้าแล้ว (กันวินาทีดินฟรี)
     */
    function tickProgress() {
      var progDone = Math.abs(progTarget - progCur) < 0.001;
      progCur = progDone ? progTarget : progCur + (progTarget - progCur) * 0.16;
      progress.style.transform = "scaleX(" + progCur.toFixed(4) + ")";
      if (progDone) progRaf = null;
      else progRaf = requestAnimationFrame(tickProgress);
    }
    ScrollEngine.subscribe(function () {
      if (!progRaf) progRaf = requestAnimationFrame(tickProgress);
    });
  },
});
