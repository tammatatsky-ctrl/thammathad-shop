# คู่มือ Deploy ขึ้น PythonAnywhere

เตรียมโดย: ธรรมธัช รูปไธสง | เว็บหลัง deploy: **https://tammatat.pythonanywhere.com**

---

## สิ่งที่ต้องรู้ก่อน (อ่านให้จบ)

1. **ZIP ชื่อ `pa_update.zip`** (ไม่ใช่ `my_django_app_deploy.zip`)
   ต้องมี `myproject/` อยู่ในนั้นด้วย — ถ้าไม่มี `settings.py` บน server จะเป็นตัวเก่า
   แล้วเว็บรันด้วย config เก่าโดย**ไม่มีอาการผิดปกติให้เห็น** (เคยพลาดมาแล้ว)
2. **ZIP ไม่รวม `db.sqlite3`** — ตั้งใจ ฐานข้อมูลบนเซิร์ฟคือข้อมูลจริง
   ถ้าอัปโหลดทับทิ้ง ออเดอร์/เงิน/ลูกค้าทั้งหมดหาย
3. **ZIP ไม่รวม `media/`** — รูป avatar พนักงานจึงไม่ติดไปด้วย
   (หน้าเว็บมีภาพสำรองให้อยู่แล้ว จึงไม่พัง แต่ถ้าต้องการรูปจริงให้อัปโหลด
   `media/` แยกทีหลัง)
4. `staticfiles/` **รวมอยู่ใน ZIP แล้ว** จึงไม่ต้องรัน `collectstatic` บน server
   (รันซ้ำก็ไม่เสียหาย)

---

## สิ่งที่ต้องตั้งก่อนแตะเซิร์ฟ (fail-closed)

`settings.py` ตั้งใจให้ **error ตอน boot** ถ้า env ไม่ครบ ดีกว่ารันแล้วรั่ว

> ⚠️ **อ่านข้อนี้ก่อน — เป็นกับดักที่ทำให้เสียเวลามากที่สุดตอน deploy**
>
> **Environment variables ที่ตั้งในแท็บ Web มีผลกับเฉพาะ process ของเว็บ**
> คำสั่ง `manage.py` ที่รันใน **Bash console จะไม่เห็นค่าเหล่านั้น**
> ผลคือเว็บอาจขึ้นปกติ แต่ `python manage.py migrate` / `seed_catalog` /
> `seed_demo_data` / `preflight` จะ error ว่า
> `ต้องตั้ง env DJANGO_SECRET_KEY` — ทั้งที่เพิ่งตั้งไปแล้วในแท็บ Web
>
> → ต้องตั้ง **สองที่** ตามคำสั่งด้านล่าง

### A) สำหรับเว็บ — แท็บ Web → Environment variables

| ตัวแปร | ค่า | ถ้าไม่ตั้ง |
|---|---|---|
| `DJANGO_DEBUG` | `0` | หน้า error สีเหลืองชอว์ settings ทั้งหมดรวม API key |
| `DJANGO_SECRET_KEY` | ค่าสุ่มใหม่ | **เว็บไม่ขึ้นเลย** (`RuntimeError`) |
| `EMAIL_URL` | เว้นว่างได้ | ระบบจะไม่ลอกว่าส่งแล้ว แต่ "ลืมรหัสผ่าน" ใช้กับลูกค้าจริงไม่ได้ |
| `GEMINI_API_KEY` / `SLIPOK_API_KEY` | เว้นว่างได้ | ฟีเจอร์นั้นถูกซ่อน (ตั้งใจ ไม่ใช่ของพัง) |

### B) สำหรับ Bash console — เขียนลง `~/.bashrc` (ทำครั้งเดียว)

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
# คัดลอกค่าที่ได้ → K

cat >> ~/.bashrc <<'EOF'
export DJANGO_DEBUG=0
export DJANGO_SECRET_KEY='วางค่าKตรงนี้'
EOF

