"""เทสต์ชั้น service — ตรรกะบริสุทธิ์ (ไม่มี HTTP/Session ของ view).

ครอบคลุม:
- Cart: กัน oversell, clamp จำนวน, ข้ามสินค้าที่ซ่อนโดยไม่ล้าง session
- OrderStatusService: บันไดสถานะ pending→paid→shipped→delivered
  (ห้ามข้าม/ถอยหลัง; 'paid' เป็นขั้นอัตโนมัติ — เจ้าหน้าที่ตั้งด้วยมือไม่ได้)
- PaymentService.record_payment: จุดรับเงินจุดเดียว — จ่ายสะสมครบยอด → paid อัตโนมัติ
- Validators / ThaiCalendar: ตัวช่วยบริสุทธิ์

สายเงินสำคัญของใบงาน: ออเดอร์ขึ้น "ชำระเงินแล้ว" ได้ทางเดียว = จ่ายครบผ่าน
PaymentService (หรือ staff ยืนยันเมื่อยอดแจ้งครบ) — จากันความผิดพลาดระดับบริการ.
"""
from decimal import Decimal

from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase
from django.utils import timezone

from myapp.models import Order, Product
from myapp.services import Cart, OrderStatusService, PaymentService, ThaiCalendar, Validators


class CartServiceTest(TestCase):
    """พฤติกรรมตะกร้าใน session: เพิ่ม/กันเกิน/แก้/ลบ/ข้ามสินค้าที่ซ่อน"""

    def setUp(self):
        self.product = Product.objects.create(
            name='เมาส์ RGB', price=Decimal('100.00'), stock=5,
            category='อุปกรณ์', is_active=True,
        )
        self.session = SessionStore()
        self.cart = Cart(self.session)

    def test_add_success_updates_count_total(self):
        """เพิ่ม 2 ชิ้น → count 2, total 200"""
        self.assertTrue(self.cart.add(self.product, 2))
        self.assertEqual(self.cart.count, 2)
        self.assertEqual(self.cart.total, Decimal('200.00'))

    def test_add_refuses_over_stock(self):
        """สั่งเกิน stock → False และไม่เก็บอะไรในตะกร้า"""
        self.assertFalse(self.cart.add(self.product, 6))   # stock = 5
        self.assertTrue(self.cart.is_empty)

    def test_add_accumulates_and_blocks_on_over_total(self):
        """มี 3 ชิ้นอยู่แล้ว เติมอีก 3 → เกิน 5 → ไม่เพิ่ม"""
        self.assertTrue(self.cart.add(self.product, 3))
        self.assertFalse(self.cart.add(self.product, 3))
        self.assertEqual(self.cart.count, 3)

    def test_add_coerces_invalid_quantity_to_one(self):
        """จำนวนมั่ว ('abc') ถูกถอยเป็น 1 (กันข้อมูลไม่ตั้งใจจากฟอร์ม)"""
        self.assertTrue(self.cart.add(self.product, 'abc'))
        self.assertEqual(self.cart.count, 1)

    def test_update_clamps_high_and_floor_to_one(self):
        """แก้จำนวน: เกิน stock → clamp ที่ stock; ติดลบ/0 → 1"""
        self.assertTrue(self.cart.add(self.product, 1))
        self.cart.update(self.product.id, 99)
        self.assertEqual(self.cart.count, 5)
        self.cart.update(self.product.id, -50)
        self.assertEqual(self.cart.count, 1)

    def test_remove_of_missing_and_clear(self):
        """remove สินค้าที่ไม่เคยมี = เงียบ (ไม่ raise); clear หลังใช้"""
        self.assertTrue(self.cart.add(self.product, 2))
        self.cart.remove(999)
        self.assertEqual(self.cart.count, 2)
        self.cart.remove(self.product.id)
        self.assertTrue(self.cart.is_empty)
        self.assertTrue(self.cart.add(self.product, 1))
        self.cart.clear()
        self.assertDictEqual(self.session['cart'], {})

    def test_lines_skip_inactive_product_but_keep_session(self):
        """สินค้าถูกซ่อน → หายจากรายการ แต่ session ยังมีอยู่ (พฤติกรรมตั้งใจ)"""
        self.assertTrue(self.cart.add(self.product, 2))
        self.product.is_active = False
        self.product.save(update_fields=['is_active'])
        self.assertEqual(self.cart.lines(), [])
        self.assertEqual(self.cart.total, Decimal('0.00'))
        self.assertEqual(self.cart.count, 0)
        self.assertFalse(self.cart.is_empty)   # session ยังมีข้อมูลรอการ "หลุด" เอง


