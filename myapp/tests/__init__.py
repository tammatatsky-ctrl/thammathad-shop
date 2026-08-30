"""แพ็กเกจเทสต์ของ myapp — แบ่งตามชั้น (services / cart-checkout / staff / API / account).

การเรียก::
    python manage.py test myapp -v 2

หลักการ: test แต่ละชุดใช้ DB จำลอง (in-memory) แยกกัน — ไม่แตะ db.sqlite3 จริง.
ไฟล์ทุกชุดต้องควบคุมตัวแปร env ที่เปิด/ปิดฟีเจอร์ (GEMINI/SLIPOK key) ให้ deterministic
ด้วย override_settings หรือ mock เสมอ.
"""