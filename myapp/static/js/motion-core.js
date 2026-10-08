/* ============================================================================ */
/*  THAMMATHAD SHOP — Motion Core + FX Loader  (สถาปัตยกรรม mod-loader)          */
/*                                                                            */
/*  ไฟล์นี้ = "แกนระบบ" ที่โหลดก่อนเสมอ ไม่บรรจุเอฟเฟกต์ติดมาด้วย:                */
/*  - FXBus (EventBus)  : บัสเหตุการณ์เดียว 'cfx:*' — toggle/scroll/move/boot lifecycle */
/*                        วิ่งผ่านกันหมด (fan-out จุดเดียว แรงบันดาลใจ Neoforge IEventBus) */
/*  - Motion           : ตัวเดียวที่จัดการ "เปิด/ปิดอนิเมชั่น" ด้วยปุ่ม ⚡ (+ subscribe ผ่าน FXBus) */
/*  - FX loader        : Registry ให้ mod register() — โมเดล "loader + mods"      */
/*  - ScrollEngine     : 1 scroll listener + rAF → แจก scroll state (ผ่าน FXBus)  */
/*  - EntryEngine      : 1 IntersectionObserver → จัดการ reveal/stagger/countup   */
/*  - InteractionEngine: 1 mousemove + rAF → แจกพิกัดเมาส์ (ผ่าน FXBus)            */
/*  เอฟเฟกต์อยู่ที่ js/effects/fx-*.js — register ผ่าน FX.register({id, boot(ctx)}) */
/*  แล้ว FX.boot() (ท้าย basetemplate) เรียก boot ทุก mod แยก try ป้องกันตัวพัง    */
/*  สำคัญ: ห้ามผูก OS prefers-reduced-motion — มีปุ่ม ⚡ เท่านั้นคุมสถานะ            */
/* ============================================================================ */

/* ==================== 0. EVENT BUS (cfx) ==================== */
/*  FXBus — บัสเหตุการณ์เดียวของระบบ (แรงบันดาลใจ Neoforge IEventBus แต่ตัดให้พอดี):
 *  - subscribe(name, fn[, priority]): เก็บแบบเรียง priority (HIGHEST→LOWEST) แบบ stable
 *    (ค่าเท่ากัน = ลำดับที่ลงข้อแรก) → คืน unsubscribe() สำหรับถอดทีหลัง
 *  - off(name, fn): ถอดโดย identity (fn ตัวเดิม) — เวอร์ชันที่ไม่มี unsubscribe handle
 *  - emit(name, ...args): เรียกทุก handler + แยก try ต่อตัว (ตัวพังไม่ฉุดตัวอื่น)
 *  - งด TriState/cancellable/result ตั้งใจ: ระบบเราไม่มีผู้ฟังต้อง "สั่งยกเลิก/โหวต" เหตุการณ์
 *  เหตุการณ์ทั้งหมดใช้ namespace 'cfx:' (เดียวกับ prefix effect) กันชนกับ DOM event ตัวจริง
 *  — ส่วนที่ core ใช้: 'cfx:toggle' | 'cfx:scroll' | 'cfx:move' | 'cfx:boot:start/mod/done'
 */
