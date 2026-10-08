---
name: anti-slop-design
description: >-
  Design system and cognitive framework for coding agents to engineer distinctive,
  bespoke frontend web interfaces. Eliminates generic 'AI slop' aesthetics (such as
  predictable purple gradients, ubiquitous 3-card grids, Inter font defaults, and
  template monoculture) by enforcing domain grounding, opinionated design archetypes,
  token-driven constraints, and rigorous interaction craft.
---

# Design Systems for Coding Agents: Anti-AI-Slop Architecture
# ระบบการออกแบบสำหรับ Coding Agent: ป้องกันงานดีไซน์สำเร็จรูปสไตล์ AI (Anti-AI Slop)

> **Purpose / วัตถุประสงค์**:
> เมื่อ AI Coding Agents (เช่น Claude Code, Cursor, Antigravity, Copilot, v0) ถูกสั่งให้ "สร้างหน้าเว็บสวยๆ" หรือ "ออกแบบ UI ใหม่" โมเดลจะดึงค่าทางสถิติเฉลี่ย (Statistical Mean) ของโค้ดที่มีในชุดข้อมูลฝึกฝนออกมาโดยอัตโนมัติ ส่งผลให้เกิดหน้าเว็บหน้าตาซ้ำซาก ขาดเอกลักษณ์ และดูออกทันทีว่าเป็น **"AI Slop"** (งานดีไซน์สำเร็จรูปสไตล์ปัญญาประดิษฐ์)
>
> เอกสารนี้ทำหน้าที่เป็น **Machine-Readable Design System Contract** (สัญญาการออกแบบที่ Agent อ่านและเข้าใจได้) เพื่อบังคับให้ Coding Agent ข้ามค่าเริ่มต้นทั่วไป แล้วสร้างสรรค์ UI ที่มีระดับความประณีต มีเหตุผลรองรับ และดูเหมือนผลงานของดีไซเนอร์มืออาชีพที่เป็นมนุษย์

---

## 1. บัญชีดำสัญญาณเตือน "AI Tells" (The Anti-Slop Blacklist)

ก่อนที่ Agent จะเริ่มเขียนโค้ด HTML/CSS/Tailwind ให้ตรวจสอบและหลีกเลี่ยง **สัญญาณบ่งบอกว่าเป็น AI (AI Tells)** ต่อไปนี้อย่างเด็ดขาด หากหน้าเว็บมีลักษณะตรงกับ 3 ข้อขึ้นไป ผู้ใช้จะจับได้ทันทีว่าเป็นงานที่เจนจาก AI โดยไม่มีความประณีต:

### 1.1 กับดักสไตล์ยอดนิยม (Aesthetic Traps & Monocultures)
| ชื่อกับดักสไตล์ | สัญญาณบ่งบอก (The AI Tells) | สาเหตุที่ AI ชอบใช้ |
|---|---|---|
| **The "v0 / Vibe-SaaS" Monoculture** | พื้นหลังสีดำเข้มหรือน้ำเงินมืดมาก (`#090d16`), แสงฟุ้งสีม่วง-ฟ้า (Purple-to-Cyan Radial Glow), การ์ดกระจกแก้วเงา (`backdrop-blur` + `border-white/10`), ปุ่มขอบมนทรงแคปซูลพร้อมเส้นขอบสีเหลือบ | โค้ดเทมเพลต Landing page ของ AI ยุค 2023–2025 มีใน Dataset สูงเกินไป |
| **The "Anthropic Warm Cream"** | พื้นหลังสีครีมกระดาษ (`#F4F1EA`), ฟอนต์หัวเรื่อง Serif โบราณ, สีเน้นสีอิฐหรือดินเผา (`#D97757`), เส้นแบ่งบางเฉียบ 1px, ไร้ความโค้งมน (0px radius) | โมเดลเรียนรู้คู่สีและอัตลักษณ์องค์กรของตนเองมากเกินไปจนนำมาใช้เป็นค่าเริ่มต้น |
| **The "Neon Cyber Hacker"** | พื้นหลังสีดำสนิท (`#000000`), สีเขียวสะท้อนแสง (`#00FF66`) หรือสีส้มแสด, ซับไตเติลฟอนต์ Monospace, ป้ายตกแต่งสไตล์เทอร์มินัล | การเหมารวมอัตโนมัติเมื่อเจองานประเภท "Developer Tools" หรือ "Crypto/Web3" |
| **The "Linear / Vercel Copycat"** | โทนเทาดำสนิท, เส้นขอบบางเฉียบ (`#27272a`), แบดจ์วงกลมมีจุดกะพริบด้านบน, ฟอนต์ Inter ทุกจุด, การ์ดมืดที่เมาส์เลื่อนผ่านแล้วมีไฟฉายส่องตาม | การลอกเลียนแบบ UI ของบริษัทชั้นนำโดยไม่คำนึงถึงบริบทและประเภทธุรกิจจริงของลูกค้า |

