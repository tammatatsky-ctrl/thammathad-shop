/* ============================================================================ */
/*  THAMMATHAD SHOP — Motion Core + FX Loader  (สถาปัตยกรรม mod-loader)          */
/*                                                                            */
/*  ไฟล์นี้ = "แกนระบบ" ที่โหลดก่อนเสมอ ไม่บรรจุเอฟเฟกต์ติดมาด้วย:                */
/*  - Motion           : ตัวเดียวที่จัดการ "เปิด/ปิดอนิเมชั่น" ด้วยปุ่ม ⚡ (จุด broadcast) */
/*  - FX loader        : Registry ให้ mod register() — โมเดล "loader + mods"      */
/*  - ScrollEngine     : 1 scroll listener + rAF → แจก scroll state ให้ทุก subscriber */
/*  - EntryEngine      : 1 IntersectionObserver → จัดการ reveal/stagger/countup   */
/*  - InteractionEngine: 1 mousemove + rAF → แจกพิกัดเมาส์                        */
/*  เอฟเฟกต์อยู่ที่ js/effects/fx-*.js — register ผ่าน FX.register({id, boot(ctx)}) */
/*  แล้ว FX.boot() (ท้าย basetemplate) เรียก boot ทุก mod แยก try ป้องกันตัวพัง    */
/*  สำคัญ: ห้ามผูก OS prefers-reduced-motion — มีปุ่ม ⚡ เท่านั้นคุมสถานะ            */
/* ============================================================================ */

/* ==================== 1. MOTION CONFIG ==================== */
/**
 * Motion — จุดเดียวที่รู้สถานะเปิด/ปิดอนิเมชั่นของทั้งเว็บ (ปุ่ม ⚡ #motionToggle).
 *
 * - enabled เก็บใน localStorage('thammathad-motion') + ฉายลง html[data-motion="on|off"]
 * - mod/engine ลงทะเบียน listener ผ่าน Motion.on(fn) → โทเกิลจะเรียกทุกตัว
 *   (จุด broadcast เดียว; fx-parallax/fx-card-pop ใช้ผ่าน ctx.onToggle)
 * - HARD RULE: ห้ามผูก `prefers-reduced-motion` ของ OS (AGENTS.md recipe #3)
 */