var FXBus = {
    /** ค่าลำดับความสำคัญ (เลียนแบบ Neoforge EventPriority — ตัวเลข มากสุดฟังก่อน). */
    PRIORITY: { HIGHEST: 100, HIGH: 50, NORMAL: 0, LOW: -50, LOWEST: -100 },
    /** @type {Object<string, Array<{fn:Function, p:number}>>} เก็บต่อ event เรียง priority อยู่แล้ว. */
    _handlers: {},
    /** ลงทะเบียนฟังเหตุการณ์ — เก็บแบบเรียง priority (ไม่ sort ตอน emit = ปลอดภัยกับ
     *  'cfx:scroll' ที่ยิงทุก rAF).
     *  @param {string} name ชื่อเหตุการณ์ 'cfx:...'
     *  @param {Function} fn รับ (...args) ตามที่ emit ส่งมา
     *  @param {number} [priority] FXBus.PRIORITY (default NORMAL=0)
     *  @returns {Function} unsubscribe() — ถอด handler นี้ทิ้ง
     */
    subscribe: function (name, fn, priority) {
        var p = typeof priority === "number" ? priority : 0;
        var list = this._handlers[name] || (this._handlers[name] = []);
        var idx = 0;
        while (idx < list.length && list[idx].p >= p) idx++;
        list.splice(idx, 0, { fn: fn, p: p });
        var self = this;
        return function () {
            self.off(name, fn);
        };
    },
    /** ถอด handler โดย identity (fn ตัวเดิม) — ใช้เมื่อเรียก subscribe โดยไม่ถือ unsubscribe. */
    off: function (name, fn) {
        var list = this._handlers[name];
        if (!list) return;
        for (var i = 0; i < list.length; i++) {
            if (list[i].fn === fn) {
                list.splice(i, 1);
                return;
            }
        }
    },
    /** เรียก handler ทั้งหมดของเหตุการณ์ — แยก try ต่อตัว: อันหนึ่ง throw ไม่ฉุดตัวที่เหลือ. */
    emit: function (name, a, b) {
        var list = this._handlers[name];
        if (!list) return;
        for (var i = 0; i < list.length; i++) {
            try {
                list[i].fn(a, b);
            } catch (e) { }
        }
    },
};

