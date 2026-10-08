---
name: liquid-glass-design
description: >-
  ระบบดีไซน์ประจำโปรเจกต์ Thammathad Shop (Apple Liquid Glass) — ใช้ทุกครั้งที่สร้าง/แก้ UI ใน repo นี้:
  template, theme.css, effect (fx-*), motion, สี, typography ไทย, dark mode, accessibility, ตาราง/dashboard
  ของโซน staff และหน้าร้าน. Triggers: "แก้ UI", "ปรับหน้า", "เพิ่มการ์ด/ปุ่ม", "theme", "Liquid Glass", "fx-",
  "motion", "สี", "ฟอนต์", "responsive", "navbar", "ตาราง". บังคับ Liquid Glass archetype + token contract
  ของ theme.css + motion contract (ปุ่ม ⚡ เท่านั้น — ห้าม reintroduce prefers-reduced-motion) +
  FX DeferredRegister (fx-assets.js) + pre-flight rules ของ repo. ห้ามใช้กับโปรเจกต์อื่น (ผูก token/class ที่นี่).
---

# Liquid Glass Design System — Thammathad Shop (project skill)

สกิลนี้คือ "สัญญาการออกแบบ" ของโปรเจกต์นี้ — ทับซ้อนกับสกิลกลาง 3 ตัว (ซึ่งให้หลักการ)
แต่สกิลนี้ให้ **ค่าจริง/คลาสจริง/กฎจริงของ repo**: อ่านคู่กัน