### 1.2 ข้อผิดพลาดด้านฟอนต์และข้อความ (Typographic & Copywriting Tells)
- **นิสัยกดใช้ Inter / Roboto / System-UI โดยไม่คิด**: การเลือกฟอนต์กลางๆ ปลอดภัยไว้ก่อน ทำให้แบรนด์ขาดบุคลิก
- **ลูกเล่นเน้นคำเดี่ยวในพาดหัว (Single Accented Word Cliché)**: พาดหัวยาวๆ แล้วใส่สีไล่ระดับหรือทำฟอนต์เอียงแค่คำเดียว (เช่น `สร้างสรรค์ <span class="gradient">อนาคต</span> ของการทำงาน`)
- **คำโฆษณาสำเร็จรูปไร้ตัวตน (Formulaic Copywriting)**:
  - *"Supercharge your workflow"* (ยกระดับการทำงานของคุณ)
  - *"The modern all-in-one platform for [X]"* (แพลตฟอร์มที่รวมทุกอย่างสำหรับ...)
  - *"Elevate your experience"* (เปิดประสบการณ์ใหม่)
- **หัวข้อย่อยตัวพิมพ์ใหญ่ล้นเกิน (All-Caps Micro-Eyebrows)**: ใส่ `text-xs uppercase tracking-widest text-muted` ไว้เหนือทุกหัวข้ออย่างพร่ำเพรื่อ
- **เลขลำดับปลอม (Fake Sequential Numbers)**: ใส่เลข `01 / 02 / 03` ประดับหัวการ์ด ทั้งๆ ที่เนื้อหาไม่ได้เป็นขั้นตอนตามลำดับเวลาหรือกระบวนการทำงานจริง

### 1.3 ความซ้ำซากของโครงสร้างเลย์เอาต์ (Spatial & Structural Monotony)
- **ตารางการ์ด 3 กล่องมาตรฐาน (The Ubiquitous 3-Card Grid)**: แบ่งสัดส่วนทุก Section ออกเป็นกล่องสี่เหลี่ยม 3 คอลัมน์เท่าๆ กัน มีไอคอนด้านบน พาดหัว 2 บรรทัด และข้อความสั้น 3 บรรทัด
- **ตัวเลขสถิติสามเกลอ (The Metric Triptych)**: ตัวเลขขนาดใหญ่ 3 ตัวเรียงกัน (`99.9% Uptime`, `10M+ Users`, `4.9★ Rating`)
- **ภาพม็อกอัปเอียงลอยได้ (Floating Angled Mockup)**: ภาพจำลองหน้าแดชบอร์ดลอยเอียง 15 องศาพร้อมเงาสีม่วงฟุ้ง
- **จัดกึ่งกลางทุกสิ่งทุกอย่าง (Strict Center-Alignment Syndrome)**: แบดจ์กึ่งกลาง, หัวข้อกึ่งกลาง, คำอธิบายกึ่งกลาง, ปุ่มกดคู่กึ่งกลางตลอดทั้งหน้า

