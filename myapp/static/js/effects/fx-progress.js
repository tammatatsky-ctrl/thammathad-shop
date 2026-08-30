/* ===== FX MOD: progress (แถบความคืบหน้า + parallax mesh) ===== */
/**
 * FX mod id: 'progress' — สร้าง #scrollProgress (แถบบอกตำแหน่งอ่านหน้า) + ขยับ .liquid-mesh
 * (พื้น hero) แบบ parallax เล็กน้อยตาม scroll — ทั้งคู่ใช้ ScrollEngine subscriber หนึ่งเดียว
 * แล้วค่อยๆ lerp ใน rAF (tickProgress) กันกระตุก.
 * ctx ที่ใช้: ScrollEngine.subscribe(), Motion.reduced() (mesh หยุดขยับเมื่อปิดระบบ).
 */
FX.register({
  id: "progress",
  boot: function (ctx) {
    /* ---- Progress bar + hero parallax mesh (single rAF via ScrollEngine) ---- */
    var progress = document.createElement("div");
    progress.id = "scrollProgress";
    document.body.appendChild(progress);
    var progTarget = 0,
      progCur = 0;
    var heroMesh = document.querySelector(".liquid-mesh");
    var heroShell = document.querySelector(".hero-shell");
    var paraTarget = 0,
      paraCur = 0;
    var lastSY = 0;
    ScrollEngine.subscribe(function (s) {
      var y = s.y;
      progTarget = Math.max(
        0,
        Math.min(
          1,
          y /
            Math.max(
              1,
              document.documentElement.scrollHeight - window.innerHeight,
            ),
        ),
      );
      if (heroMesh && heroShell) {
        var hr = heroShell.getBoundingClientRect();
        paraTarget =
          hr.bottom > 0 ? Math.max(-60, Math.min(60, hr.top * -0.08)) : 0;
      }
      lastSY = y;
    });
    var progRaf = null;
    /** tickProgress() — lerp ค่าปัจจุบันเข้าหาเป้าหมาย (progress 0..1 + mesh offset)
     *  แล้วเขียน transform; หยุด rAF เมื่อเข้าใกล้เป้าแล้ว (กันวินาทีดินฟรี)
     */
    function tickProgress() {
      var progDone = Math.abs(progTarget - progCur) < 0.001;
      var paraDone = Math.abs(paraTarget - paraCur) < 0.1;
      progCur = progDone ? progTarget : progCur + (progTarget - progCur) * 0.16;
      paraCur = paraDone ? paraTarget : paraCur + (paraTarget - paraCur) * 0.12;
      progress.style.transform = "scaleX(" + progCur.toFixed(4) + ")";
      if (heroMesh && !Motion.reduced())
        heroMesh.style.transform =
          "translate3d(0," + paraCur.toFixed(2) + "px, 0)";
      if (progDone && paraDone) progRaf = null;
      else progRaf = requestAnimationFrame(tickProgress);
    }
    ScrollEngine.subscribe(function () {
      if (!progRaf) progRaf = requestAnimationFrame(tickProgress);
    });
  },
});
