# AGENTS.md

## Project Overview

Django 6.0.6 e-commerce system with employee management. Apple Liquid Glass UI, Thai-language UI, SQLite, deployed on PythonAnywhere (`tammatat.pythonanywhere.com`).

**Dual-zone architecture**: Public shop (customer-facing) + Staff admin (auth required). Two separate navbar bases: `basetemplate.html` (public) and `adminbase.html` (staff).

**IMPORTANT — assignment context**: ทั้งหมดนี้คือ**โปรเจกต์ส่งงานอาจารย์** ระบบเป็น demo — **ไม่มีการซื้อขาย/โอนเงินจริง** แต่ฟีเจอร์ต้อง**ทำงานถูกต้องครบตามความต้องการ**ของใบงาน รวมถึงสายงานเงิน/สถานะออเดอร์ที่เป็นส่วนหนึ่งของใบงาน (จุดรับเงินจุดเดียว `PaymentService` + บันไดสถานะ `OrderStatusService`: รอ → ชำระเงินแล้ว → จัดส่ง → ถึงมือ — ห้ามข้าม/ถอยหลัง, จ่ายครบแล้วขึ้น "ชำระเงินแล้ว" อัตโนมัติ) ความสมบูรณ์แบบเชิงพาณิชย์ (SEO, performance เจาะลึก ฯลฯ) ไม่จำเป็น — โฟกัสที่ feature ทำงานถูกต้อง, ข้อมูลครบ, UI สวยตรงธีม, และส่งงานได้เรียบร้อย

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python manage.py runserver
```

Access: http://127.0.0.1:8000/ (public shop) or `/staff/login/` → `/employees/` (staff zone)

## Structure

```
myproject/          Django config (settings, urls, wsgi)
  settings.py       SQLite, DEBUG=True, Asia/Bangkok, env-overridable secrets
  urls.py           Delegates all routes to myapp/urls.py

myapp/
  models.py         7 models: Employee, Product, Order, OrderItem, Payment,
                    CustomerProfile, CustomerAddress + custom QuerySets/Managers
  views.py          ~1400 lines, all CBV (50+ classes), StaffRequiredMixin for auth
  urls.py           70 lines, all .as_view() routes
  services.py       14 service classes: Cart, Catalog, RateLimit, LoginThrottle,
                    ThaiCalendar, ExchangeRate, GeoIP, Translate, PromptPay,
                    QrCode, SlipOK, GeminiAI, Validators, OrderStatusService,
                    PaymentService
  api.py            DRF ViewSets (products read-only, orders read-only, employees CRUD)
  serializers.py    DRF serializers
  forms.py          EmployeeForm, StaffLoginForm
  context_processors.py   cart_context (injects cart_count to all templates)
  templates/        34 templates (Bootstrap 5, Thai labels, Liquid Glass style)
  static/
    css/theme.css   ~1150 lines: Apple Liquid Glass design system (core — เอฟเฟกต์แยกอยู่ effects/)
    css/effects/    11 FX mod CSS: fx-glass, fx-reveal, fx-progress, fx-blur-up, fx-card-pop,
                    fx-morph, fx-skeleton, fx-ripple, fx-parallax, fx-liquid, fx-halo
                    — โหลดทีละไฟล์ใน basetemplate
    js/motion-core.js   ~560 lines: Motion (ปุ่ม ⚡ จุดเดียว) + FX loader +
                    ScrollEngine / EntryEngine / InteractionEngine + core UX (island modal, slip OCR, ...)
    js/effects/     11 FX mod JS: fx-countup, fx-ripple, fx-glass, fx-progress, fx-blur-up,
                    fx-magnetic, fx-parallax, fx-liquid, fx-halo, fx-card-pop, fx-morph
                    — ลงทะเบียนผ่าน FX.register()
    data/thai-address.json   350 KB Thai province/district/subdistrict cascade data
    images/         Product images (prod1-6), shop assets
  templatetags/     Custom template tags