var Motion = {
    ease: {
        apple: "cubic-bezier(0.28,0.11,0.32,1)",
        spring: "cubic-bezier(0.34,1.56,0.64,1)",
        out: "cubic-bezier(0.16,1,0.3,1)",
    },
    duration: { fast: 200, normal: 350, slow: 600, entrance: 900 },
    enabled: true,
    /** @type {Function[]} listeners — เรียกหมดทุกครั้งที่ toggle (รับ (enabled)) */
    _listeners: [],
    /** ลงทะเบียน listener ตอบสนองปุ่ม ⚡ — ถูกเรียกด้วย (enabled: boolean) เมื่อ toggle.
     *  @param {Function} fn callback
     */
    on: function (fn) {
        if (typeof fn === "function") this._listeners.push(fn);
    },
    /** โหลดสถานะจาก localStorage + ฉายลง html[data-motion] (เรียกครั้งเดียวตอนเริ่ม).
     *  default = ON เสมอ — ผู้ใช้ที่ไม่เคยกดปุ่ม/ค่าเสียหายจะได้ animation เต็ม.
     */
    init: function () {
        var saved = null;
        try {
            saved = localStorage.getItem("thammathad-motion");
        } catch (e) { }
        if (saved === "off") this.enabled = false;
        else this.enabled = true;
        document.documentElement.dataset.motion = this.enabled ? "on" : "off";
    },
    /** สลับเปิด/ปิด + อัปเดต aria/ปุ่ม + toast + broadcast ไป listener ทั้งหมด.
     *
     *  ตอน "เปิดกลับ" (enabled) — เหมือน rerun เอฟเฟกต์ entry ที่ค้างไว้:
     *  - ลบ .in จาก reveal/stagger → recalc เฉพาะที่อยู่ในจอ ให้เล่นซ้ำทันที
     *  - element ที่ยังอยู่ใต้จอ → ส่งกลับเข้า EntryEngine._obs.observe ใหม่ (เล่นเมื่อเลื่อนถึง)
     *    (ต้องใช้ _obs ของ EntryEngine — this._obs ไม่เคยถูกตั้ง = บั๊ก reveal ค้างที่เคยเจอ)
     *  - countup: เคลียร์ dataset.hoisted/counted → ตัวในจอ FX.callActor เล่นซ้ำทันที,
     *    ตัวใต้จอ observe แล้วให้ IO เป็นคนเรียกเล่น
     */
    toggle: function () {
        this.enabled = !this.enabled;
        document.documentElement.dataset.motion = this.enabled ? "on" : "off";
        try {
            localStorage.setItem("thammathad-motion", this.enabled ? "on" : "off");
        } catch (e) { }
        var btn = document.getElementById("motionToggle");
        if (btn) {
            btn.setAttribute("aria-checked", this.enabled ? "true" : "false");
            btn.setAttribute(
                "aria-label",
                this.enabled ? "ปิดอนิเมชั่น" : "เปิดอนิเมชั่น",
            );
            btn.setAttribute(
                "title",
                this.enabled ? "ปิดอนิเมชั่น" : "เปิดอนิเมชั่น",
            );
        }
        if (this.enabled) {
            var els = document.querySelectorAll(
                '[data-motion="reveal"], [data-motion="stagger"]',
            );
            var counts = document.querySelectorAll('[data-motion="countup"]');
            els.forEach(function (el) {
                el.classList.remove("in");
            });
            counts.forEach(function (el) {
                delete el.dataset.hoisted;
                delete el.dataset.counted;
            });
            this._reflow = document.body.offsetHeight;
            requestAnimationFrame(function () {
                var lim = window.innerHeight - 40;
                els.forEach(function (el) {
                    var b = el.getBoundingClientRect();
                    if (b.top < lim && b.bottom > 0) el.classList.add("in");
                    else if (EntryEngine._obs) EntryEngine._obs.observe(el);
                    else el.classList.add("in");
                });
                counts.forEach(function (el) {
                    var b = el.getBoundingClientRect();
                    if (b.top < lim && b.bottom > 0) {
                        el.dataset.hoisted = "1";
                        FX.callActor("countup", el);
                    } else if (EntryEngine._obs) EntryEngine._obs.observe(el);
                });
            });
            for (var i = 0; i < this._listeners.length; i++) {
                try {
                    this._listeners[i](this.enabled);
                } catch (e) { }
            }
        }
        var stack = document.getElementById("islandStack");
        if (stack) {
            var toast = document.createElement("div");
            toast.className = "island-toast";
            toast.setAttribute("data-level", "success");
            toast.setAttribute("role", "status");
            toast.innerHTML =
                '<span class="island-icon"><i class="bi bi-' +
                (this.enabled ? "play-circle-fill" : "pause-circle-fill") +
                '"></i></span>' +
                '<span class="island-text">' +
                (this.enabled ? "เปิดอนิเมชั่นแล้ว" : "ปิดอนิเมชั่นแล้ว") +
                "</span>";
            stack.appendChild(toast);
            setTimeout(function () {
                toast.classList.add("show");
            }, 10);
            setTimeout(function () {
                toast.classList.remove("show");
                toast.classList.add("hide");
                setTimeout(function () {
                    if (toast.parentNode) toast.parentNode.removeChild(toast);
                }, 550);
            }, 3000);
        }
    },
    /** ตัวเดียวที่ใช้ตรวจ "ปิดอนิเมชั่น" ทั้งระบบ (แทน matchMedia ของ OS).
     *  @returns {boolean} true = ปิดอยู่ (เอฟเฟกต์ข้าม animation ได้)
     */
    reduced: function () {
        return !this.enabled;
    },
};
Motion.init();

/* ==================== FX: MOD LOADER ==================== */
/*  เอฟเฟกต์ (js/effects/fx-*.js) โหลดตามหลัง แล้วมาลงทะเบียนผ่าน FX.register({id, boot})
    boot ทำงานหลัง script เอฟเฟกต์โหลดครบ (FX.boot() อยู่ท้าย basetemplate) โดยแยก try ต่อ mod
    เพื่อให้ mod ที่พังไม่ฉุด core หรือ mod อื่นล้มตาม                                      */
/**
 * FX — Registry/Dispatcher ของเอฟเฟกต์ (โมเดล "loader + mods")
 * mod ลงทะเบียน = FX.register({id, boot(ctx)}) → เมื่อโหลดครบ FX.boot() เรียก boot
 * ของทุก mod พร้อม ctx ที่แจกเครื่องมือ core มาให้ (Motion/scroll/move/onToggle)
 * อีกช่อง = actor registry: FX.actor('countup', fn) → เรียกผ่าน FX.callActor(type, el)
 */
