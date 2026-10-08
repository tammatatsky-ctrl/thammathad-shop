# สถาปัตยกรรมพร้อมสำหรับเทียบกับ NeoForge (Registries / Sides / Events)

เอกสารนี้สรุปว่าระบบ frontend ของ Thammathad Shop ออกแบบโดย**จำลองแนวคิดของ NeoForge**
(mod loader ของ Minecraft) ขนาดไหนก่อนและหลัง refactor — ใช้ประกอบอธิบายสถาปัตยกรรมในรายงาน/การนำเสนอส่งงาน

> ไฟล์สำคัญที่อ้างอิง: `myapp/static/js/motion-core.js` (แกน + FXBus + FX loader),
> `myapp/static/js/fx-assets.js` (DeferredRegister), `myapp/static/js/fx-boot.js` (materializer),
> `myapp/static/js/effects/*.js` (mods)

## สรุปความเหมือน (ภาพรวม ~55% → ~70%)

| แนวคิด NeoForge | ก่อน refactor | หลัง refactor |
|---|---|---|
| Registries | ~85% | ~85% (เดิมอยู่แล้ว) |
| Events | ~45% | ~75% |
| Sides | ~35% | ~35% (สถาปัตยกรรม web = ต่างโดยเนื้อแท้) |

---

## 1. Registries — เหมือน ~85%

หลักของ NeoForge: ลงทะเบียนสิ่งของโดยไม่สร้างทันที (`DeferredRegister` → `DeferredHolder`),
**อย่า query registry ระหว่างกำลังลงทะเบียน**, แล้วค่อย materialize ทีเดียวหลัง registration เสร็จ.

| NeoForge | ระบบเรา | ตำแหน่ง |
|---|---|---|
| `DeferredRegister.create(reg, modid)` — register ราคาถูก | `FXAssets.register({id, css, js, match, always})` — แค่เก็บ config ไม่โหลดไฟล์ | fx-assets.js:93 |
| `DeferredHolder<T>` = supplier ที่ยังไม่ `.get()` | registry entry = config object ล้วน, inject เฉพาะตอน `provide()` | fx-assets.js:121 |
| **ห้าม query registry ระหว่าง registration** | เขียนเป็นกฎในโค้ดตรง ๆ: "query registry ต้องหลัง registration เสร็จ" | fx-assets.js:97-101 |
| Materialize = `DeferredRegister.register(modBus)` | `provide(ids)` + `FX.boot()` — dynamic inject เฉพาะ effect ที่หน้านั้นใช้ | fx-boot.js:24-44 |
| Query: `getValue(key)` / `containsKey` / iterate | `needed(body)` ไล่ match ว่าหน้าใช้ตัวไหน + `get(id)` | fx-assets.js:102-115 |
| Singleton ต่อ registry | แต่ละ effect register ครั้งเดียว, inject ครั้งเดียว (`loadedCss`/`loadedJs` กันซ้ำ) | fx-assets.js:37-38, 68-81 |

**ที่ต่าง**: key เป็น id แบน ๆ (`"ripple"`) ไม่มี namespace `modid:name` — เพราะระบบมี "mod" เจ้าของเดียว
(ไม่มีคนนอกมาลงทะเบียนให้ชนชื่อกัน) ความเสี่ยงที่ NeoForge สร้าง namespace มาป้องกันจึงไม่มีในบริบทนี้.

---

## 2. Events — เหมือน ~45% → ~75%

หลักของ NeoForge: event bus (subscriber แบบฟัง event ที่ตั้งชื่อ),
lifecycle ของ mod (constructor → register → setup → load complete), ลำดับความสำคัญ.

### หลัง refactor: `FXBus` (motion-core.js:27-71)

บัสเหตุการณ์เดียวของระบบ — fan-out ของทุกช่องถูกบังคับให้วิ่งผ่าน bus ตัวนี้:

| Event (namespace `cfx:`) | เกิดเมื่อ | ตำแหน่ง |
|---|---|---|
| `cfx:toggle` | กดปุ่ม ⚡ เปิด/ปิดอนิเมชั่น (broadcast เฉพาะตอน "เปิดกลับ" — รักษา behavior เดิม) | motion-core.js:169 |
| `cfx:scroll` | เฟรมที่ scroll (1 ครั้ง/rAF ผ่าน ScrollEngine) | motion-core.js:429 |
| `cfx:move` | เฟรมที่ mousemove (1 ครั้ง/rAF ผ่าน InteractionEngine) | motion-core.js:571 |
| `cfx:boot:start` / `cfx:boot:mod` / `cfx:boot:done` | lifecycle ของ FX.boot() — ทุก mod + ผล ok:true/false | motion-core.js:211-225 |

