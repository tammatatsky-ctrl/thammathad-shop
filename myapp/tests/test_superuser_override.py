"""เทสต์สิทธิ์ Superuser — บังคับสถานะ "ชำระแล้ว" เหนือระบบอัตโนมัติ

บริบท
    ขั้น 'paid' เป็นขั้น**อัตโนมัติ** ตามกติกาใบงาน และเจ้าหน้าที่ตั้งเองไม่ได้
    (`OrderStatusService.AUTOMATIC`) — ซึ่งถูกต้องเพราะกันคนแก้สถานะเอง
    แต่งานจริงมีกรณีที่รอบเงินไม่ได้มาในระบบ (เงินสดหน้าร้าน, โอนผิดบัญชี
    แล้วแก้ทีหลัง) ถ้าไม่มีทางออก คนต้องไปแก้ข้อมูลตรง DB ซึ่งอันตรายกว่า

    ทางออกนี้จึงเปิดให้เฉพาะ superuser และบังคับให้: ต้องใส่เหตุผล ·
    ต้องสร้าง Payment ให้รายได้กับประวัติเงินตรงกัน · ต้องมี audit ทุกครั้ง
    แต่**ยังคงกฎ "ห้ามข้ามขั้น/ห้ามถอยหลัง"** ไว้ เพราะ override มีไว้ข้าม
    "ขั้นอัตโนมัติ" ไม่ใช่ข้าม "บันได"
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from myapp.models import Order, OrderItem, Payment, Product
from myapp.services import OrderStatusService, PaymentService


class SuperuserOverrideTest(TestCase):
    """superuser บังคับสถานะได้ / คนอื่นทำไม่ได้"""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='root', password='pw', email='root@example.com')
        self.staff = User.objects.create_user(
            username='teacher', password='pw', is_staff=True)
        self.product = Product.objects.create(
            name='สินค้าทดสอบ', price=Decimal('1290.00'), stock=10)
        self.order = Order.objects.create(
            customer_name='ลูกค้า', phone='0812345678', address='กทม',
            total=Decimal('1290.00'), payment_method='bank')
        OrderItem.objects.create(
            order=self.order, product=self.product, quantity=1,
            price=Decimal('1290.00'))

    # ---------- helper ----------
    def _post_paid(self, reason='รับเงินสดหน้าร้าน'):
        return self.client.post(
            reverse('order_status', args=[self.order.id]),
            {'status': 'paid', 'reason': reason}, follow=True)

    # ---------- ใช้งานได้จริง ----------
    @override_settings(ACTIVITY_LOG_ENABLED=True)
    def test_superuser_can_mark_paid_without_payment_intake(self):
        self.client.force_login(self.superuser)
        r = self._post_paid()

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid',
                         'superuser ต้องบังคับเป็นชำระแล้วได้โดยไม่ผ่านจุดรับเงิน')
        msgs = [str(m) for m in r.context['messages']]
        self.assertTrue(any('superuser override' in m for m in msgs), msgs)

        # ต้องสร้าง Payment ให้เท่ายอดที่ขาด → รายได้กับ /payments/ ตรงกัน
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.amount, Decimal('1290.00'))
        self.assertIn('[Superuser override]', payment.note)
        self.assertIn('รับเงินสดหน้าร้าน', payment.note)

        # รายได้ต้องนับออเดอร์นี้ (ตรงกับตัวเลขในแดชบอร์ด)
        self.assertEqual(Order.objects.revenue(), Decimal('1290.00'))

        # ต้องมีร่องรอยตรวจสอบ พร้อมเหตุผล
        log = self.client.get(reverse('activity_log'))
        self.assertContains(log, 'superuser')

    @override_settings(ACTIVITY_LOG_ENABLED=True)
    def test_override_records_reason_in_audit(self):
        self.client.force_login(self.superuser)
        self._post_paid(reason='ลูกค้าโอนผิดบัญชี แก้ทีหลังด้วยการโอนใหม่')
        html = self.client.get(reverse('activity_log')).content.decode('utf-8')
        self.assertIn('ลูกค้าโอนผิดบัญชี', html,
                      'เหตุผลต้องอยู่ในประวัติการทำงาน ไม่ใช่แค่บันทึกลง Payment.note')

    def test_reason_is_mandatory(self):
        self.client.force_login(self.superuser)
        r = self._post_paid(reason='   ')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending', 'ไม่มีเหตุผล = บังคับไม่ได้')
        msgs = [str(m) for m in r.context['messages']]
        self.assertTrue(any('ต้องระบุเหตุผล' in m for m in msgs), msgs)
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 0)

    # ---------- กันคนอื่นได้จริง ----------
    def test_plain_staff_cannot_override(self):
        """staff ธรรมดา (ไม่ใช่ superuser) บังคับไม่ได้ แม้จะเข้าหลังบ้านได้"""
        self.client.force_login(self.staff)
        self._post_paid()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_service_raises_for_non_superuser(self):
        with self.assertRaises(PermissionError):
            PaymentService.override_mark_paid(self.order, self.staff, 'ข้ามกันดี')

    def test_override_unavailable_once_paid(self):
        """ถ้ายอดครบแล้วระบบปิดให้อัตโนมัติ ไม่ต้องบังคับซ้ำ"""
        PaymentService.record_payment(
            order=self.order, name='ลูกค้า', phone=self.order.phone,
            amount=Decimal('1290.00'), transfer_date='2026-01-01', source='quickpay')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')
        self.assertFalse(OrderStatusService.can_override(self.order, self.superuser),
                         'ออเดอร์ที่จ่ายครบแล้วไม่ควรมีปุ่มบังคับ')

    # ---------- กติกาเดิมยังอยู่ ----------
    def test_override_does_not_break_the_ladder(self):
        """override ข้าม "ขั้นอัตโนมัติ" เท่านั้น — ห้ามข้ามจาก pending ไป delivered"""
        self.client.force_login(self.superuser)
        self.client.post(reverse('order_status', args=[self.order.id]),
                         {'status': 'delivered'}, follow=True)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending', 'ห้ามข้ามบันไดแม้เป็น superuser')

    def test_staff_still_cannot_set_paid_the_normal_way(self):
        """เส้นทางเดิมยังปฏิเสธเหมือนเดิม (ไม่ถูก override ทำให้หลุด)"""
        self.client.force_login(self.staff)
        r = self.client.post(reverse('order_status', args=[self.order.id]),
                             {'status': 'paid'}, follow=True)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')
        msgs = [str(m) for m in r.context['messages']]
        self.assertTrue(any('superuser' in m for m in msgs), msgs)

    def test_override_button_only_visible_to_superuser(self):
        """ปุ่มต้องไม่ปรากฏในหน้าจอของ staff ธรรมดาเลย (ไม่ใช่แค่กดไม่ได้)

        ตรวจที่ field ของฟอร์ม ไม่ใช่ชื่อ class — เพราะบล็อก <style> ของหน้าโหลด
        ทุกคนตามธรรมชาติ (ไม่มีผลถ้าไม่มี element ให้จับสไตล์)"""
        self.client.force_login(self.staff)
        html = self.client.get(
            reverse('order_detail', args=[self.order.id])).content.decode('utf-8')
        self.assertNotIn('name="reason"', html, 'staff ธรรมดาเห็นช่องเหตุผลได้')
        self.assertNotIn('value="paid"', html,
                         'staff ธรรมดาเห็นตัวเลือก paid ได้')

        self.client.force_login(self.superuser)
        html = self.client.get(
            reverse('order_detail', args=[self.order.id])).content.decode('utf-8')
        self.assertIn('name="reason"', html)
        self.assertIn('value="paid"', html)