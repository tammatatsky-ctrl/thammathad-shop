"""ทดสอบว่า "ยืนยันยอดชำระ" ของเจ้าหน้าที่ใช้ได้จริงไหม

ทำไมต้องทดสอบ
    คิวตรวจการแจ้งชำระบนแดชบอร์ด (`_pending_reports`) แสดงเฉพาะ Payment
    ที่ออเดอร์ยังเป็น 'pending' แต่ `PaymentService.record_payment()` จะ
    **เลื่อนเป็น 'paid' ทันทีที่ยอดสะสมครบยอดรวม**
    → ออเดอร์ที่ยัง 'pending' ก็แปลว่า **ยอดยังไม่ครบเสมอ**
    → ปุ่ม "ยืนยัน" จึงเข้า `PaymentVerifyView` แล้วได้แต่สาขา error
    ("ยังยืนยันไม่ได้ — ขาดอีก x บาท") = **ปุ่มที่กดแล้วไม่มีทางสำเร็จ**

    นี่คือปุ่มที่อาจารย์อาจกดตอนโชว์ ถ้าพัง = เดโมพังตรงหน้าคน
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from myapp.models import Order, OrderItem, Payment, Product


class StaffPaymentVerifyTest(TestCase):
    """ปุ่มยืนยันยอดชำระบนแดชบอร์ดต้องใช้งานได้จริง"""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='teacher', password='pw', is_staff=True)
        self.product = Product.objects.create(
            name='สินค้าทดสอบ', price=Decimal('1000.00'), stock=10)
        self.order = Order.objects.create(
            customer_name='ลูกค้า', phone='0812345678', address='กทม',
            total=Decimal('1000.00'), payment_method='bank')
        OrderItem.objects.create(
            order=self.order, product=self.product, quantity=1,
            price=Decimal('1000.00'))
        self.client.force_login(self.staff)

    def _post_verify(self):
        payment = Payment.objects.filter(order=self.order).first()
        return self.client.post(
            reverse('payment_verify', args=[payment.id]), follow=True)

    def test_dashboard_does_not_offer_an_action_that_cannot_work(self):
        """ห้ามแสดงปุ่ม "ยืนยัน" ในคิว — เพราะกดแล้วไม่มีทางสำเร็จ

        เหตุผลเชิงตรรกะ: คิวนี้คือ Payment ที่ออเดอร์ยัง 'pending'
        แต่ record_payment() ปิดออเดอร์ทันทีที่ยอดครบ
        → ทุกรายการในคิวจึง "ขาดอยู่" เสมอ → ปุ่มยืนยันจะได้แต่ error

        ถ้าวันหนึ่งกติกาการชำระเปลี่ยน (เช่น ต้องให้เจ้าหน้าที่ยืนยันก่อน
        จึงปิดออเดอร์) ให้กลับมาใส่ปุ่มพร้อมกับแก้ PaymentVerifyView ให้รันได้จริง
        """
        from myapp.services import PaymentService

        PaymentService.record_payment(
            order=self.order, name='ลูกค้า', phone=self.order.phone,
            amount=Decimal('600.00'), transfer_date='2026-01-01',
            source='test')
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode('utf-8')
        self.assertNotIn(reverse('payment_verify', args=[
            Payment.objects.get(order=self.order).id]),
            html, 'แดชบอร์ดยังลิงก์ไปยืนยันที่กดแล้วไม่มีทางสำเร็จ')
        # แต่ต้องบอกความจริงว่ากำลังรออะไร
        self.assertIn('รอยอดที่เหลือ', html)

    def test_verify_endpoint_refuses_partial_payment(self):
        """ชั้นป้องกัน: ถ้ามีทางเรียก verify เข้ามา ต้องปฏิเสธพร้อมบอกเหตุผล

        (route ยังอยู่เพื่อกันการเรียกจากที่อื่นที่ไม่ได้ควบคุม —
        พฤติกรรมต้องเป็น 'ปฏิเสธพร้อมอธิบาย' ไม่ใช่เงียบๆ ไป)"""
        from myapp.services import PaymentService

        PaymentService.record_payment(
            order=self.order, name='ลูกค้า', phone=self.order.phone,
            amount=Decimal('600.00'), transfer_date='2026-01-01',
            source='test')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')
        self.assertEqual(self.order.reported_total(), Decimal('600.00'))

        r = self._post_verify()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending',
                         'ยืนยันไม่ได้เมื่อยอดยังไม่ครบ (ต้องเปลี่ยนกติกาการชำระก่อน)')
        msgs = [str(m) for m in r.context['messages']]
        self.assertTrue(any('ยังยืนยันไม่ได้' in m for m in msgs), msgs)