### การเทียบ

| NeoForge | ระบบเรา |
|---|---|
| game bus (เหตุการณ์ของเกม) | FXBus ช่อง `cfx:toggle`/`cfx:scroll`/`cfx:move` |
| mod bus (lifecycle การโหลด mod) | FXBus ช่อง `cfx:boot:*` + `ctx.on(name, fn, priority)` ให้ mod ดักได้ (motion-core.js:247) |
| `IEventBus.register` / `@SubscribeEvent` | `FXBus.subscribe(name, fn, priority)` → คืน `unsubscribe()` (motion-core.js:39-49) |
| `EventPriority.HIGHEST → LOWEST` | `FXBus.PRIORITY` (มากสุดฟังก่อน, เรียงตอน subscribe ไม่ sort ตอน emit) (motion-core.js:28-29) |
| unsubscribe `EVENT_BUS.register` | `off(name, fn)` แบบ identity รองรับ pattern `offMove(fn)` เดิม (motion-core.js:550) |

**priority ใช้งานจริงในระบบ**: `fx-progress.js:45` จอง `FXBus.PRIORITY.HIGH` ให้ตัวจับ scroll ของแถบ
อ่านหน้า เพื่อให้วิ่งก่อน subscriber ตัวอื่นที่อ่าน layout ในเฟรมเดียวกัน (glass/magnetic) —
ทำให้ path เรียงลำดับมีคนใช้จริง ไม่ใช่ API แขวน.

**ที่ตัดออก (ตั้งใจ)**: cancellable events / `TriState`/`Result` — ระบบเราไม่มีผู้ฟังที่ต้อง
"สั่งยกเลิก/โหวต" เหตุการณ์; `InterModComms` — ระบบเดียวไม่มี "mod คุย mod" ผ่านแพ็กเกจ.
ถ้าเพิ่มในอนาคตต้องมีเหตุผลประกอบจริง ไม่ใช่ใส่ตามแบบ.

---

## 3. Sides — เหมือน ~35%

NeoForge: logical server (ตรรกะเกม) vs logical client (แสดงผล) + `@EventBusSubscriber(dist=...)`
สำหรับสิ่งเฉพาะฝั่งเดียว. ของเราแยกตามหลัก "ใคร authoritative ใคร display" แต่คนละกลไก:

| NeoForge | ระบบเรา |
|---|---|
| logical server = กฎเกม | Django = ตรรกะโชว์: ตรวจราคา/สต็อก/สถานะออเดอร์/การเงิน (services.py) — เบราว์เซอร์แค่แสดงผล |
| `Level#isClientSide()` | ตรวจจับโหมดใน view ผ่าน `X-Requested-With == 'fetch'` (AJAX) |
| `FMLEnvironment#getDist()` (physical) | `window.__DEBUG__` (= `settings.DEBUG`) บังคับเปิด/ปิด diagnostic (basetemplate) |
| Sided event (เฉพาะ client) | เอฟเฟกต์โหลดเฉพาะหน้า + CSS eager head กัน FOUC — semantic เดียวกัน, ชั้นต่างกัน |

**ทำไมต่างโดยเนื้อแท้**: web ไม่มี "jar แยก client/server" ให้ต้อง guard ตอน pack —
เกิด side ไม่จำเป็นต้องมี mechanism ระดับนั้น.

---

## อะนาล็อกเสริม: "DOM = datapack"

`FXAssets.needed(body)` scan DOM ว่า `[data-motion=...]`/`.hero-shell`/`.card` ฯลฯ มีตัวไหน
→ คืนชุด effect ที่ "ถูกขอใช้" เหมือน NeoForge เปิด datapack ให้ระบบ entries
โดย DOM (หน้า template) เป็นตัวประกาศว่า "หน้านี้ใช้ mod อะไรบ้าง".

---

## สรุปเป็นประโยคเดียว

ระบบนี้เอา **แนวคิด Registries ของ NeoForge มาครบ**, เพิ่ม **event bus ฝั่ง client (FXBus)
ที่จำลอง game bus + mod bus**, ส่วน **Sides เราไม่ได้เลียนแบบกลไก** เพราะประเภทของ "สองฝั่ง"
ของเว็บ (server/browser) เดินคนละเส้นกับโลกเกม แล้ว.