### 1.4 ความมักง่ายด้าน Interaction และอนิเมชั่น
- **Scatter Stagger**: ทุก Section ทำอนิเมชั่นเลื่อนขึ้นพร้อมเฟดอิน (Fade & Slide up) แบบเดียวกันทั้งหน้าเวลาเลื่อนเมาส์
- **Floaty Card Hover**: การ์ดทุกใบทำ `transform: translateY(-4px)` ลอยขึ้นพร้อมเงาฟุ้งเมื่อวางเมาส์
- **ขาดสถานะโต้ตอบ (State Blindness)**: ขาด `:focus-visible` สำหรับคีย์บอร์ด, ขาด `:active` แสดงการกดคลิก, ขาด Loading Skeleton, ขาด Empty State

---

## 2. กรอบการทำงาน 5 ขั้นตอนสำหรับ Coding Agent (The 5-Step Workflow)

เมื่อได้รับคำสั่งให้ออกแบบหรือปรับแต่งหน้าตาเว็บไซต์ ให้ปฏิบัติตามลำดับขั้นตอนดังนี้:

```
[โจทย์จากผู้ใช้ / User Brief]
          │
          ▼
[ขั้นที่ 0: ทำความเข้าใจบริบทแบรนด์ (Domain Grounding)] ──► หาเอกลักษณ์และภาษาของอุตสาหกรรมนั้นจริง
          │
          ▼
[ขั้นที่ 1: เลือกสไตล์หลักที่ชัดเจน (Visual Archetype)] ──► กำหนดแนวทางศิลป์ 1 แนว ไม่ปะปน
          │
          ▼
[ขั้นที่ 2: วางโทเค็นดีไซน์ (Design Tokens Contract)]   ──► โทนสี, ลำดับฟอนต์, สัดส่วนระยะห่าง, ขอบมน
          │
          ▼
[ขั้นที่ 3: จัดวางเลย์เอาต์แบบอสมมาตร (Asymmetry)]     ──► ใส่จังหวะหนักเบา, ความหนาแน่นของข้อมูล
          │
          ▼
[ขั้นที่ 4: เติมความสมบูรณ์ของสถานะ (Interaction Physics)] ──► Active, Focus-visible, Disabled, Empty
          │
          ▼
[ขั้นที่ 5: ตรวจสอบย้อนกลับ (Anti-Slop Pre-Flight Audit)] ──► ลบสัญญาณ AI ทิ้งก่อนส่งมอบโค้ด
```

---

### ขั้นที่ 0: ทำความเข้าใจบริบทแบรนด์ (Domain Grounding)
อย่าเริ่มออกแบบจากความว่างเปล่า จงตอบคำถามเหล่านี้ก่อน:
1. **โลกทางกายภาพของธุรกิจนี้คืออะไร?**
   - *ตัวอย่าง*: เว็บไซต์ระบบคลังสินค้า/โลจิสติกส์ มีที่มาจากบาร์โค้ด ฉลากตู้คอนเทนเนอร์ แถบเตือนสีสะท้อนแสง ตัวเลขน้ำหนัก และตารางข้อมูลที่อ่านได้ชัดแม้อยู่กลางแจ้ง
   - *ตัวอย่าง*: เว็บไซต์ร้านน้ำชาหรือเครื่องหอม มีที่มาจากผิวกระดาษสา สีดินเผา เนื้อไม้ธรรมชาติ จังหวะความเงียบ และช่องไฟที่โปร่งสบาย
2. **ผู้ใช้งานดูเว็บนี้ในสถานการณ์ใด?**
   - ผู้จัดการตรวจสต็อกบนแท็บเล็ตในโกดัง (ต้องการ Contrast สูง, ปุ่มกดง่าย, ข้อมูลกระชับ)
   - ลูกค้าเลือกชมงานคราฟต์ยามค่ำคืน (ต้องการความรู้สึกประณีต อบอุ่น ฟอนต์อ่านสบายตา)

