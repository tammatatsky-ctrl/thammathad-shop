/* ===================================================================== */
/*  THAMMATHAD SHOP — FXAssets: DeferredRegister ของชุด effect            */
/*                                                                       */
/*  ตามหลัก NeoForge Registries:                                          */
/*  - register() = "ลงทะเบียน" ราคาถูก: เก็บ id + supplier (css/js/match)    */
/*    ที่ไหน ยังไม่โหลดไฟล์จริง — เหมือน DeferredHolder ที่ยังไม่ .get()       */
/*  - needed(scope) = "query หลัง registration จบ": scan DOM ว่าหน้านี้       */
/*    มี element ตรง match ไหน → คืนชุด effect ที่ "ถูกขอใช้" เท่านั้น         */
/*  - provide(ids) = "materialize": dynamic inject CSS+JS เฉพาะที่ถูกขอ     */
/*    รอโหลดครบ แล้วค่อยเรียก FX.boot() (ใน fx-boot.js)                     */
/*                                                                          */
/*  ประโยชน์: ฐานเทมเพลตโหลด effect แค่ไฟล์ที่หน้าใช้จริง (เฉพาะ hero/        */
/*  lab/liquid ถึงโหลด heavy effect) — หน้า staff ทั่วไป (customer_list/     */
/*  orders/...) โหลด ripple+magnetic+progress แทน 13 ไฟล์ที่เคยโหลดทุก     */
/*  หน้า → first paint + งานโหลดลดลงมาก                                     */
/*                                                                          */
/*  CSS ที่เป็น eager (อยู่ head basetemplate แล้ว — ห้าม inject ซ้ำ):       */
/*  fx-blur-up.css (รูปเบลอ→ชัด — ต้องมีก่อน first paint กัน FOUC),          */
/*  fx-reveal.css (ซ่อน [data-motion] ก่อน), fx-progress.css (แถบทุกหน้า).   */
/*  — effect ที่ eager เหล่านี้ใน registry จะตั้ง css: null ไว้                */
/*                                                                          */
/*  IMPORTANT — mapping กับ template ต้องตามนี้ (ถ้าเพิ่ม effect ใหม่      */
/*  ต้อง register เข้าตารางนี้ + เติม match ให้ตรง DOM ที่ใช้):            */
/*    glass→.hero-shell,  halo→.card/.apple-tile,  liquid→.liquid-mesh,     */
/*    morph→.card-expand,     */
/*    card-pop→[data-card-parallax],  blur-up→รูปสินค้า,                 */
/*    countup→[data-motion="countup"],                                  */
/*    magnetic→.btn-primary,  ripple/progress→always (ทุกหน้า)            */
/*  หมายเหตุ: drag/playground/parallax/scene ถูกถอดสมรรถนะแล้ว (ไม่มีผู้ใช้ใน   */
/*  template จริง — เก็บไฟล์ไว้ใน static เผื่อคืน แต่ไม่ถูก scan/inject)         */
/* ===================================================================== */
(function () {
    "use strict";
    if (window.FXAssets) return;

    /** registry กลาง: id → { id, css, js, match(Array|string|null), always(bool) } */
    var registry = {};
    /** กัน inject ซ้ำต่อ url (loaded flag สำหรับ css และ js แยก) */
    var loadedCss = {};
    var loadedJs = {};

    /** จริงไหมว่า DOM scope มี element ตรง selector (fail-soft ไม่ throw). */
    function has(scope, sel) {
        try {
            return !!(scope && sel && scope.querySelector(sel));
        } catch (e) {
            return false;
        }
    }
    /** effect นี้ "ถูกขอใช้" บนหน้านี้ไหม: always → เสมอ; match → ตัวใดตัวหนึ่งปรากฏ. */
    function isNeeded(cfg, scope) {
        if (cfg.always) return true;
        if (!cfg.match) return false;
        var sels = Object.prototype.toString.call(cfg.match) === "[object Array]"
            ? cfg.match
            : [cfg.match];
        for (var i = 0; i < sels.length; i++) {
            if (has(scope, sels[i])) return true;
        }
        return false;
    }

    /* ---- static base (ฉีดจาก basetemplate เป็น STATIC_URL + "css/effects/" —
            เปลี่ยน STATIC_URL ได้โดยไม่ต้องแก้ JS ตรงนี้;
            fallback ไว้สำหรับ dev ที่ไม่ได้ผ่าน template) ----
     * ตัด "?..." / "#..." ออกจาก path ฐาน — จำเป็นมาก
     * ถ้า base มี query ติดมา (เช่นถ้าวันหนึ่งใครเขียนกลับไปใช้
     * {% static 'css/effects/' %} ซึ่ง storage แบบ versioned จะเติม ?v=...
     * ต่อท้ายให้แม้ทั้งที่เป็นโฟลเดอร์) แล้วเอาไปต่อชื่อไฟล์
     * จะได้ URL พัง ".../effects/?v=2026...fx-glass.css" → 404 → effect ไม่โหลด */
    function stripQuery(url) {
        if (!url) return url;
        var i = url.search(/[?#]/);
        return i === -1 ? url : url.slice(0, i);
    }
    function baseCss() { return stripQuery(window.FX_CSS_BASE || "/static/css/effects/"); }
    function baseJs() { return stripQuery(window.FX_JS_BASE || "/static/js/effects/"); }

    /* ---- cache-busting สำหรับ URL ที่ "สร้างเองตอน runtime" ----
     *  URL ที่ inject ตรงนี้เกิดหลัง Django render เสร็จ จึงไม่ได้ผ่าน static
     *  storage ที่ใส่ ?v= ให้ (ดู myapp/static_storage.py) → ต้องต่อเอง
     *  ไม่งั้นหลัง deploy ใหม่ ผู้ใช้จะได้ effect เวอร์ชันเก่าจาก cache
     *  เวอร์ชันมาจาก window.FX_STATIC_V (basetemplate ฉีดจาก settings.STATIC_VERSION)
     *  ว่างไว้ (dev / ไม่ได้ตั้งค่า) = ไม่ต่อ query = พฤติกรรมเดิม */
    function stamp(url) {
        var v = window.FX_STATIC_V;
        if (!v || !url) return url;
        if (url.indexOf("?") !== -1) return url;          // มี query แล้ว — ไม่ยัด
        if (url.indexOf("http://") === 0 || url.indexOf("https://") === 0) return url;
        var hash = "";
        var hi = url.indexOf("#");
        if (hi !== -1) { hash = url.slice(hi); url = url.slice(0, hi); }
        return url + "?v=" + encodeURIComponent(v) + hash;
    }

    /** inject <link rel="stylesheet"> เดียว (ไม่รอ — decoration โหลดแค่ให้พร้อม)
     *  stamp() = แนบ ?v=<STATIC_VERSION> กัน browser cache (ดูคอมเมนต์ข้างบน) */
    function injectCss(url) {
        var key = stamp(url);
        if (loadedCss[key]) return;
        loadedCss[key] = 1;
        var l = document.createElement("link");
        l.rel = "stylesheet";
        l.href = key;
        l.onload = l.onerror = function () { };
        (document.head || document.documentElement).appendChild(l);
    }

    /** inject <script> เดียว + track ครบ/พังผ่าน done() (dynamic = async ตามเบราว์เซอร์). */
    function injectJs(url, done) {
        var key = stamp(url);
        if (loadedJs[key]) return done();
        loadedJs[key] = 1;
        var s = document.createElement("script");
        s.src = key;
        s.onload = s.onerror = function () {
            done();
        };
        document.body.appendChild(s);
    }

    var FXAssets = {
        /** DeferredRegister: register({id, css, js, match, always}) — แค่เก็บไว้ ไม่โหลด.
         *  @param {Object} cfg - id, css(ชื่อไฟล์|null), js(ชื่อไฟล์|null), match, always
         */
        register: function (cfg) {
            if (!cfg || !cfg.id) return;
            registry[cfg.id] = cfg;
        },
        /** คืน id ทั้งหมดที่ "ถูกขอใช้" บน scope นี้ — เรียกทีหลัง DOM พร้อมเท่านั้น
         *  (หลัก NeoForge: query registry ต้องหลัง registration เสร็จ)
         *  @param {HTMLElement} scope - จุด scan (ปกติ document.body)
         *  @returns {string[]} id ชุดที่ต้อง materialize
         */
        needed: function (scope) {
            var out = [];
            for (var k in registry) {
                if (registry.hasOwnProperty(k) && isNeeded(registry[k], scope)) out.push(k);
            }
            return out;
        },
        /** lookup config ของ effect ตัวเดียว (เผื่อ mod อื่นเรียกนานๆ).
         *  @param {string} id
         *  @returns {Object|undefined}
         */
        get: function (id) {
            return registry[id];
        },
        /** materialize ทั้งชุด: inject css (fire-and-forget) + js (รอทุกตัว load ครบ)
         *  แล้วเรียก done() — พัง/ไม่มีก็เดินหน้าต่อ กันตัวเดียวฉุดทั้งระบบ.
         *  @param {string[]} ids - จาก needed()
         *  @param {Function} done - callback เมื่อ js ทั้งหมดครบ (css ไม่บล็อก)
         */
        provide: function (ids, done) {
            var cssFiles = [], jsFiles = [];
            (ids || []).forEach(function (id) {
                var cfg = registry[id];
                if (!cfg) return;
                if (cfg.css) cssFiles.push(baseCss() + cfg.css);
                if (cfg.js) jsFiles.push(baseJs() + cfg.js);
            });
            /* CSS ไม่ต้องรอ: decoration จะค่อยๆ เสริมหลัง first paint */
            cssFiles.forEach(injectCss);
            var pending = jsFiles.length;
            if (!pending) { done && done(); return; }
            jsFiles.forEach(function (url) {
                injectJs(url, function () {
                    pending -= 1;
                    if (pending <= 0) done && done();
                });
            });
        },
    };

    /* ===================== ลงทะเบียน effect (ตารางเดียวกับ basetemplate) ===================== */
    FXAssets.register({ id: "ripple",    css: "fx-ripple.css",     js: "fx-ripple.js",     always: true });                        /* ปุ่ม/ลิงก์ทุกหน้า */
    FXAssets.register({ id: "magnetic",  css: null,                js: "fx-magnetic.js",   match: [".btn-primary"] });               /* start/button หลัก */
    FXAssets.register({ id: "progress",  css: "fx-progress.css",   js: "fx-progress.js",   always: true });                        /* แถบอ่านหน้า + mesh parallax */
    FXAssets.register({ id: "glass",     css: "fx-glass.css",      js: "fx-glass.js",      match: [".hero-shell", ".liquid-glass"] }); /* เลนส์ hero (index) */
    FXAssets.register({ id: "halo",      css: "fx-halo.css",       js: "fx-halo.js",       match: [".card", ".apple-tile", ".liquid-glass"] }); /* backlight การ์ด */
    FXAssets.register({ id: "liquid",    css: "fx-liquid.css",     js: "fx-liquid.js",     match: [".liquid-mesh"] });               /* ฟองสีแสง (index) */
    FXAssets.register({ id: "morph",     css: "fx-morph.css",      js: "fx-morph.js",      match: [".card-expand[data-expand]"] });    /* การ์ดขยาย modal (product_grid) */
    FXAssets.register({ id: "card-pop",  css: "fx-card-pop.css",   js: "fx-card-pop.js",   match: ["[data-card-parallax]"] });        /* center-pop การ์ด */
    FXAssets.register({ id: "blur-up",   css: null,                js: "fx-blur-up.js",    match: [".product-img", ".cart-thumb", ".product-detail-image", ".table-avatar", ".placeholder-avatar"] }); /* รูป blur→ชัด (css eager ใน head กัน FOUC — inject เฉพาะ js) */
    FXAssets.register({ id: "skeleton",  css: "fx-skeleton.css",   js: null,               match: [".skeleton-img"] });               /* skeleton placeholder (css-only) */
    FXAssets.register({ id: "countup",   css: null,                js: "fx-countup.js",    match: ['[data-motion="countup"]'] });      /* เลขวิ่ง (dashboard) */
    FXAssets.register({ id: "hero-expand", css: "fx-hero-expand.css", js: "fx-hero-expand.js", match: [".scroll-expand-stage"] });    /* Scroll Expansion Hero (21st.dev inspired) */

    window.FXAssets = FXAssets;
})();