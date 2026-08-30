from myapp.services import Cart


def cart_context(request):
    """จำนวนสินค้าในตะกร้าบนแถบเมนู — ใช้ Cart service ตัวเดียวกับหน้าตะกร้า
    (สินค้าที่ถูกซ่อนจะไม่นับ — กฎเดียวกันกับที่ Cart.lines ใช้)"""
    try:
        return {'cart_count': Cart(request.session).count}
    except (ValueError, TypeError, KeyError):
        return {'cart_count': 0}