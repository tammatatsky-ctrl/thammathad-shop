"""เทสต์โซน staff — auth, live search (AJAX partial), สต็อก, สถานะออเดอร์, จ่ายยืนยัน, export.

ครอบคลุม:
- Mixin: หน้า staff ต้อง redirect ไป /staff/login/; ลูกค้าไป /account/login/
- protocol: คำสั่งเขียน (logout/order_status/payment_verify/stock_adjust) เป็น POST เท่านั้น
- LiveSearchListView: header X-Requested-With: fetch → คืน partial (data-slot) ไม่มี navbar
- StockAdjust: clamp ไม่ติดลบ + delta มั่วมองข้าม
- OrderStatusView: 'paid' ตั้งด้วยมือไม่ได้, ข้ามขั้นไม่ได้, ขั้นถัดไปเปลี่ยนได้
- PaymentVerifyView: ยอดแจ้งครบ → paid; ไม่ครบ → ค้าง pending
- Export CSV + หน้า staff ทุกหน้า render 200 + AI gating (ไม่มี key = 503)

บันทึกบั๊ก (เคยแก้): staff login ใช้ StaffLoginForm ที่ปฏิเสธบัญชี non-staff (code not_staff) —
ทดสอบกำกับไว้แล้วที่นี่.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from myapp.models import Employee, Order, Payment, Product
from myapp.services import OrderStatusService


class StaffAuthTest(TestCase):
    """สิทธิ์เข้าถึงโซน staff / ลูกค้า + protocol POST-only"""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='teacher', email='t@shop.com', password='Shop2026!', is_staff=True)
        self.client.force_login(self.staff)

    def test_anonymous_redirected_to_staff_login(self):
        """หน้า staff ที่ไม่ได้ล็อกอิน → /staff/login/?next=..."""
        self.client.logout()
        self.assertRedirects(self.client.get(reverse('employee_list')),
                             '/staff/login/?next=/employees/')

    def test_anonymous_redirected_to_customer_login(self):
        """หน้า /account/ ที่ไม่ได้ล็อกอิน → /account/login/?next=..."""
        self.client.logout()
        self.assertRedirects(self.client.get(reverse('account')),
                             '/account/login/?next=/account/')

    def test_post_only_protocol_returns_405(self):
        """คำสั่งเขียนทั้งหมดห้าม GET — crawler/แคชไม่ควรล็อกเอาต์/จ่ายเงินเอง"""
        self.client.logout()
        self.assertEqual(self.client.get(reverse('staff_logout')).status_code, 405)
        self.assertEqual(self.client.get(reverse('account_logout')).status_code, 405)
        self.client.force_login(self.staff)
        for name, args in [('order_status', [1]), ('payment_verify', [1]),
                           ('stock_adjust', [1])]:
            r = self.client.get(reverse(name, args=args))
            self.assertEqual(r.status_code, 405, name)


class StaffLoginTest(TestCase):
    """ล็อกอินฝั่ง staff — เฉพาะบัญชี staff จริง ๆ"""

    def setUp(self):
        User.objects.create_user(username='teacher', password='pw123456', is_staff=True)
        User.objects.create_user(username='plainuser', password='pw123456', is_staff=False)

    def test_staff_already_logged_in_redirects_away(self):
        """staff ล็อกอินอยู่แล้ว → พาไป /employees/ ไม่โชว์ฟอร์มซ้ำ"""
        self.client.force_login(User.objects.get(username='teacher'))
        self.assertRedirects(self.client.get(reverse('staff_login')), reverse('employee_list'))

    def test_correct_login_redirects_to_employees(self):
        """POST ถูกต้อง → /employees/ + จำ session ไว้"""
        r = self.client.post(reverse('staff_login'),
                             {'username': 'teacher', 'password': 'pw123456'})
        self.assertRedirects(r, reverse('employee_list'))
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_non_staff_account_rejected(self):
        """บัญชีธรรมดา login หน้า staff ไม่ได้ (StaffLoginForm ปฏิเสธ code not_staff)"""
        r = self.client.post(reverse('staff_login'),
                             {'username': 'plainuser', 'password': 'pw123456'})
        self.assertEqual(r.status_code, 200)   # กลับ render ฟอร์ม + error
        self.assertContains(r, 'ไม่มีสิทธิ์')

    def test_wrong_password_stays_on_form(self):
        """รหัสผิด → อยู่หน้าเดิม (200)"""
        r = self.client.post(reverse('staff_login'),
                             {'username': 'teacher', 'password': 'nope'})
        self.assertEqual(r.status_code, 200)


class LiveSearchTest(TestCase):
    """LiveSearchListView — fetch header คืน partial, form ปกติคืนเต็มหน้า"""

    def setUp(self):
        self.staff = User.objects.create_user(username='teacher', password='pw', is_staff=True)
        self.client.force_login(self.staff)
        Employee.objects.create(
            emp_code='EMP001', name='สมชาย ขยัน', gender='M', department='ไอที',
            phone='0812345678', status='active',
            salary=Decimal('25000.00'), hire_date=timezone.localdate(), address='กทม',
        )
        Employee.objects.create(
            emp_code='EMP002', name='สมหญิง ใจดี', gender='F', department='บุคคล', status='leave',
            salary=Decimal('20000.00'), hire_date=timezone.localdate(), address='กทม',
        )

    def test_full_page_includes_chrome(self):
        """GET ปกติ → หน้าเต็มมี navbar THAMMATHAD SHOP"""
        r = self.client.get(reverse('employee_list'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'THAMMATHAD SHOP')

    def test_fetch_returns_partial_rows_only(self):
        """fetch header → เฉพาะ partial (data-slot) ไม่มี chrome หน้าเต็ม"""
        r = self.client.get(reverse('employee_list'), HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-slot="rows"')
        self.assertNotContains(r, 'THAMMATHAD SHOP')

    def test_search_filters_rows(self):
        """ค้นหา 'สมชาย' → เห็นเฉพาะ EMP001"""
        r = self.client.get(reverse('employee_list'), {'q': 'สมชาย'},
                            HTTP_X_REQUESTED_WITH='fetch')
        self.assertContains(r, 'EMP001')
        self.assertNotContains(r, 'EMP002')

    def test_product_manage_partial_and_full(self):
        """product manage: fetch → partial, ปกติ → เต็มหน้า"""
        Product.objects.create(name='เก้าอี้หุ้มหนัง', price=Decimal('1000.00'),
                               stock=3, category='เฟอร์นิเจอร์', is_active=True)
        r = self.client.get(reverse('product_manage'), HTTP_X_REQUESTED_WITH='fetch')
        self.assertContains(r, 'data-slot="rows"')
        self.assertNotContains(r, 'THAMMATHAD SHOP')
        self.assertContains(self.client.get(reverse('product_manage')), 'THAMMATHAD SHOP')


class StockAdjustTest(TestCase):
    """ปรับสต็อกด่วน — clamp ไม่ติดลบ, delta มั่วถือว่า 0"""

    def setUp(self):
        self.staff = User.objects.create_user(username='teacher', password='pw', is_staff=True)
        self.client.force_login(self.staff)
        self.product = Product.objects.create(
            name='เคสโทรศัพท์', price=Decimal('50.00'), stock=5,
            category='เคส', is_active=True,
        )

    def test_increase_stock(self):
        """+3 → stock 8"""
        r = self.client.post(reverse('stock_adjust', args=[self.product.id]),
                             {'delta': '3'}, HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.json()['ok'], True)
        self.assertEqual(r.json()['stock'], 8)

    def test_decrease_clamped_at_zero(self):
        """-99 → ไม่ติดลบ (clamp ที่ 0)"""
        r = self.client.post(reverse('stock_adjust', args=[self.product.id]),
                             {'delta': '-99'}, HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.json()['stock'], 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

    def test_garbage_delta_ignored(self):
        """delta 'abc' → ไม่มีผล (ถือเป็น 0)"""
        r = self.client.post(reverse('stock_adjust', args=[self.product.id]),
                             {'delta': 'abc'}, HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.json()['stock'], 5)


class OrderStatusViewTest(TestCase):
    """หน้าเปลี่ยนสถานะ post — ตามกติกาบันไดของ OrderStatusService"""

    def setUp(self):
        self.staff = User.objects.create_user(username='teacher', password='pw', is_staff=True)
        self.client.force_login(self.staff)
        self.order = Order.objects.create(
            customer_name='ลูกค้า หนึ่ง', phone='0812345678', address='กทม',
            total=Decimal('500.00'), payment_method='promptpay',
        )

    def test_staff_cannot_set_paid(self):
        """กด 'ชำระเงินแล้ว' ด้วยมือ → redirect กลับ + ออเดอร์ยัง pending"""
        r = self.client.post(reverse('order_status', args=[self.order.id]),
                             {'status': 'paid'})
        self.assertRedirects(r, reverse('order_detail', args=[self.order.id]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_skip_step_rejected(self):
        """ข้ามขั้น (pending→shipped) → โดนปฏิเสธ"""
        self.client.post(reverse('order_status', args=[self.order.id]), {'status': 'shipped'})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_forward_step_allowed(self):
        """paid→shipped กดได้ (ขั้นถัดไปตามบันได)"""
        OrderStatusService.auto_move(self.order, 'paid')
        r = self.client.post(reverse('order_status', args=[self.order.id]),
                             {'status': 'shipped'})
        self.assertEqual(r.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'shipped')

    def test_invalid_status_message(self):
        """status ที่ไม่รู้จัก → redirect ไป order_manage + error"""
        r = self.client.post(reverse('order_status', args=[self.order.id]),
                             {'status': 'hacked'})
        self.assertRedirects(r, reverse('order_manage'))


class PaymentVerifyTest(TestCase):
    """เจ้าหน้าที่ยืนยันยอดแจ้งชำระ — paid ขึ้นเมื่อยอดแจ้งครบเท่านั้น"""

    def setUp(self):
        self.staff = User.objects.create_user(username='teacher', password='pw', is_staff=True)
        self.client.force_login(self.staff)
        self.order = Order.objects.create(
            customer_name='ลูกค้า หนึ่ง', phone='0812345678', address='กทม',
            total=Decimal('500.00'), payment_method='promptpay',
        )
        self.payment = Payment.objects.create(
            order=self.order, name='ลูกค้า หนึ่ง', phone='0812345678',
            amount=Decimal('300.00'), transfer_date=timezone.localdate(), note='สลิป 1',
        )

    def test_underpaid_keeps_pending(self):
        """แจ้งมา 300/500 → ยังยืนยันไม่ได้ (ออเดอร์ค้าง pending + เตือนยอดขาด)"""
        r = self.client.post(reverse('payment_verify', args=[self.payment.id]))
        self.assertRedirects(r, reverse('dashboard') + '#reports')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_reported_total_reached_marks_paid(self):
        """เพิ่มอีก 200 → ยอดแจ้ง 500/500 → ยืนยันได้ → paid อัตโนมัติ"""
        Payment.objects.create(
            order=self.order, name='ลูกค้า หนึ่ง', phone='0812345678',
            amount=Decimal('200.00'), transfer_date=timezone.localdate(), note='สลิป 2',
        )
        self.client.post(reverse('payment_verify', args=[self.payment.id]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')


class StaffPagesRenderTest(TestCase):
    """หน้า staff ทุกหน้า render ได้ + export CSV + gating ฟีเจอร์ external"""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='teacher', email='t@shop.com', password='pw123456', is_staff=True)
        self.client.force_login(self.staff)
        Employee.objects.create(
            emp_code='EMP001', name='สมชาย ขยัน', gender='M', department='ไอที',
            phone='0812345678', status='active',
            salary=Decimal('25000.00'), hire_date=timezone.localdate(), address='กทม',
        )
        self.product = Product.objects.create(
            name='เมาส์', price=Decimal('100.00'), stock=5, category='อุปกรณ์', is_active=True,
        )
        self.order = Order.objects.create(
            customer_name='ลูกค้า หนึ่ง', phone='0812345678', address='กทม',
            total=Decimal('100.00'), payment_method='promptpay',
        )
        Payment.objects.create(
            order=self.order, name='ลูกค้า หนึ่ง', phone='0812345678',
            amount=Decimal('100.00'), transfer_date=timezone.localdate(), note='สลิป',
        )

    def test_all_staff_pages_render_200(self):
        """dashboard/employees/product/manage/orders/customers/reports/payments เปิดได้"""
        urls = [reverse('dashboard'), reverse('employee_list'), reverse('product_manage'),
                reverse('order_manage'), reverse('customer_list'), reverse('reports'),
                reverse('payment_list'), reverse('employee_create'), reverse('product_add'),
                reverse('order_detail', args=[self.order.id]), reverse('product_edit', args=[self.product.id])]
        for url in urls:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)

    def test_employee_export_csv(self):
        """export พนักงาน → CSV utf-8 BOM + header รหัสพนักงาน"""
        r = self.client.get(reverse('employee_export'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'text/csv; charset=utf-8')
        self.assertEqual(r.content[:3], b'\xef\xbb\xbf')   # BOM กัน Excel อ่านไทยเพี้ยน
        self.assertContains(r, 'รหัสพนักงาน')
        self.assertContains(r, 'สมชาย ขยัน')

    def test_payment_export_csv(self):
        """export การชำระ → CSV + header เลขออเดอร์"""
        r = self.client.get(reverse('payment_export'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'เลขออเดอร์')

    def test_order_export_csv(self):
        """export ออเดอร์ → CSV utf-8 BOM + header เลขออเดอร์ + ข้อมูลออเดอร์"""
        r = self.client.get(reverse('order_export'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'text/csv; charset=utf-8')
        self.assertEqual(r.content[:3], b'\xef\xbb\xbf')   # BOM กัน Excel อ่านไทยเพี้ยน
        self.assertContains(r, 'เลขออเดอร์')
        self.assertContains(r, 'ลูกค้า หนึ่ง')

    def test_order_invoice_access(self):
        """ใบเสร็จ A4: staff ดูได้, เจ้าของดูได้, guest มี phone ดูได้, คนอื่นเข้าไม่ได้"""
        invoice_url = reverse('order_invoice', args=[self.order.id])

        # 1. Staff เข้าดูได้
        r = self.client.get(invoice_url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ใบเสร็จรับเงิน')
        self.assertContains(r, self.order.customer_name)

        # 2. Guest ที่มีเบอร์โทรถูกต้อง เข้าดูได้
        self.client.logout()
        r = self.client.get(f"{invoice_url}?phone={self.order.phone}")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ใบเสร็จรับเงิน')

        # 3. Guest ที่ไม่มีเบอร์โทรหรือไม่ถูกต้อง → redirect ไป login
        r = self.client.get(invoice_url)
        self.assertRedirects(r, f"{reverse('account_login')}?next={invoice_url}")

        # 4. ลูกค้าอื่นที่ล็อกอินแล้วแต่ไม่ใช่เจ้าของ → 404
        other_user = User.objects.create_user(username='other', password='pw123456')
        self.client.force_login(other_user)
        r = self.client.get(invoice_url)
        self.assertEqual(r.status_code, 404)

        # 5. ลูกค้าที่เป็นเจ้าของออเดอร์ → ดูได้
        self.order.user = other_user
        self.order.save()
        r = self.client.get(invoice_url)
        self.assertEqual(r.status_code, 200)

    def test_dashboard_low_stock_alert_and_quick_adjust(self):
        """แดชบอร์ดมี Alert Banner เมื่อมีสินค้าใกล้หมด + ปุ่มเติมสต็อก +5"""
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'แจ้งเตือนสต็อกสินค้าวิกฤต')
        self.assertContains(r, 'สต็อกต้องเฝ้าระวัง')

        # ทดสอบเติมสต็อก +5 จากแดชบอร์ด
        old_stock = self.product.stock
        r_post = self.client.post(
            reverse('stock_adjust', args=[self.product.id]),
            {'delta': '5', 'next': reverse('dashboard')}
        )
        self.assertRedirects(r_post, reverse('dashboard'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, old_stock + 5)

    @override_settings(GEMINI_API_KEY='')
    def test_ai_disabled_returns_503(self):
        """ไม่มี GEMINI_API_KEY → /describe-ai/ ตอบ 503 พร้อมข้อความไทย"""
        r = self.client.post(reverse('product_describe_ai'), {'name': 'เมาส์'})
        self.assertEqual(r.status_code, 503)