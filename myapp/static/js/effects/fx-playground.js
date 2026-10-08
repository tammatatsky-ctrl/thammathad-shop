/* ===== FX MOD: playground (Glass Lab — ลากแสงผ่านผิวแก้ว) ===== */
/**
 * FX mod id: 'playground' — Light-Drag Glass Lab: พื้นที่ที่ผู้ใช้ลากเมาส์/นิ้วเพื่อ
 * เลื่อน "แหล่งแสง" เดียวข้ามผิวแก้ว แสงที่ --lx/--ly ไหลผ่าน CSS var ลงการ์ดทุกใบ
 * (.lab-glass) พร้อมกัน → รู้สึกเหมือนส่องไฟฉายบนจอแก้ว.
 *
 * หลัก: ลาก pointer (press + move) บน .lab-stage → อัปเดต --lx/--ly (% ของ stage)
 * บน .lab-shell (host) ให้ CSS (fx-playground.css) วาด aurora/light/rim ตาม.
 * รองรับ touch ด้วย pointer events + setPointerCapture.
 *
 * ทำให้ "โต้ตอบ" ซ้ำได้ตลอด: เมื่อเริ่มลาก เปิด .lab-active (CSS เน้นแสง + ไฮไลต์),
 * เมื่อปล่อย เอา .lab-active ออก (แต่แสงยังค้างตำแหน่งสุดท้าย — ไม่กลับที่เดิม).
 *
 * ⚡ off (Motion.reduced()): ลดความเข้มของแสงลงนิด (ยังโต้ตอบได้—เป็น interaction
 * ของ user ไม่ใช่ animation อัตโนมัติ) แต่ไม่รัน rAF ต่อเนื่องตอนไม่ได้ลาก.
 *
 * ctx ที่ใช้: ctx.reduced() (คุมความเข้ม/loop), ctx.onToggle — สถาปัตยกรรม FX เดียว.
 */
FX.register({
  id: "playground",
  boot: function (ctx) {
    var shell = document.querySelector(".lab-shell");
    if (!shell) return; // หน้าไม่มี playground → ข้าม

    var stage = shell.querySelector(".lab-stage");
    var dragging = false;

    function setLight(x, y) {
      /* x,y = client coords → % ของ shell */
      var r = shell.getBoundingClientRect();
      if (!r.width || !r.height) return;
      var lx = Math.max(0, Math.min(100, ((x - r.left) / r.width) * 100));
      var ly = Math.max(0, Math.min(100, ((y - r.top) / r.height) * 100));
      shell.style.setProperty("--lx", lx.toFixed(1) + "%");
      shell.style.setProperty("--ly", ly.toFixed(1) + "%");
    }

    /* ตั้งแสงเริ่มกลางหน้า */
    setLight(window.innerWidth / 2, 260);

    /* ผูก pointerdown ที่ .lab-shell (container ใหญ่) ไม่ใช่ .lab-stage เพราะการ์ด
       .lab-cards มี z-index สูงกว่าทับ stage → เดิมลากบนการ์ด pointer ไปโดนการ์ด
       ไม่โดน stage = startDrag ไม่ถูกเรียก แสงไม่ขยับเมื่อลากบนการ์ด/พื้นที่ส่วนใหญ่.
       ย้ายขึ้นมาที่ shell + ใช้ capture ขยับได้ทุกจุดในกล่อง. */
    function startDrag(e) {
      dragging = true;
      shell.setPointerCapture && shell.setPointerCapture(e.pointerId);
      shell.classList.add("lab-active");
      setLight(e.clientX, e.clientY);
      e.preventDefault(); // กัน text select บน desktop
    }
    function move(e) {
      if (!dragging) return;
      setLight(e.clientX, e.clientY);
    }
    function endDrag() {
      dragging = false;
      shell.classList.remove("lab-active");
    }

    shell.addEventListener("pointerdown", startDrag, { passive: false });
    window.addEventListener("pointermove", move, { passive: false });
    window.addEventListener("pointerup", endDrag);
    window.addEventListener("pointercancel", endDrag);
    shell.addEventListener("lostpointercapture", endDrag);

    /* รองรับกรณี pointerdown เกิดซ้ำ (touch) — กัน double */
    function onUpAll() { dragging = false; }
    window.addEventListener("pointerup", onUpAll);

    /* ---- motion gate: off → ความเข้มแสง/aurora ลดลง (โค้ดประกาศไว้เผื่อ layer CSS
       ใช้ class นี้ปรับ แต่ interaction ยังทำงาน) ---- */
    ctx.onToggle(function (enabled) {
      shell.classList.toggle("lab-motion-off", !enabled);
    });
  },
});
