from django.conf import settings

from myapp.services import Cart


def cart_context(request):
    """จำนวนสินค้าในตะกร้าบนแถบเมนู — ใช้ Cart service ตัวเดียวกับหน้าตะกร้า
    (สินค้าที่ถูกซ่อนจะไม่นับ — กฎเดียวกันกับที่ Cart.lines ใช้)"""
    try:
        cart_count = Cart(request.session).count
    except (ValueError, TypeError, KeyError):
        cart_count = 0
    return {
        'cart_count': cart_count,
        # เปิด/ปิด diagnostic ของ motion-core (FX._report toast + uncaught error watch)
        # — true เฉพาะ dev (DEBUG=True); prod เงียบ กัน toast รั่ว/console โนย
        'debug': settings.DEBUG,
        # เวอร์ชัน static สำหรับ URL ที่ fx-assets.js สร้างเองตอน runtime
        # (ดู stamp() ใน fx-assets.js) — ถ้าไม่ส่งมา ค่านี้จะว่าง แล้ว effect ทุกไฟล์
        # จะถูกเบราว์เซอร์ cache โดยไม่มี ?v= → แก้ effect แล้วผู้ใช้ไม่เห็น
        # (settings ไม่ได้อยู่ใน context เป็นอัตโนมัติ ต้องส่งมาเอง)
        'STATIC_VERSION': getattr(settings, 'STATIC_VERSION', ''),
    }