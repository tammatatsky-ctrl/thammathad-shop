"""เทสต์ "สัญญา AJAX" ของทั้งระบบ — `is_ajax()` จุดเดียวที่ตัดสิน JSON/partial vs redirect เต็มหน้า.

บริบท: เดิมแต่ละ view ตรวจเองคนละแบบ (header fetch / ?partial=1 / ?drawer=1 / XMLHttpRequest)
หลังรวมเป็น `myapp/views.py::is_ajax()` — ไฟล์นี้ล็อกสัญญาไว้ไม่ให้ถอยกลับ:

- หน่วย (RequestFactory): ทุกช่องทางที่ประกาศต้องคืน True และคำขอธรรมดาต้องเป็น False
- รวมระบบ: order drawer (URL mode ที่เคยไม่มีเทสต์) เปิดได้ทั้ง ?drawer=1 และ header
  และต้องได้ fragment ที่ไม่มี chrome ของหน้าเต็ม
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from myapp.models import Order
from myapp.views import is_ajax


class IsAjaxHelperTest(TestCase):
    """unit test ของ is_ajax() — ครบทุกช่องทาง + ไม่ over-match"""

    def setUp(self):
        self.rf = RequestFactory()

    def test_standard_fetch_header(self):
        """ช่องทางมาตรฐานของโปรเจกต์: X-Requested-With: fetch"""
        self.assertTrue(is_ajax(self.rf.get('/', HTTP_X_REQUESTED_WITH='fetch')))

    def test_legacy_xmlhttprequest_accepted(self):
        """compat: ไลบรารี/โค้ดเก่าที่ส่ง XMLHttpRequest ต้องไม่พัง"""
        self.assertTrue(is_ajax(self.rf.get('/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')))

    def test_drawer_channels(self):
        """drawer: query ?drawer=1 · header X-Drawer: true · ฟิลด์ฟอร์ม ajax=1"""
        self.assertTrue(is_ajax(self.rf.get('/', {'drawer': '1'})))
        self.assertTrue(is_ajax(self.rf.get('/', HTTP_X_DRAWER='true')))
        self.assertTrue(is_ajax(self.rf.post('/', {'ajax': '1'})))

    def test_partial_query_mode(self):
        """fragment สาธารณะ: ?partial=1 (product grid / cart panel)"""
        self.assertTrue(is_ajax(self.rf.get('/', {'partial': '1'})))

    def test_plain_request_is_not_ajax(self):
        self.assertFalse(is_ajax(self.rf.get('/')))
        self.assertFalse(is_ajax(self.rf.get('/', {'partial': '0', 'drawer': '0'})))
        self.assertFalse(is_ajax(self.rf.post('/', {'ajax': '0'})))


class OrderDrawerAjaxTest(TestCase):
    """order detail drawer (fragment) — ทั้งสองช่องทางให้ผลเดียวกัน และหน้าเต็มยังมี chrome"""

    def setUp(self):
        self.staff = User.objects.create_user(username='teacher', password='pw', is_staff=True)
        self.client.force_login(self.staff)
        self.order = Order.objects.create(
            customer_name='ลูกค้า หนึ่ง', phone='0812345678', address='กทม',
            total=Decimal('500.00'), payment_method='promptpay',
        )

    def test_full_page_has_chrome(self):
        """GET ปกติ → หน้าเต็ม (มี navbar ของ basetemplate)"""
        r = self.client.get(reverse('order_detail', args=[self.order.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'THAMMATHAD SHOP')

    def test_drawer_by_query_param(self):
        """?drawer=1 → เฉพาะเนื้อหา drawer (ไม่มี chrome)"""
        r = self.client.get(reverse('order_detail', args=[self.order.id]), {'drawer': '1'})
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'THAMMATHAD SHOP')

    def test_drawer_by_header(self):
        """header มาตรฐาน (fetch) + X-Drawer: true → ได้ fragment เหมือน ?drawer=1"""
        r = self.client.get(reverse('order_detail', args=[self.order.id]),
                            HTTP_X_REQUESTED_WITH='fetch', HTTP_X_DRAWER='true')
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'THAMMATHAD SHOP')
