"""เทสต์ P0 — ความถูกต้องของ "สายเงิน" + ไม่หลอกผู้ใช้เรื่องอีเมล + cache-busting static

กลุ่มนี้ล็อกบั๊ก 4 ตัวที่เจอระหว่างทำ P0 (ทั้งหมดกระทบการใช้งานจริง):

1. **อัปโหลดสลิปใส่ออเดอร์ที่จ่ายแล้วได้** → `Payment` ยอดเกิน → รายงานการเงินเพี้ยน
   (`SlipVerifyView` ไม่เช็คสถานะ ต่างจาก `QuickPayView` ที่เช็ค)
2. **`record_payment()` ไม่มี transaction** → 2 request พร้อมกันอ่าน `reported`
   ได้ค่าเดิม ทั้งคู่ผ่านเงื่อนไข "จ่ายครบ"
3. **อีเมลใช้ console backend** → ลิงก์รีเซ็ตหลุดใน console ที่ลูกค้าเข้าไม่ถึง
   แต่หน้าเว็บยังขึ้น "ส่งลิงก์ไปทางอีเมลแล้ว" = หลอกผู้ใช้
4. **static ไม่มี cache-busting** → deploy ใหม่แล้วผู้ใช้เจอ CSS/JS เก่า
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from myapp.models import Order, Payment
from myapp.services import PaymentService


def make_order(total='1000.00', status='pending'):
    return Order.objects.create(
        customer_name='ลูกค้า ทดสอบ', phone='0812345678',
        address='กรุงเทพฯ', total=Decimal(total), status=status,
        payment_method='promptpay',
    )


def slip_upload(name='slip.jpg'):
    """ไฟล์สลิปจริง (ต้องเป็นไฟล์จริง ไม่ใช่ Mock — test client ต้องอ่าน bytes)"""
    return SimpleUploadedFile(name, b'\x89PNG\r\n\x1a\n' + b'0' * 256,
                              content_type='image/jpeg')


class PaymentIntegrityTest(TestCase):
    """จุดรับเงินจุดเดียว: ปฏิเสธยอดเกิน + atomic + ล็อกแถวออเดอร์"""

    def test_refuses_payment_when_order_not_pending(self):
        """ออเดอร์ที่จ่ายแล้ว/ส่งแล้ว/ถึงมือแล้ว → ปฏิเสธ ไม่บันทึก ไม่แตะ DB"""
        for status in ('paid', 'shipped', 'delivered'):
            with self.subTest(status=status):
                order = make_order(status=status)
                result = PaymentService.record_payment(
                    order=order, name='ทดสอบ', phone='0812345678',
                    amount=Decimal('1000.00'), transfer_date='2026-10-13',
                    source='slip',
                )
                self.assertFalse(result['ok'], 'ต้องปฏิเสธ')
                self.assertIsNone(result['payment'])
                self.assertIn('รอชำระ', result['error'])
                self.assertEqual(
                    Payment.objects.filter(order=order).count(), 0,
                    'ห้ามสร้าง Payment ให้ออเดอร์ที่ไม่รอชำระ')

    def test_rejected_payment_does_not_inflate_reported_total(self):
        """บั๊กเดิม: ยอดแจ้งสะสมต้องไม่เกินยอดรวมออเดอร์ (สำคัญต่อรายงานการเงิน)"""
        order = make_order(total='500.00', status='delivered')
        PaymentService.record_payment(
            order=order, name='ทดสอบ', phone='0812345678',
            amount=Decimal('9999.00'), transfer_date='2026-10-13', source='slip',
        )
        self.assertEqual(
            order.reported_total(), Decimal('0'),
            'ยอดแจ้งสะสมต้องยังเป็น 0 — ไม่ใช่ยอดเกิน')

    def test_partial_payments_accumulate_then_paid(self):
        """จ่ายบางส่วน 2 ครั้ง → ยอดสะสมครบ → paid อัตโนมัติ (พฤติกรรมเดิมต้องยังดี)"""
        order = make_order(total='1000.00')
        r1 = PaymentService.record_payment(
            order=order, name='ทดสอบ', phone='0812345678',
            amount=Decimal('400.00'), transfer_date='2026-10-13', source='button')
        self.assertTrue(r1['ok'])
        self.assertFalse(r1['just_paid'])
        self.assertEqual(r1['remaining'], Decimal('600.00'))

        r2 = PaymentService.record_payment(
            order=order, name='ทดสอบ', phone='0812345678',
            amount=Decimal('600.00'), transfer_date='2026-10-13', source='button')
        self.assertTrue(r2['ok'])
        self.assertTrue(r2['just_paid'], 'ยอดครบต้องขึ้น paid อัตโนมัติ')

        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(order.reported_total(), Decimal('1000.00'))

    def test_record_payment_returns_ok_contract(self):
        """ผู้เรียกต้องพึ่งพา key 'ok'/'error' ได้ — กัน view ที่ยังไม่อัปเดตพังเงียบ"""
        order = make_order()
        result = PaymentService.record_payment(
            order=order, name='ท', phone='0812345678', amount=Decimal('1000.00'),
            transfer_date='2026-10-13')
        for key in ('ok', 'error', 'payment', 'reported', 'remaining', 'just_paid', 'paid'):
            self.assertIn(key, result, f'ผลลัพธ์ต้องมี key "{key}"')


class SlipEndpointStatusGuardTest(TestCase):
    """`/payment/slip/` ต้องไม่รับสลิปของออเดอร์ที่ไม่รอชำระแล้ว"""

    def setUp(self):
        self.order = make_order(total='1000.00', status='delivered')

    def test_slip_rejected_for_paid_order(self):
        """สถานะอื่นที่ไม่ใช่ pending → 409 + ไม่บันทึก Payment"""
        parsed = {'amount': Decimal('1000.00'), 'transfer_date': None, 'note': 'x'}
        with mock.patch('myapp.views.SlipOK.enabled', return_value=True), \
             mock.patch('myapp.views.SlipOK.verify', return_value=parsed):
            r = self.client.post('/payment/slip/', {
                'order_id': str(self.order.id), 'phone': '0812345678',
                'slip': slip_upload(),
            })
        self.assertEqual(r.status_code, 409, 'ต้องตอบ 409 Conflict')
        self.assertEqual(
            Payment.objects.filter(order=self.order).count(), 0,
            'ห้ามบันทึก Payment ของออเดอร์ที่จ่าย/ส่งเสร็จแล้ว')

    def test_slip_accepted_for_pending_order(self):
        """ออเดอร์ยัง pending → ผ่านตามปกติ (ไม่เผื่อกว้างจนพังของเดิม)"""
        order = make_order(total='1000.00', status='pending')
        parsed = {'amount': Decimal('1000.00'), 'transfer_date': None, 'note': 'x'}
        with mock.patch('myapp.views.SlipOK.enabled', return_value=True), \
             mock.patch('myapp.views.SlipOK.verify', return_value=parsed):
            r = self.client.post('/payment/slip/', {
                'order_id': str(order.id), 'phone': '0812345678',
                'slip': slip_upload(),
            })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['just_paid'])
        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')


class PasswordResetHonestyTest(TestCase):
    """ระบบต้องไม่อ้างว่า 'ส่งอีเมลแล้ว' ตอนส่งไม่ถึงจริง"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='buyer@example.com', email='buyer@example.com',
            password='pw123456')

    def _submit(self):
        return self.client.post(reverse('password_reset'), {'email': self.user.email})

    @override_settings(EMAIL_CONFIGURED=True)
    def test_configured_sends_real_email(self):
        """ตั้งค่าแล้ว → ส่งอีเมลจริง ไปหน้า 'ส่งแล้ว'"""
        mail.outbox = []
        r = self._submit()
        self.assertRedirects(r, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1, 'ต้องส่งอีเมลจริง 1 ฉบับ')

    @override_settings(EMAIL_CONFIGURED=False)
    def test_unconfigured_does_not_claim_email_sent(self):
        """ไม่ได้ตั้ง SMTP → ห้ามพาไปหน้า 'ส่งลิงก์ไปทางอีเมลแล้ว'"""
        mail.outbox = []
        r = self._submit()
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ยังไม่ได้ส่ง')
        self.assertEqual(len(mail.outbox), 0, 'ไม่ควรส่งอีเมลปลอม ๆ')

    @override_settings(EMAIL_CONFIGURED=False)
    def test_unconfigured_form_warns_before_submit(self):
        """ฟอร์มต้องเตือนล่วงหน้า ว่าจะไม่ได้ส่งอีเมล (ไม่ใช่หลังกดแล้วค่อยบอก)"""
        r = self.client.get(reverse('password_reset'))
        self.assertContains(r, 'ยังไม่ได้ตั้งค่าการส่งอีเมล')

    @override_settings(EMAIL_CONFIGURED=True)
    def test_unknown_email_same_response(self):
        """อีเมลที่ไม่มีบัญชี → ตอบเหมือนกัน (กัน user enumeration)"""
        r = self.client.post(reverse('password_reset'), {'email': 'nobody@example.com'})
        self.assertRedirects(r, reverse('password_reset_done'))

    @override_settings(EMAIL_CONFIGURED=False, DEBUG=True)
    def test_revealed_link_actually_works(self):
        """ลิงก์ที่เผยให้ dev/staff ต้องใช้ได้จริง (token จริง ไม่ใช่ของปลอม)

        Django 6 มีขั้นตอนกลาง: ลิงก์แรก redirect ไปหน้า "set password"
        ก่อนแสดงฟอร์ม — จึงต้อง follow ต่อแล้วต้องเจอฟอร์มจริง
        """
        r = self._submit()
        self.assertEqual(r.status_code, 200)
        reset_url = r.context['reset_url']
        self.assertTrue(reset_url)

        r2 = self.client.get(reset_url)
        self.assertEqual(r2.status_code, 302, 'token ถูกต้อง → ไปขั้นตอน set-password')
        self.assertIn('set-password', r2['Location'])

        r3 = self.client.get(r2['Location'])
        self.assertEqual(r3.status_code, 200)
        self.assertTrue(r3.context.get('form'), 'ต้องมีฟอร์มตั้งรหัสผ่านใหม่')

    @override_settings(EMAIL_CONFIGURED=False, DEBUG=False)
    def test_customer_does_not_see_link(self):
        """ลูกค้าทั่วไป (ไม่ใช่ staff, ไม่ใช่ dev) → เห็นแค่คำแนะนำให้ติดต่อร้าน"""
        r = self._submit()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context['can_reveal'])
        self.assertNotIn('ตั้งรหัสผ่านใหม่ทันที', r.content.decode())


