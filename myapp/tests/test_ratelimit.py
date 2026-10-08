"""เทสต์ rate limiting ของ endpoint ที่มีต้นทุน/ความเสี่ยง:

- `/api/token/`  → DRF `AnonRateThrottle` scope 'token' (10 ครั้ง/นาที/IP) กัน brute force
- `/payment/slip/` → `RateLimit` service (10 ครั้ง/นาที/IP) กันยิง OCR รัว

ทำไมต้อง `cache.clear()` ทุกเทสต์: ทั้ง DRF throttle และ RateLimit เก็บประวัตินับใน
Django cache (locmem) ซึ่ง**ไม่ถูกล้างระหว่างเทสต์อัตโนมัติ** — ถ้าไม่ล้าง โควตาจะรั่ว
ข้ามเทสต์/ข้ามคลาส (เทสต์อื่นในชุดก็ยิง /api/token/ อยู่หลายครั้ง).
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from myapp.services import RateLimit


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
