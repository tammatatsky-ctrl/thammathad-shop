"""Custom template tags — ต่อยอดด้วย external API โดยไม่แตะ view
usd : ฿ราคา → "≈ $xx.xx" (อัตราจาก ExchangeRate service, ซ่อนถ้าดึงไม่ได้)
"""
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.safestring import mark_safe

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


@register.simple_tag
def user_role(user):
    """คืน badge HTML แสดงสิทธิ์ของผู้ใช้ (ลาย Liquid Glass) ให้ใช้ซ้ำตาม navbar/หน้า profile.

    ลำดับสิทธิ์: superuser > ผู้จัดการร้าน (Manager) > เจ้าหน้าที่ (Staff/is_staff) > ลูกค้าทั่วไป (สมาชิก).
    ใช้ใน account.html (customer) และ adminbase.html (staff navbar) ตามงาน C9.
    """
    if not user or not user.is_authenticated:
        return ''
    if user.is_superuser:
        return mark_safe('<span class="role-badge role-admin"><i class="bi bi-shield-fill-check"></i> '
                         'ผู้ดูแลระบบ</span>')
    if user.groups.filter(name='Manager').exists():
        return mark_safe('<span class="role-badge role-manager"><i class="bi bi-briefcase-fill"></i> '
                         'ผู้จัดการร้าน</span>')
    if user.groups.filter(name='Staff').exists() or user.is_staff:
        return mark_safe('<span class="role-badge role-staff"><i class="bi bi-shield-check"></i> '
                         'เจ้าหน้าที่</span>')
    return mark_safe('<span class="role-badge role-member"><i class="bi bi-person-circle"></i> '
                     'สมาชิก</span>')


@register.simple_tag
def user_groups(user):
    """คืนรายชื่อกลุ่ม (Groups) ที่ user สังกัด คั่นด้วย comma หรือ '-' ถ้าไม่มีกลุ่ม"""
    if not user or not user.is_authenticated:
        return ''
    groups = list(user.groups.values_list('name', flat=True))
    if not groups:
        return '-'
    return ', '.join(groups)


@register.simple_tag
def user_group_badges(user):
    """คืน badge HTML สำหรับแต่ละกลุ่มสิทธิ์ที่ user สังกัด (คมชัดสูง รองรับทั้ง Light/Dark mode)"""
    if not user or not user.is_authenticated:
        return ''
    groups = list(user.groups.values_list('name', flat=True))
    if not groups:
        return mark_safe('<span class="group-badge group-badge-none">-</span>')
    badges = []
    for g in groups:
        gl = g.lower()
        if 'manager' in gl:
            badges.append(f'<span class="group-badge group-badge-manager"><i class="bi bi-briefcase-fill me-1"></i>{g}</span>')
        elif 'staff' in gl:
            badges.append(f'<span class="group-badge group-badge-staff"><i class="bi bi-shield-check me-1"></i>{g}</span>')
        elif 'member' in gl:
            badges.append(f'<span class="group-badge group-badge-member"><i class="bi bi-person-circle me-1"></i>{g}</span>')
        else:
            badges.append(f'<span class="group-badge group-badge-default"><i class="bi bi-people-fill me-1"></i>{g}</span>')
    return mark_safe(' '.join(badges))