---

### ขั้นที่ 1: เลือกสไตล์หลักที่ชัดเจน (Commit to an Opinionated Visual Archetype)

เลือกแนวทางใดแนวทางหนึ่งจาก 4 แบบนี้อย่างเด็ดเดี่ยว และคุมโทนให้ตรงกันทั้งระบบ:

#### 1. สไตล์สวิสและเครื่องมือเทคนิค (Swiss / Technical Utilitarian)
- **อารมณ์**: แผงควบคุมวิศวกรรม, หน้าจอห้องแล็บ, เครื่องมือวัดความแม่นยำสูง
- **ชุดสี**: พื้นเทาสเลทเข้ม (`#0b0f19`, `#1e293b`) + สีบอกสถานะชัดเจน 1 สี (International Klein Blue `#002fa7` หรือ Signal Amber `#f59e0b`)
- **ฟอนต์**: ตัวเลข/ข้อมูลใช้ Monospace (`JetBrains Mono`, `Geist Mono`), หัวข้อใช้ Sans ทรงเหลี่ยมเรียบคม (`Prompt`, `Plus Jakarta Sans`)
- **ขอบและเส้น**: ขอบมนเล็กน้อย (2px ถึง 6px), เส้นตารางคมชัด 1px ไม่เน้นเงาฟุ้ง

#### 2. สไตล์บรรณาธิการประณีต (Warm Crafted Editorial)
- **อารมณ์**: นิตยสารอิสระ, แกลเลอรีงานฝีมือ, สตูดิโอสถาปัตยกรรม
- **ชุดสี**: พื้นหลังสีกระดาษฝ้ายหรือลินิน (`#f9f8f6`, `#f2ede4`), ตัวหนังสือสีหมึกเข้ม (`#1c1917`), สีเน้นสีเขียวมะกอก (`#444a38`) หรือสีดินแดง
- **ฟอนต์**: หัวข้อใช้ Serif คลาสสิกทรงสง่า (`Playfair Display`, `Newsreader`, `Fraunces`), ข้อความใช้ Sans มนุษยนิยมอ่านง่าย
- **เลย์เอาต์**: การแบ่งคอลัมน์แบบอสมมาตร (เช่น 8:4), ช่องไฟกว้างขวาง, พาดหัวขนาดใหญ่ที่จัดวางเสมือนงานพิมพ์

#### 3. สไตล์มินิมอลโมโนโครม (Architectural Monochrome)
- **อารมณ์**: แบรนด์ลักชัวรีร่วมสมัย, งานสถาปัตยกรรมแถบสแกนดิเนเวีย
- **ชุดสี**: ขาว-ดำ-เทา 95% โดยสร้างมิติผ่านความทึบแสง (Opacity Layering) และการเว้นที่ว่าง **ปราศจาก Gradient สีฉูดฉาด**
- **ฟอนต์**: Sans สะอาดตา ลดระยะห่างตัวอักษรของหัวข้อลงเล็กน้อย (`letter-spacing: -0.02em`)
- **การจัดวาง**: อาศัยพื้นที่ว่าง (Negative Space) และความคมชัดของข้อความแทนการใช้กรอบและการ์ดลอย

#### 4. สไตล์อุตสาหกรรมสัมผัสได้ (Tactile Industrial / Neo-Craft)
- **อารมณ์**: ฮาร์ดแวร์สังเคราะห์เสียง (Synthesizer), อุปกรณ์เครื่องเสียงสไตล์ Teenage Engineering
- **ชุดสี**: พื้นเทาคอนกรีต เสริมด้วยสีอุตสาหกรรมสดชัด (Safety Orange `#ff5500`, Warning Yellow `#ffd000`)
- **ลูกเล่น**: เส้นขอบหนา 1.5–2px, ปุ่มกดที่มีมิติแบบ Bevel เล็กน้อย, ไอคอนสไตล์ Dot Matrix, สวิตช์สลับโหมดที่ให้ความรู้สึกกลไก

