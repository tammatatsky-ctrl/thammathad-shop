"""เทสต์ "เส้นทางเดโม" — ลูกค้าสั่งซื้อแล้วระบบเดินต่อได้อย่างไรโดยไม่ต้องจ่ายเงินจริง

ทำไมต้องมีเทสต์นี้
    โจทย์คือระบบ demo **ไม่มีการโอนเงินจริง** แต่ต้องโชว์อาจารย์ได้ว่า
    วงจรชีวิตออเดอร์เดินครบ (สั่งซื้อ → จ่าย → จัดส่ง → ถึงมือ)
    ถ้าวันส่งงานกดแล้วมันค้าง แปลว่าเดโมพังตอนหน้าคน ซึ่งแย่กว่าพังตอนเทสต์มาก

    เส้นทางที่ต้องใช้ตอนโชว์ (ไม่มี API key / ไม่มีเงินจริง / ไม่มี OCR):
        1. ลูกค้าสั่งซื้อ → ออเดอร์เป็น 'pending'
        2. ลูกค้ากดปุ่ม "ฉันโอนยอดเต็มแล้ว — แจ้งชำระ 1 คลิก" (POST /payment/quick/)
           → PaymentService.record_payment() → ยอดครบ → สถานะเป็น 'paid' **อัตโนมัติ**
        3. เจ้าหน้าที่กด "จัดส่ง" → 'shipped'
        4. เจ้าหน้าที่กด "ถึงมือ" → 'delivered'

    ข้อสำคัญ: ขั้น 'paid' ตั้งด้วยมือไม่ได้ (OrderStatusService.AUTOMATIC) — ต้องเดินผ่าน
    จุดรับเงินจุดเดียวเสมอ การทดสอบนี้จึงพิสูจน์เส้นทางจริง ไม่ใช่แค่แก้ status ในฐานข้อมูล
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from myapp.models import Order, OrderItem, Payment, Product


class DemoJourneyTest(TestCase):
    """สั่งซื้อ → แจ้งชำระ 1 คลิก → จัดส่ง → ถึงมือ (ครบวงจร ไม่ใช้เงินจริง)"""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='teacher', password='pw', is_staff=True)
        self.product = Product.objects.create(
            name='คีย์บอร์ดทดสอบ', price=Decimal('1290.00'), stock=10)
        self.order = Order.objects.create(
            customer_name='ลูกค้า เดโม', phone='0812345678',
            address='กรุงเทพฯ', total=Decimal('1290.00'),
            payment_method='bank',
        )
        OrderItem.objects.create(
            order=self.order, product=self.product, quantity=1,
            price=Decimal('1290.00'))

    def _quickpay(self):
        """กดปุ่ม "ฉันโอนยอดเต็มแล้ว" จากหน้าสำเร็จ/ติดตามออเดอร์"""
        return self.client.post(reverse('payment_quick'), {
            'order_id': self.order.id,
            'phone': self.order.phone,
            'back': reverse('order_tracking'),
        })

    def test_full_journey_pending_to_delivered(self):
        """ไล่ทีละขั้นตามที่เจ้าหน้าที่จะโชว์จริง"""
        self.assertEqual(self.order.status, 'pending')

        # --- 2. ลูกค้าแจ้งชำระ 1 คลิก (ไม่มีเงินจริง) ---
        r = self._quickpay()
        self.assertEqual(r.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid',
                         'กดปุ่ม 1 คลิกแล้วต้องขึ้นชำระแล้วอัตโนมัติ')

        # มี Payment จริง 1 รายการ เท่ากับยอดรวมออเดอร์
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.amount, Decimal('1290.00'))
        self.assertIn('1-คลิก', payment.note)   # ที่มาคือช่องทางแจ้งชำระ 1 คลิก

        # --- 3-4. เจ้าหน้าที่เดินบันไดที่เหลือ ---
        self.client.force_login(self.staff)
        for target in ('shipped', 'delivered'):
            self.client.post(reverse('order_status', args=[self.order.id]),
                             {'status': target})
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, target)

    @override_settings(ACTIVITY_LOG_ENABLED=True)
    def test_quickpay_uses_single_payment_intake(self):
        """ปุ่ม 1 คลิกต้องเดินผ่าน PaymentService จริง และต้องมีร่องรอยตรวจย้อนหลัง

        ถ้ามีทางอื่นที่เขียน Payment นอกจุดรับเงินจุดเดียว บัญชีจะเพี้ยน
        และขั้น 'pending → paid' ที่เกิดโดยระบบเองจะไม่มีใครรู้ว่าเกิดเมื่อไร"""
        from myapp.models import ActivityLog

        self._quickpay()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')

        # ต้องมี audit ประเภท 'payment' ผูกกับออเดอร์นี้
        log = ActivityLog.objects.filter(
            action='payment', target_type='order',
            target_id=str(self.order.id)).first()
        self.assertIsNotNone(log, 'รับเงินแล้วต้องมี audit log (action=payment)')
        self.assertIn('quickpay', log.summary, 'ต้องระบุว่ารับเงินผ่านช่องทางไหน')
        self.assertIn('ปิดออเดอร์อัตโนมัติ', log.summary)
        # before/after ต้องเห็นการเปลี่ยนสถานะ
        self.assertEqual((log.before or {}).get('status'), 'pending')
        self.assertEqual((log.after or {}).get('status'), 'paid')

    def test_partial_payment_does_not_close_order(self):
        """จ่ายบางส่วน → ยัง 'pending' และบอกยอดที่เหลือ (กันเดโมโชว์ผิด)"""
        from myapp.services import PaymentService

        result = PaymentService.record_payment(
            order=self.order, name='ลูกค้า เดโม', phone=self.order.phone,
            amount=Decimal('500.00'), transfer_date='2026-01-01',
            source='test-partial')
        self.order.refresh_from_db()
        self.assertTrue(result['ok'])
        self.assertEqual(self.order.status, 'pending', 'ยังจ่ายไม่ครบ ต้องไม่ปิดออเดอร์')
        self.assertEqual(result['remaining'], Decimal('790.00'))

        # จ่ายที่เหลือทีเดียว → ปิดอัตโนมัติ
        PaymentService.record_payment(
            order=self.order, name='ลูกค้า เดโม', phone=self.order.phone,
            amount=Decimal('790.00'), transfer_date='2026-01-02',
            source='test-partial')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')

    def test_cannot_pay_twice(self):
        """จ่ายแล้วกดซ้ำ → ไม่เกินยอด (กันเดโมทำให้ตัวเลขเงินเพี้ยน)"""
        self._quickpay()
        self._quickpay()
        self.order.refresh_from_db()
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 1)
        self.assertEqual(self.order.reported_total(), Decimal('1290.00'))

    def test_customer_sees_pay_button_on_success_page(self):
        """หน้าสำเร็จต้องมีปุ่ม 1 คลิกให้ลูกค้าเห็น — ไม่งั้นเดโมจะต้องพึ่งลิงก์ตรงๆ

        ลูกค้าแบบ guest เข้าหน้านี้ด้วย ?phone= ตรงกับออเดอร์ (ดู OrderSuccessView)
        ซึ่งเป็นก้าวที่ต้องไม่พังตอนโชว์สด"""
        url = f"{reverse('order_success', args=[self.order.id])}?phone={self.order.phone}"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode('utf-8')
        self.assertIn(reverse('payment_quick'), html)
        self.assertIn('name="order_id"', html)

    def test_guest_is_redirected_away_from_success_page_without_phone(self):
        """ลูกค้า guest ที่เข้าหน้าสำเร็จโดยไม่แนบ ?phone= ต้องถูกส่งไปหน้าติดตาม

        ออเดอร์เจ้าของเข้าผ่าน checkout ได้ แต่ถ้าเผลอหลุดลิงก์ตอนโชว์สด
        ระบบต้องพาไปที่ที่เข้าถึงได้ ไม่ใช่ค้างหน้าว่างหรือ 404"""
        r = self.client.get(reverse('order_success', args=[self.order.id]))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('order_tracking'), r['Location'])