var FX = {
    _mods: {},
    _actors: {},
    _order: [],
    api: {},
    /** ลงทะเบียน mod เข้า loader (ถ้า id ซ้ำจะทับ path เดิมใน _order). */
    register: function (mod) {
        if (!mod || !mod.id) return;
        this._mods[mod.id] = mod;
        this._order.push(mod.id);
    },
    /** เริ่ม boot ทุก mod ตามลำดับ register — แยก try/catch: ตัวพังไม่ฉุดตัวอื่น. */
    boot: function () {
        for (var i = 0; i < this._order.length; i++) {
            var mod = this._mods[this._order[i]];
            try {
                if (mod.boot) mod.boot(this.ctx());
            } catch (e) {
                if (window.console && console.error)
                    console.error("[fx] " + this._order[i] + " boot failed:", e);
            }
        }
    },
    /** เตรียม "ชุดเครื่องมือ" ให้ mod (ctx) — สร้างใหม่ทุก boot กัน state ตัวตรวจข้าม boot. */
    ctx: function () {
        return {
            Motion: Motion,
            reduced: function () {
                return Motion.reduced();
            },
            scroll: function (fn) {
                return ScrollEngine.subscribe(fn);
            },
            move: function (fn) {
                return InteractionEngine.onMove(fn);
            },
            offMove: function (fn) {
                InteractionEngine.offMove(fn);
            },
            onToggle: function (fn) {
                Motion.on(fn);
            },
        };
    },
    /** ลงทะเบียน actor (ฟังก์ชันรับ element) ภายใต้ type — เช่น 'countup'.
     *  @param {string} type ชื่อ actor
     *  @param {Function} fn ฟังก์ชันที่จะถูกเรียกด้วย element
     */
    actor: function (type, fn) {
        this._actors[type] = fn;
    },
    /** เรียก actor ตาม type (ถ้ามี) กับ element ที่ให้ — fail-soft (ไม่ throw). */
    callActor: function (type, el) {
        var fn = this._actors[type];
        if (fn) {
            try {
                fn(el);
            } catch (e) { }
        }
    },
};

/* ==================== 2. SCROLL ENGINE ==================== */
/**
 * ScrollEngine — scroll listener ตัวเดียว + rAF → ส่ง "สถานะ scroll ล่าสุด" ให้ทุก subscriber.
 * (เดิมแต่ละเอฟเฟกต์ผูก window scroll เอง = หลาย listener → change เป็น architecture นี้)
 */
var ScrollEngine = {
    y: 0,
    prevY: 0,
    direction: "down",
    velocity: 0,
    _subs: [],
    _ticking: false,
    /** ลงทะเบียน subscriber — ถูกเรียกทุกเฟรมที่ scroll ด้วย object สถานะ (.y/.direction/.velocity). */
    subscribe: function (fn) {
        this._subs.push(fn);
    },
    /** (internal) เรียก subscriber ทั้งหมดในเฟรม — เก็บค่าใหม่ก่อน broadcast. */
    _flush: function () {
        this._ticking = false;
        var y = window.scrollY;
        this.direction = y > this.prevY ? "down" : "up";
        this.velocity = Math.abs(y - this.prevY);
        this.y = y;
        for (var i = 0; i < this._subs.length; i++) this._subs[i](this);
    },
    schedule: function () {
        if (!this._ticking) {
            this._ticking = true;
            var self = this;
            requestAnimationFrame(function () {
                self._flush();
            });
        }
    },
};
window.addEventListener(
    "scroll",
    function () {
        ScrollEngine.schedule();
    },
    { passive: true },
);

/* ==================== 3. ENTRY ENGINE ==================== */
/**
 * EntryEngine — IntersectionObserver ตัวเดียวของระบบ ปลุกเอฟเฟกต์ entry (reveal/stagger/countup)
 * เมื่อ element เข้าจอ (threshold 15% + ขอบล่างหัก 40px).
 * dispatch ตาม data-motion: reveal → ใส่ .in; stagger → ตั้ง --d ไล่ลูก; countup → FX.callActor.
 */
var EntryEngine = {
    /** observer ตัวจริงของระบบ — Motion.toggle ก็นำ observe ใหม่ตอนเปิดกลับด้วย (อย่าไปสร้างเองที่อื่น) */
    _obs: null,
    /** ตั้ง observer หนึ่งตัว + สังเกต element เป้าหมายทั้งหมด (เรียกครั้งเดียวหลัง hoist รอบแรก). */
    init: function () {
        var self = this;
        if (!("IntersectionObserver" in window)) {
            self._revealAll();
            return;
        }
        this._obs = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (en) {
                    if (!en.isIntersecting) return;
                    var el = en.target,
                        type = el.dataset.motion;
                    if (Motion.reduced()) {
                        el.classList.add("in");
                        if (type !== "countup") {
                            self._obs.unobserve(el);
                        }
                        return;
                    }
                    if (type === "reveal") {
                        el.classList.add("in");
                        el.style.willChange = "auto";
                    } else if (type === "stagger") {
                        var kids = el.children;
                        for (var i = 0; i < kids.length; i++)
                            kids[i].style.setProperty("--d", i * 110 + "ms");
                        el.classList.add("in");
                    } else if (type === "countup" && !el.dataset.hoisted)
                        FX.callActor("countup", el);
                    self._obs.unobserve(el);
                });
            },
            { threshold: 0.15, rootMargin: "0px 0px -40px 0px" },
        );
        document
            .querySelectorAll(
                '[data-motion="reveal"], [data-motion="stagger"], [data-motion="countup"]',
            )
            .forEach(function (el) {
                self._obs.observe(el);
            });
    },
    /** (fallback) ไม่มี IntersectionObserver → โชว์ reveal/stagger ทั้งหมดทันที (ไม่มี animation). */
    _revealAll: function () {
        document
            .querySelectorAll('[data-motion="reveal"], [data-motion="stagger"]')
            .forEach(function (el) {
                el.classList.add("in");
            });
    },
    /** สังเกต element entry ซ้ำใหม่ (ใช้เมื่อ DOM เปลี่ยน/โหลดเนื้อหาเพิ่ม แล้วอยากให้เล่นอีก).
     *  Note: IO จะไม่เล่นซ้ำ element ที่ยังมี .in/.hoisted อยู่ — ถ้าต้องการรีแอนิเมทให้ลบก่อน.
     */
    refresh: function () {
        var self = this;
        document
            .querySelectorAll(
                '[data-motion="reveal"], [data-motion="stagger"], [data-motion="countup"]',
            )
            .forEach(function (el) {
                if (self._obs) self._obs.observe(el);
            });
    },
};