/* ==================== 1. MOTION CONFIG ==================== */
/**
 * Motion — จุดเดียวที่รู้สถานะเปิด/ปิดอนิเมชั่นของทั้งเว็บ (ปุ่ม ⚡ #motionToggle).
 *
 * - enabled เก็บใน localStorage('thammathad-motion') + ฉายลง html[data-motion="on|off"]
 * - mod/engine ลงทะเบียน listener ผ่าน Motion.on(fn) (เบื้องหลัง = FXBus 'cfx:toggle')
 *   → โทเกิลจะเรียกทุกตัว เฉพาะตอน "เปิดกลับ" (ตอนปิดไม่ broadcast — ดู toggle)
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
    /** ลงทะเบียน listener ตอบสนองปุ่ม ⚡ — ถูกเรียกด้วย (enabled: boolean) ตอนเปิดกลับ.
     *  เบื้องหลังลง FXBus 'cfx:toggle' (fan-out จุดเดียวของระบบ).
     *  @param {Function} fn callback
     *  @returns {Function} unsubscribe() — ถอดจาก bus ได้
     */
    on: function (fn) {
        if (typeof fn !== "function") return;
        return FXBus.subscribe("cfx:toggle", fn);
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
            /* broadcast ผ่าน FXBus — เรียก listener เฉพาะตอนเปิดกลับเท่านั้น (ตอนปิดเงียบ
             * เหมือน ระบบเดิม; mod ฟังแล้วเช็ค enabled เอง ถ้าอยาก rerun ตอนเปิด) */
            FXBus.emit("cfx:toggle", this.enabled);
        }
        FX.toast(
            this.enabled ? "เปิดอนิเมชั่นแล้ว" : "ปิดอนิเมชั่นแล้ว",
            "success",
            this.enabled ? "play-circle-fill" : "pause-circle-fill",
        );
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
 * ของทุก mod พร้อม ctx ที่แจกเครื่องมือ core มาให้ (Motion/scroll/move/onToggle/on)
 * on(name, fn) = ฟัง event FXBus ตรง ๆ เช่น 'cfx:boot:mod' (subscribe "mod bus" ได้โดยไม่แตะ core)
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
    /** เริ่ม boot ทุก mod ตามลำดับ register — แยก try/catch: ตัวพังไม่ฉุดตัวอื่น.
     *  emit lifecycle ผ่าน FXBus ('cfx:boot:start' / 'cfx:boot:mod' / 'cfx:boot:done')
     *  ให้ "mod อื่น" ดักว่า mod ไหน boot เสร็จแล้วโดยไม่ต้องแตะ core (เทียบ mod bus Neoforge).
     */
    boot: function () {
        FXBus.emit("cfx:boot:start");
        for (var i = 0; i < this._order.length; i++) {
            var id = this._order[i];
            var mod = this._mods[id];
            var ok = false;
            try {
                if (mod.boot) mod.boot(this.ctx());
                ok = true;
            } catch (e) {
                this._report("fx-mod", id, e);
            }
            FXBus.emit("cfx:boot:mod", { id: id, ok: ok });
        }
        FXBus.emit("cfx:boot:done");
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
                return Motion.on(fn);
            },
            on: function (name, fn, priority) {
                return FXBus.subscribe(name, fn, priority);
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

    /** แสดง toast กล่องแก้วใน islandStack — ตัวเดียวของระบบ (Motion.toggle ก็เรียกตัวนี้).
     *  @param {string} msg ข้อความ
     *  @param {string} [level] success|danger|warning (default success)
     *  @param {string} [icon] ชื่อ bootstrap icon เช่น 'play-circle-fill'
     *  @param {number} [dur] ระยะเวลาแสดง ms (default 3000)
     */
    toast: function (msg, level, icon, dur) {
        var stack = document.getElementById("islandStack");
        if (!stack) return;
        var toast = document.createElement("div");
        toast.className = "island-toast";
        toast.setAttribute("data-level", level || "success");
        toast.setAttribute("role", "status");
        toast.innerHTML =
            '<span class="island-icon"><i class="bi bi-' +
            (icon || "check-circle-fill") +
            '"></i></span>' +
            '<span class="island-text">' + msg + "</span>";
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
        }, dur || 3000);
    },

    /** ฝัง "watch attribute" ที่ปลอดภัยจาก infinite loop (AGENTS recipe #9) —
     *  ใช้แทนการเขียน MutationObserver ที่ handles เขียน attribute เดียวกับที่ตัวเองฟัง.
     *
     *  ทำไม safety: MutationObserver callback เป็น async microtask (รันทีหลัง synchronous เสมอ)
     *  → guard แบบ boolean (`suppress=true; setAttribute(...); suppress=false`) ใช้คุมไม่ได้
     *  เพราะตอน callback ทำงาน flag ถูก reset แล้ว → เขียนซ้ำ → คิวไม่อั้น = หน้าแพ. วิธีที่ถูก
     *  คือ**เทียบค่า**: จด `lastWritten` ที่ตัวเองเขียนล่าสุด แล้ว callback ข้ามถ้าค่าเห็น == ค่านั้น
     *  (echo ของตัวเองอ่านได้ทีหลัง จึงปล่อยให้ "คนอื่น" (เช่น fx-drag) เขียนแล้วค่อย onChange).
     *
     *  @param {HTMLElement} node - ตัวที่อยากฟัง attribute
     *  @param {string} attr - ชื่อ attribute ที่ฟัง (เช่น data-drag-idx)
     *  @param {Function} onChange - เรียกเมื่อ คนอื่น เปลี่ยนค่าจริง (ไม่ใช่ echo ของเรา);
     *                               รับ (newVal: string|null, api: {set}) — อยากตอบกลับเขียนผ่าน api.set()
     *  @returns {{set: Function, disconnect: Function}} set(v)=เขียน attr + จดค่า (กัน loop),
     *           disconnect()=เลิกฟัง
     */
    watchAttr: function (node, attr, onChange) {
        var lastWritten = null;
        function read() {
            return node && node.getAttribute
                ? node.getAttribute(attr)
                : null;
        }
        function set(v) {
            var sv = String(v);
            if (node && node.setAttribute) node.setAttribute(attr, sv);
            lastWritten = sv;
        }
        var obs = null;
        if (window.MutationObserver && node) {
            obs = new MutationObserver(function () {
                var v = read();
                if (v === lastWritten) return; /* echo ของ set() ตัวเอง → ข้าม */
                if (typeof onChange === "function") {
                    try {
                        onChange(v, {
                            set: set,
                            get: read,
                        });
                    } catch (e) { }
                }
            });
            obs.observe(node, { attributes: true, attributeFilter: [attr] });
        }
        return {
            set: set,
            disconnect: function () {
                if (obs) obs.disconnect();
            },
        };
    },

    /** รายงาน error เข้าศูนย์กลาง + ทางออกตรวจ (debug-only toast / console)
     *  — ตัวนี้ "เห็น error", ไม่ได้ "กันค้าง": main-thread freeze แบบ recipe #9 ไม่มีโค้ดได้รัน
     *  จะไปเร่งบอกไม่ได้ (watchAttr/การ์ดค่าเป็นตัวกันที่ต้นทาง).
     *  @param {string} tag กลุ่ม (fx-mod / window / promise)
     *  @param {string} label ป้ายเล่า เช่น mod id หรือไฟล์
     *  @param {*} e error object / ข้อความ
     */
    _report: function (tag, label, e) {
        var msg = (e && e.message) ? e.message : String(e);
        if (window.console && console.error) {
            console.groupCollapsed("[fx] " + tag + (label ? " :: " + label : "") + " failed");
            console.error(e);
            try { console.trace(); } catch (err) { }
            console.groupEnd();
        }
        if (window.__DEBUG__) {
            var stack = document.getElementById("islandStack");
            if (stack) {
                var t = typeof this.toast === "function" ? this.toast : null;
                var short = msg.length > 90 ? msg.slice(0, 90) + "…" : msg;
                if (t) {
                    this.toast(
                        (label ? label + ": " : "") + short,
                        "danger",
                        "exclamation-triangle-fill",
                        5000,
                    );
                }
            }
        }
    },
};

