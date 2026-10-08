"""เทสต์ REST API (/api/) — สิทธิ์ + read-only + รหัสอัตโนมัติ.

ครอบคลุม:
- /api/products/ + /api/categories/ + /api/ : สาธารณะ (กันสินค้าซ่อน + filter/sort)
- /api/orders/ : staff เท่านั้น + read-only (create/update ถูก Router ตัด) + items ซ้อน
- /api/employees/ : staff, emp_code สร้างอัตโนมัติเสมอ (ต้องไม่รับจาก client)
- /api/token/ : ออก token ผ่าน username/password + ใช้ token ยิง endpoint staff (CRUD)
- ตรวจว่า DEFAULT_PERMISSION_CLASSES (IsAuthenticated) ไม่ทับ AllowAny ของ view สาธารณะ

อ้างอิง: apps.api.py — ใช้ DefaultRouter + permission class ต่อ view (OOP).
"""
from decimal import Decimal
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from myapp.models import Order, OrderItem, Product


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

    def test_products_exclude_inactive(self):
        """สินค้าที่ซ่อน (is_active=False) ต้องไม่โผล่ใน API สาธารณะ"""
        hidden = Product.objects.create(
            name='สินค้าซ่อน', price=Decimal('99.00'), stock=1,
            category='หมวดทดสอบ', is_active=False,
        )
        r = self.client.get('/api/products/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['count'], 1)
        self.assertNotIn(hidden.id, [p['id'] for p in data['results']])

    def test_products_filter_and_sort(self):
        """query params q / cat / sort ใช้ QuerySet ชุดเดียวกับหน้าร้าน"""
        Product.objects.create(name='คีย์บอร์ดกลไก', price=Decimal('2000.00'),
                               stock=3, category='อุปกรณ์', is_active=True)
        r = self.client.get('/api/products/', {'q': 'คีย์บอร์ด'})
        self.assertEqual(r.json()['count'], 1)
        r = self.client.get('/api/products/', {'cat': 'อุปกรณ์'})
        self.assertEqual(r.json()['count'], 1)
        r = self.client.get('/api/products/', {'sort': 'price_desc'})
        self.assertEqual(r.json()['results'][0]['name'], 'คีย์บอร์ดกลไก')

    def test_product_detail_ok(self):
        """รายละเอียดสินค้า + image_url เต็ม (build_absolute_uri)"""
        p = Product.objects.get(name='สินค้า A')
        r = self.client.get(f'/api/products/{p.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['name'], 'สินค้า A')
        self.assertIn('image_url', r.json())

    def test_categories_exclude_inactive_and_empty(self):
        """หมวดของสินค้าซ่อน/หมวดว่างต้องไม่ถูกนับใน /api/categories/"""
        Product.objects.create(name='ซ่อน', price=Decimal('1.00'), stock=1,
                               category='หมวดซ่อน', is_active=False)
        Product.objects.create(name='ไม่มีหมวด', price=Decimal('1.00'), stock=1,
                               category='', is_active=True)
        r = self.client.get('/api/categories/')
        names = [c['name'] for c in r.json()]
        self.assertEqual(names, ['หมวดทดสอบ'])


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

    def test_orders_include_nested_items(self):
        """items ซ้อนในออเดอร์ + product_name (prefetch items__product กัน N+1)"""
        product = Product.objects.create(name='หูฟังทดสอบ', price=Decimal('500.00'),
                                         stock=5, category='อุปกรณ์', is_active=True)
        order = Order.objects.first()
        OrderItem.objects.create(order=order, product=product,
                                 quantity=2, price=Decimal('500.00'))
        self.client.force_login(self.staff)
        r = self.client.get('/api/orders/')
        self.assertEqual(r.status_code, 200)
        row = r.json()['results'][0]
        self.assertEqual(row['items'][0]['product_name'], 'หูฟังทดสอบ')
        self.assertEqual(row['items'][0]['quantity'], 2)

    def test_order_detail_ok(self):
        self.client.force_login(self.staff)
        order = Order.objects.first()
        r = self.client.get(f'/api/orders/{order.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['id'], order.id)


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


class ApiTokenAuthTest(TestCase):
    """Token authentication กับ endpoint staff — ใช้ Authorization: Token xxx แทน session"""

    def setUp(self):
        self.staff = User.objects.create_user(username='teacher', password='pw123456', is_staff=True)

    def _token(self, username='teacher', password='pw123456'):
        """ขอ token ผ่าน endpoint จริง (integration)"""
        r = self.client.post('/api/token/', {'username': username, 'password': password})
        self.assertEqual(r.status_code, 200)
        return r.json()['token']

    def test_token_full_crud_flow(self):
        """token เดียวใช้ GET/POST/PATCH/DELETE employees ได้ครบ (ไม่พึ่ง session).

        สังเกต: Django 6.0 ตั้ง default content_type ของ Client.patch()/put() เป็น
        application/octet-stream (ไม่ใช่ multipart) → DRF ไม่มี parser รองรับ → 415
        จึงต้องส่ง content_type='application/json' ให้ตรงกับที่ client จริงเรียก API.
        """
        auth = {'HTTP_AUTHORIZATION': f'Token {self._token()}'}

        r = self.client.get('/api/employees/', **auth)
        self.assertEqual(r.status_code, 200)

        r = self.client.post('/api/employees/', json.dumps({
            'name': 'ทดสอบ โทเคน', 'gender': 'F', 'department': 'ไอที',
            'status': 'active', 'salary': '25000.00',
            'hire_date': timezone.localdate().isoformat(), 'address': 'กทม 10110',
        }), content_type='application/json', **auth)
        self.assertEqual(r.status_code, 201)
        emp_id = r.json()['id']
        self.assertTrue(r.json()['emp_code'].startswith('EMP'))

        r = self.client.patch(f'/api/employees/{emp_id}/',
                              json.dumps({'department': 'การเงิน'}),
                              content_type='application/json', **auth)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['department'], 'การเงิน')

        r = self.client.delete(f'/api/employees/{emp_id}/', **auth)
        self.assertEqual(r.status_code, 204)

    def test_invalid_token_denied(self):
        """token มั่ว → 403 (ไม่ใช่ 401 เพราะ SessionAuthentication เป็น authenticator
        ตัวแรกและไม่ส่ง WWW-Authenticate → DRF แปลง NotAuthenticated เป็น 403)"""
        r = self.client.get('/api/employees/', HTTP_AUTHORIZATION='Token deadbeef')
        self.assertEqual(r.status_code, 403)

    def test_non_staff_token_denied(self):
        """token ของลูกค้าทั่วไป (is_staff=False) → 403 (IsAdminUser)"""
        User.objects.create_user(username='member', password='pw123456')
        tok = self._token('member', 'pw123456')
        r = self.client.get('/api/employees/', HTTP_AUTHORIZATION=f'Token {tok}')
        self.assertEqual(r.status_code, 403)


class ApiDocsTest(TestCase):
    """OpenAPI schema + Swagger UI (drf-spectacular) — จำกัดเฉพาะ staff

    เคยเป็น AllowAny: คนนอกเข้าดูโครงสร้าง API ทั้งระบบได้โดยไม่ต้องล็อกอิน
    (เปิดโครงสร้าง endpoint + พารามิเตอร์ + ชนิดข้อมูลให้คนอื่นนำไปเล่นกับเว็บได้)
    ตอนนี้ใช้ IsAdminUser — เจ้าหน้าที่ยังดูได้ตามปกติ
    """

    def setUp(self):
        self.staff = User.objects.create_user(
            username='boss', password='pw123456', is_staff=True)

    def test_schema_requires_staff(self):
        """ยังไม่ล็อกอิน → ไม่เห็น schema"""
        r = self.client.get('/api/schema/')
        self.assertIn(r.status_code, (401, 403), 'schema ต้องปิดสาธารณะ')

    def test_schema_denied_for_customer(self):
        """ลูกค้าที่ล็อกอินแล้วก็ยังเข้าไม่ได้ (ไม่ใช่แค่ไม่ล็อกอิน)"""
        User.objects.create_user(username='member', password='pw123456')
        self.client.login(username='member', password='pw123456')
        r = self.client.get('/api/schema/')
        self.assertEqual(r.status_code, 403, 'ลูกค้าเข้า schema ไม่ได้')

    def test_schema_lists_public_endpoints(self):
        """staff ดูได้ และ schema ยังครบ endpoint ที่ต้องมี"""
        self.client.force_login(self.staff)
        r = self.client.get('/api/schema/')
        self.assertEqual(r.status_code, 200)
        body = r.content.decode('utf-8')
        self.assertIn('/api/products/', body)
        self.assertIn('/api/orders/', body)
        self.assertIn('/api/token/', body)

    def test_swagger_ui_ok_for_staff(self):
        self.client.force_login(self.staff)
        r = self.client.get('/api/docs/')
        self.assertEqual(r.status_code, 200)

    def test_swagger_ui_denied_for_anonymous(self):
        r = self.client.get('/api/docs/')
        self.assertIn(r.status_code, (401, 403), 'Swagger UI ต้องปิดสาธารณะ')

    def test_api_root_lists_schema_and_docs(self):
        r = self.client.get('/api/')
        data = r.json()
        self.assertIn('schema', data)
        self.assertIn('docs', data)