/* ==================== 4. INTERACTION ENGINE ==================== */
/**
 * InteractionEngine — mousemove listener 1 ตัว + rAF → ส่งพิกัด (mouseX, mouseY) ให้ handler
 * ที่ลงทะเบียน. ใช้ในเอฟเฟกต์แบบ mouse-follow (glass light, morph tilt) — อย่าลืม offMove กัน leak.
 */
var InteractionEngine = {
    mouseX: 0,
    mouseY: 0,
    _ticking: false,
    _moveHandlers: [],
    /** ลงทะเบียน handler รับ (mouseX, mouseY) — ต้อง offMove เองเมื่อเลิกใช้.
     *  @param {Function} fn - รับพิกัดเมาส์ 2 args
     *  @returns {Function} ตัว fn เดิม (เผื่ออยาก offMove ภายหลัง)
     */
    onMove: function (fn) {
        this._moveHandlers.push(fn);
        return fn;
    },
    /** เลิกส่งค่าให้ handler นี้ (ถอดออกจากรายการ). */
    offMove: function (fn) {
        var i = this._moveHandlers.indexOf(fn);
        if (i >= 0) this._moveHandlers.splice(i, 1);
    },
    /** ผูก mousemove ระดับ document หนึ่งครั้ง (passive) → กัน handler ท่วม. */
    init: function () {
        var self = this;
        document.addEventListener(
            "mousemove",
            function (e) {
                self.mouseX = e.clientX;
                self.mouseY = e.clientY;
                if (!self._ticking) {
                    self._ticking = true;
                    requestAnimationFrame(function () {
                        self._flush();
                    });
                }
            },
            { passive: true },
        );
    },
    _flush: function () {
        this._ticking = false;
        for (var i = 0; i < this._moveHandlers.length; i++) {
            this._moveHandlers[i](this.mouseX, this.mouseY);
        }
    },
};
InteractionEngine.init();

/* ---- spring() primitive: damped spring physics ---- */
/**
 * spring() — คำนวณ bounce ด้วยฟิสิกส์สปริงแบบ damped (เดิมใช้กับ hero/countup effect)
 * เหลือไว้เป็น primitive ให้ mod นำไปใช้ได้ (ยังไม่มี caller — คงไว้โดยตั้งใจ).
 *
 * @param {Object} [opts]
 * @param {number} [opts.from=0] ค่าเริ่มต้น
 * @param {number} [opts.to=1] ค่าเป้าหมาย
 * @param {number} [opts.stiffness=180] ความแข็งสปริง
 * @param {number} [opts.damping=12] แรงคุมการสั่น (มาก = หยุดเร็ว)
 * @param {number} [opts.mass=1] มวล (มาก = ดูช้า/หนืด)
 * @param {number} [opts.precision=0.01] เกณฑ์หยุดการสั่น
 * @param {Function} [opts.onUpdate] เรียกทุกเฟรมด้วยค่าปัจจุบัน
 * @param {Function} [opts.onComplete] เรียกเมื่อจบ
 * @returns {{stop: Function, set: Function}} ตัวควบคุม animation (stop=หยุดทันที, set=เปลี่ยนเป้า)
 */
