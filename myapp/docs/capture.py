"""บันทึกภาพหน้าจอจริงของระบบ (Web Screenshots Capture)

ใช้ Playwright (ผ่าน Chrome) แคปภาพหน้าเว็บจริงจากเซิร์ฟเวอร์
เพื่อนำไปฝังในรายงานเชิงวิชาการ (บทที่ 4: ผลการพัฒนาส่วนต่อประสานผู้ใช้)
"""

from pathlib import Path
from typing import List, Tuple

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from playwright.sync_api import sync_playwright

from myapp.models import Order, Product


def create_user_session(user: User) -> str:
    """สร้าง Django SessionStore สำหรับผู้ใช้ที่ระบุ และคืนค่า session_key"""
    session = SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    return session.session_key


def capture_all_screenshots(out_dir: Path | None = None, base_url: str = 'http://127.0.0.1:8000') -> List[Tuple[str, Path, str]]:
    """แคปภาพหน้าจอทุกส่วนสำคัญของระบบ

    Returns:
        List of (figure_key, file_path, caption)
    """
    if out_dir is None:
        out_dir = Path(settings.BASE_DIR) / 'docs' / 'screenshots'
    out_dir.mkdir(parents=True, exist_ok=True)

    staff_user = User.objects.filter(is_staff=True).first()
    customer_user = User.objects.filter(is_staff=False, orders__isnull=False).first()
    if not customer_user:
        customer_user = User.objects.filter(is_staff=False).first()

    staff_session_key = create_user_session(staff_user) if staff_user else ''
    customer_session_key = create_user_session(customer_user) if customer_user else ''

    # สร้าง cart session ที่มีสินค้า 1-2 ชิ้นสำหรับหน้าตะกร้า
    cart_session = SessionStore()
    prod = Product.objects.filter(is_active=True).first()
    if prod:
        cart_session['cart'] = {str(prod.pk): 2}
    cart_session.save()
    cart_session_key = cart_session.session_key

    # หาออเดอร์ที่มีปัญหาเพื่อถ่ายรูปหน้า tracking และ staff order detail
    order_with_issue = Order.objects.filter(issues__isnull=False).first()
    if not order_with_issue:
        order_with_issue = Order.objects.first()

    first_prod = Product.objects.first()
    prod_url = f'{base_url}/product/{first_prod.id}/' if first_prod else f'{base_url}/'

    tracking_url = f'{base_url}/order/tracking/'
    order_detail_url = f'{base_url}/orders/'
    if order_with_issue:
        tracking_url += f'?order={order_with_issue.id}&phone={order_with_issue.phone}'
        order_detail_url += f'{order_with_issue.id}/'

    results = []

    import os
    os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)

        # 1. หน้าร้านค้าทั่วไป (Public Storefront)
        pub_ctx = browser.new_context(viewport={'width': 1280, 'height': 820}, device_scale_factor=1.5)
        page = pub_ctx.new_page()

        # 1.1 หน้าแรกและแคตตาล็อกสินค้า
        p1 = out_dir / '01_home_catalog.png'
        page.goto(f'{base_url}/', wait_until='networkidle')
        page.wait_for_timeout(400)
        page.screenshot(path=str(p1))
        results.append(('fig_4_1', p1, 'ภาพที่ 4.1 หน้าแรกของระบบและแคตตาล็อกสินค้า (Home & Product Catalog)'))

        # 1.2 หน้ารายละเอียดสินค้า
        p2 = out_dir / '02_product_detail.png'
        page.goto(prod_url, wait_until='networkidle')
        page.wait_for_timeout(300)
        page.screenshot(path=str(p2))
        results.append(('fig_4_2', p2, 'ภาพที่ 4.2 หน้ารายละเอียดสินค้าและข้อมูลจำเพาะ (Product Detail & Specifications)'))

        # 1.3 หน้าติดตามพัสดุและประวัติการแจ้งปัญหา
        p4 = out_dir / '04_order_tracking.png'
        page.goto(tracking_url, wait_until='networkidle')
        page.wait_for_timeout(300)
        page.screenshot(path=str(p4))
        results.append(('fig_4_4', p4, 'ภาพที่ 4.4 หน้าติดตามสถานะคำสั่งซื้อและประวัติการแจ้งปัญหา (Order Tracking & Issues History)'))
        pub_ctx.close()

        # 2. หน้าตะกร้าสินค้า (Cart Session)
        cart_ctx = browser.new_context(viewport={'width': 1280, 'height': 820}, device_scale_factor=1.5)
        cart_ctx.add_cookies([{'name': 'sessionid', 'value': cart_session_key, 'domain': '127.0.0.1', 'path': '/'}])
        cart_page = cart_ctx.new_page()
        p3 = out_dir / '03_cart_checkout.png'
        cart_page.goto(f'{base_url}/cart/', wait_until='networkidle')
        cart_page.wait_for_timeout(300)
        cart_page.screenshot(path=str(p3))
        results.append(('fig_4_3', p3, 'ภาพที่ 4.3 หน้าตะกร้าสินค้าและการสรุปรายการสั่งซื้อ (Shopping Cart & Summary)'))
        cart_ctx.close()

        # 3. หน้าบัญชีลูกค้า (Customer Account)
        if customer_session_key:
            cust_ctx = browser.new_context(viewport={'width': 1280, 'height': 820}, device_scale_factor=1.5)
            cust_ctx.add_cookies([{'name': 'sessionid', 'value': customer_session_key, 'domain': '127.0.0.1', 'path': '/'}])
            cust_page = cust_ctx.new_page()
            p5 = out_dir / '05_customer_account.png'
            cust_page.goto(f'{base_url}/account/', wait_until='networkidle')
            cust_page.wait_for_timeout(300)
            cust_page.screenshot(path=str(p5))
            results.append(('fig_4_5', p5, 'ภาพที่ 4.5 หน้าบัญชีผู้ใช้งานและการแสดงผลการแก้ไขปัญหา (Customer Account & Resolution Detail)'))
            cust_ctx.close()

        # 4. ส่วนเจ้าหน้าที่ (Staff Zone)
        if staff_session_key:
            staff_ctx = browser.new_context(viewport={'width': 1280, 'height': 820}, device_scale_factor=1.5)
            staff_ctx.add_cookies([{'name': 'sessionid', 'value': staff_session_key, 'domain': '127.0.0.1', 'path': '/'}])
            staff_page = staff_ctx.new_page()

            # 4.1 หน้าตารางจัดการคำสั่งซื้อ
            p6 = out_dir / '06_staff_orders.png'
            staff_page.goto(f'{base_url}/orders/', wait_until='networkidle')
            staff_page.wait_for_timeout(300)
            staff_page.screenshot(path=str(p6))
            results.append(('fig_4_6', p6, 'ภาพที่ 4.6 หน้าจัดการคำสั่งซื้อสำหรับเจ้าหน้าที่พร้อมป้ายเตือนปัญหาค้าง (Order Management & Open Issue Alert)'))

            # 4.2 หน้ารายละเอียดคำสั่งซื้อ
            p7 = out_dir / '07_staff_order_detail.png'
            staff_page.goto(order_detail_url, wait_until='networkidle')
            staff_page.wait_for_timeout(300)
            staff_page.screenshot(path=str(p7))
            results.append(('fig_4_7', p7, 'ภาพที่ 4.7 หน้ารายละเอียดคำสั่งซื้อและการแจ้งเตือนปัญหาค้าง (Order Detail & Action Alerts)'))

            # 4.3 หน้าคิวการแจ้งปัญหา
            p8 = out_dir / '08_staff_issues.png'
            staff_page.goto(f'{base_url}/orders/issues/', wait_until='networkidle')
            staff_page.wait_for_timeout(300)
            staff_page.screenshot(path=str(p8))
            results.append(('fig_4_8', p8, 'ภาพที่ 4.8 หน้าจัดการคิวการแจ้งปัญหาและฟอร์มบันทึกผลการแก้ไข (Issue Management Queue & Actions)'))

            # 4.4 แดชบอร์ดสถิติยอดขาย
            p9 = out_dir / '09_staff_dashboard.png'
            staff_page.goto(f'{base_url}/dashboard/', wait_until='networkidle')
            staff_page.wait_for_timeout(400)
            staff_page.screenshot(path=str(p9))
            results.append(('fig_4_9', p9, 'ภาพที่ 4.9 แดชบอร์ดสรุปสถิติยอดขายและประวัติการดำเนินงาน (Executive Dashboard & Sales Analytics)'))

            # 4.5 หน้าจัดการบุคลากร
            p10 = out_dir / '10_staff_employees.png'
            staff_page.goto(f'{base_url}/employees/', wait_until='networkidle')
            staff_page.wait_for_timeout(300)
            staff_page.screenshot(path=str(p10))
            results.append(('fig_4_10', p10, 'ภาพที่ 4.10 หน้าจัดการข้อมูลบุคลากรและระบบสืบค้นข้อมูลสด (Employee Management & Live Search)'))

            staff_ctx.close()

        browser.close()

    return results