class OrderStatusLadderTest(TestCase):
    """บันไดสถานะออเดอร์ — กฎหัวใจของใบงาน: ห้ามข้าม/ถอยหลัง, paid ตั้งมือไม่ได้"""

    def setUp(self):
        self.order = Order.objects.create(
            customer_name='ทดสอบระบบ', phone='0812345678', address='กทม 10110',
            total=Decimal('90.00'), payment_method='promptpay',
        )

    def test_next_status_follows_ladder(self):
        """ขั้นถัดไปเรียงตาม FLOW; delivered = ปลายทาง (None)"""
        self.assertEqual(OrderStatusService.next_status('pending'), 'paid')
        self.assertEqual(OrderStatusService.next_status('paid'), 'shipped')
        self.assertEqual(OrderStatusService.next_status('shipped'), 'delivered')
        self.assertIsNone(OrderStatusService.next_status('delivered'))

    def test_staff_options_hide_automatic_paid(self):
        """UI ไม่เสนอ 'paid' (ขั้นอัตโนมัติ) — เสนอได้เฉพาะขั้นที่กดด้วยมือได้"""
        self.assertEqual(OrderStatusService.staff_options(self.order), [])
        self.order.status = 'paid'
        self.order.save(update_fields=['status'])
        self.assertEqual(OrderStatusService.staff_options(self.order), ['shipped'])

    def test_move_blocks_same_status(self):
        """ย้ายไปสถานะเดิม → ปฏิเสธพร้อมข้อความแจ้ง"""
        ok, msg = OrderStatusService.move(self.order, 'pending')
        self.assertFalse(ok)
        self.assertIn('สถานะเป็นอย่างนี้อยู่แล้ว', msg)

    def test_move_blocks_skip_and_backward(self):
        """ข้ามขั้น (pending→shipped) และถอยหลัง (shipped→paid) → ปฏิเสธ"""
        ok, _ = OrderStatusService.move(self.order, 'shipped')
        self.assertFalse(ok)
        self.order.status = 'shipped'
        self.order.save(update_fields=['status'])
        ok, _ = OrderStatusService.move(self.order, 'paid')
        self.assertFalse(ok)
        ok, _ = OrderStatusService.move(self.order, 'delivered')
        self.assertTrue(ok)

    def test_move_to_paid_impossible_by_hand(self):
        """เจ้าหน้าที่กด 'ชำระเงินแล้ว' เองไม่ได้ — ต้องจ่ายครบให้ระบบขึ้นเอง"""
        ok, msg = OrderStatusService.move(self.order, 'paid')
        self.assertFalse(ok)
        self.assertIn('เปลี่ยนด้วยมือไม่ได้', msg)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_auto_move_walks_full_ladder(self):
        """ระบบเลื่อนทั้งบันได: pending→paid→shipped→delivered"""
        self.assertTrue(OrderStatusService.auto_move(self.order, 'paid'))
        self.assertTrue(OrderStatusService.auto_move(self.order, 'shipped'))
        self.assertTrue(OrderStatusService.auto_move(self.order, 'delivered'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'delivered')

    def test_auto_move_repeat_false_and_jump_raises(self):
        """ซ้ำขั้นเดิม → False; ข้ามขั้น → ValueError (ไม่เก็บเงียบ)"""
        self.assertTrue(OrderStatusService.auto_move(self.order, 'paid'))
        self.assertFalse(OrderStatusService.auto_move(self.order, 'paid'))
        with self.assertRaises(ValueError):
            OrderStatusService.auto_move(self.order, 'delivered')


class PaymentServiceTest(TestCase):
    """จุดรับเงินจุดเดียว — จ่ายไม่ครบคง pending, ครบ → paid อัตโนมัติ"""

    def setUp(self):
        self.order = Order.objects.create(
            customer_name='สมบัติ มีเงิน', phone='0812345678', address='กทม 10110',
            total=Decimal('1000.00'), payment_method='promptpay',
        )

    def _pay(self, amount, note='', source=''):
        """จ่ายเงินผ่านจุดเดียว แล้วคืนผล dict ตรง ๆ"""
        return PaymentService.record_payment(
            self.order, 'สมบัติ มีเงิน', '0812345678',
            Decimal(amount), timezone.localdate(), note=note, source=source,
        )

    def test_partial_keeps_pending_with_remaining(self):
        """แจ้งจ่าย 600/1000 → ยัง pending, เหลือ 400"""
        res = self._pay('600.00')
        self.assertFalse(res['just_paid'])
        self.assertFalse(res['paid'])
        self.assertEqual(res['remaining'], Decimal('400.00'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_full_payment_flips_to_paid_auto(self):
        """จ่ายครบสะสม 1000 → สถานะเป็น 'ชำระเงินแล้ว' อัตโนมัติ"""
        self._pay('600.00')
        res = self._pay('400.00')
        self.assertTrue(res['just_paid'])
        self.assertTrue(res['paid'])
        self.assertEqual(res['remaining'], Decimal('0'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')

    def test_overshoot_is_paid_with_zero_remaining(self):
        """จ่ายเกินยอด → paid + ไม่เหลือยอด (ตัดส่วนเกินได้)"""
        res = self._pay('1200.00')
        self.assertTrue(res['paid'])
        self.assertEqual(res['remaining'], Decimal('0'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')

    def test_payment_row_saved_with_note(self):
        """ทุกการจ่ายบันทึกแถว Payment พร้อม source/note กำกับ"""
        self._pay('1000.00', note='สลิปจากธนาคาร', source='slip-audit')
        p = self.order.payments.get()
        self.assertEqual(p.amount, Decimal('1000.00'))
        self.assertEqual(p.note, 'สลิปจากธนาคาร')


class ValidatorsTest(TestCase):
    """ตัวช่วยตรวจข้อมูลร่วม — เบอร์โทร + ปฏิทินไทย"""

    def test_normalize_phone_strips_junk(self):
        """ตัด -, ช่องว่าง ออก เหลือตัวเลขล้วน"""
        self.assertEqual(Validators.normalize_phone(' 08 12-345-678 '), '0812345678')
        self.assertEqual(Validators.normalize_phone(''), '')

    def test_valid_phone_accepts_thai_numbers_only(self):
        """มือถือ 10 หลัก / เบอร์บ้าน 9 หลัก ขึ้นต้น 0 — อื่นไม่ผ่าน"""
        self.assertTrue(Validators.valid_phone('0812345678'))
        self.assertTrue(Validators.valid_phone('021234567'))
        self.assertTrue(Validators.valid_phone('08-12-345-678'))   # normalize ในตัว
        self.assertFalse(Validators.valid_phone('0812345'))       # สั้นไป
        self.assertFalse(Validators.valid_phone('912345678'))     # ไม่ขึ้น 0
        self.assertFalse(Validators.valid_phone(''))

    def test_thai_calendar_returns_strings(self):
        """greeting/full_date คืนข้อความภาษาไทยเสมอ (ไม่มีปีฝรั่งโชว์)"""
        self.assertIsInstance(ThaiCalendar.greeting(), str)
        self.assertTrue(ThaiCalendar.greeting())
        self.assertIsInstance(ThaiCalendar.full_date(), str)
        self.assertTrue(ThaiCalendar.full_date())