source ~/.bashrc
```

> ต้องมี **เครื่องหมายคำพูดเดี่ยว** `'...'` ครอบค่าคีย์ เพราะค่าที่ Django สุ่ม
> มี `&` และ `%` ปนอยู่ — ไม่มีเครื่องหมายจะโดน shell ตัดทิ้ง
>
> ต้องใส่ **ค่าเดียวกับแท็บ Web** ไม่งั้น session ที่สร้างจาก console
> จะใช้กับเว็บไม่ได้ (คีย์ไม่ตรงกัน)

### ตรวจว่าได้ผล

```bash
python manage.py check    # ต้องขึ้น System check identified no issues
```

> หมายเหตุ: `settings.py` มี `load_dotenv()` อยู่แล้ว แต่พึ่ง `python-dotenv`
> ซึ่งต้องติดตั้งสำเร็จก่อน ถ้า `pip install` ล้มกลางทาง
> `except ImportError: pass` จะกลืน error **เงียบ ๆ** แล้วไปต่อง่าย
> โดยไม่บอกว่าไม่ได้อ่าน `.env` — ดู §"ติดตั้งไม่ผ่าน" ด้านล่าง

---

## ขั้นตอนบน PythonAnywhere (ครั้งแรก ~15 นาที)

### 1) อัปโหลด ZIP

แท็บ **Files** → **Upload a file** → อัปโหลด `pa_update.zip` ไปที่ `/home/tammatat/`

### 2) แตกไฟล์ (Bash console)

```bash
cd ~/my_django_app 2>/dev/null || mkdir -p ~/my_django_app
cd ~/my_django_app
unzip -o ~/pa_update.zip
rm ~/pa_update.zip
ls   # ต้องเห็น manage.py  myproject/  myapp/  staticfiles/
```

> คำสั่งนี้ทับไฟล์ที่มีอยู่ **แต่ไม่ลบ** ไฟล์ที่ไม่ได้อยู่ใน ZIP
> ถ้าต้องการเริ่มใหม่สะอาด: `mv ~/my_django_app ~/my_django_app.bak` ก่อนแล้วค่อยแตกใหม่
> (ทำเฉพาะครั้งแรกเท่านั้น — หลังจากนั้น `db.sqlite3` อยู่ในโฟลเดอร์นั้น)

### 3) Virtualenv + packages

```bash
mkvirtualenv django-shop --python=$(ls /usr/bin/python3.* | sort -V | tail -1)
pip install -r ~/my_django_app/requirements.txt
```

> ⚠️ Django 6 ต้องใช้ **Python 3.12+**
>
> **อย่าติดตั้ง `requirements-docs.txt` บน server** — ไฟล์นั้นมี `pycairo`
> ซึ่งต้องคอมไพล์ต่อกับ C library ชื่อ `cairo` ที่ PythonAnywhere บัญชีฟรีไม่มี
> ถ้าติดตั้งแล้วล้ม **Django จะไม่ถูกติดตั้งตามไปด้วย** เพราะ pip หยุดที่แพ็กเกจ
> ที่ล้มก่อน — เหลือแต่เว็บที่รันไม่ขึ้น โดยข้อความ error ไม่ได้บอกว่า
> เพราะติดตั้งอะไร เป็นการเสียเวลาไปตามหาสาเหตุผิดทาง
>
> `requirements-docs.txt` (reportlab / python-docx / pycairo / rlPyCairo)
> ต้องการเฉพาะตอนสร้างเอกสารรายงานบนเครื่องนักพัฒนาเท่านั้น
> ถ้าอยากรัน `build_report` บน server ให้ติดตั้งแยกทีหลัง:
> `pip install reportlab python-docx` (สองตัวนี้ล้วน wheel สำเร็จรูป ติดตั้งได้)
> — แต่ `build_report` จะยังบอกว่าขาด `rlPyCairo` (ใช้ฝังภาพลง Word)
> ส่วน **PDF สร้างได้ปกติ** เพราะเป็น vector ไม่ต้องใช้ PNG

### 4) เตรียมฐานข้อมูล (**ต้องเรียงตามลำดับ**)

```bash
workon django-shop
cd ~/my_django_app
python manage.py migrate            # ครั้งแรก DB ว่าง
python manage.py seed_catalog      # สินค้า 12 ชิ้น 4 หมวด — ต้องทำก่อนข้อถัดไป
python manage.py seed_demo_data    # พนักงาน 13 · ลูกค้า 6 · ออเดอร์ 10 · ปัญหา 4
```

> `seed_demo_data` จะ**ล้ม** พร้อมบอกว่า "ต้องมีสินค้าอย่างน้อย 12 ชิ้น"
> ถ้าเห็นข้อความนั้น แปลว่าลืมรันข้อ 2 — ไม่ใช่ระบบพัง
>
> ถ้าบน server มีข้อมูลจริงอยู่แล้ว **ไม่ต้องรัน seed** — seed จะไปแตะข้อมูลที่มีอยู่

### 5) ตรวจว่าติดตั้งได้ครบ (ก่อน seed — อย่าข้าม)

```bash
pip list | grep -Ei '^(Django|djangorestframework|drf-spectacular|Pillow|python-dotenv|qrcode|promptpay-qr)'
```

ต้องเห็น **7 บรรทัด** ถ้าไม่ครบ = การติดตั้งล้มกลางทาง ให้ทำตาม §"ติดตั้งไม่ผ่าน"

### 6) เตรียมฐานข้อมูล (**ต้องเรียงตามลำดับ**)

```bash
python manage.py preflight
```

ต้องขึ้น `ระบบพร้อมใช้งาน` · ถ้าขึ้น FAIL ให้แก้ตามที่มันบอกแล้วรันซ้ำ
(ตรวจ 10 อย่าง: DEBUG/SECRET_KEY · ALLOWED_HOSTS · CSRF · HSTS · อีเมล ·
staticfiles ตรงกับ source · migration · ฐานข้อมูล · เขียน log · ไฟล์สำรอง)

### 6) ตั้ง Web App

แท็บ **Web**:

- **Source code**: `/home/tammatat/my_django_app`
- **Virtualenv**: `/home/tammatat/.virtualenvs/django-shop`

**Static files mapping**:

| URL | Directory |
|---|---|
| `/static/` | `/home/tammatat/my_django_app/staticfiles` |
| `/media/` | `/home/tammatat/my_django_app/media` |

### 7) WSGI

ในแท็บ Web กด **WSGI configuration file** → **ลบเนื้อหาเดิมทั้งหมด** → วาง:

```python
import os
import sys

