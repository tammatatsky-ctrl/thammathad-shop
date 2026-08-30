# คู่มือ Deploy ขึ้น PythonAnyhere (Workshop 4)

เตรียมโดย: ธรรมธัช รูปไธสง | เว็บหลัง deploy: **https://tammatat.pythonanywhere.com**

---

## สิ่งที่เตรียมให้แล้ว (ฝั่งโปรเจกต์)

- `requirements.txt` — Django 6.0.6 + Pillow 12.3.0
- `db.sqlite3` — มีข้อมูล seed (พนักงาน 12 คน, สินค้า 3 รายการ) + บัญชี admin พร้อมใช้
- `media/` — รูป avatar พนักงานทั้งหมด
- `staticfiles/` — ผลลัพธ์ collectstatic (ไม่ต้องรันซ้ำบน server)
- `ALLOWED_HOSTS` มี `tammatat.pythonanywhere.com` อยู่แล้ว

**บัญชี Admin ส่งอาจารย์:** user = `teacher` / password = `Shop2026!`

---

## ขั้นตอนบน PythonAnywhere (ทำบนเว็บ ~10 นาที)

### 1) อัปโหลด ZIP
1. Login https://www.pythonanywhere.com → แท็บ **Files**
2. กด **Upload a file** → อัปโหลด `my_django_app_deploy.zip` ไปที่ `/home/tammatat/`

### 2) แตกไฟล์ (Bash console)
เปิดแท็บ **Consoles** → **Bash** แล้วพิมพ์:

```bash
cd ~
unzip -o my_django_app_deploy.zip -d my_django_app_tmp
mkdir -p ~/my_django_app
cp -r ~/my_django_app_tmp/my_django_app/* ~/my_django_app/
rm -rf ~/my_django_app_tmp my_django_app_deploy.zip
ls ~/my_django_app   # ต้องเห็น manage.py myproject myapp db.sqlite3 ...
```

### 3) สร้าง Virtualenv + ติดตั้ง packages

```bash
mkvirtualenv django-shop --python=$(ls /usr/bin/python3.* | sort -V | tail -1)
pip install -r ~/my_django_app/requirements.txt
```

> ⚠️ Django 6 ต้องใช้ **Python 3.12+** ถ้า PythonAnywhere ให้เลือกได้ไม่ถึง 3.12
> ให้แก้ไฟล์ `~/my_django_app/requirements.txt` เป็น `Django==5.1.10` แล้ว pip install ใหม่
> (โค้ดเขียนแบบรองรับทั้ง 5/6 ใช้ได้เหมือนกัน)

จด path ของ virtualenv ไว้: `/home/tammatat/.virtualenvs/django-shop`

### 4) สร้าง Web App
แท็บ **Web** → **Add a new web app** → Next (domain `tammatat.pythonanywhere.com`)
→ **Manual configuration** → เลือก **Python เวอร์ชันเดียวกับ virtualenv**

### 5) ตั้งค่าในแท็บ Web (สำคัญ!)
| ช่อง | ค่าที่กรอก |
|---|---|
| Source code (Working directory) | `/home/tammatat/my_django_app` |
| Virtualenv | `/home/tammatat/.virtualenvs/django-shop` |

**Static files mapping** (ส่วนล่างของแท็บ Web):
| URL | Directory |
|---|---|
| `/static/` | `/home/tammatat/my_django_app/staticfiles` |
| `/media/` | `/home/tammatat/my_django_app/media` |

### 6) แก้ไฟล์ WSGI
ในแท็บ Web กดลิงก์ **WSGI configuration file** (`/var/www/tammatat_pythonanywhere_com_wsgi.py`)
**ลบเนื้อหาเดิมทั้งหมด** แล้ววาง:

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

กด **Save** แล้วกดปุ่มสีเขียว **Reload** บนแท็บ Web

### 7) ทดสอบ
- Login ผู้ดูแล: https://tammatat.pythonanywhere.com/staff/login/
- ระบบพนักงาน (หลัง Login): https://tammatat.pythonanywhere.com/employees/
- Admin: https://tammatat.pythonanywhere.com/admin/ (teacher / Shop2026!)

---

## Checklist ส่งอาจารย์

- [ ] URL เว็บไซต์: `https://tammatat.pythonanywhere.com`
- [ ] ระบบจัดการพนักงาน: `/employees/`
- [ ] Backend Admin: `/admin/` → user `teacher` / pass `Shop2026!`

## แก้ไขโค้ดภายหลัง (Update)

แก้ไฟล์บนแท็บ Files ของ PythonAnywhere โดยตรง แล้วกด **Reload** ในแท็บ Web
ถ้าแก้ models อย่าลืมใน Bash console:

```bash
workon django-shop
cd ~/my_django_app
python manage.py makemigrations && python manage.py migrate
```
