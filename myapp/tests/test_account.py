"""เทสต์บัญชีลูกค้า — register, สมุดที่อยู่ (auto-default / สลับ / ลบทิ้ง), สิทธิ์.

ครอบคลุม:
- สมัครบัญชี: สร้าง User(username=email) + CustomerProfile + ล็อกอินอัตโนมัติ
- ฟอร์ม register: เบอร์ไทย, อีเมล, รหัสผ่านซ้ำ — ปฏิเสธแบบมีข้อความไทย
- สมุดที่อยู่: ที่อยู่แรก = ค่าเริ่มต้นอัตโนมัติ, ที่อยู่ถัดไปไม่ใช่,
  ตั้ง default ใหม่ได้, ลบตัว default → เลื่อนให้ตัวถัดไป
- ความเป็นเจ้าของ: แก้ที่อยู่ของคนอื่น → 404 (ไม่หลุดข้อมูลข้ามบัญชี)

หมายเหตุ: checkout ของล็อกอิน user ผูก order.user (เทสต์ใน test_cart_checkout).
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from myapp.models import CustomerAddress


class RegisterTest(TestCase):
    """สมัครบัญชีลูกค้า"""

    def _register(self, **over):
        data = {
            'name': 'ใจดี วันใหม่', 'email': 'u@test.com', 'phone': '0812345678',
            'address': 'กทม 10110', 'password1': 'secret123', 'password2': 'secret123',
        }
        data.update(over)
        return self.client.post(reverse('account_register'), data)

    def test_success_creates_user_profile_and_login(self):
        r = self._register()
        self.assertRedirects(r, reverse('product'))
        user = User.objects.get(username='u@test.com')
        self.assertIsNotNone(user.customer_profile)
        self.assertEqual(user.customer_profile.phone, '0812345678')
        self.assertEqual(self.client.get(reverse('account')).status_code, 200)

    def test_bad_phone_rerenders_with_message(self):
        """เบอร์ไม่ใช่เบอร์ไทย (999) → ไม่สร้างบัญชี + ข้อความไทย"""
        r = self._register(phone='999')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'เบอร์โทรศัพท์ไม่ถูกต้อง')
        self.assertEqual(User.objects.count(), 0)

    def test_password_mismatch_rejected(self):
        """รหัสทั้งสองช่องไม่ตรง → ไม่สร้าง"""
        r = self._register(password2='different1')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(User.objects.count(), 0)

    def test_duplicate_email_rejected(self):
        """อีเมลซ้ำ → แจ้งเตือน"""
        User.objects.create_user(username='dup@test.com', password='x')
        r = self._register(email='dup@test.com')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ถูกใช้สมัครแล้ว')


class AddressBookTest(TestCase):
    """สมุดที่อยู่จัดส่ง — กติกาค่าเริ่มต้น"""

    def setUp(self):
        self.user = User.objects.create_user(username='cust@test.com', password='pw123456')
        self.client.force_login(self.user)
        self.data = {
            'label': 'บ้าน', 'receiver_name': 'สมชาย ใจดี', 'phone': '0812345678',
            'detail': '12/3 ถ.สุขุมวิท', 'province': 'กรุงเทพมหานคร',
            'district': 'วัฒนา', 'subdistrict': 'คลองเตย', 'zipcode': '10110',
        }

    def _add(self, **over):
        return self.client.post(reverse('address_add'), {**self.data, **over})

    def test_first_address_auto_default(self):
        """ที่อยู่แรก → is_default=True อัตโนมัติ"""
        r = self._add()
        self.assertRedirects(r, reverse('account'))
        addr = self.user.addresses.get()
        self.assertTrue(addr.is_default)

    def test_second_address_not_default(self):
        """ที่อยู่ที่สอง → ไม่เป็นค่าเริ่มต้น (มีตัวแรกครองอยู่)"""
        self._add()
        self._add(receiver_name='นางสาว สอง ใจ', label='ที่ทำงาน')
        addresses = list(self.user.addresses.order_by('id'))
        self.assertFalse(addresses[1].is_default)

    def test_set_default_switches_flag(self):
        """ตั้ง default ใหม่ → ตัวเก่าถูกปลด default"""
        self._add()
        second = CustomerAddress.objects.create(
            user=self.user, label='ที่ทำงาน', receiver_name='นางสาว สอง ใจ',
            phone='0812345678', detail='99', province='นนทบุรี',
            district='เมือง', subdistrict='บางเขน', zipcode='11000',
            is_default=False,
        )
        r = self.client.post(reverse('address_default', args=[second.id]))
        self.assertRedirects(r, reverse('account'))
        second.refresh_from_db()
        first = self.user.addresses.exclude(id=second.id).get()
        self.assertTrue(second.is_default)
        self.assertFalse(first.is_default)

    def test_delete_default_promotes_next(self):
        """ลบตัว default → เลื่อนค่าเริ่มต้นไปให้ที่อยู่ถัดไป"""
        self._add()
        second = CustomerAddress.objects.create(
            user=self.user, label='ที่ทำงาน', receiver_name='นางสาว สอง ใจ',
            phone='0812345678', detail='99', province='นนทบุรี',
            district='เมือง', subdistrict='บางเขน', zipcode='11000',
            is_default=False,
        )
        first = self.user.addresses.exclude(id=second.id).get()
        self.client.post(reverse('address_delete', args=[first.id]))
        second.refresh_from_db()
        self.assertTrue(second.is_default)

    def test_address_bad_phone_rejected(self):
        """เบอร์โทรผิด → ไม่บันทึก (ป้องกันที่อยู่เถื่อน)"""
        r = self._add(phone='1')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'เบอร์โทรศัพท์ไม่ถูกต้อง')
        self.assertEqual(CustomerAddress.objects.count(), 0)

    def test_cannot_edit_others_address(self):
        """แก้ที่อยู่ของคนอื่น → 404 (เจ้าของเท่านั้น ตรวจใน view)"""
        other = User.objects.create_user(username='other@test.com', password='pw123456')
        their_addr = CustomerAddress.objects.create(
            user=other, receiver_name='คนอื่น', phone='0812345678',
            detail='1', province='จ.ซ', district='อ.ย', subdistrict='ต.ซ',
            zipcode='10000',
        )
        r = self.client.get(reverse('address_edit', args=[their_addr.id]))
        self.assertEqual(r.status_code, 404)