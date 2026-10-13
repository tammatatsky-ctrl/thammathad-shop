"""เทสต์ "ทุกฟีเจอร์ต้องโชว์ให้อาจารย์ได้" แม้ไม่ได้ตั้ง API key

บริบท
    `GEMINI_API_KEY` เป็น secret ของเจ้าของงาน — ตั้งบนเครื่อง dev ได้
    แต่**ตั้งบนเซิร์ฟเวอร์ที่ส่งงานไม่ได้** เช่นเดียวกับ `SLIPOK_API_KEY`
    เดิมระบบแก้ปัญหานี้ด้วยการ**ซ่อนปุ่มไปเลย** ผลคืออาจารย์เห็นระบบขาดไป 2 ฟีเจอร์
    โดยไม่รู้ว่าขาด และถ้าเอาไปรันเองก็จะเจอ 503

    ทางออกคือ **ทำให้ฟีเจอร์ทำงานได้จริงเสมอ** แล้วบอกตรงว่าใช้อะไรทำงาน
    ไม่ใช่ปลอมผลลัพธ์ และไม่ใช่ซ่อนปุ่ม

เคสนี้กันสองอย่าง
    1. ปุ่ม/ฟอร์มที่ฟีเจอร์ต้องการหายไปเมื่อไม่มี key (ทำให้โชว์ไม่ได้)
    2. ระบบอ้างว่าใช้สิ่งที่ไม่ได้ใช้ (เช่นบอกว่า AI ทั้งที่เป็นแม่แบบ)
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from myapp.models import Order, OrderItem, Payment, Product
from myapp.services import ProductDescription


def _png_bytes():
    """ไฟล์ PNG 1x1 จิ๊ง (ไม่ต้องผ่าน OCR เพราะไม่มี key — แต่ต้องผ่านการตรวจไฟล์ก่อน)"""
    return (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
        b'\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
        b'\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05'
        b'\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    )


class EveryFeatureIsReachableTest(TestCase):
    """ไม่มี API key — ฟีเจอร์ที่ต้องใช้ key ต้องยังทดสอบได้"""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='teacher', password='pw', is_staff=True)
        self.product = Product.objects.create(
            name='สินค้าทดสอบ', price=Decimal('1290.00'), stock=5)
        self.order = Order.objects.create(
            customer_name='ลูกค้า', phone='0812345678', address='กทม',
            total=Decimal('1290.00'), payment_method='bank')
        OrderItem.objects.create(
            order=self.order, product=self.product, quantity=1,
            price=Decimal('1290.00'))

    # ---------- 1. แจ้งยอดโอนเอง (แทนการพึ่ง OCR) ----------

    def test_manual_payment_form_is_always_shown_when_awaiting_payment(self):
        """ลูกค้าต้องมีทางแจ้งยอดเสมอ แม้ไม่มี SLIPOK_API_KEY"""
        for url in (f"/order/success/{self.order.id}/?phone={self.order.phone}",
                    f"/order/tracking/?order={self.order.id}&phone={self.order.phone}"):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode('utf-8')
                self.assertIn(reverse('payment_manual'), html,
                              f'{url} ไม่มีช่องแจ้งยอดโอนเอง')
                self.assertIn('name="amount"', html)
                self.assertIn('name="transfer_date"', html)

    def test_pay_buttons_show_on_a_fresh_order_with_no_payment_history(self):
        """ออเดอร์ใหม่ = ยังไม่มี Payment เลย → ต้องเห็นปุ่มชำระ

        กันบั๊กเดิม: บล็อกชำระทั้งหมดเคยอยู่ใน `{% if payments %}`
        ซึ่งแปลว่า 'ยังไม่เคยจ่าย' ซึ่งเป็นสถานะเริ่มต้นของออเดอร์ทุกใบ
        จะไม่มีทางจ่ายได้เลย — ตรงกันข้ามกับที่ควรเป็น
        """
        self.assertFalse(Payment.objects.filter(order=self.order).exists())
        html = self.client.get(
            f"/order/tracking/?order={self.order.id}&phone={self.order.phone}"
        ).content.decode('utf-8')
        self.assertIn(reverse('payment_quick'), html, 'ไม่มีปุ่มแจ้งชำระ 1 คลิก')
        self.assertIn(reverse('payment_manual'), html, 'ไม่มีช่องกรอกยอดเอง')

    def test_manual_payment_records_through_the_single_intake(self):
        """ต้องเดินผ่าน PaymentService เหมือนทุกช่องทาง (รวมจ่ายบางส่วน)"""
        r = self.client.post(reverse('payment_manual'), {
            'order_id': self.order.id, 'phone': self.order.phone,
            'amount': '500', 'transfer_date': '2026-01-01',
            'back': reverse('order_tracking'),
        }, follow=True)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending', 'จ่าย 500/1290 ยังไม่ครบ')
        msgs = [str(m) for m in r.context['messages']]
        self.assertTrue(any('790' in m for m in msgs), msgs)

    def test_manual_payment_rejects_nonsense_amount(self):
        for bad in ('abc', '-5', '0'):
            with self.subTest(amount=bad):
                r = self.client.post(reverse('payment_manual'), {
                    'order_id': self.order.id, 'phone': self.order.phone,
                    'amount': bad, 'transfer_date': '',
                    'back': reverse('order_tracking'),
                }, follow=True)
                self.order.refresh_from_db()
                self.assertEqual(self.order.status, 'pending',
                                 f'ยอด "{bad}" ต้องถูกปฏิเสธ ไม่ใช่ทำออเดอร์เป็น paid')

    def test_manual_payment_wrong_phone_rejected(self):
        self.client.post(reverse('payment_manual'), {
            'order_id': self.order.id, 'phone': '0899999999',
            'amount': '1290', 'back': reverse('order_tracking'),
        })
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending',
                         'เบอร์ไม่ตรงต้องไม่มีสิทธิ์แจ้งยอด')

    def test_no_lie_in_ocr_error_message(self):
        """ข้อความ error ต้องชี้ไปที่ช่องที่มีอยู่จริง

        ตรวจจากพฤติกรรม (ตอบ 503 ของ OCR) ไม่ใช่การค้นซอร์ส —
        เพราะคำนี้อาจปรากฏใน docstring ซึ่งไม่ใช่สิ่งที่ผู้ใช้เห็น
        """
        from unittest import mock

        r = self.client.post(reverse('payment_slip'), {
            'order_id': self.order.id, 'phone': self.order.phone,
            'slip': _png_bytes(),
        })
        self.assertEqual(r.status_code, 503)  # ยังไม่ได้ตั้ง key
        self.assertIn('ยังไม่เปิดใช้งาน', r.json()['error'])

    # ---------- 2. ช่วยเขียนคำอธิบาย ----------

    @override_settings(GEMINI_API_KEY='')
    def test_describe_button_exists_without_api_key(self):
        """เดิมปุ่มถูกซ่อนทั้งหมด → ทดสอบฟีเจอร์นี้ไม่ได้เลย"""
        self.client.force_login(self.staff)
        html = self.client.get(
            reverse('product_add')).content.decode('utf-8')
        self.assertIn('id="aiBtn"', html, 'ปุ่มช่วยเขียนหายไปเมื่อไม่มี key')
        self.assertIn('data-ai-mode="rule"', html,
                      'ต้องบอกว่าเป็นโหมดแม่แบบ ไม่ใช่ AI')

    @override_settings(GEMINI_API_KEY='')
    def test_describe_endpoint_returns_usable_text_without_key(self):
        """ต้องได้ข้อความใช้ได้จริง + บอกตรงว่าไม่ใช่ AI"""
        self.client.force_login(self.staff)
        r = self.client.post(reverse('product_describe_ai'), {
            'name': 'เมาส์ไร้สาย Glide', 'category': 'อุปกรณ์ต่อพ่วง'})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data['description'].strip())
        self.assertEqual(data['source'], 'rule')
        self.assertIn('ไม่ได้ใช้ AI', data['notice'])

    def test_describe_endpoint_returns_a_response_on_success(self):
        """กันบั๊กเดิม: `return JsonResponse(...)` อยู่ในบล็อก except (โค้ดตาย)

        สัญญาคือ 'description' ต้องเป็น key ที่ตอบ — ถ้าโค้ดย้ายกลับไปผิดชั้น
        view จะไม่คืนค่าเลยและ Django ตอบ 500
        """
        from unittest import mock

        self.client.force_login(self.staff)
        with mock.patch('myapp.views.GeminiAI.enabled', return_value=True), \
             mock.patch('myapp.views.GeminiAI.describe_product',
                        return_value='ข้อความจาก AI'):
            r = self.client.post(reverse('product_describe_ai'), {
                'name': 'คีย์บอร์ด Mechanical'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['description'], 'ข้อความจาก AI')
        self.assertEqual(r.json()['source'], 'ai')

    def test_rule_fallback_never_claims_to_be_ai(self):
        for name, cat in (('เมาส์ไร้สาย', 'อุปกรณ์ต่อพ่วง'),
                          ('สินค้าแปลกปลอม', '')):
            text = ProductDescription.suggest(name, cat)
            self.assertTrue(text.strip())
            self.assertIn(name.split()[0], text)
            self.assertNotIn('AI', text)