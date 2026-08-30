"""เทสต์ REST API (/api/) — สิทธิ์ + read-only + รหัสอัตโนมัติ.

ครอบคลุม:
- /api/products/ + /api/categories/ + /api/ : สาธารณะ
- /api/orders/ : staff เท่านั้น + read-only (create/update ถูก Router ตัด)
- /api/employees/ : staff, emp_code สร้างอัตโนมัติเสมอ (ต้องไม่รับจาก client)
- /api/token/ : ออก token ผ่าน username/password

อ้างอิง: apps.api.py — ใช้ DefaultRouter + permission class ต่อ view (OOP).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from myapp.models import Order, Product


class ApiPublicTest(TestCase):
    """API สาธารณะ — เปิดอ่านได้ไม่ต้องล็อกอิน"""

    def setUp(self):
        Product.objects.create(
            name='สินค้า A', price=Decimal('10.00'), stock=5,
            category='หมวดทดสอบ', is_active=True,
        )

    def test_products_list_public(self):
        r = self.client.get('/api/products/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['count'], 1)

    def test_categories_public(self):
        r = self.client.get('/api/categories/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data[0]['name'], 'หมวดทดสอบ')
        self.assertEqual(data[0]['count'], 1)

    def test_api_root_ok(self):
        r = self.client.get('/api/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('products', r.json())


class ApiOrdersStaffOnlyTest(TestCase):
    """/api/orders/ — ค่าอ่านได้เฉพาะ staff + read-only"""

    def setUp(self):
        self.staff = User.objects.create_user(username='teacher', password='pw', is_staff=True)
        Order.objects.create(
            customer_name='ลูกค้า หนึ่ง', phone='0812345678', address='กทม 10110',
            total=Decimal('10.00'), payment_method='promptpay',
        )

    def test_anonymous_denied(self):
        r = self.client.get('/api/orders/')
        self.assertIn(r.status_code, (401, 403))

    def test_staff_can_read_orders(self):
        self.client.force_login(self.staff)
        r = self.client.get('/api/orders/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['count'], 1)

    def test_orders_are_read_only(self):
        """REST ไม่เปิดเขียนออเดอร์ (อ่านอย่างเดียว) — POST → 405"""
        self.client.force_login(self.staff)
        r = self.client.post('/api/orders/', {'customer_name': 'X'})
        self.assertEqual(r.status_code, 405)


class ApiEmployeesTest(TestCase):
    """/api/employees/ — CRUD staff + emp_code อัตโนมัติ"""

    def setUp(self):
        self.staff = User.objects.create_user(username='teacher', password='pw', is_staff=True)

    def test_anonymous_denied(self):
        self.assertIn(self.client.get('/api/employees/').status_code, (401, 403))

    def test_staff_create_auto_emp_code(self):
        """สร้างพนักงานผ่าน API — client ส่ง emp_code ไม่ได้ (read_only) → รันให้เอง"""
        self.client.force_login(self.staff)
        today = timezone.localdate()
        r = self.client.post('/api/employees/', {
            'name': 'ใหม่ มาเพิ่ม', 'gender': 'M', 'department': 'ไอที',
            'status': 'active', 'salary': '20000.00',
            'hire_date': today.isoformat(), 'address': 'กทม 10110',
        })
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertTrue(data['emp_code'].startswith('EMP'))

    def test_staff_list_200(self):
        self.client.force_login(self.staff)
        r = self.client.get('/api/employees/')
        self.assertEqual(r.status_code, 200)


class ApiTokenTest(TestCase):
    """/api/token/ — obtain_auth_token (ใช้กับ client ภายนอก)"""

    def setUp(self):
        self.user = User.objects.create_user(username='teacher', password='pw123456', is_staff=True)

    def test_obtain_token_success(self):
        r = self.client.post('/api/token/', {'username': 'teacher', 'password': 'pw123456'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('token', r.json())

    def test_bad_credentials_400(self):
        r = self.client.post('/api/token/', {'username': 'teacher', 'password': 'wrong'})
        self.assertEqual(r.status_code, 400)