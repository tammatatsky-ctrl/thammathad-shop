"""เทสต์ flow ตะกร้า + Checkout — หน้าหลักที่ลูกค้าเจอจริง.

ครอบคลุม:
- protocol: cart/checkout ฝั่งเขียนเป็น POST เท่านั้น (GET = 405 กัน crawler)
- Cart AJAX: เพิ่ม/กันเกิน(409)/แก้ clamp/ลบ
- Checkout: สร้างออเดอร์ + หักสต็อก + ล้างตะกร้าใน transaction เดียว,
  validate ฟิลด์, oversell rollback (select_for_update กันคนแย่งซื้อจุกจิก)
- order_success / order_tracking: การยืนยันตัวตนด้วยเบอร์โทร (guest)

สายเงิน: สถานะออเดอร์เกิดเป็น 'pending' เสมอตอนสั่ง — เปลี่ยนเป็น paid
เฉพาะผ่าน PaymentService (เทสต์ใน test_services) เท่านั้น.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from myapp.models import Order, Product


class CartFlowTest(TestCase):
    """ตะกร้า: protocol + AJAX add/update/remove"""

    def setUp(self):
        self.product = Product.objects.create(
            name='คีย์บอร์ด', price=Decimal('300.00'), stock=10,
            category='อุปกรณ์', is_active=True,
        )

    def _add(self, qty=1, **extra):
        return self.client.post(
            reverse('cart_add', args=[self.product.id]),
            {'quantity': qty}, **extra)

    def test_cart_page_and_ajax_partial(self):
        """GET /cart/ ใช้ได้ + ?partial=1 คืน JSON {html, count}"""
        self.assertEqual(self.client.get(reverse('cart')).status_code, 200)
        r = self.client.get(reverse('cart'), {'partial': '1'})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn('html', data)
        self.assertIn('count', data)

    def test_cart_write_endpoints_are_post_only(self):
        """GET คำสั่งเขียนทั้งหมด → 405 Method Not Allowed"""
        for name, args in [('cart_add', [self.product.id]),
                           ('cart_remove', [self.product.id]),
                           ('cart_update', [self.product.id])]:
            r = self.client.get(reverse(name, args=args))
            self.assertEqual(r.status_code, 405, name)

    def test_add_ajax_ok(self):
        """เพิ่ม 2 ชิ้นแบบ fetch → ok:true, count=2"""
        r = self._add(2, HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['count'], 2)

    def test_add_over_stock_409(self):
        """สั่งเกินสต็อก → HTTP 409 + ok:false (ให้ UI เตือนทันที)"""
        r = self._add(99, HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.json()['ok'])

    def test_update_clamps_to_stock(self):
        """แก้จำนวนเกินสต็อก → server clamp ให้เอง"""
        self._add(2, HTTP_X_REQUESTED_WITH='fetch')
        r = self.client.post(
            reverse('cart_update', args=[self.product.id]),
            {'quantity': '500'}, HTTP_X_REQUESTED_WITH='fetch')
        data = r.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['count'], 10)

    def test_remove_empties_cart(self):
        """ลบสินค้าออก → count 0"""
        self._add(3, HTTP_X_REQUESTED_WITH='fetch')
        r = self.client.post(
            reverse('cart_remove', args=[self.product.id]),
            HTTP_X_REQUESTED_WITH='fetch')
        self.assertTrue(r.json()['ok'])
        self.assertEqual(r.json()['count'], 0)


class CheckoutFlowTest(TestCase):
    """Checkout เต็ม flow — สร้างออเดอร์/หักสต็อก/validate/rolling back"""

    def setUp(self):
        self.product = Product.objects.create(
            name='จอมอนิเตอร์', price=Decimal('500.00'), stock=5,
            category='หน้าจอ', is_active=True,
        )
        self.full = {
            'customer_name': 'สมชาย ใจดี',
            'phone': '0812345678',
            'detail': '12/3 ถ.สุขุมวิท',
            'province': 'กรุงเทพมหานคร',
            'district': 'วัฒนา',
            'subdistrict': 'คลองเตย',
            'zipcode': '10110',
            'payment_method': 'promptpay',
        }

    def _place(self, **over):
        """POST checkout พร้อมข้อมูลลัพธ์ เอา override ไปแทนตรงไหนก็ได้"""
        return self.client.post(reverse('checkout'), {**self.full, **over})

    def test_guest_full_flow(self):
        """guest สั่งของ: ออเดอร์เกิดขึ้น pending, หักสต็อก, ล้างตะกร้า"""
        self.client.post(reverse('cart_add', args=[self.product.id]), {'quantity': 2})
        r = self._place()
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith('/order/success/'))
        order = Order.objects.get(customer_name='สมชาย ใจดี')
        self.assertEqual(order.phone, '0812345678')
        self.assertEqual(order.total, Decimal('1000.00'))
        self.assertEqual(order.status, 'pending')           # ยังจ่าย — รอ PaymentService
        self.assertEqual(order.user_id, None)               # guest
        self.assertEqual(order.payments.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)             # 5 - 2
        self.assertDictEqual(self.client.session['cart'], {})   # ล้างแล้ว

    def test_missing_fields_rerender_error(self):
        """ไม่กรอกเบอร์ → ไม่สร้างออเดอร์ + โชว์ข้อความเป็นภาษาไทย"""
        r = self._place(phone='')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertContains(r, 'กรุณากรอกข้อมูล')

    def test_invalid_phone_rejected(self):
        """เบอร์ไม่ขึ้น 0 → ปฏิเสธ (reserve valid_phone กลับถูกเรียก)"""
        r = self._place(phone='999')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertContains(r, 'เบอร์โทรศัพท์ไม่ถูกต้อง')

    def test_bad_zipcode_rejected(self):
        """zipcode ไม่ใช่ 5 หลัก → ปฏิเสธ"""
        r = self._place(zipcode='12')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

    def test_oversell_rolls_back_entire_order(self):
        """สต็อกขาดตอนสั่ง (คนอื่นซื้อหมด) → ทั้งก้อน rollback: ไม่มีออเดอร์ ไม่หักสต็อก"""
        session = self.client.session
        session['cart'] = {str(self.product.id): 6}   # 6 > stock 5
        session.save()
        r = self._place()
        self.assertEqual(r.status_code, 200)          # re-render พร้อม error
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)

    def test_authenticated_checkout_links_user(self):
        """ล็อกอินสั่งซื้อ → ออเดอร์ผูก user (account เห็นประวัติได้)"""
        from django.contrib.auth.models import User
        user = User.objects.create_user(username='cust@shop.com', password='pw123456')
        self.client.force_login(user)
        self.client.post(reverse('cart_add', args=[self.product.id]), {'quantity': 1})
        self._place()
        order = Order.objects.get()
        self.assertEqual(order.user, user)


class OrderSuccessGuardTest(TestCase):
    """หน้า success — guest ต้องยืนยันตัวตนด้วยเบอร์โทรที่ตรงกับออเดอร์"""

    def setUp(self):
        self.order = Order.objects.create(
            customer_name='สมชาย ใจดี', phone='0812345678', address='กทม',
            total=Decimal('10.00'), payment_method='promptpay',
        )

    def test_no_phone_redirects_to_tracking(self):
        """ไม่มี ?phone → พาไปหน้า tracking เพื่อกรอกข้อมูล"""
        r = self.client.get(reverse('order_success', args=[self.order.id]))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('order_tracking'), r.url)

    def test_wrong_phone_redirected_away(self):
        """เบอร์ผิด → ไป tracking (ไม่อยากบอกใบ้ว่าออเดอร์นี้มีอยู่จริง)"""
        r = self.client.get(reverse('order_success', args=[self.order.id]) + '?phone=0899999999')
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('order_tracking'), r.url)

    def test_correct_phone_opens_page(self):
        """เบอร์ตรง? → เห็นหน้า success 200"""
        r = self.client.get(reverse('order_success', args=[self.order.id]) + '?phone=0812345678')
        self.assertEqual(r.status_code, 200)


class OrderTrackingTest(TestCase):
    """ค้นหาออเดอร์ด้วย id + เบอร์ (guest)"""

    def setUp(self):
        self.order = Order.objects.create(
            customer_name='สมชาย ใจดี', phone='0812345678', address='กทม',
            total=Decimal('100.00'), payment_method='promptpay',
        )

    def test_guest_finds_order_with_correct_phone(self):
        """id + เบอร์ตรง → เห็นสถานะออเดอร์"""
        r = self.client.post(reverse('order_tracking'),
                             {'order_id': self.order.id, 'phone': '0812345678'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'สมชาย ใจดี')

    def test_wrong_phone_shows_not_found(self):
        """เบอร์ผิด → แจ้ง 'ไม่พบออเดอร์' เป็นภาษาไทย"""
        r = self.client.post(reverse('order_tracking'),
                             {'order_id': self.order.id, 'phone': '0899999999'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ไม่พบออเดอร์')