"""Custom template tags — ต่อยอดด้วย external API โดยไม่แตะ view
usd : ฿ราคา → "≈ $xx.xx" (อัตราจาก ExchangeRate service, ซ่อนถ้าดึงไม่ได้)
"""
from decimal import Decimal, InvalidOperation

from django import template

from ..services import ExchangeRate

register = template.Library()


@register.filter
def usd(price_thb):
    """แปลงราคาบาทเป็นข้อความ USD เช่น '≈ $12.34' — '' ถ้าไม่มีอัตรา/ราคาไม่ถูกต้อง"""
    if price_thb in (None, ''):
        return ''
    rate = ExchangeRate.usd_per_thb()
    if not rate:
        return ''
    try:
        value = Decimal(str(price_thb)) * rate
    except (InvalidOperation, TypeError):
        return ''
    return f'≈ ${value:,.2f}'
