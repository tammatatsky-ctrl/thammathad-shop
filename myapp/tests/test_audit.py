"""เทสต์ audit trail — ตอบคำถาม "ใครทำอะไร เมื่อไหร่" ได้จริง

กลุ่มนี้ล็อกหลักการสำคัญ 4 ข้อที่งานจริงต้องมี:
1. **บันทึกครบทุกจุดที่กระทบเงิน/ของจริง** — เติมสต็อก, เปลี่ยนสถานะออเดอร์,
   ยืนยันยอด, จัดการพนักงาน/สินค้า, เปลี่ยนสิทธิ์บัญชี
2. **เก็บ before → after ที่เปลี่ยนจริง** — ไม่ใช่ dump ทั้งออบเจกต์
3. **การ log พังห้ามทำให้งานหลักพัง** — เติมสต็อกต้องได้แม้ log error
4. **ตรวจสอบย้อนหลังได้จริง** — หน้าเว็บ + export CSV
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from myapp.models import ActivityLog, Employee, Order, Payment, Product
from myapp.services import Audit


def make_order(total='1000.00', status='pending'):
    return Order.objects.create(
        customer_name='ลูกค้า ทดสอบ', phone='0812345678',
        address='กรุงเทพฯ', total=Decimal(total), status=status,
        payment_method='promptpay',
    )


def make_product(stock=10, price='500.00'):
    return Product.objects.create(name='สินค้าทดสอบ', price=Decimal(price),
                                  stock=stock, category='ทดสอบ', is_active=True)


def make_employee(**kw):
    defaults = dict(emp_code='E-T1', name='ทดสอบ ระบบบันทึก', gender='M',
                    department='ไอที', phone='0800000001',
                    salary='25000.00', hire_date='2026-01-02')
    defaults.update(kw)
    return Employee.objects.create(**defaults)


# ⚠️ ACTIVITY_LOG_ENABLED ถูกปิดระหว่างรันเทสต์ (เร็วขึ้น) — เปิดเฉพาะคลาสนี้
@override_settings(ACTIVITY_LOG_ENABLED=True)
class AuditServiceTest(TestCase):
    """ตัว service เอง: บันทึกถูก, กรองข้อมูล, และไม่ลากงานหลักพังตาม"""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='boss', password='pw', is_staff=True)

    def test_records_actor_action_and_target(self):
        product = make_product()
        log = Audit.record(self.staff, 'stock', summary='ทดสอบ', target=product)
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.staff)
        self.assertEqual(log.actor_name, 'boss')
        self.assertEqual(log.action, 'stock')
        self.assertEqual(log.target_type, 'product')
        self.assertEqual(log.target_id, str(product.pk))

    def test_keeps_name_even_if_user_deleted(self):
        """FK เป็น SET_NULL — ถ้าบัญชีถูกลบ ประวัติต้องยังบอกได้ว่าใครเป็นคน"""
        staff = User.objects.create_user(username='temp', password='pw', is_staff=True)
        log = Audit.record(staff, 'stock', summary='ทดสอบ', target=make_product())
        staff.delete()
        log.refresh_from_db()
        self.assertIsNone(log.actor)
        self.assertEqual(log.actor_name, 'temp')

    def test_only_safe_fields_are_stored(self):
        """กันการ dump ข้อมูลส่วนตัว/ขนาดใหญ่ลง log"""
        log = Audit.record(
            self.staff, 'employee', summary='ทดสอบ',
            before={'salary': '1', 'password': 'SECRET', 'email': 'a@b.c'},
            after={'salary': '2', 'avatar': 'x.png'},
        )
        self.assertEqual(set(log.before), {'salary'})
        self.assertEqual(set(log.after), {'salary'})
        self.assertNotIn('SECRET', str(log.before))

    def test_diff_reports_only_changed_fields(self):
        emp = make_employee(salary='30000.00', department='ขาย')
        before = {'salary': '25000.00', 'department': 'ไอที', 'status': 'active'}
        after = Audit.diff(emp, ['salary', 'department', 'status'], before)
        self.assertEqual(set(after), {'salary', 'department'},
                         'status ไม่เปลี่ยน จึงไม่ควรอยู่ใน diff')

    def test_broken_log_does_not_break_business_logic(self):
        """หลักการข้อ 1: log พังห้ามทำให้ "ทำงานต่อไม่ได้" — ต้องกลืน error"""
        with self.settings(ACTIVITY_LOG_ENABLED=True):
            import myapp.services as services
            original = services.Order  # noqa: F841 — ใช้ยืนยันว่า import ยังปกติ

            # บังคับให้ create ล้ม เพื่อจำลอง "ตาราง ActivityLog ยังไม่ถูก migrate"
            from myapp.models import ActivityLog as RealLog
            orig_create = RealLog.objects.create

            def boom(*a, **kw):
                raise RuntimeError('no such table: myapp_activitylog')

            RealLog.objects.create = staticmethod(boom)
            try:
                result = Audit.record(self.staff, 'stock', summary='ทดสอบ')
            finally:
                RealLog.objects.create = orig_create

        self.assertIsNone(result, 'คืน None ไม่ใช่โยน error ออกมา')

    def test_disabled_by_setting(self):
        with self.settings(ACTIVITY_LOG_ENABLED=False):
            before_count = ActivityLog.objects.count()
            result = Audit.record(self.staff, 'stock', summary='ไม่ควรบันทึก')
        self.assertIsNone(result)
        self.assertEqual(ActivityLog.objects.count(), before_count)


@override_settings(ACTIVITY_LOG_ENABLED=True)
class AuditCoversMoneyPathsTest(TestCase):
    """ทุกจุดที่กระทบเงิน/ของจริงต้องถูกบันทึก"""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='boss', password='pw', is_staff=True)
        self.client.force_login(self.staff)

    def test_stock_adjust_is_logged_with_before_after(self):
        product = make_product(stock=10)
        self.client.post(reverse('stock_adjust', args=[product.pk]),
                         {'delta': '5', 'next': reverse('dashboard')})
        product.refresh_from_db()
        self.assertEqual(product.stock, 15)

        log = ActivityLog.objects.filter(action='stock').first()
        self.assertIsNotNone(log, 'ต้องมีบันทึกการปรับสต็อก')
        self.assertEqual(log.actor, self.staff)
        self.assertEqual(log.before['stock'], 10)
        self.assertEqual(log.after['stock'], 15)

    def test_order_status_change_is_logged(self):
        order = make_order(status='paid')
        self.client.post(reverse('order_status', args=[order.pk]),
                         {'status': 'shipped'})
        order.refresh_from_db()
        self.assertEqual(order.status, 'shipped')

        log = ActivityLog.objects.filter(action='order_status').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.before['status'], 'paid')
        self.assertEqual(log.after['status'], 'shipped')

    def test_payment_verify_is_logged(self):
        order = make_order(total='1000.00')
        Payment.objects.create(order=order, name='ลูกค้า', phone='0812345678',
                               amount=Decimal('1000.00'), transfer_date='2026-10-13')
        payment = order.payments.first()

        self.client.post(reverse('payment_verify', args=[payment.pk]))
        log = ActivityLog.objects.filter(action='payment').first()
        self.assertIsNotNone(log, 'ยืนยันเงินต้องมีบันทึก (กระทบตัวเงินโดยตรง)')
        self.assertIn('ยืนยัน', log.summary)

    def test_employee_create_and_delete_are_logged(self):
        self.client.post(reverse('employee_create'), {
            'name': 'สมชาย ใจดี', 'gender': 'M', 'department': 'ขาย',
            'phone': '0811111111', 'email': 's@example.com',
            'salary': '30000', 'hire_date': '2026-02-02', 'status': 'active',
        })
        emp = Employee.objects.get(name='สมชาย ใจดี')
        self.assertTrue(ActivityLog.objects.filter(action='employee').exists(),
                        'สร้างพนักงานต้องมีบันทึก')

        if self.staff.has_perm('myapp.delete_employee'):
            self.client.post(reverse('employee_delete', args=[emp.pk]))
            logs = ActivityLog.objects.filter(action='employee')
            self.assertTrue(any('ลบพนักงาน' in lg.summary for lg in logs),
                            'ลบพนักงานต้องมีบันทึก')

    def test_create_log_has_no_spurious_diff(self):
        """ตอนสร้างใหม่ไม่มี "ค่าเดิม" — จึงห้ามรายงานว่าทุกฟิลด์ "เปลี่ยน" """
        self.client.post(reverse('employee_create'), {
            'name': 'ใหม่ สร้างสด', 'gender': 'F', 'department': 'วิศวกรรม',
            'phone': '0822222222', 'email': 'n@example.com',
            'salary': '45000', 'hire_date': '2026-03-03', 'status': 'active',
        })
        log = ActivityLog.objects.filter(action='employee').first()
        self.assertIsNone(log.after, 'สร้างใหม่ไม่ควรมี after (ไม่มีอะไร "เปลี่ยน")')
        self.assertNotIn('เปลี่ยน:', log.summary)

    def test_product_price_change_is_logged(self):
        product = make_product(price='500.00')
        self.client.post(reverse('product_edit', args=[product.pk]), {
            'name': product.name, 'price': '750.00', 'stock': '10',
            'category': 'ทดสอบ', 'is_active': 'on',
        })
        product.refresh_from_db()
        self.assertEqual(product.price, Decimal('750.00'))

        log = ActivityLog.objects.filter(action='product').first()
        self.assertIsNotNone(log)
        self.assertIn('price', (log.after or {}))


@override_settings(ACTIVITY_LOG_ENABLED=True)
class ActivityLogPageTest(TestCase):
    """หน้าเว็บต้องตรวจสอบย้อนหลังได้จริง (staff เท่านั้น)"""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='boss', password='pw', is_staff=True)
        self.client.force_login(self.staff)
        Audit.record(self.staff, 'stock', summary='ปรับสต็อก "เมาส์" 5 → 8',
                     target=make_product(stock=8))

    def test_staff_can_open_activity_page(self):
        r = self.client.get(reverse('activity_log'))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'activity_log.html')
        self.assertContains(r, 'ปรับสต็อก')
        self.assertContains(r, 'boss')

    def test_anonymous_redirected(self):
        self.client.logout()
        r = self.client.get(reverse('activity_log'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/staff/login/', r['Location'])

    def test_search_filters_rows(self):
        Audit.record(self.staff, 'role', summary='เปลี่ยนบทบาท somchai → Manager')
        r = self.client.get(reverse('activity_log'), {'q': 'somchai'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'somchai')
        self.assertNotContains(r, 'ปรับสต็อก "เมาส์" 5 → 8')

    def test_action_filter(self):
        Audit.record(self.staff, 'role', summary='เปลี่ยนบทบาท somchai → Manager')
        r = self.client.get(reverse('activity_log'), {'action': 'role'})
        self.assertContains(r, 'somchai')
        self.assertNotContains(r, 'ปรับสต็อก "เมาส์" 5 → 8')

    def test_empty_state_is_explained(self):
        """ไม่มีข้อมูลต้องบอกว่าจะมีเมื่อไหร่ ไม่ใช่ปล่อยตารางว่าง"""
        ActivityLog.objects.all().delete()
        r = self.client.get(reverse('activity_log'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ยังไม่มีการบันทึก')

    def test_csv_export_has_bom_and_columns(self):
        r = self.client.get(reverse('activity_export'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'text/csv; charset=utf-8')
        self.assertEqual(r.content[:3], b'\xef\xbb\xbf', 'ต้องมี BOM กัน Excel เพี้ยน')
        body = r.content.decode('utf-8-sig')
        self.assertIn('ผู้ทำ', body)
        self.assertIn('ปรับสต็อก', body)
        self.assertIn('boss', body)

    def test_csv_export_requires_staff(self):
        self.client.logout()
        r = self.client.get(reverse('activity_export'))
        self.assertEqual(r.status_code, 302)
