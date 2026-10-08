"""เทสต์หน้าแดชบอร์ด — ล็อก "สัญญาการจัดวาง" ตามหลัก Dashboard Design ไว้ไม่ให้ถอยกลับ.

ครอบคลุม:
- ลำดับชั้นข้อมูล: KPI ธุรกิจ (ออเดอร์) มาก่อนบุคลากร (พนักงาน) ตาม F-pattern/inverted pyramid
- Action layer: มี empty state "ทุกอย่างเรียบร้อย" เมื่อไม่มีงานค้าง (state completeness)
- สัญญาเดิมที่ห้ามหลุด: `id="reports"` (ปลายทาง redirect ของ PaymentVerifyView) + ข้อความแจ้งเตือนสต็อก
- Offline-ready: ห้ามมีสคริปต์/สไตล์จาก CDN ภายนอก และ QR ต้องถูกสร้างฝั่งเซิร์ฟเวอร์ (data URI)
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from myapp.models import Order, Product


class DashboardLayoutTest(TestCase):
    """โครงหน้า + ลำดับความสำคัญ + สถานะว่าง"""

    def setUp(self):
        self.staff = User.objects.create_user(username='teacher', password='pw', is_staff=True)
        self.client.force_login(self.staff)

    def _html(self):
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.status_code, 200)
        return r.content.decode('utf-8')

    def test_kpi_hierarchy_business_metrics_first(self):
        """KPI สำคัญทางธุรกิจ (ออเดอร์) ต้องมาก่อน KPI บุคลากร (พนักงาน)"""
        html = self._html()
        self.assertIn('ออเดอร์ทั้งหมด', html)
        self.assertIn('พนักงานทั้งหมด', html)
        self.assertLess(html.index('ออเดอร์ทั้งหมด'), html.index('พนักงานทั้งหมด'))

    def test_empty_state_when_no_pending_work(self):
        """ไม่มีงานค้าง → แสดงแถบยืนยันว่าตรวจแล้ว (ไม่ซ่อนเงียบ ๆ)"""
        html = self._html()
        self.assertIn('ทุกอย่างเรียบร้อย', html)

    def test_reports_anchor_present(self):
        """#reports = ปลายทาง redirect ของ payment_verify (ห้ามหลุด)"""
        self.assertIn('id="reports"', self._html())

    def test_low_stock_alert_texts(self):
        """ข้อความที่เทสต์อื่นอ้างถึง (แจ้งเตือนวิกฤต + ชื่อการ์ด) ต้องคงอยู่"""
        Product.objects.create(name='สินค้าใกล้หมด', price=Decimal('10.00'), stock=1,
                               category='ทดสอบ', is_active=True)
        html = self._html()
        self.assertIn('แจ้งเตือนสต็อกสินค้าวิกฤต', html)
        self.assertIn('สต็อกต้องเฝ้าระวัง', html)

    def test_urgent_queue_when_work_pending(self):
        """มีออเดอร์ pending → เห็นคิว 'ต้องดำเนินการ' พร้อมปุ่มลงมือ"""
        Order.objects.create(customer_name='ลูกค้า ทดสอบ', phone='0812345678', address='กทม',
                             total=Decimal('100.00'), payment_method='promptpay')
        html = self._html()
        self.assertIn('ต้องดำเนินการ', html)
        self.assertNotIn('ทุกอย่างเรียบร้อย', html)


class DashboardOfflineAssetsTest(TestCase):
    """หน้าแดชบอร์ดต้องไม่พึ่ง CDN ภายนอก (เปิดออฟไลน์ + ตามหลัก self-host ของโปรเจกต์)"""

    def setUp(self):
        self.staff = User.objects.create_user(username='teacher', password='pw', is_staff=True)
        self.client.force_login(self.staff)

    def test_no_external_cdn_in_dashboard(self):
        html = self.client.get(reverse('dashboard')).content.decode('utf-8')
        for host in ('cdnjs.cloudflare.com', 'fonts.googleapis.com', 'fonts.gstatic.com', 'cdn.jsdelivr.net'):
            self.assertNotIn(host, html, f'ห้ามพึ่ง CDN: {host}')

    def test_mobile_qr_generated_server_side(self):
        """QR เปิดบนมือถือ = <img> data URI ที่สร้างฝั่งเซิร์ฟเวอร์ (ไม่ต้องมี JS)"""
        html = self.client.get(reverse('dashboard')).content.decode('utf-8')
        self.assertIn('data:image/png;base64,', html)
        self.assertIn('/employees/', html)
        self.assertIn('เปิดระบบบนมือถือ', html)