path = '/home/tammatat/my_django_app'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'myproject.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

### 8) Reload

กดปุ่มเขียว **Reload** → เปิด https://tammatat.pythonanywhere.com

---

## 🔴 "ติดตั้งไม่ผ่าน" — อ่านท้ายสุดของ output เสมอ

`pip` พิมพ์หลายบล็อกเรียงกัน และคนมักคัดลอกมาแค่บล็อกแรกซึ่ง**ไม่ใช่ตัวที่ทำให้ล้ม**

```
ERROR: pip's dependency resolver does not currently take into account ...
moviepy 2.1.1 requires pillow<11.0 ...          ← คำเตือน (ไม่ใช่ตัวที่ทำให้ล้ม)
dj-rest-auth 6.0.0 requires Django<6.0 ...       ← คำเตือน
Successfully installed ...                        ← ติดตั้งสำเร็จ
...
error: command '/usr/bin/gcc' failed ...          ← ตัวที่ทำให้ล้มจริง (อยู่ข้างล่าง)
```

คำสั่งช่วยดู:
```bash
pip install -r requirements.txt 2>&1 | tail -20
```

**ตรวจว่าครบจริง** (ไม่ใช่ดูข้อความ แต่ดูรายการที่ติดตั้ง):
```bash
pip list | grep -Ei '^(Django|djangorestframework|drf-spectacular|Pillow|python-dotenv|qrcode|promptpay-qr)'
```

> อาการที่พบจริง: `pip` ล้มที่ `pycairo` → หยุดกลางทาง → `Django` **ไม่ถูกติดตั้ง**
> แต่ข้อความ `Successfully installed` ที่อยู่ด้านบนทำให้เข้าใจว่าสำเร็จ
> แล้วไปหาปัญหาที่ผิดทางนาน

---

## อัปเดตครั้งถัดไป (ไม่ต้องทำข้อ 3/5/6/7 ซ้ำ)

1. สร้าง zip ใหม่บนเครื่องตัวเอง (ดูคำสั่งด้านล่าง)
2. อัปโหลด `pa_update.zip` → Files
3. Bash:

```bash
cd ~/my_django_app
unzip -o ~/pa_update.zip && rm ~/pa_update.zip
workon django-shop
python manage.py migrate
python manage.py collectstatic --noinput   # ถ้ามีไฟล์ static ใหม่
python manage.py preflight
```

4. แท็บ Web → **Reload**