---

### ขั้นที่ 2: วางสัญญาโทเค็นดีไซน์ (Establish Token Contract)

ก่อนเริ่มเขียนคอมโพเนนต์ ต้องนิยามตัวแปรกลาง CSS Variables ให้ชัดเจน ห้ามใช้ค่าสี Hex หรือระยะห่างแบบสุ่มตามใจชอบ:

```css
/* DESIGN SYSTEM TOKENS CONTRACT */
:root {
  /* 1. Surfaces & Canvas (พื้นผิวตามระดับความลึก) */
  --surface-canvas:  #0b0f19;   /* พื้นหลังหลัก */
  --surface-raised:  #141b2d;   /* พื้นผิวการ์ด/คอนเทนเนอร์ */
  --surface-overlay: #1c263d;   /* หน้าต่างป๊อปอัป/โมดอล */
  --surface-sunken:  #070a12;   /* ช่องป้อนข้อมูล/แถบโค้ดจมลง */

  /* 2. Content Hierarchy (ลำดับสายตาข้อความ) */
  --text-primary:   #f8fafc;    /* ข้อความหลัก ชัดเจนสุด */
  --text-secondary: #94a3b8;    /* คำอธิบายรอง */
  --text-muted:     #64748b;    /* ข้อความประกอบ/คำใบ้ */
  --text-inverse:   #0b0f19;    /* ข้อความบนพื้นสว่าง */

  /* 3. Brand & Functional Accent (กำหนดไม่เกิน 1 สีหลัก + 1 สีเตือน) */
  --brand-primary:       #0284c7;  /* สีประจำแบรนด์เฉพาะทาง (เช่น Ocean Blue) */
  --brand-primary-hover: #0369a1;  /* สเตท Hover */
  --brand-accent:        #f59e0b;  /* สีเน้นสถานะรอง */

  /* 4. Structural Boundaries (เส้นขอบเพื่อโครงสร้าง ไม่ใช่เพื่อประดับ) */
  --border-subtle: rgba(255, 255, 255, 0.08);
  --border-strong: rgba(255, 255, 255, 0.18);
  --border-focus:  #38bdf8;

  /* 5. Spatial Scale & Radius (รัศมีความโค้งมนที่สอดคล้อง) */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-pill: 9999px;

  /* 6. Typography Scale */
  --font-display: 'Prompt', 'Plus Jakarta Sans', sans-serif;
  --font-body:    'Prompt', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono:    'JetBrains Mono', 'Consolas', monospace;

  /* 7. Physical Shadows (เงาที่มีทิศทาง ไม่ใช่แสงฟุ้งสีม่วง) */
  --shadow-subtle: 0 1px 2px 0 rgba(0, 0, 0, 0.35);
  --shadow-card:   0 4px 16px -2px rgba(0, 0, 0, 0.45);
}
```

---

### ขั้นที่ 3: จัดวางเลย์เอาต์แบบอสมมาตรและเน้นคุณค่าจริง (Asymmetric Layout & Craft)

ทำลายความจำเจของบล็อก 3 ช่องด้วยเทคนิคเหล่านี้:

1. **Hero Section ที่มีภารกิจจริง (Functional Hero)**:
   - เลิกใช้สูตร `หัวข้อ + คำโปรย + ปุ่ม 2 ปุ่ม` แบบโล่งๆ
   - นำ **ฟังก์ชันหลักของระบบ** มาแสดงตั้งแต่หน้าแรก เช่น ตัวคำนวณราคาแบบโต้ตอบได้, พรีวิวสินค้าพร้อมฟิลเตอร์จริง, ตารางแสดงสถานะอัปเดตล่าสุด
   - ใช้สัดส่วน 60:40 หรือ 65:35 แทนการจัดกลาง (ฝั่งหนึ่งเป็นพาดหัวทรงพลัง อีกฝั่งเป็นเครื่องมือจริง)