function spring(opts) {
    opts = opts || {};
    var from = opts.from || 0,
        to = opts.to || 1;
    var stiffness = opts.stiffness || 180,
        damping = opts.damping || 12,
        mass = opts.mass || 1;
    var precision = opts.precision || 0.01;
    var onUpdate = opts.onUpdate || function () { },
        onComplete = opts.onComplete || function () { };
    var v = 0,
        x = from,
        t0 = null;
    var running = true;
    function step(ts) {
        if (!running) return;
        if (!t0) t0 = ts;
        var dt = Math.min((ts - t0) / 1000, 0.064);
        t0 = ts;
        var displacement = x - to;
        var springForce = -stiffness * displacement;
        var dampingForce = -damping * v;
        var acceleration = (springForce + dampingForce) / mass;
        v += acceleration * dt;
        x += v * dt;
        onUpdate(x);
        if (Math.abs(v) < precision && Math.abs(x - to) < precision) {
            running = false;
            onUpdate(to);
            onComplete();
            return;
        }
        requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
    return {
        stop: function () {
            running = false;
        },
        set: function (newTo) {
            to = newTo;
        },
    };
}

/* ==================== 7. CORE UX — registered with engines ==================== */
/*  พฤติกรรม UI หลักของเทมเพลตทั้งระบบ (ไม่ใช่เอฟเฟกต์): hoist entry, navbar scrolled,
    theme toggle, motion toggle, island modal, auto-dismiss, back-top, copy chips,
    slip OCR, pay highlight — ทั้งหมดใน try เดียว อันไหนพังไม่พังตัวระบบ             */
try {
    (function () {
        "use strict";
        requestAnimationFrame(function () {
            document.body.classList.add("loaded");
        });

        /* ---- Body load fade-in ---- */
        setTimeout(function () {
            /* hoist: เอฟเฟกต์ entry ที่อยู่ในจอตอนโหลดครั้งแรก เริ่มได้ทันทีไม่ต้องรอ scroll */
            if (!Motion.reduced()) {
                var hoist = document.querySelectorAll(
                    '[data-motion="reveal"], [data-motion="stagger"], [data-motion="countup"]',
                );
                var vh = window.innerHeight;
                hoist.forEach(function (el) {
                    var r = el.getBoundingClientRect();
                    if (r.top > vh || r.bottom <= 0) return;
                    var t = el.getAttribute("data-motion");
                    if (t === "reveal") {
                        el.classList.add("in");
                        el.style.willChange = "auto";
                    } else if (t === "stagger") {
                        var kids = el.children;
                        for (var k = 0; k < kids.length; k++)
                            kids[k].style.setProperty("--d", k * 110 + "ms");
                        el.classList.add("in");
                    } else if (t === "countup") {
                        el.dataset.hoisted = "1";
                        FX.callActor("countup", el);
                    }
                });
            }
            EntryEngine.init();
        }, 600);

        /* ---- Navbar scrolled state ---- */
        var navbar = document.getElementById("navbar");
        ScrollEngine.subscribe(function (s) {
            if (navbar) navbar.classList.toggle("scrolled", s.y > 20);
            if (navbar) navbar.classList.remove("nav-hidden");
        });

        /* ---- Theme toggle ---- */
        var root = document.documentElement;
        var themeToggle = document.getElementById("themeToggle");
        function syncThemeToggle() {
            if (!themeToggle) return;
            var dark = root.dataset.theme === "dark";
            themeToggle.setAttribute("aria-checked", dark ? "true" : "false");
            themeToggle.setAttribute("aria-pressed", dark ? "true" : "false");
            themeToggle.setAttribute(
                "aria-label",
                dark ? "เปลี่ยนเป็นโหมดสว่าง" : "เปลี่ยนเป็นโหมดมืด",
            );
            themeToggle.setAttribute(
                "title",
                dark ? "เปลี่ยนเป็นโหมดสว่าง" : "เปลี่ยนเป็นโหมดมืด",
            );
        }
        syncThemeToggle();
        if (themeToggle) {
            themeToggle.addEventListener("click", function () {
                var next = root.dataset.theme === "dark" ? "light" : "dark";
                var applyTheme = function () {
                    root.dataset.theme = next;
                    try {
                        localStorage.setItem("thammathad-theme", next);
                    } catch (e) { }
                    syncThemeToggle();
                };
                if (document.startViewTransition)
                    document.startViewTransition(applyTheme);
                else applyTheme();
            });
        }

        /* ---- Motion toggle ---- */
        var motionToggle = document.getElementById("motionToggle");
        if (motionToggle) {
            motionToggle.setAttribute(
                "aria-checked",
                Motion.enabled ? "true" : "false",
            );
            motionToggle.setAttribute(
                "aria-label",
                Motion.enabled ? "ปิดอนิเมชั่น" : "เปิดอนิเมชั่น",
            );
            motionToggle.setAttribute(
                "title",
                Motion.enabled ? "ปิดอนิเมชั่น" : "เปิดอนิเมชั่น",
            );
            motionToggle.addEventListener("click", function () {
                Motion.toggle();
            });
        }

        /* ---- Navbar press effect ---- */
        document
            .querySelectorAll(".navbar .nav-link, .navbar .navbar-brand")
            .forEach(function (el) {
                el.addEventListener("mousedown", function () {
                    el.style.transform = "scale(0.97)";
                    el.style.transition = "transform .15s var(--ease-apple)";
                });
                el.addEventListener("mouseup", function () {
                    el.style.transform = "";
                });
                el.addEventListener("mouseleave", function () {
                    el.style.transform = "";
                });
            });

        /* ---- Auto-dismiss alerts ---- */
        document.querySelectorAll("[data-auto-dismiss]").forEach(function (al) {
            setTimeout(function () {
                al.classList.add("alert-out");
                setTimeout(function () {
                    if (al.parentNode) al.parentNode.removeChild(al);
                }, 400);
            }, 5000);
        });

        /* ---- Dynamic Island Toast ---- */
        var stack = document.getElementById("islandStack");
        if (stack) {
            var toasts = stack.querySelectorAll(".island-toast");
            toasts.forEach(function (t, i) {
                setTimeout(
                    function () {
                        t.classList.add("show");
                    },
                    180 + i * 140,
                );
                setTimeout(
                    function () {
                        t.classList.remove("show");
                        t.classList.add("hide");
                        setTimeout(function () {
                            if (t.parentNode) t.parentNode.removeChild(t);
                        }, 550);
                    },
                    4500 + i * 140,
                );
            });
        }

        /* ---- Glass Confirm dialog ---- */
        /** ผูก "แสงกระจกไล่ตามเมาส์" ให้การ์ดกล่องแก้ว (ตั้ง CSS --mouse-* / --spec-o / --bloom-o).
         *  ผูกผ่าน InteractionEngine ตัวเดียว เช็ค dataset.lightBound กันผูกซ้ำซ้อน.
         *  @param {HTMLElement} card ตัวการ์ดที่ต้องการรับแสง
         *  @returns {Function} offLight - เลิกผูก (offMove + ปลด flag) ควรเรียกเมื่อกล่องปิด
         */
        function bindCardLight(card) {
            if (card.dataset.lightBound) return;
            card.dataset.lightBound = "1";
            var moveFn = function (mx, my) {
                var r = card.getBoundingClientRect();
                if (!r.width || !r.height) return;
                var dx = mx - (r.left + r.width / 2);
                var dy = my - (r.top + r.height / 2);
                var ex = Math.max(Math.abs(dx) - r.width / 2, 0);
                var ey = Math.max(Math.abs(dy) - r.height / 2, 0);
                var t = 1 - Math.min(1, Math.sqrt(ex * ex + ey * ey) / 240);
                t = t * t * (3 - 2 * t);
                var lx = Math.max(-1, Math.min(1, dx / (r.width / 2)));
                var ly = Math.max(-1, Math.min(1, dy / (r.height / 2)));
                var lz = 1.35,
                    vSum = lz + 1;
                var ndh = vSum / Math.sqrt(lx * lx + ly * ly + vSum * vSum);
                var lLen = Math.sqrt(lx * lx + ly * ly + lz * lz);
                var ndl = lz / lLen;
                var fres = 0.04 + 0.96 * Math.pow(1 - ndl, 5);
                var spec =
                    Math.min(1, Math.pow(ndh, 36) * 1.9 * t * (0.45 + fres)) * 0.5;
                var bloom = Math.min(1, Math.pow(ndh, 4.5) * 0.75 * t) * 0.5;
                card.style.setProperty(
                    "--mouse-x",
                    (((mx - r.left) / r.width) * 100).toFixed(2) + "%",
                );
                card.style.setProperty(
                    "--mouse-y",
                    (((my - r.top) / r.height) * 100).toFixed(2) + "%",
                );
                card.style.setProperty("--spec-o", spec.toFixed(3));
                card.style.setProperty("--bloom-o", bloom.toFixed(3));
            };
            InteractionEngine.onMove(moveFn);
            card.addEventListener("mouseleave", function () {
                card.style.setProperty("--spec-o", "0");
                card.style.setProperty("--bloom-o", "0");
            });
            return function () {
                if (!card.dataset.lightBound) return;
                card.dataset.lightBound = "";
                InteractionEngine.offMove(moveFn);
            };
        }
        FX.api.bindCardLight = bindCardLight;

        /** กล่องยืนยันแบบแก้ว (แทน native confirm — ตรงธีม) → exposed เป็น window.islandConfirm
         *  form/link ที่ใส่ data-confirm ถูก auto-wire ด้านล่าง (submit/click listener).
         *  @param {string} msg ข้อความยืนยัน
         *  @param {Function} onConfirm callback เมื่อกดปุ่ม "ยืนยัน"
         *  @param {Node} [detailsNode] template รายละเอียดเสริม (content ของ template)
         */
        function islandConfirm(msg, onConfirm, detailsNode) {
            var backdrop = document.createElement("div");
            backdrop.className = "island-backdrop";
            var wrap = document.createElement("div");
            wrap.className = "glass-confirm-wrap";
            wrap.innerHTML =
                '<div class="glass-confirm-card" role="alertdialog" aria-modal="true">' +
                '<div class="gc-head"><span class="gc-icon"><i class="bi bi-trash3-fill"></i></span>' +
                '<div><h5 class="gc-title">ยืนยันการลบ</h5><p class="gc-sub"></p></div></div>' +
                '<div class="gc-details"></div>' +
                '<div class="gc-actions">' +
                '<button type="button" class="gc-btn" data-act="cancel">ยกเลิก</button>' +
                '<button type="button" class="gc-btn gc-btn-danger" data-act="ok"><i class="bi bi-trash3 me-1"></i>ยืนยันลบ</button>' +
                "</div></div>";
            wrap.querySelector(".gc-sub").textContent = msg;
            var detBox = wrap.querySelector(".gc-details");
            if (detailsNode) {
                detBox.appendChild(detailsNode.cloneNode(true).content);
            } else {
                detBox.style.display = "none";
            }
            document.body.appendChild(backdrop);
            document.body.appendChild(wrap);
            var card = wrap.querySelector(".glass-confirm-card");
            var offLight = bindCardLight(card);
            requestAnimationFrame(function () {
                card.classList.add("show");
                backdrop.classList.add("show");
            });
            var okBtn = card.querySelector('[data-act="ok"]');
            var done = false;
            function close() {
                if (done) return;
                done = true;
                if (offLight) offLight();
                document.removeEventListener("keydown", onKey, true);
                card.classList.remove("show");
                backdrop.classList.remove("show");
                setTimeout(function () {
                    if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
                    if (backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
                }, 550);
            }
            function onKey(e) {
                if (e.key === "Escape") close();
                if (
                    e.key === "Enter" &&
                    document.activeElement &&
                    document.activeElement.tagName !== "BUTTON"
                ) {
                    e.preventDefault();
                    okBtn.click();
                }
            }
            okBtn.addEventListener("click", function () {
                close();
                onConfirm();
            });
            card
                .querySelector('[data-act="cancel"]')
                .addEventListener("click", close);
            backdrop.addEventListener("click", close);
            document.addEventListener("keydown", onKey, true);
            setTimeout(function () {
                okBtn.focus();
            }, 80);
        }
        window.islandConfirm = islandConfirm;

        /** แจ้งเตือนแบบแก้ว (แทน native alert) → exposed เป็น window.islandAlert.
         *  ถ้าให้ title เนื้อหาจะแสดงช่องหัวเรื่อง; ไฟล์อื่นเรียกเป็น islandAlert(msg) ปกติ.
         *  @param {string} msg เนื้อความ
         *  @param {string} [title] หัวเรื่อง (default 'แจ้งเตือน')
         */
        function islandAlert(msg, title) {
            var backdrop = document.createElement("div");
            backdrop.className = "island-backdrop";
            var wrap = document.createElement("div");
            wrap.className = "glass-confirm-wrap";
            wrap.innerHTML =
                '<div class="glass-confirm-card" role="alertdialog" aria-modal="true">' +
                '<div class="gc-head"><span class="gc-icon gc-icon-info"><i class="bi bi-info-circle-fill"></i></span>' +
                '<div><h5 class="gc-title">แจ้งเตือน</h5><p class="gc-sub"></p></div></div>' +
                '<div class="gc-actions"' +
                (title ? ' style="display:none"' : "") +
                ">" +
                '<button type="button" class="gc-btn" data-act="ok">ตกลง</button>' +
                "</div></div>";
            if (title) {
                wrap.querySelector(".gc-sub").textContent = title;
            } else {
                wrap.querySelector(".gc-title").textContent = "แจ้งเตือน";
                wrap.querySelector(".gc-sub").textContent = msg;
            }
            document.body.appendChild(backdrop);
            document.body.appendChild(wrap);
            var card = wrap.querySelector(".glass-confirm-card");
            var offLight = bindCardLight(card);
            requestAnimationFrame(function () {
                card.classList.add("show");
                backdrop.classList.add("show");
            });
            var okBtn = card.querySelector('[data-act="ok"]');
            var done = false;
            function close() {
                if (done) return;
                done = true;
                if (offLight) offLight();
                document.removeEventListener("keydown", onKey, true);
                card.classList.remove("show");
                backdrop.classList.remove("show");
                setTimeout(function () {
                    if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
                    if (backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
                }, 550);
            }
            function onKey(e) {
                if (e.key === "Escape") close();
            }
            okBtn.addEventListener("click", close);
            backdrop.addEventListener("click", close);
            document.addEventListener("keydown", onKey, true);
            setTimeout(function () {
                okBtn.focus();
            }, 80);
        }
        window.islandAlert = islandAlert;

        /* ---- Form/link data-confirm ---- */
        document.addEventListener(
            "submit",
            function (e) {
                var f = e.target;
                if (
                    f.matches &&
                    f.matches("form[data-confirm]") &&
                    !f.dataset.confirmed
                ) {
                    e.preventDefault();
                    islandConfirm(
                        f.getAttribute("data-confirm"),
                        function () {
                            f.dataset.confirmed = "1";
                            f.submit();
                        },
                        f.querySelector("template.confirm-details"),
                    );
                }
            },
            true,
        );

        document.addEventListener("click", function (e) {
            var a = e.target.closest ? e.target.closest("a[data-confirm]") : null;
            if (a && !a.dataset.confirmed) {
                e.preventDefault();
                var t = a.nextElementSibling;
                var details =
                    t &&
                        t.tagName === "TEMPLATE" &&
                        t.classList.contains("confirm-details")
                        ? t
                        : null;
                islandConfirm(
                    a.getAttribute("data-confirm"),
                    function () {
                        a.dataset.confirmed = "1";
                        window.location.href = a.href;
                    },
                    details,
                );
            }
        });

        /* ---- Back to top ---- */
        var backTop = document.getElementById("backTop");
        if (backTop) {
            ScrollEngine.subscribe(function (s) {
                backTop.classList.toggle("is-show", s.y > window.innerHeight * 0.9);
            });
            backTop.addEventListener("click", function () {
                window.scrollTo({ top: 0, behavior: "smooth" });
            });
        }

        /* ---- Compact navbar: ปิดไว้ — ไม่ย่อขนาดเพื่อกัน 'แถบ 2 แบบ' ตอนเลื่อน ---- */

        /* ---- Hero entrance (bypasses reduced motion — intentional) ---- */
        var hero = document.querySelector(".hero-card");
        if (hero) hero.classList.add("hero-in");

        /* ---- Copy chips ---- */
        document.addEventListener("click", function (e) {
            var btn = e.target.closest(".copy-btn");
            if (!btn) return;
            var text = btn.dataset.copy || "";
            function done() {
                var old = btn.textContent;
                btn.textContent = "คัดลอกแล้ว ✓";
                setTimeout(function () {
                    btn.textContent = old;
                }, 1500);
            }
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(done);
            } else {
                var ta = document.createElement("textarea");
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                try {
                    document.execCommand("copy");
                    done();
                } catch (err) { }
                ta.remove();
            }
        });

        /* ---- Slip OCR ---- */
        var form = document.getElementById("slipForm");
        if (form) {
            var input = document.getElementById("slipInput");
            var label = document.getElementById("slipLabel");
            var btn = document.getElementById("slipBtn");
            var result = document.getElementById("slipResult");
            input.addEventListener("change", function () {
                label.textContent = input.files.length
                    ? input.files[0].name
                    : "คลิกเลือกรูปสลิป (JPG/PNG/WebP ≤5MB)";
            });
            ["dragover", "dragenter"].forEach(function (ev) {
                form.addEventListener(ev, function (e) {
                    e.preventDefault();
                    form.classList.add("drag");
                });
            });
            ["dragleave", "drop"].forEach(function (ev) {
                form.addEventListener(ev, function (e) {
                    e.preventDefault();
                    form.classList.remove("drag");
                });
            });
            form.addEventListener("drop", function (e) {
                if (e.dataTransfer.files.length) {
                    input.files = e.dataTransfer.files;
                    label.textContent = input.files[0].name;
                }
            });
            form.addEventListener("submit", function (e) {
                e.preventDefault();
                if (!input.files.length) return;
                btn.disabled = true;
                btn.innerHTML =
                    '<span class="spinner-border spinner-border-sm me-1"></span> กำลังอ่านสลิป...';
                result.innerHTML = "";
                fetch(
                    form.getAttribute("data-url") || window.__slipUrl || "/payment/slip/",
                    {
                        method: "POST",
                        body: new FormData(form),
                        headers: { "X-Requested-With": "fetch" },
                    },
                )
                    .then(function (r) {
                        return r.json().then(function (j) {
                            return { ok: r.ok, j: j };
                        });
                    })
                    .then(function (res) {
                        if (res.ok && res.j.ok) {
                            var cls = res.j.paid ? "success" : "warning";
                            result.innerHTML = "";
                            var d = document.createElement("div");
                            d.className = "alert alert-" + cls + " mb-0 py-2 small";
                            d.textContent = res.j.message;
                            result.appendChild(d);
                        } else {
                            result.innerHTML = "";
                            var d = document.createElement("div");
                            d.className = "alert alert-danger mb-0 py-2 small";
                            d.textContent = res.j.error || "ไม่สำเร็จ";
                            result.appendChild(d);
                        }
                    })
                    .catch(function () {
                        result.innerHTML =
                            '<div class="alert alert-danger mb-0 py-2 small">เชื่อมต่อไม่ได้ — ลองใหม่ภายหลัง</div>';
                    })
                    .finally(function () {
                        btn.disabled = false;
                        btn.innerHTML =
                            '<i class="bi bi-stars me-1"></i> ตรวจสลิปอัตโนมัติ';
                    });
            });
        }

        /* ---- Pay method highlight ---- */
        function syncPay() {
            document.querySelectorAll(".pay-method").forEach(function (el) {
                var input = el.querySelector("input");
                if (input) el.classList.toggle("selected", input.checked);
            });
        }
        document.addEventListener("change", function (e) {
            if (e.target && e.target.name === "payment_method") syncPay();
        });
        syncPay();
    })();
} catch (error) {
    if (window.console && console.error)
        console.error("[shop] core UX skipped:", error);
}
