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
    }