2. **การจัดกลุ่มแบบ Bento ที่มีลำดับความสำคัญ (Bento with Hierarchy)**:
   - หลีกเลี่ยงการทำกล่องขนาดเท่ากัน
   - **กล่องหลัก (Hero Box)**: กินพื้นที่ 2 คอลัมน์ ใส่การสาธิตแบบอินเทอร์แอคทีฟ
   - **กล่องรอง (Metric Box)**: มีกราฟเส้นขนาดเล็ก (Sparkline) หรือความเคลื่อนไหวจริง
   - **กล่องสเปก (Data Box)**: แสดงตัวเลขและหน่วยวัดในฟอนต์ Monospace ที่ดูเป็นมืออาชีพ
3. **ความลึกของเนื้อหา (Content Realism)**:
   - ใช้ข้อความจริง ตัวเลขราคาจริง ชื่อสินค้าจริง
   - เติมรายละเอียดที่มนุษย์ใส่ใจ เช่น แป้นพิมพ์ลัด `<kbd>⌘K</kbd>`, สถานะเซิร์ฟเวอร์แบบ Real-time, ป้ายระบุเวอร์ชันระบบ

---

### ขั้นที่ 4: เติมความสมบูรณ์ของสถานะโต้ตอบ (Interaction Physics)

ดีไซน์ของมนุษย์มีความใส่ใจในทุกสภาวะ (Complete State Machine):

```css
/* ตัวอย่างปุ่มมาตรฐานที่รองรับครบทุกสเตท */
.btn-crafted {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background-color: var(--brand-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 10px 20px;
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 14px;
  line-height: 1.4;
  cursor: pointer;
  /* การเคลื่อนไหวที่เป็นธรรมชาติ (Fast out, Slow in) */
  transition: background-color 120ms ease, border-color 120ms ease, transform 80ms ease, box-shadow 120ms ease;
  box-shadow: var(--shadow-subtle);
}

/* 1. Hover: ปรับความสว่างสี ไม่ใช่ขยับลอยอย่างไร้ทิศทาง */
.btn-crafted:hover {
  background-color: var(--brand-primary-hover);
  border-color: var(--border-strong);
}

/* 2. Active: กดแล้วยุบตัวลงตามแรงกดจริง */
.btn-crafted:active {
  transform: scale(0.975);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.2) inset;
}

/* 3. Focus-visible: วงแหวนเข้าถึงได้สำหรับคีย์บอร์ด ห้ามลบ outline ทิ้งเปล่า */
.btn-crafted:focus-visible {
  outline: 2px solid var(--border-focus);
  outline-offset: 2px;
}

/* 4. Disabled: จางลงและปิดตัวชี้ */
.btn-crafted:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}
```

---

### ขั้นที่ 5: ตรวจสอบย้อนกลับก่อนส่งมอบ (The Pre-Flight Anti-Slop Audit)

ก่อนจะสรุปงานโค้ดหน้าบ้าน ให้รันแบบประเมินตนเองนี้เสมอ:

| หัวข้อตรวจสอบ | สิ่งที่ผ่านเกณฑ์ (Pass) | สัญญาณเตือนที่ต้องแก้ทันที (Fail) |
|---|---|---|
| **จานสี (Color Palette)** | ใช้สีหลักไม่เกิน 1 สี + สีเน้นสถานะ 1 สี พื้นที่ 85%+ เป็นโทนกลางธรรมชาติ | แสงฟุ้งสีม่วง-ฟ้าเต็มจอ, ไอคอนทุกการ์ดใช้คนละสี, ไล่สีรุ้ง |
| **ตัวอักษร (Typography)** | ฟอนต์คู่ที่มีบุคลิกชัดเจน, ความยาวบรรทัดไม่เกิน 75 ตัวอักษร | ฟอนต์ Inter ทั้งหน้า, หัวข้อมีคำเอียงสีรุ้งคำเดียว |
| **ความหนาแน่น (Density)** | มีตารางข้อมูล, สถิติจริง, จังหวะการจัดวางอสมมาตร | การ์ด 3 ช่องเรียงกันเป๊ะๆ ทั้งหน้า, ข้อความ Lorem ipsum |
| **ภาษาคำโปรย (Copywriting)** | ภาษาตรงไปตรงมา ระบุข้อมูลทางเทคนิคและคุณประโยชน์ชัดเจน | คำเพ้อฝันสำเร็จรูป เช่น "Supercharge your future" |
| **เส้นสายประดับ (Decorations)**| เส้นและกรอบมีหน้าที่แยกกลุ่มข้อมูลจริง | เลข 01, 02, 03 ประดับไว้เฉยๆ ทั้งที่ไม่ใช่ขั้นตอน |
| **สภาวะการใช้งาน (States)** | มีครบทั้ง Default, Hover, Active, Focus-Visible, Disabled, Empty | มีแค่สี Default ไม่มีปฏิกิริยาเมื่อกดคลิกหรือกด Tab |

---

## 3. ตัวอย่างโค้ดพร้อมใช้งาน (Bespoke UI Recipes)

### ตัวอย่างที่ 1: หน้าต่างเครื่องมือระดับวิศวกรรม (Precision Technical Card)
```html
<!-- การ์ดมอนิเตอร์ระบบ สไตล์ Swiss Technical Utilitarian -->
<div class="bg-[#0e1526] border border-[#1e2d47] rounded-lg p-5 shadow-sm font-sans">
  <div class="flex items-center justify-between pb-3.5 border-b border-[#1e2d47]">
    <div class="flex items-center gap-2.5">
      <span class="relative flex h-2.5 w-2.5">
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
        <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
      </span>
      <span class="font-mono text-xs font-semibold uppercase tracking-wider text-slate-300">Node Cluster · Bangkok-01</span>
    </div>
    <span class="font-mono text-xs text-slate-500">PID: 88402</span>
  </div>

  <div class="mt-4 grid grid-cols-3 gap-4">
    <div>
      <div class="text-xs text-slate-400">Throughput</div>
      <div class="font-mono text-xl font-bold text-white mt-1">
        18.4 <span class="text-xs font-normal text-slate-400">MB/s</span>
      </div>
    </div>
    <div>
      <div class="text-xs text-slate-400">P99 Latency</div>
      <div class="font-mono text-xl font-bold text-sky-400 mt-1">
        1.12 <span class="text-xs font-normal text-slate-400">ms</span>
      </div>
    </div>
    <div>
      <div class="text-xs text-slate-400">Error Rate</div>
      <div class="font-mono text-xl font-bold text-emerald-400 mt-1">
        0.00%
      </div>
    </div>
  </div>

  <div class="mt-4 pt-3 border-t border-[#1e2d47]/60 flex items-center justify-between text-xs text-slate-400">
    <span>Uptime: 99.98% (34d 12h)</span>
    <button class="text-sky-400 hover:text-sky-300 font-medium transition-colors focus-visible:outline-none focus-visible:underline">
      ดูข้อมูล Trace →
    </button>
  </div>
</div>
```