class StaticCacheBustingTest(TestCase):
    """static ต้องมี ?v= ใน production (กันผู้ใช้เจอไฟล์เก่าหลัง deploy)"""

    def test_static_storage_appends_version_in_production(self):
        with override_settings(DEBUG=False, STATIC_VERSION='20260101-000000',
                               STORAGES={'default': {
                                   'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                                   'staticfiles': {
                                       'BACKEND': 'myapp.static_storage.VersionedStaticFilesStorage'}}):
            from django.templatetags.static import static
            url = static('css/theme.css')
        self.assertEqual(url, '/static/css/theme.css?v=20260101-000000')

    def test_filename_is_not_hashed(self):
        """ห้าม hash ในชื่อไฟล์ — fx-assets.js สร้าง URL เองตอน runtime จะ 404"""
        from myapp.static_storage import VersionedStaticFilesStorage
        with override_settings(STATIC_VERSION='v1'):
            url = VersionedStaticFilesStorage().url('css/effects/fx-glass.css')
        self.assertEqual(url, '/static/css/effects/fx-glass.css?v=v1')

    def test_versioned_storage_never_double_appends(self):
        from myapp.static_storage import VersionedStaticFilesStorage
        with override_settings(STATIC_VERSION='v1'):
            storage = VersionedStaticFilesStorage()
            once = storage.url('css/theme.css')
            twice = storage.url('css/theme.css')
        self.assertEqual(once.count('?v='), 1)
        self.assertEqual(once, twice, 'เรียกซ้ำต้องได้ URL เดิม (กัน inject ซ้ำ)')

    def test_no_version_leaves_url_untouched(self):
        """ไม่มีเวอร์ชัน (dev) → URL เหมือนเดิม ไม่ต่อง query เปล่า ๆ"""
        from myapp.static_storage import VersionedStaticFilesStorage
        with override_settings(STATIC_VERSION=''):
            storage = VersionedStaticFilesStorage()
            self.assertEqual(storage.url('css/theme.css'), '/static/css/theme.css')

    def test_basetemplate_exposes_version_to_runtime_injector(self):
        """fx-assets.js สร้าง URL effect เองตอน runtime → ต้องได้รับเวอร์ชัน"""
        html = self.client.get('/').content.decode('utf-8')
        self.assertIn('window.FX_STATIC_V', html,
                      'basetemplate ต้องฉีดเวอร์ชัน static ให้ fx-assets.js')
