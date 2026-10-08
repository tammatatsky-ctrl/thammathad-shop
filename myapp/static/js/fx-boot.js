/* ===================================================================== */
/*  THAMMATHAD SHOP — fx-boot.js: materializer ของ FXAssets (Deferred)   */
/*                                                                       */
/*  เดิม: ไฟล์นี้แค่เรียก FX.boot() หลัง script effect โหลดครบ (ทุกหน้า)    */
/*  ตอนนี้: เป็น "จุด materialize" ตามหลัก NeoForge DeferredRegister —     */
/*  - รอ DOM พร้อม + รอให้ motion-core (FX loader) ลงทะเบียนเรียบร้อย     */
/*  - FXAssets.needed(body) = "query registry หลัง registration":         */
/*    ไล่ match ที่ DOM ว่าหน้านี้ใช้ effect ตัวไหน                         */
/*  - FXAssets.provide(ids) = dynamic inject CSS+JS เฉพาะตัวที่ใช้จริง     */
/*  - เมื่อ JS โหลดครบ → FX.boot() เรียก boot ของเฉพาะตัวที่ register      */
/*                                                                       */
/*  effect ที่หน้าไม่ใช้จะไม่ถูกโหลดเลย (หน้า staff ธรรมดาโหลด ~3 ตัว      */
/*  ที่ไม่ใช่ 13 ตัวเดิม) — CSS ที่จำเป็นก่อน first paint อยู่ที่ head      */
/*  (theme.css + fx-reveal.css + fx-progress.css) ไม่ใช่ของตรงนี้         */
/*  ===================================================================== */
(function () {
    "use strict";
    if (!window.FXAssets || !window.FX) return;

    /** กัน boot ซ้ำ (เช่น navigation กลับมาใน SPA-style) — boot ครั้งเดียวพอ. */
    if (window.__fxBootedOnce) return;
    window.__fxBootedOnce = 1;

    function run() {
        /* scan DOM ที่ render แล้ว — หลัง DOMContentLoaded หรือทันทีถ้า DOM พร้อมแล้ว */
        var ids = FXAssets.needed(document.body);
        FXAssets.provide(ids, function () {
            if (window.FX) FX.boot();
            /* countup-retry: hoist ของ EntryEngine (motion-core setTimeout 600) วิ่งก่อน
             * effect JS โหลด (fx-boot ทำงานหลัง DOMContentLoaded → defer) → actor ยังไม่มี
             * → callActor fail-soft + el.dataset.hoisted ถูกตั้ง → IO จะข้ามถาวร ตัวเลขไม่เคยวิ่ง.
             * จุดนี้ provide() รอ JS ทุกตัวโหลดครบ + boot เสร็จแล้ว → actor 'countup' มีแน่นอน
             * สำหรับ element ในจอตอนโหลด (ถ้า animation ยังไม่เริ่มเพราะความช้าของ race) — ยิงซ้ำ. */
            if (ids.indexOf("countup") !== -1 && window.FX) {
                var els = document.querySelectorAll('[data-motion="countup"]');
                var vh = window.innerHeight;
                Array.prototype.forEach.call(els, function (el) {
                    if (el.dataset.counted) return;
                    var r = el.getBoundingClientRect();
                    if (r.top <= vh && r.bottom >= 0) window.FX.callActor("countup", el);
                });
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", run);
    } else {
        run();
    }
})();