### ตัวอย่างที่ 2: ส่วนหัวข้อและแบบฟอร์มสไตล์คราฟต์ร่วมสมัย (Crafted Form Hero)
```html
<!-- ส่วนพาดหัวและฟอร์มสไตล์ Modernist Editorial -->
<section class="bg-[#0b0f19] text-white py-16 px-6 sm:px-12 border-b border-[#1e2d47]">
  <div class="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
    <!-- ฝั่งพาดหัวอสมมาตร (7 คอลัมน์) -->
    <div class="lg:col-span-7 space-y-6">
      <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#141b2d] border border-[#1e2d47] text-xs text-sky-400 font-medium">
        <span>สถาปัตยกรรมระดับองค์กร</span>
        <span class="text-slate-500">·</span>
        <span class="text-slate-300">เวอร์ชัน 6.0</span>
      </div>
      <h1 class="text-4xl sm:text-5xl font-bold tracking-tight text-white leading-[1.15]">
        จัดการสิทธิ์และการเข้าถึงข้อมูล โดยไม่มีความซับซ้อนส่วนเกิน
      </h1>
      <p class="text-base text-slate-300 max-w-xl leading-relaxed">
        โครงสร้าง Role-Based Access Control แบบกำหนดสิทธิ์รายโมดูล พร้อมชุดทดสอบอัตโนมัติ 117 กรณีทดสอบ ครอบคลุมทั้ง Public Zone และ Staff Zone
      </p>
    </div>

    <!-- ฝั่งเครื่องมือทำงานจริง (5 คอลัมน์) -->
    <div class="lg:col-span-5 bg-[#141b2d] border border-[#1e2d47] rounded-xl p-6 shadow-xl">
      <h2 class="text-sm font-semibold text-slate-200 uppercase tracking-wider mb-4">
        ตรวจสอบสิทธิ์การเข้าถึงด่วน
      </h2>
      <div class="space-y-3">
        <div class="flex items-center justify-between p-3 rounded-lg bg-[#0b0f19] border border-[#1e2d47]">
          <span class="text-sm text-slate-300">/staff/users/ (RBAC Portal)</span>
          <span class="px-2 py-0.5 rounded text-xs font-semibold bg-amber-950/60 text-amber-400 border border-amber-800/60">เฉพาะ Manager</span>
        </div>
        <div class="flex items-center justify-between p-3 rounded-lg bg-[#0b0f19] border border-[#1e2d47]">
          <span class="text-sm text-slate-300">/employees/ (จัดการพนักงาน)</span>
          <span class="px-2 py-0.5 rounded text-xs font-semibold bg-sky-950/60 text-sky-400 border border-sky-800/60">Staff & Manager</span>
        </div>
      </div>
    </div>
  </div>
</section>
```

---

## 4. ข้อกำหนดการปฏิบัติงานของ Coding Agent (Operational Rules)

ทุกครั้งที่ผู้ใช้มอบหมายงานเขียนโค้ดหน้าเว็บ (Frontend UI):

1. **ห้ามตอบรับด้วยโค้ดสำเร็จรูปทั่วไปทันที**:
   - ประกาศมุมมองการดีไซน์ของตนเองสั้นๆ 1-2 ประโยคก่อนเริ่มลงมือ เช่น:
     *"เลือกใช้สไตล์ Technical Utilitarian ร่วมกับชุดสี Ocean Blue และฟอนต์ Prompt เพื่อขับเน้นความน่าเชื่อถือระดับองค์กร"*
2. **ใช้โทเค็นตัวแปรเสมอ**:
   - อ้างอิงตัวแปร CSS / Tailwind Token ห้ามฮาร์ดโค้ดสีตามใจชอบ
3. **รักษาความประณีตของสเตท (State Completeness)**:
   - ตรวจสอบให้แน่ใจว่าปุ่ม ลิงก์ และกล่องอินพุตมี Hover, Active, Focus-visible ครบทุกองค์ประกอบ
4. **ทำ Anti-Slop Audit ก่อนส่งงาน**:
   - ตรวจสอบกับ Section 1 เสมอว่าไม่มีแสงม่วงฟุ้ง, ไม่มีการ์ด 3 กล่องซ้ำซาก, และไม่มีพาดหัวสำเร็จรูปหลุดออกไป