staticfiles/        collectstatic output (production serves from here)
media/employees/    Uploaded employee avatars
db.sqlite3          Database with seed data (12 employees, 3 products)
```

## Key Commands

```bash
python manage.py runserver           # Dev server
python manage.py makemigrations      # Generate migrations
python manage.py migrate             # Apply migrations
python manage.py collectstatic       # Collect to staticfiles/
```

## Architecture

### Models & OOP

- **Custom QuerySets** on every model: `EmployeeQuerySet.search()`, `ProductQuerySet.of_category()`, `OrderQuerySet.revenue()`, etc.
- **Managers from QuerySets**: `EmployeeManager = models.Manager.from_queryset(EmployeeQuerySet)` — gives `Employee.objects.next_code()`, `.stats()`, etc.
- **Service layer** (`services.py`): Cart (session-based), Catalog, RateLimit, ThaiCalendar, ExchangeRate (open.er-api.com), GeoIP (ipwho.is), Translate (MyMemory), PromptPay QR, SlipOK OCR, GeminiAI, Validators, OrderStatusService, PaymentService — no business logic in views.
- **Order status lifecycle** (`OrderStatusService`): บันไดขั้นเดียว รอ → ชำระเงินแล้ว → จัดส่ง → ถึงมือ — ห้ามข้าม/ถอยหลัง; ขั้น "ชำระเงินแล้ว" ขึ้นอัตโนมัติ (เจ้าหน้าที่ตั้งด้วยมือไม่ได้).
- **PaymentService.record_payment()**: จุดรับเงินจุดเดียวของทุกช่องทาง (สลิป OCR / ปุ่มโอน 1 คลิก / เจ้าหน้าที่ยืนยัน) — เมื่อยอดแจ้งสะสมครบยอดรวม → สถานะเป็น paid อัตโนมัติ.

### Views

- All CBV. Base class `StaffRequiredMixin` checks `request.user.is_staff`.
- `LiveSearchListView` is a reusable base for AJAX live-search tables (employee, product pages).
- Cart operations (`CartAddView`, `CartRemoveView`, `CartUpdateView`) are POST-only (GET = 405).
- `OrderStatusView` เปลี่ยนสถานะได้เฉพาะขั้นถัดไปตามบันได (`OrderStatusService`) — ขั้น "ชำระเงินแล้ว" เจ้าหน้าที่กดเองไม่ได้ (ขึ้นอัตโนมัติเมื่อจ่ายครบผ่าน PaymentService)
- Logout views (`CustomerLogoutView`, `StaffLogoutView`) are POST-only (GET = 405).

### Auth Zones

| Zone | Login URL | Required For |
|---|---|---|
| Staff | `/staff/login/` | `/employees/`, `/product/manage/`, `/orders/`, `/customers/`, `/reports/`, `/payments/`, `/dashboard/` |
| Customer | `/account/login/` | `/account/`, `/account/addresses/`, checkout with saved address |
| Django Admin | `/admin/` | Full model CRUD |

- Staff login: `StaffLoginView` → redirects to `/employees/`
- Customer: `CustomerRegisterView` → `CustomerLoginView` → `AccountView` (order history + address book)

### REST API

- `/api/` — API root (list of endpoints)
- `/api/products/` — read-only (public)
- `/api/orders/` — read-only (staff only)
- `/api/employees/` — CRUD (staff only)
- `/api/token/` — obtain auth token (POST) + **throttle 10 ครั้ง/นาที/IP** (`TokenObtainThrottledView`)
- `/api/categories/` — category list
- `/api/schema/` + `/api/docs/` — OpenAPI 3 (drf-spectacular) + Swagger UI · **IsAdminUser** (เคยเป็น AllowAny = เปิดโครงสร้าง API ทั้งระบบให้คนนอกดู)
- `/payment/slip/` (AJAX ภายในที่เปิดสาธารณะ) — throttle 10 ครั้ง/นาที/IP ผ่าน `RateLimit` service (`services.py`)
- Auth: Session (browser) or Token (`Authorization: Token xxx`)
- `DEFAULT_PERMISSION_CLASSES = IsAuthenticated` (fail-safe ใน settings.py) — view ใหม่ที่ลืมระบุ permission จะถูกล็อกก่อน; view สาธารณะ (products/categories/api root) ระบุ `AllowAny` เองอยู่แล้ว
- `/api/orders/` prefetch `items__product` — กัน N+1 จาก `product_name` (`source='product.name'`); วัดได้ 4 queries คงที่ต่อหน้า (COUNT + orders + items + products)
- เทสต์ API: `myapp/tests/test_api.py` + `test_ratelimit.py` + `test_ajax_convention.py` + `test_external_apis.py` — ระวัง gotcha ของ Django 6.0 test client (Bug Recipe #10)
- `management/commands/`: `setup_roles.py` (กลุ่ม+permission ตามบทบาท) · `backup_db.py` (สำรอง SQLite + cron)

### External Integrations (services.py)

| Service | Purpose | Setting |
|---|---|---|
| ExchangeRate | THB→USD from open.er-api.com | — |
| PromptPay | QR code for payment | `PROMPTPAY_ID` in settings |
| GeminiAI | Product description AI helper | `GEMINI_API_KEY` env var (empty = hidden) |
| SlipOK | Bank slip OCR verification | `SLIPOK_API_KEY` env var (empty = hidden) |
| GeoIP | IP → ประเทศ (คำใบ้ในฟอร์มที่อยู่ · ไม่ prefill จังหวัด) | ipwho.is — keyless |
| Translate | แปล EN↔TH ช่วยฟอร์มสินค้า (ใช้ได้โดยไม่ต้องมี key) | MyMemory — keyless |
| ThaiCalendar.holidays | วันหยุดราชการไทย + วันทำการถัดไป (ETA หน้าสั่งซื้อสำเร็จ) | Google Calendar ICS — keyless |

### Frontend

- **theme.css**: Apple Liquid Glass design system (core). Variables: `--ink`, `--ink-soft`, `--gray-bg`, `--apple-blue`, `--nav-bg`, `--ease-apple`. เอฟเฟกต์ (reveal, morph, ripple, ...) แยกอยู่ใน `css/effects/*.css` — core มีแต่ส่วนประกอบ/component transitions + motion-off gates ของ core เท่านั้น.
- **motion-core.js** (โหลดก่อนเสมอ) — core + FX loader (สถาปัตยกรรมแบบ mod loader):
  0. **FXBus (EventBus)** — บัสเหตุการณ์เดียวของระบบ (มุมมองไว้เทียบกับ NeoForge IEventBus — ดู `NEOFORGE_ARCHITECTURE.md`). fan-out ของ toggle/scroll/move/boot lifecycle **ทั้งหมด** วิ่งผ่าน bus ตัวนี้ (`FXBus.subscribe/off/emit`, prefix `cfx:`); `FXBus.PRIORITY` (HIGHEST→LOWEST) เรียงตอน subscribe (ไม่ sort ตอน emit — ปลอดภัยกับ scroll ที่ยิงทุก rAF). งด cancellable/TriState/result ตั้งใจ (ไม่มีผู้ฟังต้อง "ยกเลิก") — ห้ามแอบเพิ่มโดยไม่มีเหตุผลจริง. Prioritiy ที่ใช้งานจริง: `fx-progress.js` จอง `HIGH` ให้แถบอ่านหน้า.
  1. **Motion** — single source of truth: `ease`, `duration`, `enabled`, `reduced()`. ปุ่ม `#motionToggle` (⚡) สลับ `html[data-motion="on"|"off"]` + `localStorage('thammathad-motion')`. **จุด broadcast เดียว** เบื้องหลัง = `FXBus 'cfx:toggle'`, ผ่าน `Motion.on(fn)` (mod ใช้ `ctx.onToggle`) — toggle เรียก listener **เฉพาะตอนเปิดกลับ** (ปิดเงียบ รักษา behavior เดิม). OS `prefers-reduced-motion` NOT consulted (0 occurrences).
  2. **ScrollEngine** — one scroll listener + rAF, `subscribe(fn[, priority])` → ผ่าน `FXBus 'cfx:scroll'` (subscriber ได้ object สถานะ `.y/.direction/.velocity`), คืน unsubscribe().
  3. **EntryEngine** — one IntersectionObserver, dispatch `reveal`/`stagger` (เพิ่ม `.in`) + `countup` ผ่าน `FX.callActor('countup', el)`; **initial-load hoist** ใน `setTimeout(600)` เริ่ม reveal/stagger/countup ที่อยู่ในจอได้ทันที และ mark `el.dataset.hoisted` กัน IO รันซ้ำ.
  4. **InteractionEngine** — one mousemove + rAF, `onMove/offMove(fn)` → ผ่าน `FXBus 'cfx:move'` (must `offMove` หรือ leak listeners). **HARD: `onMove` ต้องคืน `fn` เดิม** (fx-liquid/halo ใช้ identity กับ `offMove`).
  5. **FX loader** — `FX.register({id, boot(ctx)})` / `FX.boot()`, `ctx = {Motion, reduced(), scroll(), move(), offMove(), onToggle(), on(name, fn, priority)}` (`on` = ฟัง event FXBus เช่น 'cfx:boot:mod') และ `FX.actor(type, fn)` + `FX.callActor(type, el)`, `FX.api.bindCardLight` (ให้ fx-morph ใช้ตอนเปิด lightbox), **`FX.watchAttr(node, attr, onChange)` = attribute-observer ที่ปลอดภัยจาก infinite loop** (การ์ดเทียบค่า `lastWritten` ให้อัตโนมัติ — โค้ดที่ฝัง observer ฟัง attribute ที่ตัวเองต้องเขียนควรผ่านตัวนี้เสมอ ดู recipe #9) และ **`FX.toast(msg[, level, icon, dur])` = island toast ตัวเดียวของระบบ** (Motion.toggle ก็เรียกตัวนี้). boot แยก try/catch ต่อ mod — mod ที่พังไม่ฉุด core/mod อื่น + emit `cfx:boot:start/mod/done` (mod ผูก lifecycle ได้). **FX.boot() เดี๋ยวนี้ถูกเรียกจาก fx-boot.js (materializer) ไม่ใช่ script tag ตรง** — หลัง inject effect ที่จำเป็นเสร็จเท่านั้น (ดูด้านล่าง).
  6. **Core UX** (ใน motion-core) — island modal (`window.islandConfirm`/`islandAlert` + `data-confirm` auto-wire), back-top, theme toggle, body loaded, **cart AJAX (debatable — อยู่จริงใน `cart.html` block extra_js ไม่ใช่ motion-core; motion-core จัด island/confirm ให้)**, slip OCR, copy chips, pay highlight.
- **Runtime error diagnostic (debug-only)**: motion-core ผูก `window 'error'` + `'unhandledrejection'` → เก็บเข้า `FX._report(tag, label, e)` (console.group พร้อมแหล่งที่มา + island toast เฉพาะ `window.__DEBUG__=true`) — มีไว้**ช่วยหาว่า error มาจาก mod/script ไหน**, ไม่ใช่ตัวตรวจจับ "ค้าง/main-thread starve" (โค้ดไม่รันตอน main thread ตาย — กันค้างต้องใช้ watchAttr/recipe #9 ที่ต้นทาง). `window.__DEBUG__` ฉีดจาก `basetemplate` ผ่าน context processor `cart_context` (`{% if debug %}`) — **เฉพาะ dev (DEBUG=True); prod เงียบ**.
- **fx-assets.js / fx-boot.js — DeferredRegister ของ effect (หลัก NeoForge Registries)**: `myapp/static/js/fx-assets.js` = registry id→{css, js, match selector | always} ที่ **ไม่โหลดอะไรตอน register**; `myapp/static/js/fx-boot.js` = materializer: ตอน DOM ready → `FXAssets.needed(body)` scan element ว่าหน้านี้ใช้ effect ตัวไหน → `FXAssets.provide(ids)` dynamic inject เฉพาะตัว (CSS fire-and-forget, JS รอครบ) → แล้วค่อย `FX.boot()`. หน้า staff ธรรมดาโหลด ripple+magnetic+progress แทน 13 ไฟล์เก่า.
- **CSS eager (กัน FOUC — ต้องอยู่ใน head basetemplate ห้ามปลด)**: `theme.css` (core) → `fx-blur-up.css` (รูปซ่อนเบลอไว้ก่อน first paint) → `fx-reveal.css` (ซ่อน `[data-motion]`) → `fx-progress.css` (แถบอ่านหน้า). effect ที่ eager ตั้ง `css: null` ใน fx-assets.js เพื่อกัน inject ซ้ำ (เช่น blur-up). CSS effect ตัวอื่นเป็น decoration → inject ทีหลังได้ (ไม่ FOUC หนัก).
- **match selectors (ตารางเดียวที่รักษา — ต่อ effect ใหม่ต้อง register นี่ + เติม match ให้ตรง)**: ripple/progress = `always`; magnetic = `.btn-primary`; glass = `.hero-shell,.liquid-glass`; halo = `.card,.apple-tile,.liquid-glass`; liquid = `.liquid-mesh`; morph = `.card-expand[data-expand]`; card-pop = `[data-card-parallax]`; blur-up = `.product-img,.cart-thumb,.product-detail-image,.table-avatar,.placeholder-avatar`; skeleton = `.skeleton-img` (css-only); countup = `[data-motion="countup"]` (js-only); drag = `[data-drag-scope],[data-drag-track]`; playground = `.lab-shell`; parallax = `[data-motion="parallax"]`.
- **countup-retry (fx-boot)**: EntryEngine hoist (600ms) วิ่งก่อน effect JS โหลด (fx-boot ทำงานหลัง DOMContentLoaded — deferred) → ถ้า dashboard มี countup, fx-boot **ยิง countup ซ้ำ** หลัง boot เพื่อกัน `dataset.hoisted` ขวาง IO ถาวร — อย่าลบ.
- **js/effects/*.js** — 1 ไฟล์ = 1 เอฟเฟกต์ (countup/ripple/glass/progress/blur-up/magnetic/parallax/liquid/halo/card-pop/morph); แต่ละไฟล์ = `FX.register({id, boot})`, โค้ดเดียวกับเวอร์ชัน monolith เดิม morph (card-expand) เป็น interaction feedback → ไม่ถูก gate ด้วย `Motion.reduced()` — อย่าใส่ gate. liquid (aurora blobs หลังเลนส์) = decoration → gate; halo (backlight) = แสง ไม่ใช่ animation → **ไม่ gate** (เหมือน specular เดิม).
- **basetemplate.html**: จุดโหลดที่เดียว (adminbase extends มาอีกทอด): head = CSS eager 4 ตัว (theme → blur-up → reveal → progress) + inline `window.__DEBUG__` (จาก context processor `cart_context`, `{% if debug %}` — เปิดเฉพาะ dev); ท้าย body (ก่อน SVG lens) = `motion-core.js` → `fx-assets.js` → `fx-boot.js` (ลำดับนี้เท่านั้น — fx-boot ทำงานหลัง registry ครบ). ต่อเอฟเฟกต์ใหม่ = **register เข้า fx-assets.js (พร้อม match) + สร้างไฟล์** — ห้ามกลับไปเพิ่ม script/link effect ตรง basetemplate (ลบระบบ deferred) แต่ถ้าเป็น CSS ที่กัน FOUC ให้เพิ่มใน head eager + ตั้ง `css: null`.
- **Product cards** (`product_grid.html`): `class="... card-expand"` + `data-card-parallax` + `data-expand` + `data-detail-url` (note: `data-card-speed` was REMOVED — center-pop replaced depth-scroll; do not re-add).
- **Thai address cascade**: `thai-address.json` + `thai-address.js` — province → district → subdistrict dropdowns.
- **Chart.js** on reports page — dark-mode-aware, rebuilds on theme toggle.
- **Anti-Slop Design System (Skill: `anti-slop-design` / `DESIGN_SYSTEMS_FOR_CODING_AGENTS.md`)**: เมื่อสร้าง ปรับปรุง หรือแก้ไขหน้าเว็บ/UI ทุกหน้า ต้องปฏิบัติตามหลักการออกแบบ Anti-AI-Slop อย่างเคร่งครัด:
  - บัญชีดำ AI Tells: ห้ามแสงฟุ้งสีม่วง-ฟ้า (v0 trap), ห้ามตาราง 3 การ์ดซ้ำซาก, ห้ามเลขประดับปลอม 01/02/03, ห้ามคำโฆษณาสำเร็จรูป (Formulaic copy), ห้ามขาด active/focus-visible states
  - ยึดหลัก Domain Grounding, เลือก Visual Archetype ให้ชัดเจน 1 แนว (เช่น Apple Liquid Glass / Swiss Technical / Warm Editorial) และรักษา Token Contract เสมอ
- **User-Centric UX/UI Framework (Skill: `user-centric-ux-ui` / `USER_CENTRIC_UX_UI_GUIDELINES.md`)**: ยึดหลักการออกแบบเพื่อคนทำงานจริง (Empirical Enterprise UX):
  - 4 เสาหลัก: ปุ่มทำงานบ่อยมองเห็นได้ทันที (Action Availability), ไม่ทำลายบริบทเดิม (Context Preservation ผ่าน Side Drawer/Inline แทนการบังคับเปลี่ยนหน้า), รวมข้อมูลหน้าเดียวเลื่อนตรวจง่าย (Scrolling Beats Paging), ตารางข้อมูลแน่นพร้อมใช้ (High Data Density พร้อม Sticky Header และตัวเลข Monospace)
  - ปฏิบัติตามกฎจิตวิทยา UX (Fitts, Hick, Miller, Tesler, Postel, Doherty) และระบบ Inline Validation ("Reward Early, Punish Late") เสมอ
- **Color System Design (Skill: `color-system-design` / `COLOR_SYSTEM_GUIDELINES.md`)**: ยึดหลักวิทยาศาสตร์การมองเห็นและโครงสร้างระบบสีเชิงหน้าที่ (Perceptual Color Infrastructure):
  - ระบบสี OKLCH & Display P3: ความสว่างรับรู้คงที่ (Perceptual Uniformity), สถาปัตยกรรมโทเคน 3 ระดับ (Primitive -> Semantic -> Component)
  - กฎการกระจายพื้นที่ 60-30-10: สีพื้นผิว 60%, สีโครงสร้าง 30%, สีเน้น 10% เพื่อป้องกันสายตาล้าและคุม Visual Hierarchy
  - การเข้าถึง (A11y): WCAG 2.2 AA (4.5:1 / 3:1) / APCA, กฎ Dual-Encoding (ห้ามสื่อความหมายด้วยสีเพียงอย่างเดียว ต้องมีไอคอน/ข้อความกำกับเสมอ), ป้องกันตาบอดสี (CVD)
  - ฟิสิกส์โหมดมืด (Dark Mode): ไม่ Invert ดำ-ขาวตรงๆ, กฎ 87% Anti-Halation ป้องกันแสงฟุ้ง, ยกระดับชั้นด้วย Lightness แทนเงา, ลดความสดสี (Chroma Dampening) กันสีสั่น
  - บทบาทหน้าที่ 4 กลุ่ม (Semantic Quad: Success, Warning, Danger, Info) และกฎ Data Visualization (Categorical <= 8 สี, Sequential, Diverging)

## Bug Recipes — ทำแบบนี้แล้วเคยเกิด bug จริง (อย่าทำซ้ำ)

เก็บประวัติบั๊กที่เคยแก้จนเหนื่อย แต่ละข้อ = recipe ว่าอะไรทำให้พัง และกฎในการหลีกเลี่ยง

### 1. ห้ามใช้ PowerShell `Get-Content`/`Set-Content` อ่าน-เขียนไฟล์ไทย
- **สาเหตุ**: PowerShell 5.1 `Get-Content` อ่านไฟล์เป็น ANSI (cp874) ไม่ใช่ UTF-8 ต่อให้ `Set-Content -Encoding UTF8` ก็ตาม → ภาษาไทยทุกตัวกลายเป็น mojibake (`เธซเธเน...`), หน้าเว็บเพี้ยนทั้ง navbar
- **คนเคยทำ**: bump `?v=4`→`?v=5` ด้วย `(Get-Content file) -replace ... | Set-Content -Encoding UTF8`
- **กฎ**: อ่าน/เขียนไฟล์ template/static ด้วยเครื่องมือ Edit/Write ของ editor หรือ Python (`open(p, encoding="utf-8")`) เสมอ
- **วิธีตรวจจับบั๊กนี้**: ไฟล์ที่มี C1 control chars (U+0080–U+009F) หรือ grep เห็น `เธ[ก-๙]` แล้วอ่านเหมือนคำไทย เช่น `\u0e40\u0e18\u0e0b` ส่วนวิธีซ่อมคือ reverse `decode("cp874") → encode("cp874") → decode("utf-8")` เขียนด้วย Python (ทำแล้ว 1 ครั้ง ไม่ต้องทำซ้ำ)

### 2. Cache-busting ใช้ ?v= ยกเลิกแล้ว — ลืมว่าใช้ส่งหน้าเก่า
- **สาเหตุ**: เดิมแก้ `shop.js`/`theme.css` แล้วต้อง bump `?v=N` ใน `basetemplate.html` ทุกครั้ง → เบราว์เซอร์เสิร์ฟไฟล์เก่าจาก cache → ผู้ใช้/ตัว agent สรุปผิดว่า "แก้แล้วไม่เห็นอะไร"
- **สถานะปัจจุบัน**: **`?v=N` ถูกลบออกทั้งระบบแล้ว** (ใช้ `{% static %}` เปล่า ๆ) — root cause ที่แท้จริงของการ "แก้ไม่หาย" คือ OS `prefers-reduced-motion` (ดู recipe #3) ไม่ใช่ cache
- **กฎ**: แก้ไฟล์ static ⇒ ยืนยันผลด้วย browser hard-refresh (`Ctrl+Shift+R`) หรือ DevTools → Network → Disable cache. ถ้าตั้งใจประกาศผล อย่าล้นว่า "แก้แล้ว" จนกว่าจะเห็นผลจาก server จริง
- **วิธีเช็คว่า served จริง**: `Invoke-WebRequest http://127.0.0.1:8080/static/js/motion-core.js` แล้วดู content length กับล่าสุดในไฟล์ (ไม่ต้องเดา)

### 3. Motion toggle state ส่งผลต่อทุก animation และ reload ไม่ reset
- **สาเหตุ**: `Motion.reduced()` = `!enabled` ซึ่งอ่านจาก `localStorage['thammathad-motion']` — ถ้า user กด toggle OFF ไว้ (หรือ OS `prefers-reduced-motion: reduce` → default เก่าเป็น off) ทุก animation โดนปิด แม้ reload เบราว์เซอร์ใหม่ก็ยัง off → "still stiff, nothing changed" เป็นบั๊กที่วนตามมา 4 รอบ
- **กฎ HARD** (ตอนนี้ fixed แล้ว — ห้าม revert) : `Motion.init()` default = ON เสมอ; **OS `prefers-reduced-motion` ถูกตัดออกจากระบบทั้งหมด** (ทั้ง `@media` ใน theme.css และ `osReduced` ใน old-shop.js / ปัจจุบัน `motion-core.js` = 0) — ผูกกับปุ่ม ⚡ ในเว็บเท่านั้น กรรมการทั้ง OS และ localStorage จะไม่ปิด animation
- **ห้ามเชื่อมการตั้งค่าเปิด/ปิดอนิเมชั่นของ OS เข้าสู่ระบบนี้เด็ดขาด** (`prefers-reduced-motion` / `matchMedia` / `osReduced` / `@media (prefers-reduced-motion)`)— ระบบนี้เคยพังทั้งหมดเพราะสาเหตุนี้หนึ่งครั้ง (ธ.ค. 2025) ถ้าเห็นโค้ดเรียก `prefers-reduced-motion` ให้ถือว่าเป็นบั๊กด่วน ไม่ใช่ feature
- **มอร์ฟ modal (card-expand)**: เป็น interaction feedback (เหมือน lightbox) → ไม่ถูก gate ด้วย `Motion.reduced()` — อย่าใส่ gate ถ้ามีคนแก้เปิด morph ให้มอร์ฟทำงานเสมอ
- **เวลาตรวจว่า animation หาย**: เปิด console → `document.documentElement.dataset.motion` = `"on"` หรือ `"off"` (มีค่า `"off"` ได้จากปุ่ม ⚡ เท่านั้น)

### 4. เบราว์เซอร์ staging/local ก่อน deploy: อย่าเดา"เขาต้องเห็นเวอร์ชันใหม่"
- **สาเหตุ**: ไฟล์แก้แล้วแต่ไม่ได้ deploy prod (PythonAnywhere) หรือ served เป็น cache เก่า → ผู้ใช้เห็นของเก่าทั้งที่ local ถูก
- **กฎ**: ก่อนคอนเฟิร์มว่า"เปลี่ยนแล้ว" ให้ verify จาก server ด้วย URL ที่เสิร์ฟจริง (โดยเฉพาะ `?v=N` URL) หรือ deploy + Reload ให้เสร็จก่อน

### 5. `?v=N` + staticfiles ต้อง synced (ใช้ไม่ได้แล้ว — เลิกใช้ ?v=N)
- **สาเหตุ**: edit เฉพาะ `myapp\static` แต่ไม่ได้ copy ไป `staticfiles\` (product จริง) → local ดูถูก, production ฟ้องเก่า
- **กฎ**: หลังแก้ static (theme.css / motion-core.js / effects/*) → ต้อง `Copy-Item` ไป `staticfiles\... -Force` ทุกครั้ง (หรือคิดว่าจะ collectstatic ก่อน deploy) — ปัญหาแยกจาก caching ตรงกันข้าม: `myapp\static` + `staticfiles` ต่างกันคนละโลก อย่าแก้ครึ่งเดียว

### 6. Test ด้วย Django client ไม่ใช่ curl
- **สาเหตุ**: เข้าใจผิดว่าแค่ `GET` 200 ก็พอ แต่บางหน้า (การ์ด AJAX, admin) ต้อง login/session + expected JSON partial
- **กฎ**: ใช้ snippets ใน "Test Commands" (force_login teacher) ตาม pattern เสมอ

### 7. runserver 8080 เก่าค้าง — หน้าเสิร์ฟโค้ดเก่าทั้งที่โค้ดถูก
- **สาเหตุ**: เจอ runserver `8080` ค้าง 4 processes (PID 6060/38716/6740/26500) จาก session เก่า — ตัวที่ LISTENING จริงยังเสิร์ฟเทมเพลตเก่า (ไม่มี `@keyframes rowIn`), หน้า `/employees/` ดูแข็งไม่มีอนิเมชั่น ทั้งที่ Django test client กับโค้ดล่าสุดเห็นครบ → ผมเข้าใจผิดว่าโค้ดพัง ทั้งที่จริง server เก่า (ใช้เวลาไล่บั๊กนานโดยไม่จำเป็น)
- **กฎ**: ถ้า "แก้โค้ดแล้วแต่ server ไม่เห็น" (แต่ test client ผ่านเสมอ) → เช็ค process ก่อน และปิด-เปิด server ใหม่ทุกครั้ง: `netstat -ano | findstr :8080 | findstr LISTENING` → ดู PID → `Get-CimInstance Win32_Process -Filter "Name like '%python%'"` เพื่อนับ/ฆ่า `runserver 8080` บางตัว/ทั้งหมด → `Stop-Process -Id <pid> -Force` → เริ่มใหม่ 1 ตัว
- **วิธีเริ่มใหม่พอร์ต 8080**: `Start-Process -FilePath "D:\django_project\my_django_app\.venv\Scripts\python.exe" -ArgumentList "manage.py", "runserver", "8080" -WorkingDirectory "D:\django_project\my_django_app" -WindowStyle Hidden`
- **วิธียืนยันว่า server เสิร์ฟรหัสจริง (ไม่ใช้ cache)**: ดึงหน้า staff ผ่าน Invoke-WebRequest เฉพาะ ถ้า login ทำงานจริง (หน้า 401 → อธิบายว่า ต้องใช้ session login ผ่าน test client ไม่ใช่ Invoke-WebRequest ตรงๆ), และ template ที่ "ตรวจเช็ค html" ต้องดูผ่าน test client (force_login teacher) เพราะหน้า staff ต้อง auth
- **ยึดเป็นปกติ**: ก่อนประกาศ "แก้แล้ว แต่ยังไม่เห็น" → ก็ปิด-เปิด runserver (หรือตรวจ PID ค้าง) ก่อนเสมอ เพราะ process ค้างเป็นตัวการทั่วไป (เห็น 2 ครั้งแล้ว)

### 8. UTF-8 BOM ใน template → Quirks Mode → navbar ไม่ชิดขอบบน (24px gap + หน้าเลื่อนหลังโหลด)
- **สาเหตุ**: ทุกไฟล์ `myapp/templates/*.html` (30 ไฟล์) เริ่มต้นด้วย BOM `EF BB BF` — editor/export เก่าใส่ให้ (Django อ่าน BOM เป็น text แล้ว flush ออกมาก่อน `<!DOCTYPE html>`) → เบราว์เซอร์ปิ๊กว่า text อยู่หน้า DOCTYPE → เข้า **Quirks Mode** (`document.compatMode === "BackCompat"`) → UI แปลกทั้งระบบ: navbar จมลง ~24px (มี gap เหนือแถบ, ไม่ชิดขอบบน), หน้า "เลื่อนลงมานิดนึงให้แถบชิดพอดี" หลังโหลด, body children เริ่มด้วย META/TITLE แทน NAV (เหมือน head เลื่อนลงมา), ขนาด font/box-sizing ต่างจาก Standard Mode
- **สังเกตอาการ**: แม้ hard-refresh/Incognito ก็ไม่หาย, เกิดทั้ง 8080 และ PythonAnywhere (เพราะ template ผิดทั้งสองที่), CDP วินิจฉัยเจอ `compatMode: "BackCompat"` + `navTop: 24` เสมอ
- **สถานะปัจจุบัน**: **ลบ BOM ออกจาก templates ทั้งหมดแล้ว (ทำ 1 ครั้ง) — ห้ามนำกลับมา**
- **กฎ**: ห้ามเสกไฟล์ `.html` ใน `myapp/templates/` ที่ขึ้นต้นด้วย BOM — เขียนด้วยเครื่องมือ Write/Edit หรือ Python `open(p, "wb")` ต้องไม่มี `\xef\xbb\xbf` นำหน้า. และห้ามแก้ไฟล์ .html ด้วย PowerShell `Set-Content`/`Out-File` (นอกจากเสี่ยง mojibake recipe #1 ยังเสี่ยงต่อบั๊กนี้ด้วย)
- **วิธีตรวจจับ**: 
  - fast check ทุก template: ไฟล์แรก 3 bytes == `EF BB BF`:
    ```powershell
    Get-ChildItem "myapp\templates" -Filter *.html | ForEach-Object { $b=[IO.File]::ReadAllBytes($_.FullName); if($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF){ $_.Name } }
    ```
  - verify ฝั่ง server: response เริ่มที่ `3C 21` (`<!DO...`) ไม่ใช่ `EF BB BF`:
    ```powershell
    (Invoke-WebRequest http://127.0.0.1:8080/ -UseBasicParsing).RawContentStream.ToArray()[0..2]
    ```
  - verify ในเบราว์เซอร์: console → `document.compatMode` ต้องเป็น `"CSS1Compat"` (ถ้า `"BackCompat"` = มี text หน้า DOCTYPE), และ `document.getElementById('navbar').getBoundingClientRect().top === 0`
- **วิธีซ่อมถ้าเห็นอีก** (ลบ BOM ไฟล์เดียวหรือทั้งโฟลเดอร์ — ใช้ Python ห้ามใช้ PowerShell):
  ```python
  import os
  for dp, _, fns in os.walk(r"myapp/templates"):
      for n in fns:
          p = os.path.join(dp, n)
          with open(p, "rb") as f: d = f.read()
          if d[:3] == b"\xef\xbb\xbf":
              with open(p, "wb") as f: f.write(d[3:])
              print("stripped:", p)
  ```
  แล้วต้อง `runserver` ใหม่ (template load เข้า cache ของ process — ปิด-เปิดตาม recipe #7)
- **หมายเหตุ**: ไฟล์ `static/` (css/js) บางตัวก็เคยมี BOM เก่าเหมือนกัน แต่ไม่ก่ออาการนี้ (เพราะ CSS/JS ต่อท้ายเนื้อหาไม่กระทบ doctype) — ยังไว้แบบเดิมได้ แต่ห้ามนำ BOM กลับมาใน template

### 9. MutationObserver ฟัง attribute ที่ตัวมันเองเขียน → infinite loop = หน้าขาว + ค้างทั้งเว็บ
- **สาเหตุ**: ใน `index.html` (Product Rail) มี `MutationObserver` ฟัง attribute `data-drag-idx` บน `[data-drag-track]`; และ `syncRail()` ก็เขียน attribute ตัวนั้นเอง (ใช้ sync ปุ่ม ← → / จุด) — กลไก guard เดิมเป็น boolean (`suppress = true` รอบ `setAttribute` แล้ว `suppress = false`) **ใช้ไม่ได้** เพราะ MutationObserver callback เป็น **async microtask**: มันรันทีหลัง synchronous code **เสมอ** → ตอน callback ทำงาน `suppress` ถูก reset เป็น `false` แล้ว → `syncRail(readIdx())` → เขียน attribute ซ้ำ → คิว mutation ใหม่อนันต์ วนซ้ำไม่จบ
- **จุดที่จับยาก**: Chrome re-queue mutation record แม้ `setAttribute` ค่าเดิมซ้ำ (ค่าไม่เปลี่ยน = ยังฟ้อง) — ฉะนั้น ต่อให้เขียน `"0"` ซ้ำ ๆ ก็วนจริง ไม่ใช่แค่กรณีค่าเปลี่ยน ตรวจเจอด้วย headless probe: `--dump-dom` + ตัวบันทึกค่า attribute → เห็น `data-hist=",0,0,0,0,0,0,0,0,0,0,0,0"` (= observer วิ่งซ้ำหลายรอบด้วยค่าเดิม) เสมอ
- **กฎ**: ถ้าจะให้ observer กันการตอบสนองการเขียนของตัวเอง ต้อง**เทียบค่า** ไม่ใช่ boolean สลับเปิด-ปิด (แบบ async-safe): จดค่าที่ตัวเองเขียนล่าสุด (`lastWritten`), callback ตรวจ `if (v === lastWritten) return;` (echo ของตัวเอง → ข้าม) ถ้าต่าง (= user/โค้ดอื่นเขียนจริง) → ค่อย sync — **วิธีปฏิบัติตัวจริง: ฝังผ่าน `FX.watchAttr(node, attr, onChange)` ใน motion-core ที่ฝังการ์ดนี้ให้อัตโนมัติ แล้วเขียนกลับด้วย `watch.set(v)`** (index.html ใช้แบบนี้แล้ว อย่าเขียน MutationObserver ตรง ๆ) — ห้ามถอยกลับไปใช้ boolean อย่างเด็ดขาด
- **วิธีตรวจจับ**: หน้าเดียว (index) ขาว+ไม่ตอบสนอง ไม่มี error ใน console/network เหมือนเดิม — เข้าเกิดจากหน้าเดียวได้; headless บน `/` ค้าง TIMEOUT แม้ `--dump-dom` + `--virtual-time-budget` (microtask loop ไม่กิน virtual time เหมือน network wait); ตัดพรูฟ: ลบ `obs.observe()` → หาย; snapshots ยังอยู่ใน `myapp/static/test/` (v0.html = ห้องทดสอบที่จำลองค้างได้)
- **ข้อควรจำจากคดีนี้**: headless ใหม่ `--disable-javascript` **ไม่ปิด inline script** (probe พิสูจน์ JS_RAN=True) — อย่าใช้โหมดนี้เป็นตัวแบ่ง "JS on/off" และการสรุปว่า "NOJS ผ่าน = ตัวผมถูก" อาจมาจาก noise ต้อง rerun deterministic (3x) ก่อนเชื่อ และระวัง headless เก่าค้าง process (Stop-Process ก่อนรัน) + verify ตอนแก้จาก **served HTML** ไม่ใช่ source เฉย ๆ (recipe #2/#4/#7)

### 10. เทสต์ DRF API: 415/403 หลอกตา (ไม่ใช่บั๊ก API — เช็คก่อนสรุปว่า API พัง)
- **สาเหตุ (415)**: Django 6.0 เปลี่ยน default `content_type` ของ `Client.patch()`/`put()` เป็น `application/octet-stream` (ไม่ใช่ multipart; เฉพาะ `post()` ที่ยังเป็น multipart) → DRF ไม่มี parser ที่ media type ตรง → ตอบ `415 Unsupported Media Type` ทั้งที่ API ทำงานถูกต้อง (ยืนยัน: `rest_framework.test.APIClient` ยิง `format='json'`/`'multipart'` ได้ 200)
- **กฎ**: เทสต์ PUT/PATCH ของ DRF ต้องระบุ `content_type='application/json'` + `json.dumps(data)` เอง (หรือใช้ `APIClient` กับ `format='json'`) — อย่าเชื่อ default ของ Django test client
- **401 vs 403**: endpoint ที่ต้อง auth (เช่น `/api/employees/`) ตอบ **403 ไม่ใช่ 401** เมื่อไม่ auth/token มั่ว เพราะ `SessionAuthentication` เป็น authenticator ตัวแรกและ `authenticate_header` เป็น None → DRF แปลง `NotAuthenticated` เป็น 403 (เทสต์เดิมจึงใช้ `assertIn(status, (401, 403))` — assert `401` ตรง ๆ จะพัง)
- **วิธีตรวจจับ**: เทสต์ PATCH/POST ได้ 415 แต่ live curl/APIClient ได้ 200 → ดู `CONTENT_TYPE` ที่ test client ส่งจริงก่อนสรุปว่า API พัง (อ้างอิง: `myapp/tests/test_api.py` — `test_token_full_crud_flow`)

### Conventions

- **Thai language** for ALL user-facing text (labels, messages, template content, model verbose_name).
- **Advanced comments เป็นข้อกำหนดของใบงาน — ห้ามลบ/ลดระดับ**: โค้ด Python มี docstring ไทยแบบ Google-style (โมดูล header + class/method รวมถึง Args/Returns/Raises), JS มี JSDoc (engine/mod/ฟังก์ชัน), template มี header `{# #}` อธิบายหน้าที่+สายเงิน+edge case รวมถึงบันทึกบั๊กสำคัญ (เช่น Motion toggle re-observe, บันไดสถานะ, PaymentService จุดรับเงินจุดเดียว). แก้/เขียนโค้ดใหม่ในโปรเจกต์นี้ต้องรักษาระดับข้อมูลนี้ไว้เสมอ (เดิมเคยเป็น "no comments" — ถูกแทนด้วยกติกานี้แล้ว).
- **Glass modals only — ห้ามใช้ native `confirm()`/`alert()`/`prompt()`**: form ลบ/อันตรายใช้ `data-confirm="..."` (auto-wired ผ่าน motion-core), โค้ด JS ใช้ `islandAlert(msg[, title])` — ทั้งคู่แสดงเป็นกล่องแก้ว `.glass-confirm-card`. Native กล่อง Window/เบราว์เซอร์ไม่ตรงธีมและเคยถูกแทนทั้งหมดแล้ว (ตัวอย่างแก้: account.html ลบที่อยู่, product_form.html alert AI)
- **OOP patterns**: QuerySets, Managers, Mixins, Services, CBV with `.as_view()`.
- **AJAX pattern**: ตรวจด้วย **`is_ajax(request)`** (`myapp/views.py`) เท่านั้น — จุดเดียวของทั้งระบบ (ห้ามเขียน `request.headers.get('X-Requested-With') == ...` เองใน view ใหม่) รองรับ:
  - `X-Requested-With: fetch` = มาตรฐานของโปรเจกต์ · `XMLHttpRequest` = compat ของไลบรารี/โค้ดเก่า
  - `X-Drawer: true` · `?drawer=1` · ฟิลด์ฟอร์ม `ajax=1` = order drawer
  - `?partial=1` = fragment สาธารณะที่ต้องแชร์ URL ได้ (product grid, cart panel)
  เป็น AJAX → คืน JSON/partial · ไม่ใช่ → redirect/หน้าเต็มตามเดิม (progressive enhancement)
  เทสต์สัญญานี้: `myapp/tests/test_ajax_convention.py`
- **Pagination**: 5-15 items/page depending on entity. Preserves search/filter query params across pages.
- **`|urlencode`** required on all pagination query params in templates.
- **`{% csrf_token %}`** in all POST forms. AJAX stock-adjust reads CSRF from a standalone token in the page.

## Deployment

See `DEPLOY.md` for full PythonAnywhere steps.

### Zip Build (Windows)

```powershell
# From project root — ZIP อัปเดตต้องมี myproject ด้วย (settings.py/urls.py เปลี่ยนบ่อย)
# และ staticfiles/ ต้องอยู่ในไฟล์ เพราะ production serve จากโฟลเดอร์นั้น
# --exclude=test กัน debug snapshot (recipe #9) ไม่ให้หลุดขึ้น production
tar.exe -a -c -f pa_update.zip --exclude=__pycache__ --exclude=.venv --exclude=db.sqlite3 --exclude=pa_update.zip --exclude=media --exclude=test myapp myproject staticfiles requirements.txt DEPLOY.md
```

> ⚠️ เคยพลาด: recipe เดิมใส่แค่ `myapp staticfiles\workshop4.html` → ไฟล์ `workshop4.html`
> ไม่มีอยู่จริง และ **ตก `myproject/` ทั้งโฟลเดอร์** = settings.py/urls.py บน server
> ไม่ถูกอัปเดต (เป็นบั๊กเงียบ — เว็บยังรันได้แต่เป็น config เก่า)
> ตรวจหลังสร้าง ZIP: `tar.exe -tf pa_update.zip | Select-String 'myproject/settings.py'` ต้องเจอ

### เอกสารส่งอาจารย์ — `SUBMISSION.md`

คู่มือสำหรับผู้ตรวจงาน: ระบบคืออะไร · ต้องลองอะไรเพื่อดูว่าครบ ·
จุดที่ออกแบบมาเป็นพิเศษ · ข้อจำกัดที่ทราบ (เปิดเผยตรง ๆ ไม่อ้างเกินจริง)
**เมื่อเพิ่มฟีเจอร์ใหม่ ต้องอัปเดตไฟล์นี้ด้วย** — เป็นสิ่งที่อาจารย์เปิดอ่านก่อน

### Deploy Flow

1. Upload `pa_update.zip` via PythonAnywhere Files tab
2. Bash: `cd ~/my_django_app && unzip -o ~/pa_update.zip && rm ~/pa_update.zip`
3. If migrations changed: `workon django-shop && python manage.py migrate`
4. If new static files: `python manage.py collectstatic --noinput`
5. Web tab → Reload

### Critical: staticfiles sync

`staticfiles/` is what production serves. After editing `myapp/static/css/theme.css`, `myapp/static/js/motion-core.js`, or any `effects/*` file, you MUST copy to `staticfiles/` or run `collectstatic`. The zip includes both directories — if `staticfiles/` is stale, the deployed site shows old code.

```powershell
Copy-Item "myapp\static\css\theme.css" "staticfiles\css\theme.css" -Force
Copy-Item "myapp\static\css\effects\*.css" "staticfiles\css\effects\" -Force
Copy-Item "myapp\static\js\motion-core.js" "staticfiles\js\" -Force
Copy-Item "myapp\static\js\effects\*.js" "staticfiles\js\effects\" -Force
```

## Security Notes

### Fail-closed (settings.py) — ลืมตั้ง env = พังเห็นชัด ไม่ใช่รั่วเงียบ ๆ

| ค่า | dev (เครื่อง) | production (PythonAnywhere) |
|---|---|---|
| `DJANGO_DEBUG` | `1` ใน `.env` | **`0` ต้องตั้งใน Web tab** |
| `DJANGO_SECRET_KEY` | ค่า dev ใน `.env` | **ค่าสุ่มใหม่ของ production** |

- `DEBUG` **ไม่มี default เป็นเปิด** — เดิมเป็น `default='1'` (fail-open) ซึ่งแปลว่า "ลืมตั้ง env = หน้า error สีเหลืองโชว์ `GEMINI_API_KEY` + hardening 7 ข้อที่อยู่ใต้ `if not DEBUG` ไม่ทำงาน" และ**ระบบยังรันได้ปกติจึงไม่มีอาการให้สังเกต**
- `SECRET_KEY` ไม่มี dev key ฝังในโค้ดแล้ว (เคย hardcode + commit ไปแล้ว = ใครก็อ่านได้จาก git และ forge cookie ได้ถ้า prod ลืมตั้ง env) → production ที่ไม่มี key จะ `RuntimeError` ตอน boot
- สร้าง key: `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`
- Side effect ที่ต้องรู้: `SECURE_SSL_REDIRECT` ถูกปิด**เฉพาะตอนรันเทสต์** (`_RUNNING_TESTS`) เพราะ test client ยิง `http://` ถ้าไม่ปิดจะได้ 301 ทุก request ทำให้เทสต์ที่ต้องการ 200/403/429 พังหมด

### กัน brute force หน้า login — `LoginThrottle` (services.py)

`/api/token/` มี throttle แต่ `/staff/login/` + `/account/login/` เคยไม่มีเลย → 3 ชั้น:

| ชั้น | โควตา | กันอะไร |
|---|---|---|
| ต่อ IP | 20 / 5 นาที | DoS / distributed brute force |
| IP + ชื่อ | 8 / 5 นาที | credential stuffing |
| ต่อบัญชี | 5 / 15 นาที | account takeover แบบเจาะชื่อเดียว |

- ชั้นบัญชีนับจาก **ความล้มเหลว** ไม่ใช่จำนวนครั้งที่กด (ผู้ใช้ที่พิมพ์ถูกแต่กดซ้ำต้องไม่ถูกล็อกเอง)
- เข้าสำเร็จ → ล้างเฉพาะชั้นบัญชี · **ไม่ล้างชั้น IP** (ถ้าล้าง ผู้โจมตีเคลียร์ตัวนับตัวเองได้ทันที)
- ทุกกรณีที่โดนจำกัดตอบข้อความเดียวกัน (`LoginThrottle.MESSAGE`) — ห้ามแยกข้อความ ไม่งั้นผู้โจมตีเรียนรู้ว่าโดนชั้นไหน

### Audit trail — ActivityLog + `Audit` service

บันทึก "ใครทำอะไร เมื่อไหร่" สำหรับการกระทำที่กระทบเงิน/ของจริง/สิทธิ์บัญชี
→ หน้า `/staff/activity/` (ค้นหา + กรอง + ส่งออก CSV)

หลักการที่ยึด (สำคัญกว่าตัวฟังก์ชัน):
- **log พังห้ามทำให้งานหลักพัง** — `Audit.record()` กลืน error แล้วคืน `None`
- **เก็บเฉพาะ `Audit.SAFE_FIELDS`** — กันการ dump ข้อมูลส่วนตัวลง log
- **คง `actor_name` เป็นข้อความ** เพราะ FK เป็น `SET_NULL` — บัญชีถูกลบแล้ว
  ประวัติต้องยังบอกได้ว่าใครเป็นคน
- **อ่านค่าเดิมจาก `form.initial` ไม่ใช่ `form.instance`** — ModelForm เขียน
  `cleaned_data` ทับ `instance` ตั้งแต่ตอน `is_valid()` แล้ว (อ่าน instance
  ตอน `form_valid` จะได้ค่าใหม่ทั้งหมด → log ไม่บอกว่าอะไรเปลี่ยน)
- ปิดได้ด้วย `ACTIVITY_LOG_ENABLED = False` (ปิดอัตโนมัติตอนรันเทสต์)

จุดที่เรียก `Audit.record()`: ปรับสต็อก · เปลี่ยนสถานะออเดอร์ · ยืนยันยอดชำระ ·
สร้าง/แก้/ลบพนักงาน · สร้าง/แก้/ลบสินค้า · เปลี่ยนบทบาทบัญชี

### `manage.py preflight` — ตรวจความพร้อมก่อน/หลัง deploy (รันก่อนอัปโิลด์ ZIP เสมอ)

บั๊กที่ทำให้ "deploy แล้วเว็บพังแต่ไม่มีอาการ" ในโปรเจกต์นี้**มีรูปแบบเดียวกันหมด**: ระบบรันได้ปกติ แต่ไม่ได้ทำงานที่ตั้งใจ — preflight จับได้ในคำสั่งเดียว

```bash
python manage.py preflight           # exit 1 = มี FAIL (ห้าม deploy)
python manage.py preflight --quiet   # เฉพาะรายการที่ไม่ผ่าน
```

| ตรวจ | จับบั๊กอะไร |
|---|---|
| DEBUG / SECRET_KEY | ลืมตั้ง env → รั่ว (fail-closed) |
| ALLOWED_HOSTS | มี `*` หรือว่าง → Host header injection / ทุก request 400 |
| CSRF_TRUSTED_ORIGINS | ไม่มี → ผู้ใช้ส่งฟอร์มไม่ได้เมื่ออยู่หลัง proxy |
| HSTS | เปิดยาวเกิน 1 วัน → ถ้าพัง ผู้ใช้ถูกล็อกแก้ยาก |
| EMAIL_CONFIGURED | ยังไม่ได้ตั้ง → ลืมรหัสผ่านส่งไม่ถึงลูกค้า |
| staticfiles vs `myapp/static` | ไม่ sync → ผู้ใช้เห็น CSS/JS เก่า |
| migration | ยังไม่ apply หรือแก้ model ลืม `makemigrations` |
| ฐานข้อมูล | ไฟล์ไม่มี / `integrity_check` ไม่ผ่าน |
| ไฟล์ log | เขียนไม่ได้ → error หายเงียบ ไม่มี traceback ให้ไล่ |
| backup | ไม่มีไฟล์สำรอง หรือเก่ากว่า 2 วัน |

### Logging — `logs/` (หมุนรายวัน เก็บย้อนหลังได้)

| ไฟล์ | เก็บ | เนื้อหา |
|---|---|---|
| `logs/shop.log` | 14 วัน | ทุกอย่างระดับ INFO ขึ้นไป |
| `logs/error.log` | 30 วัน | ERROR เท่านั้น (ใช้ `django.request` / `django.security`) |

- เดิมไม่มี `LOGGING` เลย → ทุกอย่างไป `django.server` (console ของ WSGI)
  บน PythonAnywhere ต้องเปิดแท็บ Error log ถึงเห็น และ**ย้อนหลังไม่ได้**
- `handler500` log ผ่าน `django.request` ด้วย `logger.exception()` (ได้ traceback)
- **ตอนรันเทสต์ไม่เขียนไฟล์ log** (`_WRITE_LOG_FILES`) — กันเติมดิสก์/ผลไม่นิ่ง
- `logs/` อยู่ใน `.gitignore` + นอก `staticfiles/`

### สำรองฐานข้อมูล — `manage.py backup_db`

SQLite ไฟล์เดียว = ข้อมูลทั้งหมดอยู่ไฟล์เดียว ถ้าหายกู้ไม่ได้ → ต้องรันสำรอง

```bash
python manage.py backup_db --verify    # เก็บที่ backups/db-YYYYmmdd-HHMMSS.sqlite3 + ตรวจ integrity
python manage.py backup_db --keep 7    # ลบไฟล์เก่าเกิน 7
```

- ใช้ **sqlite3 online backup** (`Connection.backup()`) ไม่ใช่ `shutil.copy` → ได้ consistent snapshot แม้มี transaction กำลังวิ่ง
- ตรวจไฟล์ต้นฉบับก่อนเชื่อมต่อ กัน Django สร้างไฟล์ว่างให้เองแล้วสำรองของว่าง
- cron บน PythonAnywhere (พิมพ์มาให้ในผลลัพธ์ของคำสั่ง):
  `0 2 * * * .../bin/python ~/my_django_app/manage.py backup_db >> ~/my_django_app/backups/cron.log 2>&1`
- `backups/` อยู่ใน `.gitignore` + อยู่นอก `staticfiles/` (ไม่โดน collectstatic ไปด้วย)

### อื่น ๆ

- `/api/docs/` + `/api/schema/` = **IsAdminUser** (เคย AllowAny = เปิดโครงสร้าง API ทั้งระบบให้คนนอกดู)
- **Secrets via env vars**: `DJANGO_SECRET_KEY`, `GEMINI_API_KEY`, `SLIPOK_API_KEY` — loaded via `os.environ.get()` + python-dotenv `.env` file.
- **Production hardening** in settings.py: `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS` — activates when `DEBUG=False`.
- **Cart/logout POST-only**: GET requests to `/cart/add/`, `/cart/remove/`, `/cart/update/`, `/staff/logout/`, `/account/logout/` return 405 Method Not Allowed.
- **Admin credentials**: user `teacher` / pass `Shop2026!` (Django admin at `/admin/`).

## Template Hierarchy

```
basetemplate.html          Public base (navbar, footer, toast, theme switch, lens SVG)
  adminbase.html           Staff base (admin navbar with dropdowns, staff badge)
    dashboard.html, employee_list.html, product_manage.html, order_manage.html,
    customer_list.html, reports.html, payment_list.html, order_detail.html,
    customer_detail.html, product_form.html, employee_form.html

  index.html, product.html, product_detail.html, cart.html, checkout.html,
  order_tracking.html, order_success.html, contact.html, account.html,
  account_login.html, account_register.html, slip_upload.html, address_form.html
```

## Test Commands

No formal test suite. Ad-hoc testing via Django test client:

```powershell
# Smoke test (all pages render + auth + stock adjust):
$py = @'
import os, sys
sys.path.insert(0, r"D:\django_project\my_django_app")
os.environ["DJANGO_SETTINGS_MODULE"] = "myproject.settings"
import django; django.setup()
from django.conf import settings; settings.ALLOWED_HOSTS=["*"]
from django.test import Client
from django.urls import reverse
from django.contrib.auth.models import User
st = Client(HTTP_HOST="127.0.0.1")
st.force_login(User.objects.get(username="teacher"))
# ... test pages ...
'@
& ".venv\Scripts\python.exe" -X utf8 "$env:TEMP\test.py"
```
