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
  services.py       9 service classes: Cart, ThaiCalendar, ExchangeRate,
                    PromptPay, SlipOK, GeminiAI, Validators,
                    OrderStatusService, PaymentService
  api.py            DRF ViewSets (products read-only, orders read-only, employees CRUD)
  serializers.py    DRF serializers
  forms.py          EmployeeForm, StaffLoginForm
  context_processors.py   cart_context (injects cart_count to all templates)
  templates/        34 templates (Bootstrap 5, Thai labels, Liquid Glass style)
  static/
    css/theme.css   ~1150 lines: Apple Liquid Glass design system (core — เอฟเฟกต์แยกอยู่ effects/)
    css/effects/    9 FX mod CSS: fx-glass, fx-reveal, fx-progress, fx-blur-up, fx-card-pop,
                    fx-morph, fx-skeleton, fx-ripple, fx-parallax — โหลดทีละไฟล์ใน basetemplate
    js/motion-core.js   ~560 lines: Motion (ปุ่ม ⚡ จุดเดียว) + FX loader +
                    ScrollEngine / EntryEngine / InteractionEngine + core UX (island modal, slip OCR, ...)
    js/effects/     9 FX mod JS: fx-countup, fx-ripple, fx-glass, fx-progress, fx-blur-up,
                    fx-magnetic, fx-parallax, fx-card-pop, fx-morph — ลงทะเบียนผ่าน FX.register()
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
- **Service layer** (`services.py`): Cart (session-based), ThaiCalendar, ExchangeRate, PromptPay QR, SlipOK OCR, GeminiAI, Validators, OrderStatusService, PaymentService — no business logic in views.
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
- `/api/token/` — obtain auth token (POST)
- `/api/categories/` — category list
- Auth: Session (browser) or Token (`Authorization: Token xxx`)

### External Integrations (services.py)

| Service | Purpose | Setting |
|---|---|---|
| ExchangeRate | THB→USD from frankfurter.app | — |
| PromptPay | QR code for payment | `PROMPTPAY_ID` in settings |
| GeminiAI | Product description AI helper | `GEMINI_API_KEY` env var (empty = hidden) |
| SlipOK | Bank slip OCR verification | `SLIPOK_API_KEY` env var (empty = hidden) |

### Frontend

- **theme.css**: Apple Liquid Glass design system (core). Variables: `--ink`, `--ink-soft`, `--gray-bg`, `--apple-blue`, `--nav-bg`, `--ease-apple`. เอฟเฟกต์ (reveal, morph, ripple, ...) แยกอยู่ใน `css/effects/*.css` — core มีแต่ส่วนประกอบ/component transitions + motion-off gates ของ core เท่านั้น.
- **motion-core.js** (โหลดก่อนเสมอ) — core + FX loader (สถาปัตยกรรมแบบ mod loader):
  1. **Motion** — single source of truth: `ease`, `duration`, `enabled`, `reduced()`. ปุ่ม `#motionToggle` (⚡) สลับ `html[data-motion="on"|"off"]` + `localStorage('thammathad-motion')`. **จุด broadcast เดียว** ผ่าน `Motion.on(fn)` — toggle จะเรียกทุก listener (mod ใช้ `ctx.onToggle`). OS `prefers-reduced-motion` NOT consulted (0 occurrences).
  2. **ScrollEngine** — one scroll listener + rAF, `subscribe(fn)`.
  3. **EntryEngine** — one IntersectionObserver, dispatch `reveal`/`stagger` (เพิ่ม `.in`) + `countup` ผ่าน `FX.callActor('countup', el)`; **initial-load hoist** ใน `setTimeout(600)` เริ่ม reveal/stagger/countup ที่อยู่ในจอได้ทันที และ mark `el.dataset.hoisted` กัน IO รันซ้ำ.
  4. **InteractionEngine** — one mousemove + rAF, `onMove/offMove(fn)` (must `offMove` หรือ leak listeners).
  5. **FX loader** — `FX.register({id, boot(ctx)})` / `FX.boot()` (เรียกท้าย basetemplate หลัง script effects), `ctx = {Motion, reduced(), scroll(), move(), offMove(), onToggle()}` และ `FX.actor(type, fn)` + `FX.callActor(type, el)`, `FX.api.bindCardLight` (ให้ fx-morph ใช้ตอนเปิด lightbox). boot แยก try/catch ต่อ mod — mod ที่พังไม่ฉุด core/mod อื่น.
  6. **Core UX** (ใน motion-core) — island modal (`window.islandConfirm`/`islandAlert` + `data-confirm` auto-wire), back-top, theme toggle, body loaded, **cart AJAX (debatable — อยู่จริงใน `cart.html` block extra_js ไม่ใช่ motion-core; motion-core จัด island/confirm ให้)**, slip OCR, copy chips, pay highlight.