| งาน | อ่านเพิ่ม |
|---|---|
| blacklist AI tells, archetype, token workflow | `anti-slop-design` |
| OKLCH, 3-tier token, contrast/APCA, CVD, data-viz palette | `color-system-design` |
| cognitive laws, table density, form, state completeness | `user-centric-ux-ui` |
| กฎ repo (bug recipes #1–#10), โครงสร้าง, ข้อห้ามเดิม | `AGENTS.md` |

---

## 1. Archetype ที่ commit แล้ว: Apple Liquid Glass

ธีมคือ **"แก้ว" แบบ Apple** — พื้นสว่าง (`--page-bg: #f5f5f7`), surface โปร่งแสง, เลนส์/สเปกคูลาร์
บน hero, spotlight ตามเมาส์, halo backlight ใต้การ์ด, aurora blobs หลังเลนส์, เงานุ่มแบบ studio

**ต้องรักษา (ห้ามลบ/ห้ามปิด):**
- ระบบแสงทั้งหมด: `fx-glass` (spotlight/specular/tilt), `fx-halo` (`#bgLight` backlight), `fx-liquid` (aurora)
- `backdrop-filter` ของชั้นแก้ว (`--glass-blur: 10px`) — theme.css มี glass 49 จุด
- กายภาพแสงแบบจริง: specular, bloom, mouse-tracked highlight, `INERTIA_RATE` ของ halo/glass

**ห้าม (ตาม `anti-slop-design` blacklist):**
- purple-cyan radial glow แบบ v0, neon cyber, พื้นดำสนิท + ขอบม่วงเรืองแสง
- การ์ด 3 ใบขนาดเท่ากันซ้ำทุก section, metric triptych, เลขประดับ `01/02/03` ที่ไม่ใช่ลำดับจริง
- คำโฆษณาสำเร็จรูป ("Supercharge", "Seamless intuitive powerful")
- **ห้ามตีความว่า glass/backdrop-blur ของโปรเจกต์นี้คือ v0 trap** — ของเราคือแก้วสว่างแบบ Apple ไม่ใช่กลาสดำม่วง

---

## 2. Token Contract (`myapp/static/css/theme.css` → `:root` มี 72 tokens)

**กฎ: ห้าม hardcode hex ใหม่ใน template/CSS** — ถ้าต้องใช้สีใหม่ ให้เพิ่ม token ที่ `:root` ก่อน แล้วใช้ `var()`

| กลุ่ม | Token จริงที่ใช้ |
|---|---|
| แบรนด์ (accent เดียว) | `--apple-blue: #0071e3` · `--apple-blue-hover: #0077ed` · `--apple-green` · `--apple-red` |
| ตัวอักษร | `--ink: #1d1d1f` · `--ink-soft` · `--muted` · `--muted-2` · `--placeholder` |
| พื้นผิว | `--page-bg` · `--surface` (0.66) · `--surface-raised` (0.82) · `--gray-bg(-2)` · `--gray-border(-soft)` |
| แก้ว | `--glass-bg` (gradient 135°) · `--glass-blur` · `--glass-border` · `--glass-highlight` · `--glass-shadow` · `--glass-filter` |
| Navbar/Footer | `--nav-bg` (gradient 180°) · `--nav-bg-scrolled` · `--nav-border` · `--nav-highlight(-soft)` · `--nav-shadow-scrolled` · `--footer-bg/text` |
| ตาราง/คอนโทรล | `--table-bg/head/hover` · `--pagination-*` · `--control-bg` · `--control-focus-bg` |
| Semantic (3-tier แล้ว!) | primitive `--clr-{blue,emerald,amber,crimson}-{50..800}` → semantic `--semantic-{success,warning,danger,info}-{fg,bg,border}` |
| Motion | `--ease-apple: cubic-bezier(0.28,0.11,0.32,1)` · `--ease-apple-out: cubic-bezier(0.16,1,0.3,1)` |
| อื่น ๆ | `--warning-bg/text` (alert ดำ) · `--scroll-track/thumb` · `--icon-bg` · `--bs-body-color` |

**กระจายสี 60-30-10**: 60% พื้น `--page-bg`/`--surface` · 30% โครงสร้าง (nav/card/border) · 10% `--apple-blue`
(ถ้า accent เกิน ~10-15% ของ viewport = สี loud เกินไป)

**Dark mode**: กลไกคือ `html[data-theme="dark"]` (58 selectors ใน theme.css) — เพิ่ม override ที่นั่นเท่านั้น
ห้าม invert สีดิบ, เคารพ 87% anti-halation (ตัวอักษรหลักไม่ขาว 100%), elevation เพิ่มด้วย lightness ไม่ใช่เงา,
dampen chroma 15–25% (ตาม `color-system-design` §5)

---

## 3. Component จริง — ใช้ของเดิม อย่าสร้างใหม่

| งาน | คลาส/กลไกที่มีอยู่ |
|---|---|
| การ์ด/แผง | `.card` · `.panel-card` (+`.panel-card--wide`) · `.apple-tile` · `.apple-card-glow` |
| Hero | `.hero-shell` (+ `.hero-ultimate`) · `.liquid-mesh` |
| ปุ่ม/ลิงก์ | `.btn-primary` (มี magnetic) · `.link-arrow` · `.eyebrow` · `.page-title` |
| Navbar/โซน | `.admin-nav` · `.role-badge` (`role-admin/staff/member`) |
| Modal/ยืนยัน | **island modal เท่านั้น**: `window.islandConfirm` / `islandAlert` + `data-confirm="..."` (auto-wire) → `.glass-confirm-card` |
| Toast | `FX.toast(msg[, level, icon, dur])` — ตัวเดียวของระบบ |
| รูป | `.product-img` · `.cart-thumb` · `.product-detail-image` · `.table-avatar` · `.placeholder-avatar` (blur-up) · `.skeleton-img` |
| ตาราง staff | sticky header + ตัวเลข `font-variant-numeric: tabular-nums` ชิดขวา (monospace stack) |

**ห้าม native `confirm()`/`alert()`/`prompt()`** — ผิดธีมและถูกแทนหมดแล้ว

---

## 4. Motion + FX Contract (ส่วนที่พังบ่อยที่สุด)

**สวิตช์เดียวของระบบ**: ปุ่ม ⚡ `#motionToggle` → เขียน `html[data-motion="on|off"]` + `localStorage['thammathad-motion']`
→ `Motion.reduced()`; broadcast ผ่าน `FXBus 'cfx:toggle'` (listener ถูกเรียกเฉพาะตอนเปิดกลับ)

**HARD — ห้าม reintroduce OS `prefers-reduced-motion`** (recipe #3): theme.css ต้องมีคำนี้ **0 ครั้ง**
ระบบเคยพังทั้งเว็บเพราะผูก OS setting — เครื่องมือปิด animation มีแค่ปุ่ม ⚡

**อะไรถูก gate / ไม่ถูก gate** (ยึดตามโค้ดจริง):

| gate ด้วย `ctx.reduced()` | ไม่ gate (ต้องทำงานเสมอ) |
|---|---|
| tilt ของ `fx-glass` · `fx-ripple` · `fx-card-pop` · `fx-countup` · `fx-magnetic` · `fx-liquid` · `fx-hero-expand` | **`fx-morph`** (interaction feedback เหมือน lightbox — เจตนาห้ามใส่ gate) · **`fx-blur-up`** · **`fx-progress`** (แถบอ่านหน้า) · **แสง/เลนส์** ของ glass+halo |
| `fx-halo`: gate **เฉพาะการผูก move listener** (CPU หยุด) — ตัวแสงยังอยู่เสมอ | |

**API ที่ mod ใช้** (`FX.register({id, boot(ctx)})`):
`ctx = { Motion, reduced(), scroll(), move(), offMove(), onToggle(), on(name, fn, priority) }`
- **HARD: `move()` ต้องคืน `fn` เดิม** (fx-liquid/halo ใช้ identity เทียบกับ `offMove`) — ถ้าไม่คืน listener จะ leak
- `ctx.scroll(fn)` → subscribe ผ่าน FXBus `'cfx:scroll'` (ได้ `.y/.direction/.velocity`) คืน unsubscribe
- attribute observer: ใช้ **`FX.watchAttr(node, attr, onChange)`** เท่านั้น (เทียบค่า `lastWritten` — recipe #9
  ห้าม MutationObserver ตรง ๆ เพราะ callback เป็น async microtask → boolean guard พัง = infinite loop = หน้าค้าง)
- actor pattern: `FX.actor(type, fn)` + `FX.callActor(type, el)` (ใช้กับ countup)

**เพิ่ม effect ใหม่ (ขั้นตอนบังคับ):**
1. สร้าง `myapp/static/js/effects/fx-<ชื่อ>.js` = `FX.register({ id, boot(ctx) {...} })` (+ `css/effects/fx-<ชื่อ>.css` ถ้ามี)
2. register เข้า **`myapp/static/js/fx-assets.js`** พร้อม `match:` selector ที่ตรงกับ DOM จริง (หรือ `always: true`)
   — registry นี้คือ DeferredRegister: **ไม่โหลดอะไรตอน register**; `fx-boot.js` จะ scan หน้า แล้ว inject เฉพาะที่ใช้
3. **ห้ามเพิ่ม `<script>`/`<link>` ตรงใน `basetemplate.html`** (ลบระบบ deferred ไม่ได้แล้ว)
4. CSS ที่กัน FOUC ต้องอยู่ใน head eager: `theme.css → fx-blur-up.css → fx-reveal.css → fx-progress.css`
   และตั้ง `css: null` ใน registry กัน inject ซ้ำ
5. ตั้งชื่อ id ให้ตรง selector ที่ใช้ใน `match`

**registry ปัจจุบัน (12 ตัว)**: `ripple/magnetic/progress` (always/ปุ่ม), `glass` (`.hero-shell,.liquid-glass`),
`halo` (`.card,.apple-tile,.liquid-glass`), `liquid` (`.liquid-mesh`), `morph` (`.card-expand[data-expand]`),
`card-pop` (`[data-card-parallax]`), `blur-up` (รูป), `skeleton` (`.skeleton-img`), `countup` (`[data-motion="countup"]`),
`hero-expand` (`.scroll-expand-stage`)
**ถอดแล้ว (ไฟล์ยังอยู่แต่ไม่ถูก scan)**: `drag` · `playground` · `parallax` · `scene` — ห้ามเพิ่มเข้ากลับโดยไม่มีเหตุ

**Timing**: ใช้ `Motion.duration` = `{fast:200, normal:350, slow:600, entrance:900}` + `Motion.ease`
(`apple/spring/out`) หรือ CSS `--ease-apple(-out)` — อย่าตั้งตัวเลขใหม่มั่ว
`data-card-speed` ถูกถอดแล้ว — ห้ามเพิ่มกลับ (center-pop แทน) · countup บน dashboard มี retry ใน fx-boot — อย่าลบ

**Entry animations**: ใช้ `data-motion="reveal|stagger|countup"` + `data-dir` (EntryEngine จัดการ `.in`/`--d` เอง;
ห้ามเขียน IntersectionObserver ซ้ำใน template)

---

## 5. Thai Typography + ตัวเลข

**Font stack จริง** (theme.css — 2 ที่เท่านั้น):
```
-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",
"Helvetica Neue", "Prompt", "Noto Sans Thai", "Segoe UI", sans-serif
```
- **ฟอนต์โหลดแบบ self-host**: `static/vendor/css/prompt.css` โหลด Prompt woff2 (น้ำหนัก 400/500/600,
  แยก `unicode-range` ไทย/ละติน, `font-display: swap`) — **ไม่พึ่ง CDN ภายนอก** (privacy + perf ดีกว่า)
  ถ้าต้องเพิ่ม/เปลี่ยนฟอนต์: self-host เป็น woff2 + ตั้ง `font-display: swap` + แยก unicode-range เท่านั้น (ห้าม hotlink CDN)
- ฟอนต์ไทย fallback = `Prompt` → `Noto Sans Thai` → `Segoe UI` (Windows) — ทดสอบทั้งที่มี/ไม่มีฟอนต์
- เนื้อหาไทย line-height ≥ 1.6 (วรรณยุกต์/สระบนล่างต้องการที่); ไทยไม่เว้นวรรค → ระวังการตัดบรรทัดผิดคำ
  (`word-break: normal` เป็นค่าเริ่มต้น อย่าใส่ `break-all`)
- **ตัวเลขการเงิน/รหัส** ใช้ mono stack `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, ...`
  + `font-variant-numeric: tabular-nums` ชิดขวา, รูปแบบ `฿ 12,450.00` (ดูตัวอย่างในตาราง staff)

---

## 6. Accessibility ในกรอบของโปรเจกต์นี้

- ทุก interactive ต้องมี **:hover / :active (กดจริง `translateY(1px)`) / :focus-visible (ring 2px offset 2px)**
  — theme.css มี focus-visible 13 จุดแล้ว ให้ใช้ pattern เดิม; ห้าม `outline: none` ลอย ๆ
- **Dual-Encoding (บังคับ)**: สถานะ/สถานะเงินต้องมีข้อความหรือไอคอนควบสีเสมอ (เช่นบันไดสถานะออเดอร์, badge)
  ห้ามใช้สีสื่อความหมายเดี่ยว ๆ (ตาม `color-system-design` §4.3 + CVD)
- Contrast ขั้นต่ำ: 4.5:1 ตัวหนังสือ / 3:1 UI — ระวัง `--muted`/`--muted-2` บนพื้นแก้วที่โปร่งแสง
- island modal: โฟกัสไปปุ่มแรก, คืนโฟกัสหลังปิด, **ห้ามปิด backdrop ถ้ามี input dirty** (ตาม `user-centric-ux-ui`)
- ปุ่มไอคอนล้วนต้องมี `aria-label`; รูปสินค้าต้องมี `alt` ที่สื่อความ (ไม่ใช่ชื่อไฟล์)

---

## 7. Pre-Flight Checklist ของ repo (ก่อนบอกว่า "เสร็จ")

- [ ] ไม่มี BOM ใน template (recipe #8) · **ห้ามแก้ไฟล์ไทยด้วย PowerShell `Get-Content`/`Set-Content`** (recipe #1)
- [ ] template ลูกทุกตัวเริ่มด้วย `{% extends %}` เป็นบรรทัดแรก (Quirks mode — newline นำ DOCTYPE)
- [ ] แก้ static → `Copy-Item` ไป `staticfiles/` + **restart runserver** (recipe #7) + verify จาก **served HTML** (recipe #2/#4)
- [ ] effect ที่เพิ่ม/แก้ → register ใน `fx-assets.js` + `match` ตรง DOM จริง
- [ ] ทดสอบครบ 4 สถานะ: `data-motion=on/off` × `data-theme=light/dark`
- [ ] ผ่าน blacklist ของ `anti-slop-design` (ไม่มี purple glow / 3-card ซ้ำ / เลขปลอม / copy สำเร็จรูป)
- [ ] ไม่มี native `confirm/alert/prompt` · ไม่มี OS `prefers-reduced-motion`
- [ ] ตัวเลขการเงิน tabular-nums · สถานะมี dual-encoding · ทุกคอนโทรลมี focus-visible

## 8. References ในเครื่อง
- `myapp/static/css/theme.css` (core, 72 tokens) · `myapp/static/css/effects/*.css`
- `myapp/static/js/motion-core.js` (Motion/FXBus/engines/FX loader) · `myapp/static/js/fx-assets.js` (registry) · `myapp/static/js/fx-boot.js`
- `myapp/static/js/effects/*.js` · `myapp/templates/basetemplate.html` (จุดโหลด) · `AGENTS.md` (recipes + สถาปัตยกรรม)
