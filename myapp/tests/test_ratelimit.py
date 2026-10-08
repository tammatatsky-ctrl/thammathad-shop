"""เทสต์ rate limiting ของ endpoint ที่มีต้นทุน/ความเสี่ยง:

- `/api/token/`  → DRF `AnonRateThrottle` scope 'token' (10 ครั้ง/นาที/IP) กัน brute force
- `/payment/slip/` → `RateLimit` service (10 ครั้ง/นาที/IP) กันยิง OCR รัว
- `/staff/login/` + `/account/login/` → `LoginThrottle` service (3 ชั้น) กันเดารหัสผ่าน

ทำไมต้อง `cache.clear()` ทุกเทสต์: ทั้ง DRF throttle และ RateLimit เก็บประวัตินับใน
Django cache (locmem) ซึ่ง**ไม่ถูกล้างระหว่างเทสต์อัตโนมัติ** — ถ้าไม่ล้าง โควตาจะรั่ว
ข้ามเทสต์/ข้ามคลาส (เทสต์อื่นในชุดก็ยิง /api/token/ อยู่หลายครั้ง).
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from myapp.services import LoginThrottle, RateLimit


class TokenEndpointThrottleTest(TestCase):
    """/api/token/ จำกัด 10 ครั้ง/นาที ต่อ IP — ครั้งที่ 11 ต้องได้ 429"""

    def setUp(self):
        cache.clear()
        User.objects.create_user(username='teacher', password='pw123456', is_staff=True)

    def tearDown(self):
        cache.clear()

    def test_token_throttled_after_limit(self):
        for i in range(10):
            r = self.client.post('/api/token/', {'username': 'teacher', 'password': 'pw123456'})
            self.assertEqual(r.status_code, 200, f'ครั้งที่ {i + 1} ควรผ่าน')
        r = self.client.post('/api/token/', {'username': 'teacher', 'password': 'pw123456'})
        self.assertEqual(r.status_code, 429, 'ครั้งที่ 11 ต้องถูกจำกัดอัตรา')


class SlipEndpointThrottleTest(TestCase):
    """/payment/slip/ จำกัด 10 ครั้ง/นาที ต่อ IP — throttle ทำงานก่อนเช็คฟีเจอร์ (503)"""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_slip_throttled_after_limit(self):
        # เทสต์ไม่ตั้ง SLIPOK_API_KEY → 10 ครั้งแรกได้ 503 (ฟีเจอร์ปิด) แต่ครั้งที่ 11 ต้อง 429
        for i in range(10):
            r = self.client.post('/payment/slip/', {'order_id': '1', 'phone': '0800000000'})
            self.assertEqual(r.status_code, 503, f'ครั้งที่ {i + 1}')
        r = self.client.post('/payment/slip/', {'order_id': '1', 'phone': '0800000000'})
        self.assertEqual(r.status_code, 429, 'ครั้งที่ 11 ต้องถูกจำกัดอัตรา')


class LoginThrottleTest(TestCase):
    """หน้า login (staff + ลูกค้า) ต้องกัน brute force — 3 ชั้น: IP → IP+ชื่อ → ต่อบัญชี

    เคยเป็นช่องโหว่: /api/token/ มี throttle แต่ /staff/login/ + /account/login/
    ไม่มีเลย → เดารหัสผ่านได้ไม่จำกัด (Django มีแต่ session lockout ต่อ IP ที่ช้า)
    """

    def setUp(self):
        cache.clear()
        User.objects.create_user(username='boss', password='Correct123!', is_staff=True)

    def tearDown(self):
        cache.clear()

    def _fail_staff(self, times, username='boss', ip='127.0.0.1'):
        """ยิง staff login ด้วยรหัสผิด n ครั้ง — คืน status สุดท้าย"""
        last = None
        for _ in range(times):
            last = self.client.post(
                reverse('staff_login'),
                {'username': username, 'password': 'WrongWrong!'},
                REMOTE_ADDR=ip,
            )
        return last

    # ---------- ชั้นต่อบัญชี (ตัวสุดท้าย) ----------
    def test_account_locked_after_repeated_failures(self):
        """บัญชีเดียวล้มเหลวครบโควตา → รหัสผ่านถูกต้องก็ตอบ 429 (ไม่ใช่ 200)"""
        last = self._fail_staff(LoginThrottle.USER_LIMIT)
        self.assertEqual(last.status_code, 200, 'ครั้งสุดท้ายของโควตายังเป็นหน้า login ปกติ')

        r = self.client.post(
            reverse('staff_login'),
            {'username': 'boss', 'password': 'Correct123!'},   # รหัสผ่านถูกต้องแล้ว
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(r.status_code, 429, 'ถึงล็อกแล้วแม้รหัสผ่านถูก ต้อง 429 ไม่ใช่ให้เข้า')

    def test_lock_is_scoped_per_account(self):
        """ล็อกบัญชี A ต้องไม่กระทบบัญชี B (ผู้ใช้จริงหลายคนในห้องเดียวกันต้องใช้ได้)"""
        User.objects.create_user(username='boss2', password='Correct123!', is_staff=True)
        self._fail_staff(LoginThrottle.USER_LIMIT, username='boss')

        r = self.client.post(
            reverse('staff_login'),
            {'username': 'boss2', 'password': 'Correct123!'},
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(r.status_code, 302, 'อีกบัญชีหนึ่งต้องเข้าได้ตามปกติ')

    # ---------- ชั้นต่อ IP ----------
    def test_ip_locked_after_flood(self):
        """ยิงเดาชื่อผิดๆ จนถึงโควตา IP → บล็อกทั้ง IP (กัน DoS / distributed brute force)"""
        last = None
        for i in range(LoginThrottle.IP_LIMIT + 1):
            last = self.client.post(
                reverse('staff_login'),
                {'username': f'ghost{i}', 'password': 'WrongWrong!'},
                REMOTE_ADDR='10.0.0.9',
            )
        self.assertEqual(last.status_code, 429, 'เกินโควตา IP ต้อง 429')

        # แม้แต่บัญชีจริงจาก IP เดียวกันก็ถูกบล็อก (ชั้น IP เหนือกว่า)
        r = self.client.post(
            reverse('staff_login'),
            {'username': 'boss', 'password': 'Correct123!'},
            REMOTE_ADDR='10.0.0.9',
        )
        self.assertEqual(r.status_code, 429)

    # ---------- การล้างตัวนับเมื่อสำเร็จ ----------
    def test_success_clears_account_counter(self):
        """เข้าสำเร็จแล้วตัวนับความล้มเหลวของบัญชีต้องถูกล้าง (ไม่ให้ผู้ใช้จริงโดนล็อกสะสม)"""
        self._fail_staff(2)
        r = self.client.post(reverse('staff_login'),
                             {'username': 'boss', 'password': 'Correct123!'},
                             REMOTE_ADDR='127.0.0.1')
        self.assertEqual(r.status_code, 302)

        # ล้มเหลวอีก "เกือบเต็ม" โควตาหลังจากเคยล้าง → รหัสผ่านถูกยังเข้าได้
        # (ถ้าตัวนับไม่ถูกล้าง ครั้งก่อนหน้าจะทำให้โควตาหมดไปแล้ว = 429)
        self.client.logout()
        self._fail_staff(LoginThrottle.USER_LIMIT - 1)
        r = self.client.post(reverse('staff_login'),
                             {'username': 'boss', 'password': 'Correct123!'},
                             REMOTE_ADDR='127.0.0.1')
        self.assertEqual(r.status_code, 302, 'ตัวนับต้องถูกล้างจริง ไม่ใช่สะสมต่อเนื่อง')

    # ---------- หน้าลูกค้า ----------
    def test_customer_login_also_throttled(self):
        """หน้าลูกค้าใช้กลไกเดียวกัน (ไม่ใช่แค่ staff)"""
        User.objects.create_user(username='buyer@example.com', password='Correct123!')
        for _ in range(LoginThrottle.USER_LIMIT):
            self.client.post(reverse('account_login'),
                             {'username': 'buyer@example.com', 'password': 'WrongWrong!'},
                             REMOTE_ADDR='127.0.0.1')
        r = self.client.post(reverse('account_login'),
                             {'username': 'buyer@example.com', 'password': 'Correct123!'},
                             REMOTE_ADDR='127.0.0.1')
        self.assertEqual(r.status_code, 429)

    # ---------- ไม่รั่วข้อมูล ----------
    def test_same_message_regardless_of_which_layer_blocked(self):
        """ทุกกรณีที่โดนจำกัดต้องข้อความเดียวกัน (กันเรียนรู้ว่าโดนชั้นไหน)"""
        self._fail_staff(LoginThrottle.USER_LIMIT)
        r = self.client.post(reverse('staff_login'),
                             {'username': 'boss', 'password': 'Correct123!'},
                             REMOTE_ADDR='127.0.0.1')
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, LoginThrottle.MESSAGE, status_code=429)


class RateLimitServiceTest(TestCase):
    """unit test ของ service โดยตรง — นับตามโควตา และแยก bucket ตาม scope/ident"""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_allow_then_block(self):
        for i in range(3):
            self.assertTrue(RateLimit.allow('unit', 'ip-1', limit=3, window=60), f'ครั้งที่ {i + 1}')
        self.assertFalse(RateLimit.allow('unit', 'ip-1', limit=3, window=60))

    def test_scopes_and_idents_isolated(self):
        self.assertTrue(RateLimit.allow('unit', 'ip-1', limit=1, window=60))
        self.assertTrue(RateLimit.allow('unit', 'ip-2', limit=1, window=60))
        self.assertTrue(RateLimit.allow('other', 'ip-1', limit=1, window=60))