> ⚠️ **`staticfiles/` ใน ZIP จะเก่ากว่า `myapp/static/` ถ้าไม่รัน `collectstatic`
> บนเครื่องก่อนสร้าง zip** ผู้ใช้จะเห็น CSS/JS เก่าโดยไม่มีอาการผิดปกติ
> `preflight` จะเตือนเรื่องนี้ แต่บน server ตรวจจาก staticfiles ซึ่งเป็นตัวที่สเกรฟชี้อยู่
> จึงต้องรัน `collectstatic` บนเครื่องตัวเองก่อนเสมอ

### สร้าง ZIP บนเครื่องตัวเอง (PowerShell)

```powershell
cd D:\django_project\my_django_app
.venv\Scripts\python.exe manage.py collectstatic --noinput
tar.exe -a -c -f pa_update.zip --exclude=__pycache__ --exclude=.venv --exclude=db.sqlite3 --exclude=pa_update.zip --exclude=media --exclude=test --exclude=backups --exclude=logs myapp myproject staticfiles requirements.txt DEPLOY.md SUBMISSION.md AGENTS.md DEMO.md
tar.exe -tf pa_update.zip | Select-String 'myproject/settings.py'   # ต้องเจอ
```

---

## บัญชีทดสอบ

| บัญชี | รหัสผ่าน | หมายเหตุ |
|---|---|---|
| `teacher` | `Shop2026!` | superuser — เข้าได้ทุกทาง · **เปลี่ยนก่อนส่งจริง** |
| `ohm` | ตั้งเอง | superuser · บัญชีตัวอย่างของเจ้าของระบบ |
| `wichai.s` … `anon.d` | `Demo2026!` | ลูกค้าตัวอย่าง (มีออเดอร์/ที่อยู่/ปัญหาครบ) |

> ถ้าล็อกอินบัญชีตัวอย่างไม่ได้ แปลว่าเคยเปลี่ยนรหัสไปแล้ว
> (`seed_demo_data` ตั้งรหัสเฉพาะบัญชีที่ยังไม่มีรหัส โดยตั้งใจไม่ทับของเดิม)
>
> แก้ด้วย `python manage.py reset_demo_password wichai.s pornchai.k ...`
> — คำสั่งนี้**ต้องระบุชื่อทีละราย** ห้ามกวาดทั้งระบบ
> (การทับรหัสบัญชีจริงที่ชื่อคล้ายคืออุบัติเหตุที่แย่กว่าบั๊กที่มันแก้)

---

## สำรองฐานข้อมูล (ทำทันทีหลัง setup เสร็จ)

SQLite ไฟล์เดียว = ข้อมูลออเดอร์/ยอดเงิน/ลูกค้าทั้งหมดอยู่ไฟล์เดียว ถ้าเสียกู้ไม่ได้

```bash
workon django-shop && cd ~/my_django_app
python manage.py backup_db --verify     # ทดสอบก่อน
```

ตั้ง cron ในแท็บ **Tasks**:

```
0 2 * * *   /home/tammatat/.virtualenvs/django-shop/bin/python /home/tammatat/my_django_app/manage.py backup_db >> /home/tammatat/my_django_app/backups/cron.log 2>&1
```

**กู้คืน**:

```bash
cd ~/my_django_app
cp db.sqlite3 db.broken.sqlite3
cp backups/db-YYYYmmdd-HHMMSS.sqlite3 db.sqlite3
```

> ไฟล์สำรองเก็บที่ `~/my_django_app/backups/` เก็บล่าสุด 7 ไฟล์ (ลบเก่าอัตโนมัติ)

---

## เอกสารคู่มือที่ส่งอาจารย์

| ไฟล์ | อยู่ที่ไหน |
|---|---|
| `รายงาน-THAMMATHAD-SHOP.pdf` / `.docx` | `docs/รายงาน/` — สร้างด้วย `python manage.py build_report` |
| `SUBMISSION.md` | คู่มือสำหรับผู้ตรวจงาน |
| `DEMO.md` | สคริปต์ไล่โชโชร์ทุกฟีเจอร์พร้อมคลิกเป๊ะตัว |

> `docs/รายงาน/` ไม่ได้อยู่ใน ZIP (สร้างบนเครื่องแล้วส่งแยกเป็นไฟล์ PDF/Word)
> ถ้าต้องการให้อาจารย์ได้เอกสารจากเว็บ ให้รัน `build_report` บน server
> แล้วอัปโหลดไฟล์ขึ้น Files เพื่อดาวน์โหลด