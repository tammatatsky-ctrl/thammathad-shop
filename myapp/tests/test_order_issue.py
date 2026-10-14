"""แจ้งปัญหา — ลูกค้าแจ้ง → เจ้าหน้าที่ปิดเรื่อง

ทำไมต้องมีฟีเจอร์นี้
    หน้า `/contact/` เดิมมีแต่ข้อความนิ่ง (ชื่อผู้ทำ/อีเมล) — กดอะไรไม่ได้เลย
    พอมีปัญหาจริง (ของเสียหาย / ส่งผิด / ยอดชำระไม่ตรง) ลูกค้ามีทางเดียวคือ
    "ไม่รู้จะบอกใคร" และฝั่งร้านก็ไม่มีคิวงานที่จะเห็น

สิ่งที่เทสต์นี้กันกันไว้
    - ลูกค้าแจ้งแทนออเดอร์คนอื่นไม่ได้ (เดาเลขออเดอร์ถูกก็ไม่ผ่าน เพราะต้องมีเบอร์ตรง)
    - ปิดเรื่องโดยไม่บอกผลการดำเนินการไม่ได้ (ลูกค้าจะต้องถามซ้ำ)
    - ลูกค้าเห็นผลที่ร้านเขียนไว้ในหน้าบัญชีของตัวเอง (ปิดวงจรครบ)
    - หลังบ้านเปิดได้เฉพาะ staff
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from myapp.models import Order, OrderItem, Product


def make_order(pk_owner=None, phone='0812345678', total='1290.00', status='paid'):
    """สร้างออเดอร์ที่มีสินค้าจริง 1 ชิ้น (ไม่ใช้ setUpTestData เพราะแต่ละเคสต้องกันชนกัน)

    Args:
        pk_owner: ผู้ใช้ที่สั่งซื้อ (Order FK ชื่อ `user` — ลูกค้าที่สมัครสมาชิกเท่านั้น
            ที่ผูกออเดอร์ได้ ออเดอร์จาก guest จะมี user=None)
    """
    product = Product.objects.create(
        name='เมาส์ไร้สาย', price=Decimal(total), stock=5)
    order = Order.objects.create(
        customer_name='ลูกค้า', phone=phone, address='กทม',
        total=Decimal(total), payment_method='bank', status=status,
        user=pk_owner)
    OrderItem.objects.create(order=order, product=product, quantity=1,
                              price=Decimal(total))
    return order


class CustomerReportsIssueTest(TestCase):
    """ลูกค้าแจ้งปัญหาได้ — ผูกกับออเดอร์หรือไม่ก็ได้"""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='teacher', password='pw', is_staff=True)
        self.order = make_order(phone='0812345678')

    def _report(self, **overrides):
        data = {
            'order_id': self.order.id,
            'phone': self.order.phone,
            'kind': 'damaged',
            'subject': 'เมาส์ที่ได้รับชำรุด',
            'detail': 'กล่องบุ๋น ปุ่มซ้ายหลุดติดมาด้วย',
            'back': reverse('order_tracking'),
        }
        data.update(overrides)
        return self.client.post(
            reverse('order_issue', args=[self.order.id]), data, follow=True)

    def test_creates_issue_linked_to_order(self):
        r = self._report()
        msgs = [str(m) for m in r.context['messages']]
        self.assertTrue(any('รับเรื่องแล้ว' in m for m in msgs), msgs)

        from myapp.models import OrderIssue
        issue = OrderIssue.objects.get()
        self.assertEqual(issue.order_id, self.order.id)
        self.assertEqual(issue.kind, 'damaged')
        self.assertEqual(issue.status, 'open', 'ต้องเริ่มที่รอดำเนินการ')
        self.assertEqual(issue.phone, self.order.phone)

    def test_cannot_report_on_someone_elses_order(self):
        """รู้เลขออเดอร์ของคนอื่นก็แจ้งแทนไม่ได้ — ต้องมีเบอร์ตรงด้วย"""
        self._report(phone='0899999999')
        from myapp.models import OrderIssue
        self.assertEqual(OrderIssue.objects.count(), 0)

    def test_can_report_without_order_from_contact_page(self):
        """หน้า /contact/ ใช้ได้แม้ไม่มีออเดอร์ (ลูกค้ามีปัญหาสินค้าทั่วไป)"""
        self.client.post(reverse('order_issue', args=[0]), {
            'kind': 'other',
            'name': 'สมชาย',
            'phone': '0891234567',
            'email': 'somchai@example.com',
            'subject': 'อยากถามเรื่องสินค้าที่ยังไม่มีในเว็บ',
            'detail': 'มีเมาส์แบบเลื่อนต์ไหมครับ',
        }, follow=True)

        from myapp.models import OrderIssue
        issue = OrderIssue.objects.get()
        self.assertIsNone(issue.order_id)
        self.assertEqual(issue.name, 'สมชาย')
        self.assertEqual(issue.email, 'somchai@example.com')

    def test_requires_subject_and_detail(self):
        self._report(subject='', detail='')
        from myapp.models import OrderIssue
        self.assertEqual(OrderIssue.objects.count(), 0)

    def test_guest_needs_reachable_phone(self):
        """ไม่มีเบอร์ติดต่อ = ร้านติดต่อกลับไม่ได้ → ปฏิเสธตั้งแต่ต้น"""
        self.client.post(reverse('order_issue', args=[0]), {
            'kind': 'other', 'name': 'สมชาย', 'phone': '',
            'subject': 'ทดสอบ', 'detail': 'ทดสอบ',
        }, follow=True)
        from myapp.models import OrderIssue
        self.assertEqual(OrderIssue.objects.count(), 0)

    def test_issue_report_page_renders_the_form_and_contact_is_separate(self):
        """หน้า /issue/ แสดงฟอร์มแจ้งปัญหา ส่วนหน้า /contact/ แยกเป็นหน้าติดต่อที่มีปุ่มชี้ไป /issue/"""
        issue_html = self.client.get(reverse('issue_report')).content.decode('utf-8')
        self.assertIn('แจ้งปัญหา', issue_html)
        self.assertIn('name="detail"', issue_html)

        contact_html = self.client.get(reverse('contact')).content.decode('utf-8')
        self.assertNotIn('name="detail"', contact_html,
                         'ฟอร์มแจ้งปัญหาต้องแยกออกจากหน้า /contact/')
        self.assertIn(reverse('issue_report'), contact_html)

    def test_issue_report_page_prefills_verified_order(self):
        """เปิด /issue/?order=<id>&phone=<phone> ที่ตรงกัน → แสดงออเดอร์ที่ผูกไว้"""
        html = self.client.get(
            reverse('issue_report'),
            {'order': self.order.id, 'phone': self.order.phone},
        ).content.decode('utf-8')
        self.assertIn(f'ออเดอร์ #{self.order.id}', html)

    def test_report_link_on_tracking_page_carries_order_identity(self):
        html = self.client.get(
            reverse('order_tracking'),
            {'order': self.order.id, 'phone': self.order.phone}
        ).content.decode('utf-8')
        self.assertIn(reverse('issue_report'), html)
        self.assertIn(f'order={self.order.id}', html)


class StaffHandlesIssueTest(TestCase):
    """เจ้าหน้าที่เห็นคิวและปิดเรื่องได้"""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='teacher', password='pw', is_staff=True)
        self.order = make_order()

    def _open_issue(self):
        from myapp.models import OrderIssue
        return OrderIssue.objects.create(
            order=self.order, name='ลูกค้า', phone=self.order.phone,
            kind='damaged', subject='ของชำรุด', detail='กล่องบุ๋น')

    def test_queue_requires_staff(self):
        r = self.client.get(reverse('issue_list'))
        self.assertEqual(r.status_code, 302)

    def test_queue_lists_open_issue(self):
        self._open_issue()
        self.client.force_login(self.staff)
        html = self.client.get(reverse('issue_list')).content.decode('utf-8')
        self.assertIn('ของชำรุด', html)
        self.assertIn('รอเจ้าหน้าที่ดำเนินการ', html)

    def test_search_filters_by_order_number(self):
        """เจ้าหน้าที่ที่รับโทรศัพท์มามีแต่เลขออเดอร์ — ค้นด้วยตัวเลขต้องเจอ"""
        self._open_issue()
        self.client.force_login(self.staff)
        html = self.client.get(
            reverse('issue_list'), {'q': str(self.order.id)}
        ).content.decode('utf-8')
        self.assertIn('ของชำรุด', html)

    def test_status_filter_excludes_resolved(self):
        from myapp.models import OrderIssue
        keep = self._open_issue()
        OrderIssue.objects.create(
            order=self.order, name='คนสอง', phone='0899', kind='other',
            subject='เรื่องที่แก้แล้ว', detail='x', status='resolved')
        self.client.force_login(self.staff)
        html = self.client.get(
            reverse('issue_list'), {'status': 'open'}).content.decode('utf-8')
        self.assertIn('ของชำรุด', html)
        self.assertNotIn('เรื่องที่แก้แล้ว', html)
        keep.refresh_from_db()
        self.assertEqual(keep.status, 'open')

    def test_list_renders_resolved_issue_without_handled_by(self):
        """เรื่องที่แก้แล้วแต่ไม่มี handled_by (เช่น seed data) ต้องเรนเดอร์ได้ ไม่พัง 500"""
        from myapp.models import OrderIssue
        OrderIssue.objects.create(
            order=self.order, name='คนสอง', phone='0899', kind='other',
            subject='เรื่องที่แก้แล้ว', detail='x', status='resolved',
            resolution='แก้แล้ว', handled_by=None)
        self.client.force_login(self.staff)
        r = self.client.get(reverse('issue_list'))
        self.assertEqual(r.status_code, 200)
        self.assertIn('เรื่องที่แก้แล้ว', r.content.decode('utf-8'))

    @override_settings(ACTIVITY_LOG_ENABLED=True)
    def test_resolve_requires_a_resolution(self):
        """ปิดโดยไม่บอกว่าทำอะไร = ลูกค้าต้องถามซ้ำ → ต้องปฏิเสธ"""
        issue = self._open_issue()
        self.client.force_login(self.staff)
        self.client.post(reverse('issue_update', args=[issue.pk]),
                         {'status': 'resolved', 'resolution': '  '})
        issue.refresh_from_db()
        self.assertEqual(issue.status, 'open', 'ยังค้างอยู่ = ไม่รับคำสั่งที่ไม่มีผล')

    def test_resolve_records_who_and_what(self):
        issue = self._open_issue()
        self.client.force_login(self.staff)
        self.client.post(reverse('issue_update', args=[issue.pk]), {
            'status': 'resolved', 'resolution': 'ส่งของใหม่ให้แล้ว เปลี่ยนเมาส์ชิ้น'})
        issue.refresh_from_db()
        self.assertEqual(issue.status, 'resolved')
        self.assertEqual(issue.handled_by_id, self.staff.id)
        self.assertEqual(issue.resolution, 'ส่งของใหม่ให้แล้ว เปลี่ยนเมาส์ชิ้น')
        self.assertIsNotNone(issue.resolved_at)

    def test_reopen_clears_resolved_at(self):
        """เปิดเรื่องกลับมาแล้ว 'แก้เมื่อ' ต้องหาย ไม่ใช่ค้างวันที่เก่า"""
        issue = self._open_issue()
        self.client.force_login(self.staff)
        self.client.post(reverse('issue_update', args=[issue.pk]),
                         {'status': 'resolved', 'resolution': 'แก้แล้ว'})
        self.client.post(reverse('issue_update', args=[issue.pk]),
                         {'status': 'in_progress', 'resolution': ''})
        issue.refresh_from_db()
        self.assertEqual(issue.status, 'in_progress')
        self.assertIsNone(issue.resolved_at)

    def test_rejects_unknown_status(self):
        issue = self._open_issue()
        self.client.force_login(self.staff)
        self.client.post(reverse('issue_update', args=[issue.pk]),
                         {'status': 'hacked', 'resolution': 'x'})
        issue.refresh_from_db()
        self.assertEqual(issue.status, 'open')

    def test_non_staff_cannot_resolve(self):
        issue = self._open_issue()
        r = self.client.post(reverse('issue_update', args=[issue.pk]),
                             {'status': 'resolved', 'resolution': 'แก้แล้ว'})
        self.assertEqual(r.status_code, 302)
        issue.refresh_from_db()
        self.assertEqual(issue.status, 'open')

    def test_order_detail_shows_issue_alert_and_list(self):
        """หน้ารายละเอียดออเดอร์ของ staff ต้องเตือนเมื่อมีปัญหาค้างอยู่"""
        issue = self._open_issue()
        self.client.force_login(self.staff)
        html = self.client.get(reverse('order_detail', args=[self.order.id])).content.decode('utf-8')
        self.assertIn('คำสั่งซื้อนี้มีปัญหาค้างอยู่', html)
        self.assertIn('ของชำรุด', html)

    def test_order_manage_shows_open_issue_count_badge(self):
        """หน้าตารางคำสั่งซื้อของ staff ต้องมี badge เตือนปัญหาค้าง"""
        self._open_issue()
        self.client.force_login(self.staff)
        html = self.client.get(reverse('order_manage')).content.decode('utf-8')
        self.assertIn('มีปัญหาค้างอยู่ 1 เรื่อง', html)


class CustomerSeesResolutionTest(TestCase):
    """ลูกค้าเห็นผลที่ร้านเขียนไว้ — ปิดวงจรครบ ไม่ต้องโทรมาถามซ้ำ"""

    def setUp(self):
        self.customer = User.objects.create_user(
            username='buyer', password='pw', email='b@example.com',
            first_name='บ', last_name='ซ')
        self.order = make_order(pk_owner=self.customer)

    def test_issue_appears_on_account_page_with_status(self):
        from myapp.models import OrderIssue
        OrderIssue.objects.create(
            order=self.order, user=self.customer, name='บ ซ',
            phone=self.order.phone, kind='damaged',
            subject='เมาส์ชำรุด', detail='ปุ่มหลุด')

        self.client.force_login(self.customer)
        html = self.client.get(reverse('account')).content.decode('utf-8')
        self.assertIn('เมาส์ชำรุด', html)
        self.assertIn('รอเจ้าหน้าที่ดำเนินการ', html)

    def test_resolution_text_is_visible_to_the_customer(self):
        from myapp.models import OrderIssue
        issue = OrderIssue.objects.create(
            order=self.order, user=self.customer, name='บ ซ',
            phone=self.order.phone, kind='damaged',
            subject='เมาส์ชำรุด', detail='ปุ่มหลุด')
        issue.mark('resolved', self.customer, 'ส่งของใหม่ให้แล้ว')

        self.client.force_login(self.customer)
        html = self.client.get(reverse('account')).content.decode('utf-8')
        self.assertIn('แก้ไขแล้ว', html)
        self.assertIn('ส่งของใหม่ให้แล้ว', html)

    def test_guest_sees_issue_and_resolution_on_tracking_page(self):
        from myapp.models import OrderIssue
        issue = OrderIssue.objects.create(
            order=self.order, name='บ ซ',
            phone=self.order.phone, kind='damaged',
            subject='เมาส์ชำรุด', detail='ปุ่มหลุด')
        issue.mark('resolved', self.customer, 'เคลมสินค้าใหม่ให้เรียบร้อย')

        r = self.client.get(reverse('order_tracking'), {
            'order': self.order.id,
            'phone': self.order.phone,
        })
        self.assertEqual(r.status_code, 200)
        html = r.content.decode('utf-8')
        self.assertIn('ประวัติการแจ้งปัญหา / ข้อสอบถาม', html)
        self.assertIn('เมาส์ชำรุด', html)
        self.assertIn('เคลมสินค้าใหม่ให้เรียบร้อย', html)

    def test_cannot_see_another_customers_issue(self):
        from myapp.models import OrderIssue
        OrderIssue.objects.create(
            order=self.order, user=self.customer, name='บ ซ',
            phone=self.order.phone, subject='ของฉัน', detail='x')
        OrderIssue.objects.create(
            order=self.order, name='คนอื่น', phone='0899',
            subject='เรื่องของคนอื่น', detail='x')

        self.client.force_login(self.customer)
        html = self.client.get(reverse('account')).content.decode('utf-8')
        self.assertIn('ของฉัน', html)
        self.assertNotIn('เรื่องของคนอื่น', html)


class AccountOrderHistoryTest(TestCase):
    """ประวัติออเดอร์ในหน้าบัญชีต้องบอกครบว่า 'ตอนนี้เป็นยังไง และต้องทำอะไรต่อ'"""

    def setUp(self):
        self.customer = User.objects.create_user(
            username='buyer', password='pw', email='b@example.com')
        self.order = make_order(pk_owner=self.customer, total='1000.00',
                                status='pending')

    def test_shows_how_much_is_still_due(self):
        """ออเดอร์จ่ายบางส่วน = กล่อง 'แจ้งมาแล้ว ฿400 เหลืออีก ฿600' ต้องโผล่

        ผ่านเพราะ `reported_total` เป็น property แล้ว — ถ้ากลับไปเป็น method
        `{% if order.reported_total > 0 %}` จะเทียบ method กับเลข = TypeError
        แล้วเงื่อนไขเป็น False ทุกครั้ง กล่องนี้จะหายไปเงียบ ๆ
        """
        from myapp.models import Payment
        Payment.objects.create(
            order=self.order, name='บ', phone=self.order.phone,
            amount=Decimal('400.00'), transfer_date='2026-01-01')

        self.client.force_login(self.customer)
        html = self.client.get(reverse('account')).content.decode('utf-8')
        self.assertIn('400.00', html)
        self.assertIn('600.00', html)
        self.assertIn('ขาดอีก', html)

    def test_progress_bar_never_exceeds_full_width(self):
        """โอนเกินยอด (ลูกค้าเผลอ) แถบต้องไม่ล้นเกิน 100%"""
        from myapp.models import Payment
        Payment.objects.create(
            order=self.order, name='บ', phone=self.order.phone,
            amount=Decimal('1500.00'), transfer_date='2026-01-01')
        self.order.refresh_from_db()
        self.assertEqual(self.order.paid_percent, 100)

    def test_status_label_is_not_misleading(self):
        """เดิมขึ้น 'รอตรวจ' สำหรับ pending ทั้งที่จริงคือยังไม่ได้ชำระ"""
        self.client.force_login(self.customer)
        html = self.client.get(reverse('account')).content.decode('utf-8')
        self.assertIn('รอชำระเงิน', html)
        self.assertNotIn('>รอตรวจ<', html)

    def test_each_order_has_all_three_actions(self):
        self.client.force_login(self.customer)
        html = self.client.get(reverse('account')).content.decode('utf-8')
        self.assertIn(reverse('order_invoice', args=[self.order.id]), html)
        self.assertIn(f'order={self.order.id}', html)
        self.assertIn('แจ้งปัญหา', html)