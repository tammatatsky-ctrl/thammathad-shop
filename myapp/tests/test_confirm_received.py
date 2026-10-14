"""เทสต์ขั้นสุดท้าย "ถึงมือแล้ว" — ลูกค้าควรเป็นคนยืนยัน

เหตุผลที่ต้องแก้
    เดิมขั้น `delivered` ให้**เฉพาะเจ้าหน้าที่**กด → สถานะไม่ได้สะท้อนความจริง
    ของถึงมือก็ต่อเมื่อ **ผู้รับ**บอกว่าได้รับแล้ว ไม่ใช่เมื่อผู้ส่งกดว่าส่งแล้ว
    และถ้าเจ้าหน้าที่เผลอกดปุ่ม ระบบก็บันทึกว่า "ถึงมือแล้ว" ซึ่งเป็นข้อมูลผิด
    ที่ยากแก้ทีหลัง เพราะระบบเชื่อว่าของถึงแล้ว

เส้นทางที่ใช้ตอนนี้
    ลูกค้า: POST /order/<id>/confirm-received/ ยืนยันตัวตนด้วยเลขออเดอร์+เบอร์
    เจ้าหน้าที่: ยังกดได้สำหรับกรณีติดต่อลูกค้าไม่ได้ (เก็บเงินปลายทาง)
    → ทั้งสองทางเดินบันไดถูกต้อง และบันทึก audit แยกกันบอกว่าใครยืนยัน
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from myapp.models import ActivityLog, Order, OrderItem, Payment, Product


class CustomerConfirmsReceiptTest(TestCase):
    """ลูกค้ายืนยันรับสินค้าเอง — ทางหลักของขั้น 'ถึงมือแล้ว'"""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='teacher', password='pw', is_staff=True)
        self.product = Product.objects.create(
            name='สินค้า', price=Decimal('1290.00'), stock=5)
        self.order = Order.objects.create(
            customer_name='ลูกค้า', phone='0812345678', address='กทม',
            total=Decimal('1290.00'), payment_method='bank',
            status='shipped')
        OrderItem.objects.create(
            order=self.order, product=self.product, quantity=1,
            price=Decimal('1290.00'))
        Payment.objects.create(
            order=self.order, name='ลูกค้า', phone=self.order.phone,
            amount=Decimal('1290.00'), transfer_date='2026-01-01')

    def _confirm(self, phone=None):
        return self.client.post(
            reverse('order_confirm_received', args=[self.order.id]),
            {'order_id': self.order.id, 'phone': phone or self.order.phone,
             'back': reverse('order_tracking')}, follow=True)

    def test_customer_can_confirm_receipt(self):
        r = self._confirm()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')
        msgs = [str(m) for m in r.context['messages']]
        self.assertTrue(any('ขอบคุณครับ' in m for m in msgs), msgs)

    @override_settings(ACTIVITY_LOG_ENABLED=True)
    def test_customer_confirmation_is_audited_as_customer(self):
        """บันทึกต้องระบุว่าเป็น**ลูกค้า**ยืนยัน ไม่ใช่เจ้าหน้าที่"""
        self._confirm()
        log = ActivityLog.objects.filter(
            action='order_status', target_type='order',
            target_id=str(self.order.id)).first()
        self.assertIsNotNone(log)
        self.assertIn('ลูกค้ายืนยันได้รับสินค้าแล้ว', log.summary)
        self.assertEqual((log.before or {}).get('status'), 'shipped')
        self.assertEqual((log.after or {}).get('status'), 'delivered')

    def test_cannot_confirm_before_shipped(self):
        """ห้ามข้ามขั้น — ยืนยันรับได้ต่อเมื่อร้านกดจัดส่งแล้วเท่านั้น"""
        self.order.status = 'pending'
        self.order.save(update_fields=['status'])
        r = self._confirm()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')
        msgs = [str(m) for m in r.context['messages']]
        self.assertTrue(any('ยังไม่ได้จัดส่ง' in m for m in msgs), msgs)

    def test_wrong_phone_cannot_confirm_someone_elses_delivery(self):
        self._confirm(phone='0899999999')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'shipped',
                         'เบอร์ไม่ตรง = ไม่มีสิทธิ์ยืนยันรับของออเดอร์คนอื่น')

    def test_confirm_button_shown_only_when_shipped(self):
        """ปุ่มขึ้นตอน 'จัดส่งแล้ว' เท่านั้น"""
        url = f"/order/tracking/?order={self.order.id}&phone={self.order.phone}"
        html = self.client.get(url).content.decode('utf-8')
        self.assertIn(reverse('order_confirm_received', args=[self.order.id]), html)

        self.order.status = 'pending'
        self.order.save(update_fields=['status'])
        html = self.client.get(url).content.decode('utf-8')
        self.assertNotIn(reverse('order_confirm_received', args=[self.order.id]), html)

    def test_staff_still_advances_delivery_but_label_says_why(self):
        """เจ้าหน้าที่ยังกดได้ (ติดต่อลูกค้าไม่ได้) แต่ป้ายต้องบอกว่าเป็นกรณีพิเศษ"""
        self.client.force_login(self.staff)
        html = self.client.get(
            reverse('order_detail', args=[self.order.id])).content.decode('utf-8')
        self.assertIn('กรณีลูกค้าติดต่อไม่ได้', html)

    def test_full_customer_journey_ends_without_any_staff_click(self):
        """ลูกค้าปิดวงจรเองตั้งแต่สั่งซื้อถึงรับสินค้า — พนักงานไม่ต้องกด delivered"""
        fresh = Order.objects.create(
            customer_name='ลูกค้า 2', phone='0855555555', address='กทม',
            total=Decimal('1290.00'), payment_method='bank')
        OrderItem.objects.create(order=fresh, product=self.product,
                                  quantity=1, price=Decimal('1290.00'))

        # จ่ายเงินเอง (1 คลิก)
        self.client.post(reverse('payment_quick'), {
            'order_id': fresh.id, 'phone': fresh.phone,
            'back': reverse('order_tracking')})
        fresh.refresh_from_db()
        self.assertEqual(fresh.status, 'paid')

        # ร้านจัดส่ง (ขั้นเดียวที่พนักงานต้องทำ)
        self.client.force_login(self.staff)
        self.client.post(reverse('order_status', args=[fresh.id]),
                         {'status': 'shipped'})

        # ลูกค้ายืนยันรับเอง
        self.client.post(reverse('order_confirm_received', args=[fresh.id]), {
            'order_id': fresh.id, 'phone': fresh.phone,
            'back': reverse('order_tracking')})
        fresh.refresh_from_db()
        self.assertEqual(fresh.status, 'delivered',
                         'ลูกค้าควรปิดวงจรได้เองโดยไม่ต้องรอเจ้าหน้าที่')