/* ---- Runtime error watch (debug only) — เก็บทุก uncaught error + unhandled promise
       แล้วส่งเข้า FX._report → toast/console พร้อมแหล่งที่มา (ห้ามลบ: ใช้เวลาอาจารย์
       เปิดหน้าแล้วเจอ error รู้ทันทีว่ามาจาก mod/script ไหน) ---- */
(function () {
    if (window.__DEBUG__) {
        window.addEventListener("error", function (e) {
            try {
                FX._report(
                    "window",
                    (e && e.filename ? e.filename.split("/").pop() : "runtime") +
                        (e && e.lineno ? ":" + e.lineno : ""),
                    e && e.error ? e.error : (e ? e.message : "unknown"),
                );
            } catch (ignore) { }
        });
        window.addEventListener("unhandledrejection", function (e) {
            try {
                FX._report("promise", "unhandledrejection", (e && e.reason) || "Promise rejected");
            } catch (ignore) { }
        });
    }
})();

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
    _ticking: false,
    /** ลงทะเบียน subscriber ผ่าน FXBus ('cfx:scroll') — ถูกเรียกทุกเฟรมที่ scroll ด้วย
     *  object สถานะ (.y/.direction/.velocity). รองรับ priority (def NORMAL);
     *  @param {Function} fn - รับ ScrollEngine ตัวมันเอง (สถานะใน props)
     *  @param {number} [priority] FXBus.PRIORITY
     *  @returns {Function} unsubscribe()
     */
    subscribe: function (fn, priority) {
        return FXBus.subscribe("cfx:scroll", fn, priority);
    },
    /** (internal) อัปเดตสถานะ แล้ว broadcast ผ่าน FXBus — ยัง 1 ครั้งต่อ rAF เท่าเดิม. */
    _flush: function () {
        this._ticking = false;
        var y = window.scrollY;
        this.direction = y > this.prevY ? "down" : "up";
        this.velocity = Math.abs(y - this.prevY);
        this.y = y;
        FXBus.emit("cfx:scroll", this);
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
    /** ลงทะเบียน handler รับ (mouseX, mouseY) ผ่าน FXBus ('cfx:move') — ต้อง offMove เอง
     *  เมื่อเลิกใช้ (pattern fx-liquid/fx-halo). คืน fn เดิม เพื่อให้ offMove(fn) ถอดได้
     *  โดย identity (HARD: อย่าเปลี่ยน return เป็นอย่างอื่น — ที่เก่ากลับ fn เดิม).
     *  @param {Function} fn - รับพิกัดเมาส์ 2 args
     *  @returns {Function} ตัว fn เดิม
     */
    onMove: function (fn) {
        FXBus.subscribe("cfx:move", fn, 0);
        return fn;
    },
    /** เลิกส่งค่าให้ handler นี้ (ถอดจาก bus 'cfx:move' โดย identity). */
    offMove: function (fn) {
        FXBus.off("cfx:move", fn);
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
        FXBus.emit("cfx:move", this.mouseX, this.mouseY);
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

        /* ---- Tahoe Liquid Glass: Directional Specular & Bevel Light Physics ---- */
        var tahoeItems = [];
        var tahoeDirty = true;
        function updateTahoeRects() {
            var els = document.querySelectorAll(
                ".btn-tahoe, .btn-liquid-glass, .lens-btn"
            );
            tahoeItems.length = 0;
            var sy = window.scrollY || 0;
            for (var k = 0; k < els.length; k++) {
                var el = els[k];
                var r = el.getBoundingClientRect();
                tahoeItems.push({
                    el: el,
                    docCx: r.left + r.width / 2,
                    docCy: r.top + sy + r.height / 2,
                    docTop: r.top + sy,
                    docBottom: r.bottom + sy,
                    cx: r.left + r.width / 2,
                    cy: r.top + r.height / 2,
                    top: r.top,
                    bottom: r.bottom,
                    cos: "",
                    sin: "",
                    int: ""
                });
            }
            tahoeDirty = false;
        }
        function queryTahoeButtons() {
            tahoeDirty = true;
        }
        window.addEventListener("resize", queryTahoeButtons, { passive: true });
        ScrollEngine.subscribe(function (s) {
            if (tahoeDirty) {
                updateTahoeRects();
                return;
            }
            var sy = s.y;
            for (var k = 0; k < tahoeItems.length; k++) {
                var item = tahoeItems[k];
                item.cy = item.docCy - sy;
                item.top = item.docTop - sy;
                item.bottom = item.docBottom - sy;
            }
        });

        InteractionEngine.onMove(function (mx, my) {
            if (tahoeDirty) updateTahoeRects();
            if (tahoeItems.length === 0) return;
            var vh = window.innerHeight;
            for (var i = 0; i < tahoeItems.length; i++) {
                var item = tahoeItems[i];
                if (item.bottom < -50 || item.top > vh + 50) continue;
                var dx = mx - item.cx;
                var dy = my - item.cy;
                var dist = Math.sqrt(dx * dx + dy * dy);
                var MAX_DIST = 380;
                if (dist < MAX_DIST) {
                    var angle = Math.atan2(dy, dx);
                    var t = 1 - (dist / MAX_DIST);
                    var smoothT = t * t * (3 - 2 * t);
                    var targetCos = -Math.cos(angle);
                    var targetSin = -Math.sin(angle);
                    var cos = (targetCos * smoothT * 0.85).toFixed(3);
                    var sin = (targetSin * smoothT * 0.85).toFixed(3);
                    var intensity = (0.45 + 0.55 * smoothT).toFixed(2);
                    if (item.cos !== cos) {
                        item.cos = cos;
                        item.el.style.setProperty("--cos", cos);
                    }
                    if (item.sin !== sin) {
                        item.sin = sin;
                        item.el.style.setProperty("--sin", sin);
                    }
                    if (item.int !== intensity) {
                        item.int = intensity;
                        item.el.style.setProperty("--rim-intensity", intensity);
                    }
                } else {
                    if (item.cos !== "0") {
                        item.cos = "0";
                        item.sin = "0";
                        item.int = "0.45";
                        item.el.style.setProperty("--cos", "0");
                        item.el.style.setProperty("--sin", "0");
                        item.el.style.setProperty("--rim-intensity", "0.45");
                    }
                }
            }
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