- **js/effects/*.js** — 1 ไฟล์ = 1 เอฟเฟกต์ (countup/ripple/glass/progress/blur-up/magnetic/parallax/card-pop/morph); แต่ละไฟล์ = `FX.register({id, boot})`, โค้ดเดียวกับเวอร์ชัน monolith เดิม morph (card-expand) เป็น interaction feedback → ไม่ถูก gate ด้วย `Motion.reduced()` — อย่าใส่ gate.
- **basetemplate.html**: จุดโหลดที่เดียว (adminbase extends มาอีกทอด): head = `theme.css` + `css/effects/*.css`; ท้าย body (ก่อน SVG lens) = `motion-core.js` + `js/effects/*.js` แล้วปิดท้ายด้วย `<script>FX.boot();</script>`. ต่อเอฟเฟกต์ใหม่ = เพิ่ม script/link ตรงนี้ + สร้างไฟล์ (เก็บลำดับ: core ก่อน, effects ทีละไฟล์, boot สุดท้าย).
- **Product cards** (`product_grid.html`): `class="... card-expand"` + `data-card-parallax` + `data-expand` + `data-detail-url` (note: `data-card-speed` was REMOVED — center-pop replaced depth-scroll; do not re-add).
- **Thai address cascade**: `thai-address.json` + `thai-address.js` — province → district → subdistrict dropdowns.
- **Chart.js** on reports page — dark-mode-aware, rebuilds on theme toggle.

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

### Conventions

- **Thai language** for ALL user-facing text (labels, messages, template content, model verbose_name).
- **Advanced comments เป็นข้อกำหนดของใบงาน — ห้ามลบ/ลดระดับ**: โค้ด Python มี docstring ไทยแบบ Google-style (โมดูล header + class/method รวมถึง Args/Returns/Raises), JS มี JSDoc (engine/mod/ฟังก์ชัน), template มี header `{# #}` อธิบายหน้าที่+สายเงิน+edge case รวมถึงบันทึกบั๊กสำคัญ (เช่น Motion toggle re-observe, บันไดสถานะ, PaymentService จุดรับเงินจุดเดียว). แก้/เขียนโค้ดใหม่ในโปรเจกต์นี้ต้องรักษาระดับข้อมูลนี้ไว้เสมอ (เดิมเคยเป็น "no comments" — ถูกแทนด้วยกติกานี้แล้ว).
- **Glass modals only — ห้ามใช้ native `confirm()`/`alert()`/`prompt()`**: form ลบ/อันตรายใช้ `data-confirm="..."` (auto-wired ผ่าน motion-core), โค้ด JS ใช้ `islandAlert(msg[, title])` — ทั้งคู่แสดงเป็นกล่องแก้ว `.glass-confirm-card`. Native กล่อง Window/เบราว์เซอร์ไม่ตรงธีมและเคยถูกแทนทั้งหมดแล้ว (ตัวอย่างแก้: account.html ลบที่อยู่, product_form.html alert AI)
- **OOP patterns**: QuerySets, Managers, Mixins, Services, CBV with `.as_view()`.
- **AJAX pattern**: Client sends `X-Requested-With: fetch` header → view returns JSON or template partial. Detect with `request.headers.get('X-Requested-With') == 'fetch'`.
- **Pagination**: 5-15 items/page depending on entity. Preserves search/filter query params across pages.
- **`|urlencode`** required on all pagination query params in templates.
- **`{% csrf_token %}`** in all POST forms. AJAX stock-adjust reads CSRF from a standalone token in the page.

## Deployment

See `DEPLOY.md` for full PythonAnywhere steps.

### Zip Build (Windows)

```powershell
# From project root:
Copy-Item "staticfiles\workshop4.html" "staticfiles\workshop4.html" -Force -ErrorAction SilentlyContinue
tar.exe -a -c -f pa_update.zip --exclude=__pycache__ --exclude=.venv --exclude=db.sqlite3 --exclude=pa_update.zip --exclude=media myapp staticfiles\workshop4.html
```

### Deploy Flow

1. Upload `pa_update.zip` via PythonAnywhere Files tab
2. Bash: `cd ~/my_django_app && unzip -o ~/pa_update.zip && rm ~/pa_update.zip`
3. If migrations changed: `python manage.py migrate`
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
