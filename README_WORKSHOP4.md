# Workshop 4: ระบบจัดการพนักงาน (Employee Management System)

**ผู้จัดทำ:** นายธรรมธัช รูปไธสง
**รหัสนักศึกษา:** 671320104
**สาขา:** วิทยาการคอมพิวเตอร์ มหาวิทยาลัยราชภัฏกำแพงเพชร
**เทคโนโลยี:** Django 6.0.6, SQLite, Bootstrap 5.3.3, Python 3.12+

---

## 1) ข้อมูลสำหรับตรวจงาน

| รายการ | ค่า |
|---|---|
| URL เว็บไซต์ | https://tammatat.pythonanywhere.com |
| หน้าระบบจัดการพนักงาน | https://tammatat.pythonanywhere.com/employees/ |
| หน้า Login สำหรับจัดการข้อมูลผ่านเว็บ | https://tammatat.pythonanywhere.com/staff/login/ |
| Backend (Admin) | https://tammatat.pythonanywhere.com/admin/ |
| **Admin Username** | **teacher** |
| **Admin Password** | **Shop2026!** |

> กรณีตรวจบนเครื่องส่วนตัว: แตกไฟล์ zip แล้วรันตามหัวข้อ 4) แล้วเข้า http://127.0.0.1:8000

---

## 2) สรุปความสามารถระบบ (ครบตามเอกสาร Workshop 4)

| ข้อกำหนด | รายละเอียดการทำ |
|---|---|
| Project + App | โปรเจกต์ `myproject`, แอป `myapp` ลงทะเบียนใน INSTALLED_APPS |
| Model 6+ ฟิลด์ | `Employee` 9 ฟิลด์: emp_code (unique), name, gender (Choices ชาย/หญิง/อื่นๆ), department, salary (Decimal), hire_date (Date), address (Text), avatar (ImageField), created_at (DateTime) |
| makemigrations/migrate | migrations `0001`–`0005` ทำครบแล้ว (ไฟล์ DB แนบมาพร้อมข้อมูล) |
| Django ModelForm | `myapp/forms.py` → EmployeeForm + widget Bootstrap 5 + label ภาษาไทย + validation |
| CRUD | Create `/employees/create/`, Read `/employees/`, Update `/employees/<id>/update/`, Delete `/employees/<id>/delete/` (ต้อง login เป็น staff ก่อน, Delete ใช้ POST + popup ยืนยัน) |
| Search | ช่องค้นหาบนหน้า list ค้นหา 3 ฟิลด์ (รหัส/ชื่อ/แผนก) ด้วย Q objects |
| Upload + แสดงรูป | อัปโหลดรูปพนักงานผ่านฟอร์ม (multipart) เก็บที่ `media/employees/` แสดง thumbnail ในตาราง + preview ในฟอร์มแก้ไข |
| Pagination | 5 รายการ/หน้า ปุ่มก่อนหน้า/ถัดไป เลขหน้า active highlight แสดง "หน้า X จาก Y" และ preserve คำค้นหาข้ามหน้า |
| UI/Base Template | `basetemplate.html` (navbar + dropdown + footer) Bootstrap 5 flash messages ภาษาไทยทั้งระบบ |
| ทำงานได้จริง | ทดสอบครบทุก flow ไม่มี Error (Create/Read/Update/Delete/Search/Upload/Pagination) |

**ข้อมูลตัวอย่างในฐานข้อมูล:** พนักงาน 12 คน (EMP001–EMP012) พร้อมรูป avatar ทุกคน

---

## 3) โครงสร้างไฟล์หลัก

```
my_django_app/
├── manage.py
├── requirements.txt          ← Django 6.0.6 + Pillow
├── db.sqlite3                ← ฐานข้อมูล (มีข้อมูล + บัญชี admin แนบมาแล้ว)
├── DEPLOY.md                 ← คู่มือ deploy PythonAnywhere
├── myproject/                ← settings / urls / wsgi
├── myapp/
│   ├── models.py             ← Employee (+ Product, Order, Payment)
│   ├── forms.py              ← EmployeeForm (ModelForm)
│   ├── views.py              ← CRUD + search + pagination
│   ├── urls.py               ← routing ของ app
│   ├── admin.py              ← ลงทะเบียนโมเดลทั้งหมดใน admin
│   ├── templates/            ← basetemplate.html, employee_list.html,
│   │                            employee_form.html (+ หน้าร้านค้าเสริม)
│   └── static/images/        ← รูปสินค้า
├── media/employees/          ← รูป avatar พนักงานที่อัปโหลด
└── staticfiles/              ← ผลลัพธ์ collectstatic (สำหรับ deploy)
```

---

## 4) วิธีรันบนเครื่อง (Windows/macOS/Linux)

```bash
cd my_django_app
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate      # ถ้าใช้ db.sqlite3 ที่แนบมา ข้ามขั้นตอนนี้ได้
python manage.py runserver
```

เปิดเบราว์เซอร์: http://127.0.0.1:8000/employees/
Admin: http://127.0.0.1:8000/admin/ (teacher / Shop2026!)

---

## 5) หมายเหตุ

- ระบบมีส่วนเสริมนอกเหนือจาก Workshop 4 (ร้านค้าออนไลน์ THAMMATHAD SHOP: สินค้า/ตะกร้า/สั่งซื้อ/ติดตามสถานะ/แจ้งชำระเงิน) เพื่อประยุกต์ใช้ทักษะเดียวกันในกรณีศึกษาอื่น
- ผู้ใช้ทั่วไปดูสินค้าได้ ส่วนระบบพนักงานและการเพิ่ม/แก้ไข/ลบข้อมูลผ่านหน้าเว็บต้องเข้าสู่ระบบที่ `/staff/login/` ด้วยบัญชี staff
- บัญชี superuser: `admin`, `ohm`, `teacher` (ทั้งหมดเป็น admin)
