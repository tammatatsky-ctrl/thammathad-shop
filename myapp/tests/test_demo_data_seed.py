"""คำสั่ง `seed_demo_data` — เปลี่ยนข้อมูลทดสอบให้เป็นข้อมูลตัวอย่างจริง

ฟีเจอร์นี้ไม่กระทบ "การทำงาน" ของระบบ แต่ถ้าพังเงียบ ๆ ผลคือ
อาจารย์เห็นข้อมูลที่ดูเหมือนระบบยังไม่เสร็จ หรือแย่กว่านั้นคือ
ข้อมูลที่ "ดูจริง" แต่ไม่จริง เช่น เรื่องแจ้งปัญหาผูกกับสินค้าผิดชิ้น

สิ่งที่เทสต์นี้กันไว้
    - รันซ้ำแล้วไม่เกิดข้อมูลซ้ำ (idempotent) — รันผิดแล้วสร้าง
      ออเดอร์ซ้ำเท่าจำนวนออเดอร์ทุกครั้งที่รัน
    - **ไม่แตะ superuser 3 บัญชี** และทรัพย์สินของ `ohm`
    - สถานะออเดอร์ต้องสอดคล้องกับยอดที่จ่ายจริงเสมอ
      (สถานะสูงกว่า pending แต่ไม่มี Payment = รายได้ในแดชบอร์ดไม่ตรง)
    - เรื่องแจ้งปัญหาต้องผูกกับออเดอร์ที่**เป็นของลูกค้าคนนั้น**
    - ไม่มีชื่อ/อีเมลที่ดูเหมือนข้อมูลทดสอบหลงเหลือ
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from io import StringIO

from myapp.management.commands.seed_demo_data import (CUSTOMERS, EMPLOYEES,
                                                       ISSUES, JUNK_USERNAMES,
                                                       KEEP_USERS, OHM_ADDRESS,
                                                       ORDERS)
from myapp.models import (ActivityLog, CustomerAddress, CustomerProfile,
                          Employee, Order, OrderIssue, Payment, Product)


class SeedDemoDataTestMixin:
    """ตั้งข้อมูลตั้งต้นให้เหมือนฐานข้อมูลจริงหลังพัฒนา — รวมสินค้าไว้ด้วย"""

    @classmethod
    def setUpTestData(cls):
        # สเปกออเดอร์อ้างถึงสิน���้าถึงตัวที่ 12 → ต้องมีครบเท่าจำนวนจริง
        # ไม่งั้นคำสั่งจะพังด้วย IndexError ซึ่งไม่บอกว่าต้องทำอะไร
        for i in range(1, 13):
            Product.objects.create(
                name=f'สินค้าตัวอย่าง {i}', price=Decimal(450 + i * 100),
                stock=50)

    def run_seed(self, *args):
        out = StringIO()
        call_command('seed_demo_data', *args, stdout=out)
        return out.getvalue()


class SeedRequiresCatalogTest(TestCase):
    """ยังไม่มีสินค้า = ต้องบอกให้รัน seed_catalog ไม่ใช่พังแบบไม่บอกสาเหตุ"""

    def test_explains_what_to_run_when_catalog_is_empty(self):
        with self.assertRaises(SystemExit) as ctx:
            call_command('seed_demo_data', stdout=StringIO())
        self.assertIn('seed_catalog', str(ctx.exception))

    def test_explains_when_catalog_is_too_small(self):
        Product.objects.create(name='มีแค่ชิ้นเดียว',
                               price=Decimal('100.00'), stock=1)
        with self.assertRaises(SystemExit) as ctx:
            call_command('seed_demo_data', stdout=StringIO())
        self.assertIn('12', str(ctx.exception))


class SeedIsIdempotentTest(SeedDemoDataTestMixin, TestCase):
    """รันซ้ำต้องได้ผลเดิม — คำสั่ง seed ที่รันสองทีแล้วขยะข้อมูล
    ทำให้ฐานข้อมูลที่ส่งให้อาจารย์เต็มไปด้วยออเดอร์ซ้ำ"""

    def test_running_twice_changes_nothing(self):
        self.run_seed()
        first = {
            'users': User.objects.count(),
            'employees': Employee.objects.count(),
            'orders': Order.objects.count(),
            'payments': Payment.objects.count(),
            'issues': OrderIssue.objects.count(),
            'logs': ActivityLog.objects.count(),
        }
        self.run_seed()
        second = {
            'users': User.objects.count(),
            'employees': Employee.objects.count(),
            'orders': Order.objects.count(),
            'payments': Payment.objects.count(),
            'issues': OrderIssue.objects.count(),
            'logs': ActivityLog.objects.count(),
        }
        self.assertEqual(first, second, 'รันซ้ำแล้วจำนวนข้อมูลเปลี่ยน')

    def test_dry_run_writes_nothing(self):
        self.run_seed()
        before = (Order.objects.count(), User.objects.count(),
                  Employee.objects.count())
        self.run_seed('--dry-run')
        after = (Order.objects.count(), User.objects.count(),
                 Employee.objects.count())
        self.assertEqual(before, after, '--dry-run ต้องไม่เขียนอะไรจริง')

    def test_keep_junk_does_not_delete(self):
        junk = User.objects.create_user(username='cmt_probe', password='x')
        self.run_seed('--keep-junk')
        self.assertTrue(User.objects.filter(pk=junk.pk).exists(),
                        '--keep-junk ต้องเก็บบัญชีทดสอบไว้')


class SeedProtectsRealAccountsTest(SeedDemoDataTestMixin, TestCase):
    """ต้องไม่แตะบัญชีของเจ้าของงาน — `ohm` คือบัญชีทดสอบหลัก

    ถ้าคำสั่งนี้ลบ `ohm` ทีหนึ่ง การทำงานต่อทั้งโปรเจกต์จะพังทันที
    และไม่มีทางกู้จาก git เพราะมันอยู่ในฐานข้อมูล
    """

    def test_keeps_all_three_superusers(self):
        for name in KEEP_USERS:
            User.objects.create_user(username=name, password='x',
                                     is_staff=True, is_superuser=True)
        self.run_seed()
        for name in KEEP_USERS:
            self.assertTrue(User.objects.filter(username=name).exists(),
                            f'ลบบัญชี {name} ทิ้ง')

    def test_protected_username_in_junk_list_is_survivable(self):
        """แม้ผู้เขียนพลาดใส่ชื่อที่ต้องเก็บลงในรายการขยะ
        คำสั่งก็ต้องข้าม ไม่ใช่ลบตามรายการ"""
        superuser = User.objects.create_user(
            username='ohm', password='x', is_staff=True, is_superuser=True)
        self.run_seed()
        self.assertTrue(User.objects.filter(pk=superuser.pk).exists())

    def test_does_not_touch_ohm_orders(self):
        ohm = User.objects.create_user(username='ohm', password='x')
        mine = Order.objects.create(
            user=ohm, customer_name='ohm', phone='0800000000',
            address='บ้านของฉัน', total=Decimal('450.00'))
        self.run_seed()
        mine.refresh_from_db()
        self.assertEqual(mine.address, 'บ้านของฉัน',
                         'ออเดอร์ของ ohm ถูกแก้ทับ')

    def test_normalises_ohm_address_but_keeps_avatar(self):
        """ที่อยู่โปรไฟล์เพี้ยนจากการเขียนไฟล์ผิดวิธี (recipe #1)
        ต้องถูกแก้ แต่รูปที่อัปโหลดไว้ต้องอยู่"""
        ohm = User.objects.create_user(username='ohm', password='x')
        profile = CustomerProfile.objects.create(
            user=ohm, phone='0800000000', address='ะพ้เิกิดิ',
            avatar='customers/avatars/me.gif')
        self.run_seed()
        profile.refresh_from_db()
        self.assertEqual(profile.avatar, 'customers/avatars/me.gif',
                         'รูปโปรไฟล์ของฉันหาย')
        self.assertEqual(profile.address, OHM_ADDRESS)


class SeedRemovesTestDataTest(SeedDemoDataTestMixin, TestCase):
    """ข้อมูลที่อาจารย์ไม่ควรเห็นต้องหายไปจริง"""

    def test_removes_probe_and_cmprobe_accounts(self):
        for name in JUNK_USERNAMES:
            if name not in KEEP_USERS:
                User.objects.create_user(username=name, password='x')
        self.run_seed()
        left = User.objects.filter(
            username__in=[n for n in JUNK_USERNAMES if n not in KEEP_USERS])
        self.assertEqual(list(left), [], 'ยังมีบัญชีทดสอบเหลือ')

    def test_removes_test_employees(self):
        for i in range(3):
            Employee.objects.create(
                emp_code=f'EMP9{i:02d}',
                name='ทดสอบ ระบบบันทึก', department='ไอที',
                email='audit.probe@example.com', salary=Decimal('30000.00'),
                hire_date='2026-01-02')
        self.run_seed()
        self.assertEqual(
            Employee.objects.filter(email='audit.probe@example.com').count(), 0)

    def test_removes_demo_named_orders(self):
        Order.objects.create(customer_name='ลูกค้า ทดสอบ', phone='0899',
                             address='123 ถนนตัวอย่าง',
                             total=Decimal('450.00'))
        self.run_seed()
        self.assertFalse(Order.objects.filter(
            customer_name__in=['ลูกค้า สาธิต', 'ลูกค้า ทดสอบ']).exists())

    def test_removes_audit_rows_pointing_at_deleted_employees(self):
        ActivityLog.objects.create(
            actor_name='teacher', action='employee',
            summary='เพิ่มพนักงาน EMP099 — ทดสอบ ระบบบันทึก',
            target_type='employee', target_id='99')
        self.run_seed()
        self.assertFalse(
            ActivityLog.objects.filter(summary__contains='ทดสอบ ระบบบันทึก')
            .exists(),
            'audit ยังอ้างถึงพนักงานที่ถูกลบไปแล้ว')

    def test_no_sample_field_looks_like_test_data(self):
        """เช็คทั้งตารางที่ส่งให้อาจารย์ดู — ถ้ามีคำนี้โผล่แปลว่าล้างไม่ครบ"""
        self.run_seed()
        banned = ('test', 'probe', 'ทดสอบ', 'example.com', 'x@y.z')
        offenders = []
        for field, values in (
            ('ชื่อพนักงาน', list(Employee.objects.values_list('name', flat=True))),
            ('อีเมลพนักงาน', list(Employee.objects.values_list('email', flat=True))),
            ('ชื่อลูกค้า', list(Order.objects.values_list('customer_name', flat=True))),
            ('ที่อยู่', list(Order.objects.values_list('address', flat=True))),
            ('เบอร์โทร', list(CustomerProfile.objects.values_list('phone', flat=True))),
        ):
            for value in values:
                low = (value or '').lower()
                for word in banned:
                    if word in low:
                        offenders.append(f'{field}: {value!r} ({word})')
        self.assertEqual(offenders, [], 'เจอข้อมูลที่ดูเหมือนทดสอบ')


class SeedDataIsCoherentTest(SeedDemoDataTestMixin, TestCase):
    """ข้อมูลตัวอย่างต้องดูเหมือนร้านที่ใช้งานจริง — ถ้าขัดกัน
    อาจารย์จะเจอตัวเลขที่ไม่ตรงกันระหว่างหน้า ซึ่งแย่กว่าไม่มีข้อมูลเลย"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        call_command('seed_demo_data', stdout=StringIO())

    def test_every_status_is_represented(self):
        """ครบทุกขั้นของบันไดสถานะ ไม่งั้นหน้าตัวอย่างจะโชว์แค่ขั้นเดียว"""
        present = set(Order.objects.values_list('status', flat=True))
        self.assertEqual(present, {'pending', 'paid', 'shipped', 'delivered'})

    def test_every_payment_method_is_represented(self):
        present = set(Order.objects.values_list('payment_method', flat=True))
        self.assertEqual(present, {'bank', 'promptpay', 'cod'})

    def test_no_test_employee_status(self):
        """อย่างน้อยมีคนลาออก/ลาพัก หน้าพนักงานถึงจะได้เห็นสถานะอื่นนอกจาก 'ทำงานอยู่'"""
        present = set(Employee.objects.values_list('status', flat=True))
        self.assertEqual(present, {'active', 'leave', 'resigned'})

    def test_advanced_status_always_has_full_payment(self):
        """`pending` = ยังจ่ายไม่ครบเท่านั้น สถานะอื่นต้องมียอดครบ

        ถ้าออเดอร์ `delivered` แต่ไม่มี Payment รายได้ในแดชบอร์ดจะไม่ตรงกับ
        หน้าออเดอร์ เพราะสองที่อ่านคนละแหล่งข้อมูล
        """
        for order in Order.objects.exclude(status='pending'):
            self.assertEqual(
                order.reported_total, order.total,
                f'ออเดอร์ #{order.id} สถานะ {order.status} แต่ยอดไม่ครบ')

    def test_pending_order_can_show_partial_payment(self):
        """ต้องมีออเดอร์ที่จ่ายบางส่วน ไม่งั้นแถบ 'จ่ายแล้ว/ขาดอีก'
        ในหน้าบัญชีจะไม่มีอะไรให้โชว์เลย"""
        partial = [o for o in Order.objects.filter(status='pending')
                   if 0 < o.reported_total < o.total]
        self.assertTrue(partial, 'ไม่มีออเดอร์จ่ายบางส่วนให้สาธิต')

    def test_orders_are_spread_over_several_months(self):
        """ข้อมูลที่กระจุกวันเดียว = กราฟรายงานจะเป็นแท่งเดียว ไม่ได้พิสูจน์อะไร"""
        months = {o.created_at.strftime('%Y-%m') for o in Order.objects.all()}
        self.assertGreaterEqual(len(months), 3,
                                f'ข้อมูลอยู่แค่ {months}')

    def test_cod_orders_record_the_cash_collected(self):
        """เก็บเงินปลายทาง = มี Payment ตอนได้รับของ พร้อมหมายเหตุบอกช่องทาง"""
        cod = Order.objects.filter(payment_method='cod', status='delivered')
        self.assertTrue(cod.exists(), 'ไม่มีออเดอร์เก็บเงินปลายทางที่สำเร็จ')
        for order in cod:
            self.assertTrue(
                order.payments.filter(note__contains='ปลายทาง').exists(),
                f'ออเดอร์ #{order.id} ไม่มีหมายเหตุว่าเก็บปลายทาง')

    def test_each_demo_customer_has_a_profile_and_address(self):
        for username in (c['username'] for c in CUSTOMERS):
            user = User.objects.get(username=username)
            self.assertTrue(hasattr(user, 'customer_profile'),
                            f'{username} ไม่มีโปรไฟล์')
            self.assertTrue(CustomerAddress.objects.filter(user=user).exists(),
                            f'{username} ไม่มีที่อยู่ในสมุด')

    def test_employee_contact_details_are_complete(self):
        """พนักงานที่ไม่มีเบอร์/อีเมลดูเหมือนแถวที่ค้างไว้ ไม่ใช่ข้อมูลจริง"""
        for emp in Employee.objects.all():
            self.assertTrue(emp.phone, f'{emp.emp_code} ไม่มีเบอร์โทร')
            self.assertTrue(emp.email, f'{emp.emp_code} ไม่มีอีเมล')
            self.assertTrue(emp.address, f'{emp.emp_code} ไม่มีที่อยู่')

    def test_issue_belongs_to_the_customers_own_order(self):
        """เรื่องแจ้งปัญหาผูกกับออเดอร์ของคนอื่น = ข้อมูลเท็จ

        เคยเกิดจริงตอนใช้การเดา "ออเดอร์ล่าสุดของลูกค้า"
        แล้วเรื่อง "ส่งคีย์บอร์ดผิดรุ่น" ไปติดกับออเดอร์พาวเวอร์แบงก์
        """
        for issue in OrderIssue.objects.filter(order__isnull=False):
            order = issue.order
            self.assertEqual(
                order.user_id, issue.user_id,
                f'เรื่อง "{issue.subject}" ผูกกับออเดอร์ของคนอื่น '
                f'(order #{order.pk})')

    def test_issue_is_reported_after_the_order_was_placed(self):
        for issue in OrderIssue.objects.filter(order__isnull=False):
            self.assertGreaterEqual(
                issue.created_at, issue.order.created_at,
                f'เรื่อง "{issue.subject}" แจ้งก่อนวันสั่งซื้อ')

    def test_every_issue_status_is_represented(self):
        """ต้องเห็นทั้งเรื่องค้างและเรื่องที่ปิดแล้ว พร้อมผลการดำเนินการ"""
        present = set(OrderIssue.objects.values_list('status', flat=True))
        self.assertIn('open', present)
        self.assertTrue({'resolved', 'in_progress', 'closed'} & present,
                        f'ไม่มีเรื่องที่ปิด/กำลังดำเนินการ: {present}')

    def test_resolved_issues_have_a_written_resolution(self):
        """กฎเดียวกับที่ OrderIssue.mark() บังคับตอนใช้งานจริง"""
        for issue in OrderIssue.objects.filter(
                status__in=['resolved', 'closed']):
            self.assertTrue(issue.resolution.strip(),
                            f'เรื่อง "{issue.subject}" ปิดแล้วแต่ไม่มีผล')

    def test_status_audit_history_reads_as_a_real_timeline(self):
        """ต้องเดินบันไดทีละขั้นเท่านั้น — ถ้าข้ามขั้น เหมือนระบบที่ไม่มีกติกา"""
        ladder = ['pending', 'paid', 'shipped', 'delivered']
        for order in Order.objects.all():
            target = ladder.index(order.status)
            steps = ActivityLog.objects.filter(
                target_type='order', target_id=str(order.pk),
                action='order_status').count()
            self.assertEqual(steps, target,
                             f'ออเดอร์ #{order.pk} ประวัติไม่ตรงกับสถานะ')


class SeedSpecSanityTest(TestCase):
    """ตรวจตัวข้อมูลตัวอย่างในไฟล์เอง — จับความผิดพลาดตั้งแต่ตอนแก้สเปก

    ปัญหาจริงที่เจอรอบนี้คือ "เดาว่าออเดอร์ไหน" แต่ตอนนี้ระบุตรงแล้ว
    เทสต์นี้กันไม่ให้สเปกกับโค้ดหลุดจากกันอีก (เช่น เพิ่มออเดอร์แต่ลืมเพิ่มวิธีชำระ)
    """

    def test_order_and_issue_specs_have_no_orphan_references(self):
        order_days = {row[0] for row in ORDERS}
        for spec in ISSUES:
            reported_day, order_day = spec[0], spec[1]
            self.assertIn(
                order_day, order_days,
                f'เรื่อง "{spec[5]}" อ้างออเดอร์วันที่ {order_day} ที่ไม่มีอยู่')
            self.assertLessEqual(
                order_day, reported_day,
                f'เรื่อง "{spec[5]}" แจ้งก่อนวันสั่งซื้อ')

    def test_every_issue_customer_has_orders(self):
        buyers = {row[1] for row in ORDERS}
        for spec in ISSUES:
            self.assertIn(spec[2], buyers,
                          f'{spec[2]} แจ้งปัญหาแต่ไม่มีออเดอร์ในสเปก')

    def test_protected_users_never_appear_in_junk_list(self):
        """`KEEP_USERS` ต้องไม่ซ้อนกับ `JUNK_USERNAMES`
        (ถ้าซ้อน คำสั่งจะข้ามให้ แต่ตัวเลข "จะลบ N" จะทำให้สับสน)"""
        overlap = KEEP_USERS & set(JUNK_USERNAMES)
        self.assertEqual(overlap, set(),
                         f'ชื่อที่ต้องเก็บไปอยู่ในรายการขยะ: {overlap}')

    def test_partial_payment_is_never_full_amount(self):
        """จ่าย "บางส่วน" ที่ครบยอด = ออเดอร์จะปิดเอง ขัดกับที่ตั้งใจสาธิต"""
        from myapp.management.commands.seed_demo_data import PARTIAL_PAYMENT
        pending_days = {row[0] for row in ORDERS if row[4] == 'pending'}
        for day, amount in PARTIAL_PAYMENT.items():
            self.assertIn(day, pending_days,
                          f'วันที่ {day} ไม่ได้ตั้งเป็น pending แต่กำหนดยอดจ่ายบางส่วน')
            self.assertGreater(amount, 0)

    def test_employee_codes_are_unique_in_the_spec(self):
        codes = [row[0] for row in EMPLOYEES]
        self.assertEqual(len(codes), len(set(codes)), 'รหัสพนักงานซ้ำในสเปก')
        for code in codes:
            self.assertTrue(connection.ops.quote_name(code))