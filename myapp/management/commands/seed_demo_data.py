"""เปลี่ยนข้อมูลทดสอบให้เป็น "ข้อมูลตัวอย่างจริง" ที่อาจารย์อ่านแล้วเชื่อว่าเป็นร้านจริง

ทำไมต้องมีคำสั่งนี้
    หลังทดสอบระบบเสร็จ ฐานข้อมูลจะมีข้อมูลที่**ไม่ควรถูกส่งให้อาจารย์ดู**ปนอยู่:
      - พนักงานชื่อ "ทดสอบ ระบบบันทึก" 4 คน อีเมล `audit.probe@example.com`
      - บัญชีผู้ใช้ชื่อ `probe_teacher2`, `cmt_probe`, `debug@test.com`, `x@y.z`
      - ลูกค้าที่ทดสอบเว็บไปแล้วลืมลบ (`ggg@gmail.com`, `my@gmail.com`, ...)
      - ออเดอร์ชื่อ "ลูกค้า ทดสอบ" ที่อยู่ "123 ถนนตัวอย่าง"
    ข้อมูลพวกนี้ทำให้อาจารย์เห็นว่างานยังไม่เสร็จ ทั้งที่ระบบใช้งานได้ครบ

    คำสั่งนี้จึง (ก) ลบเฉพาะข้อมูลที่ระบุไว้ด้านล่างอย่างชัดเจน
    และ (ข) ใส่ข้อมูลตัวอย่างที่ดูเหมือนร้านจริงแทน — ครบทุกสถานะออเดอร์
    ครบทุกช่องทางชำระ และมีการแจ้งปัญหาทั้งที่ยังค้างและที่ปิดแล้ว

หลักการที่ยึด (เหมือน `seed_catalog`)
    - **upsert ตามคีย์คงที่** ไม่ใช้ `delete()` ทั้งตาราง → รันซ้ำกี่ครั้งก็ได้ผลเดิม
    - **ระบุข้อมูลที่จะลบไว้เป็นรายการชัดเจน** ไม่ใช้ pattern กวาด
      (การกวาดด้วย regex เช่น `probe` เสี่ยงลบบัญชีของคนจริงโดยไม่ตั้งใจ)
    - **ไม่แตะ superuser 3 บัญชี** (`admin`, `ohm`, `teacher`) และ `ohm` กับทรัพย์สิน
      ของเขา (profile / avatar / cover / ที่อยู่ / ออเดอร์) — `ohm` คือบัญชี
      ทดสอบหลักของเจ้าของงาน ลบแล้วทำงานต่อไม่ได้

คำสั่ง
    python manage.py seed_demo_data            # ล้างข้อมูลทดสอบ + ใส่ข้อมูลตัวอย่าง
    python manage.py seed_demo_data --keep-junk # ใส่ข้อมูลตัวอย่างอย่างเดียว ไม่ลบอะไร
    python manage.py seed_demo_data --dry-run   # ดูว่าจะทำอะไร โดยไม่เขียนจริง
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


#: บัญชีที่ "ห้ามแตะ" เด็ดขาด — superuser/เจ้าของงาน
KEEP_USERS = {'admin', 'ohm', 'teacher'}

#: รหัสผ่านของบัญชีลูกค้าตัวอย่างที่เอกสารระบุไว้
#: ต้องตรงกับ `DEMO.md` เสมอ — ถ้าต่างกัน เอกสารจะโกหกโดยไม่มีใครสังเกต
DEMO_PASSWORD = 'Demo2026!'


def _password_missing(user) -> bool:
    """บัญชีนี้ยังไม่มีรหัสผ่านที่ใช้ล็อกอินได้จริงหรือไม่

    ⚠ ห้ามใช้ `has_usable_password()` อย่างเดียว
        Django ถือว่ารหัสผ่านที่เป็น **สตริงว่าง** คือ "ใช้ได้" เพราะ
        `is_password_usable('')` คืนค่า True (มันเช็คแค่ว่าไม่ได้ขึ้นต้นด้วย
        เครื่องหมายที่ Django ใช้ทำเครื่องหมาย "รหัสใช้ไม่ได้")

        ผลคือบัญชีที่ `get_or_create` เพิ่งสร้างใหม่ (ยังไม่เคยตั้งรหัสเลย)
        จะผ่านเงื่อนไข "ยังไม่มีรหัส" ออกมาเป็น False → **ไม่เคยตั้งรหัสให้**
        และล็อกอินไม่ได้ แต่ไม่มี error ให้เห็น

        เคยเกิดจริง: บัญชีลูกค้าตัวอย่างทั้ง 6 รายไม่มีรหัสผ่านที่ใช้ได้
        ทั้งที่เอกสารระบุว่าเข้าด้วย `Demo2026!`

    ชื่อฟังก์ชันตั้งใจให้เป็น**บวก** (`if _password_missing(user):`)
        เพราะครั้งหนึ่งเขียนผิดเป็น `if not _needs_password(...)` ซึ่งแปลว่า
        "ถ้ามีรหัสแล้วจึงทับด้วยรหัสตัวอย่าง" — ผลคือบัญชีใหม่ไม่เคยได้รหัสเลย
        และบัญชีเก่าที่ตั้งรหัสไว้จะถูกทับ ซึ่งตรงข้ามกับเจตนาของโค้ดทั้งดุ้น
    """
    return not user.password or not user.has_usable_password()


#: บัญชีทดสอบที่สร้างจากการรันเทสต์/กดส่วนประกอบตอนพัฒนา — ลบได้
JUNK_USERNAMES = [
    'debug@test.com',      # ทดสอบ staff login
    'x@y.z',               # ทดสอบ validation อีเมล
    'cust_alert_test',     # ทดสอบแจ้งเตือน
    'ggg@gmail.com',       # ลองสมัครสมาชิกแล้วลืมลบ
    'probe_teacher2',      # ทดสอบ rate limit
    'probe_teacher3',
    'cmt_probe',           # ทดสอบ commit probe
    'cmt_probe_v2',
    'cmt_probe_v3',
    'my@gmail.com',       # ลองชำระเงินแล้วลืมลบ
]

#: พนักงานที่สร้างจากการกดทดสอบระบบ (อีเมลเดียวกันหมด = ลงมือทดสอบ ไม่ใช่ของจริง)
JUNK_EMPLOYEE_EMAIL = 'audit.probe@example.com'

#: ออเดอร์สาธิตที่ล้างทิ้ง (ชื่อลูกค้าบอกได้ชัดว่าเป็นข้อมูลทดสอบ)
JUNK_ORDER_NAMES = ['ลูกค้า สาธิต', 'ลูกค้า ทดสอบ']

#: ที่อยู่ที่ใส่ให้ `ohm` — แทนค่าที่เพี้ยนอยู่เดิม
#: (ดูหมายเหตุใน `_purge_junk` ข้อ 4 — เคยลองเขียนตัวตรวจ mojibake อัตโนมัติ
#:  แล้วตัดทิ้ง เพราะ "หนองทอง" ที่เพี้ยนเป็น "ะพ้เิกิดิ" ยังเป็น Unicode ที่ถูกต้อง
#:  แยกจากข้อความปกติด้วยกฎภาษาไทยไม่ได้ เพราะสระหน้าเกาะหน้าพยัญชนะเป็นเรื่องปกติ
#:  เช่น "ไร้สาย" จึงต้องกำหนดค่าที่ถูกต้องตรง ๆ แทนการเดา)
OHM_ADDRESS = ('165 หมู่ 2 หนองทอง ต.หนองทอง '
               'อ.ไทรงาม จ.กำแพงเพชร 62150')


# --------------------------------------------------------------------------
# ข้อมูลตัวอย่าง: พนักงาน
# --------------------------------------------------------------------------
EMPLOYEES = [
    # emp_code, name, gender, department, phone, salary, hire_date, status
    ('EMP001', 'ธรรมธัช รูปไธสง', 'M', 'ขาย',
     '089-123-4567', 65000, '2016-06-01', 'active'),
    ('EMP002', 'สมชาย ใจดี', 'M', 'ไอที',
     '089-234-5678', 45000, '2019-01-15', 'active'),
    ('EMP003', 'สมหญิง รักงาน', 'F', 'บุคคล',
     '089-345-6789', 38000, '2020-03-02', 'active'),
    ('EMP004', 'ปกรณ์ มั่นคง', 'M', 'การเงิน',
     '089-456-7890', 52000, '2018-07-23', 'active'),
    ('EMP005', 'วรรณิศา แสงทอง', 'F', 'การตลาด',
     '089-567-8901', 41000, '2021-06-14', 'active'),
    ('EMP006', 'อนุชา เพียรพยายาม', 'M', 'ขาย',
     '089-678-9012', 30000, '2022-01-10', 'active'),
    ('EMP007', 'พิมพ์ชนก สดใส', 'F', 'บุคคล',
     '089-789-0123', 36000, '2021-09-30', 'active'),
    ('EMP008', 'ธนกร ซื่อสัตย์', 'M', 'การเงิน',
     '089-890-1234', 55000, '2017-04-18', 'active'),
    ('EMP009', 'ณัฐริกา ยิ้มง่าย', 'F', 'ขาย',
     '089-901-2345', 32000, '2023-02-20', 'active'),
    ('EMP010', 'ศิริ ขยันทำงาน', 'M', 'ไอที',
     '089-012-3456', 60000, '2016-08-08', 'active'),
    ('EMP011', 'มนัสนัน อ่อนหวาน', 'F', 'การตลาด',
     '089-123-4509', 39000, '2022-05-12', 'active'),
    ('EMP012', 'ภูมิรพี เด็ดเดี่ยว', 'M', 'ขาย',
     '089-234-5018', 28000, '2024-01-03', 'resigned'),
    ('EMP013', 'กันต์ ช่างฝัน', 'M', 'ไอที',
     '089-345-0127', 48000, '2020-11-05', 'leave'),
]

EMPLOYEE_ADDRESS = '123 ถนนราชภัฏ ต.หนองบัว อ.เมือง จ.กำแพงเพชร 62150'


# --------------------------------------------------------------------------
# ข้อมูลตัวอย่าง: ลูกค้า (บัญชี + โปรไฟล์ + ที่อยู่ในสมุด)
# --------------------------------------------------------------------------
CUSTOMERS = [
    {
        'username': 'wichai.s',
        'first_name': 'วิชัย', 'last_name': 'สุขสง',
        'email': 'wichai.suk@gmail.com', 'phone': '081-642-3579',
        'member_since': '2025-11-04',
        'address': {
            'label': 'บ้าน (หนองบัว)', 'receiver_name': 'วิชัย สุขสง',
            'phone': '081-642-3579', 'detail': '123 หมู่ 4 หนองบัว',
            'province': 'กำแพงเพชร', 'district': 'เมืองกำแพงเพชร',
            'subdistrict': 'หนองบัว', 'zipcode': '62150',
        },
    },
    {
        'username': 'pornchai.k',
        'first_name': 'พรชัย', 'last_name': 'กิจจากุล',
        'email': 'pornchai.kij@outlook.com', 'phone': '089-753-1462',
        'member_since': '2026-02-18',
        'address': {
            'label': 'ที่ทำงาน (บางกะปิ)', 'receiver_name': 'พรชัย กิจจากุล',
            'phone': '089-753-1462', 'detail': '456 อาคารสินค้า ชั้น 5 ห้อง 502',
            'province': 'กรุงเทพมหานคร', 'district': 'บางกะปิ',
            'subdistrict': 'หัวหว้า', 'zipcode': '10240',
        },
    },
    {
        'username': 'siriporn.t',
        'first_name': 'ศิริพร', 'last_name': 'ทองแท้',
        'email': 'siriporn_thongtan@gmail.com', 'phone': '086-512-9043',
        'member_since': '2026-04-27',
        'address': {
            'label': 'บ้าน (นครปฐม)', 'receiver_name': 'ศิริพร ทองแท้',
            'phone': '086-512-9043', 'detail': '9 ถนนราชดำเนิ ต.พิมาย',
            'province': 'นครปฐม', 'district': 'เมืองนครปฐม',
            'subdistrict': 'พิมาย', 'zipcode': '73000',
        },
    },
    {
        'username': 'nattapong.s',
        'first_name': 'ณัฐพงษ์', 'last_name': 'สุขสง',
        'email': 'nattapong.s@gmail.com', 'phone': '092-418-6573',
        'member_since': '2026-06-09',
        'address': {
            'label': 'บ้าน (สุขุมวิท)', 'receiver_name': 'ณัฐพงษ์ สุขสง',
            'phone': '092-418-6573', 'detail': '12/3 อาคารสยาม ไทดี ชั้น 17',
            'province': 'กรุงเทพมหานคร', 'district': 'คลองเตย',
            'subdistrict': 'คลองเตย', 'zipcode': '10110',
        },
    },
    {
        'username': 'kanyarat.w',
        'first_name': 'กันยารัตน์', 'last_name': 'วงศ์ไทย',
        'email': 'kanyarat.wongthai@gmail.com', 'phone': '064-905-8213',
        'member_since': '2026-07-21',
        'address': {
            'label': 'บ้าน (ตลาดใหม่ระยอง)', 'receiver_name': 'กันยารัตน์ วงศ์ไทย',
            'phone': '064-905-8213', 'detail': '33 ซอยสุขุมวิท 62 ตลาดใหม่',
            'province': 'ระยอง', 'district': 'เมืองระยอง',
            'subdistrict': 'ตลาดใหม่', 'zipcode': '21150',
        },
    },
    {
        'username': 'anon.d',
        'first_name': 'อนันต์', 'last_name': 'ดีเลิศ',
        'email': 'anon_deelert@yahoo.com', 'phone': '081-397-5062',
        'member_since': '2026-09-02',
        'address': {
            'label': 'บ้าน (หัวหิน)', 'receiver_name': 'อนันต์ ดีเลิศ',
            'phone': '081-397-5062', 'detail': '88 หมู่ 2 หัวหิน ต.หัวหิน',
            'province': 'กำแพงเพชร', 'district': 'เมืองกำแพงเพชร',
            'subdistrict': 'หัวหิน', 'zipcode': '62130',
        },
    },
]


# --------------------------------------------------------------------------
# ข้อมูลตัวอย่าง: ออเดอร์
# --------------------------------------------------------------------------
# (วันที่สั่งซื้อ, ลูกค้า, index สินค้า, วิธีชำระ, สถานะ)
#
# สถานะกับยอดต้องสอดคล้องเสมอ: ทุกใบที่ไม่ใช่ `pending` มี Payment ครบยอด
# เพราะขั้น `paid` ขึ้นอัตโนมัติเมื่อยอดแจ้งครบ — ถ้าใส่สถานะสูงแต่ไม่มี Payment
# รายได้ในแดชบอร์ด (อ่านจาก Payment) จะไม่ตรงกับหน้าออเดอร์ และอาจารย์เห็นตัวเลขขัดกัน
#
# ปกติแต่ละใบมี 1 ชิ้น เพื่อให้ยอดรวมอ่านง่าย มี 2 ใบที่จ่ายบางส่วนไว้สาธิต
ORDERS = [
    ('2026-07-14', 'pornchai.k', 10, 'bank', 'delivered'),
    ('2026-07-28', 'wichai.s', 1, 'promptpay', 'delivered'),
    ('2026-08-05', 'siriporn.t', 3, 'bank', 'delivered'),
    ('2026-08-19', 'wichai.s', 2, 'cod', 'shipped'),
    ('2026-09-02', 'kanyarat.w', 4, 'cod', 'delivered'),
    ('2026-09-16', 'nattapong.s', 5, 'bank', 'shipped'),
    ('2026-09-30', 'anon.d', 0, 'cod', 'shipped'),
    ('2026-10-06', 'siriporn.t', 7, 'promptpay', 'paid'),
    ('2026-10-11', 'pornchai.k', 6, 'cod', 'paid'),
    ('2026-10-13', 'wichai.s', 11, 'bank', 'pending'),
]

#: ออเดอร์ที่ลูกค้าจ่ายบางส่วน — ใบนี้ค้าง "รอชำระเงิน" เพราะยังขาดอยู่
#: ใช้สาธิตแถบ "จ่ายแล้ว / ขาดอีก" ในหน้าบัญชี และช่อง "แจ้งยอดโอนเอง"
PARTIAL_PAYMENT = {'2026-10-13': Decimal('900.00')}

PAYMENT_NOTES = {
    'cod': 'เก็บเงินปลายทาง — ผู้รับสินค้าชำระเมื่อได้รับของแล้ว',
}


# --------------------------------------------------------------------------
# ข้อมูลตัวอย่าง: การแจ้งปัญหา
# --------------------------------------------------------------------------
# (วันที่แจ้ง, วันที่สั่งซื้อที่เกี่ยวข้อง, ลูกค้า, สถานะ, ประเภท, หัวข้อ, รายละเอียด, ผล)
#
# ระบุ `วันที่สั่งซื้อ` ตรง ๆ แทนการเดาว่า "ออเดอร์ล่าสุดของลูกค้าคนนี้"
# เพราะการเดาให้ผิดเมื่อลูกค้ามีหลายใบ — เช่น เรื่อง "ส่งคีย์บอร์ดผิดรุ่น"
# ต้องผูกกับใบที่สั่งคีย์บอร์ด ไม่ใช่ใบที่สั่งล่าสุด
ISSUES = [
    ('2026-09-18', '2026-09-16', 'nattapong.s', 'resolved', 'late',
     'ขอเช็คสถานะการจัดส่ง',
     'สั่งไปสามวันแล้วยังไม่เห็นเลขพัสดุครับ อยากทราบว่าติดขัดตรงไหน',
     'ติดต่อไปร้านขนส่งแล้วครับ ของเข้าสู่ระบบเมื่อวาน คาดว่าถึงพรุ่งนี้'),
    ('2026-08-21', '2026-08-19', 'wichai.s', 'open', 'wrong_item',
     'ส่งคีย์แพดเกมมิงมาแทนคีย์บอร์ด',
     'สั่งคีย์บอร์ด Mechanical RGB แต่ในกล่องเป็นคีย์แพดเกมมิงครับ '
     'รบกวนเปลี่ยนให้ตรงรุ่นด้วยนะครับ', ''),
    ('2026-09-04', '2026-09-02', 'kanyarat.w', 'in_progress', 'damaged',
     'ฮับ USB-C ช่อง USB-A หลวม',
     'ใช้เสียบครั้งเดียวก็รู้ว่าช่อง USB-A หลวม ไม่แน่น '
     'ขอเปลี่ยนชิ้นใหม่ได้ไหมคะ', ''),
    ('2026-10-08', '2026-10-06', 'siriporn.t', 'open', 'payment',
     'โอนยอดเกินไป 100 บาท',
     'ผมโอนผิด โอนไป 1790 แต่ยอดจริง 1690 รบกวนคืนส่วนเกินครับ', ''),
]


class Command(BaseCommand):
    """เปลี่ยนข้อมูลทดสอบ → ข้อมูลตัวอย่างจริง (ปลอดภัยเมื่อรันซ้ำ)"""

    help = ('ลบข้อมูลทดสอบที่เหลือ (บัญชี probe / พนักงานทดสอบ / ออเดอร์สาธิต) '
            'แล้วใส่ข้อมูลตัวอย่างจริง 13 พนักงาน · 6 ลูกค้า · '
            '10 ออเดอร์ · 4 การแจ้งปัญหา')

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-junk', action='store_true',
            help='ไม่ลบข้อมูลทดสอบ ใส่เฉพาะข้อมูลตัวอย่าง (ใช้ตอนอยากเก็บของเดิมไว้)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='แสดงว่าจะลบ/สร้างอะไร โดยไม่เขียนลงฐานข้อมูล',
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        keep_junk = options['keep_junk']

        if dry_run:
            self.stdout.write(self.style.WARNING('โหมด DRY RUN — ไม่เขียนอะไรจริง'))

        with transaction.atomic():
            if not keep_junk:
                self._purge_junk(dry_run)
            customers = self._seed_customers(dry_run)
            self._seed_employees(dry_run)
            self._seed_orders(customers, dry_run)
            self._seed_issues(customers, dry_run)

            # ต้องเรียก **ภายใน** atomic — หลังออกจากบล็อกแล้ว flag จะไม่มีผล
            # และ Django จะโยน TransactionManagementError
            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            'ข้อมูลตัวอย่างพร้อม: พนักงาน {e} · ลูกค้า {c} · ออเดอร์ {o} · แจ้งปัญหา {i}'.format(
                e=len(EMPLOYEES), c=len(CUSTOMERS),
                o=len(ORDERS), i=len(ISSUES))))
        self.stdout.write(
            'บัญชีทดสอบสำหรับเข้าใช้: teacher/Shop2026! (staff) · ohm (ลูกค้าตัวอย่าง)')
        self.stdout.write(
            'ลูกค้าตัวอย่าง (รหัสผ่าน Demo2026!): ' +
            ', '.join(c['username'] for c in CUSTOMERS))
        self._warn_password_mismatch()

    # ------------------------------------------------------------------
    def _warn_password_mismatch(self):
        """เตือนเมื่อบัญชีลูกค้าตัวอย่างเข้าด้วยรหัสที่เอกสารบอกไม่ได้

        ทำไมต้องเตือน ไม่ใช่ตั้งรหัสใหม่ทับ
            คำสั่งนี้ตั้งรหัสให้เฉพาะบัญชีที่ "ยังไม่มีรหัส" โดยตั้งใจไม่ทับรหัส
            ที่คนไปเปลี่ยนเอง — ถ้าทับทุกครั้งที่รันคำสั่ง บัญชีจริงจะถูกปรับ
            กลับไปใช้รหัสตัวอย่างซ้ำ ๆ โดยไม่มีใครสังเกต

            แต่ผลคือ `DEMO.md` ยังบอกว่าเข้าด้วย `Demo2026!` ซึ่ง**ไม่จริง**
            สำหรับบัญชีที่เปลี่ยนรหัสไปแล้ว คนที่ทำตามเอกสารจะล็อกอินไม่ได้
            โดยไม่รู้ว่าเพราะอะไร → ต้องบอกให้ชัด ไม่ใช่ปล่อยให้เงียบ

            เจอกรณีนี้จริงแล้ว: บัญชีลูกค้าตัวอย่างทั้ง 6 รายเข้าไม่ได้
            ขณะที่เอกสารยังระบุรหัสว่าใช้ได้
        """
        from django.contrib.auth.models import User

        mismatched = []
        for spec in CUSTOMERS:
            user = User.objects.filter(username=spec['username']).first()
            if user and not user.check_password(DEMO_PASSWORD):
                mismatched.append(spec['username'])
        if not mismatched:
            return

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            f'⚠ บัญชีลูกค้าตัวอย่าง {len(mismatched)} รายการ '
            f'เข้าด้วยรหัสผ่าน "{DEMO_PASSWORD}" ไม่ได้: '
            + ', '.join(mismatched)))
        self.stdout.write(
            '  คำสั่งนี้จะไม่ทับรหัสที่ตั้งไว้ (เคยเปลี่ยนผ่านหน้าเว็บไว้)')
        self.stdout.write(
            '  ถ้าต้องการให้กลับมาเป็นรหัสตัวอย่าง ให้รันกับชื่อที่เจาะจงเท่านั้น:')
        self.stdout.write(
            '    python manage.py reset_demo_password ' +
            ' '.join(mismatched))

    # ------------------------------------------------------------------
    def _purge_junk(self, dry_run):
        """ลบเฉพาะข้อมูลทดสอบที่ระบุไว้ชัดเจน

        ไม่ใช้ pattern กวาด เช่น `username__contains='probe'`
        เพราะถ้าภายหลังมีบัญชีของคนจริงที่ชื่อคล้าย ๆ จะถูกลบไปเงียบ ๆ
        """
        from myapp.models import (ActivityLog, CustomerAddress,
                                  CustomerProfile, Employee, Order)

        # 1. พนักงานที่สร้างจากการกดทดสอบ (อีเมลเดียวกันหมด)
        emp = Employee.objects.filter(email=JUNK_EMPLOYEE_EMAIL)
        self._report(dry_run, 'พนักงานทดสอบ', emp,
                     lambda e: f'{e.emp_code} {e.name}')
        if not dry_run:
            emp.delete()

        # 2. บัญชีที่สร้างจากการรันเทสต์ — ตัด superuser ออกก่อนเสมอ
        junk_users = [u for u in JUNK_USERNAMES if u not in KEEP_USERS]
        users = User.objects.filter(username__in=junk_users)
        protected = [u.username for u in users if u.username in KEEP_USERS]
        if protected:
            self.stdout.write(self.style.ERROR(
                f'ข้ามผู้ใช้ที่อยู่ในรายการห้ามแตะ: {", ".join(protected)}'))
        self._report(dry_run, 'บัญชีทดสอบ', users, lambda u: u.username)
        if not dry_run:
            # โปรไฟล์/ที่อยู่เป็น CASCADE กับ user → หายไปเอง
            orphan_profiles = CustomerProfile.objects.filter(user__isnull=True)
            orphan_addresses = CustomerAddress.objects.filter(user__isnull=True)
            users.delete()
            orphan_profiles.delete()
            orphan_addresses.delete()

        # 3. ออเดอร์สาธิต (CASCADE ไปถึง Payment / OrderItem / OrderIssue)
        orders = Order.objects.filter(customer_name__in=JUNK_ORDER_NAMES)
        self._report(dry_run, 'ออเดอร์สาธิต', orders,
                     lambda o: f'#{o.id} {o.customer_name}')
        if not dry_run:
            orders.delete()

        # 4. ที่อยู่โปรไฟล์ของ ohm เพี้ยนจากการเขียนไฟล์ด้วย PowerShell
        #    (recipe #1) — ค่าที่เพี้ยนยังเป็น Unicode ที่ถูกต้อง
        #    แยกจากข้อความปกติด้วยกฎภาษาไทยไม่ได้ เพราะสระหน้าเกาะหน้าพยัญชนะ
        #    เป็นเรื่องปกติ ("ไร้สาย") จึงต้องกำหนดค่าที่ถูกต้องตรง ๆ
        #    ข้อดีคือพิมพ์บอกด้วยว่าเปลี่ยนอะไร ไม่แก้เงียบ ๆ
        ohm = User.objects.filter(username='ohm').first()
        if ohm:
            profile = getattr(ohm, 'customer_profile', None)
            if profile and profile.address != OHM_ADDRESS:
                self.stdout.write(
                    f'  · ปรับที่อยู่ในโปรไฟล์ของ ohm: '
                    f'{profile.address!r} → {OHM_ADDRESS!r}')
                if not dry_run:
                    profile.address = OHM_ADDRESS
                    profile.save(update_fields=['address'])

        # 5. Audit ที่อ้างถึงข้อมูลที่เพิ่งถูกลบ
        #    ข้อยกเว้นของหลัก append-only: คิว audit ที่ยังชี้ไปหา
        #    "ทดสอบ ระบบบันทึก" ทำให้อาจารย์เห็นว่างานยังไม่เสร็จ
        #    และอ้างถึงพนักงานที่ไม่มีอยู่แล้ว
        logs = ActivityLog.objects.filter(
            summary__contains='ทดสอบ ระบบบันทึก')
        self._report(dry_run, 'audit ที่อ้างพนักงานทดสอบ', logs,
                     lambda a: a.summary[:50])
        if not dry_run:
            logs.delete()

    def _report(self, dry_run, label, queryset, describe):
        count = queryset.count()
        if not count:
            return
        verb = 'จะลบ' if dry_run else 'ลบ'
        self.stdout.write(f'  {verb} {label} {count} รายการ:')
        for row in queryset[:8]:
            self.stdout.write(f'      - {describe(row)}')
        if count > 8:
            self.stdout.write(f'      ... และอีก {count - 8} รายการ')

    # ------------------------------------------------------------------
    def _seed_customers(self, dry_run):
        """สร้าง/อัปเดตบัญชีลูกค้า + โปรไฟล์ + ที่อยู่ในสมุด"""
        from myapp.models import CustomerAddress, CustomerProfile

        member, _ = Group.objects.get_or_create(name='Member')
        out = {}
        for spec in CUSTOMERS:
            user, created = User.objects.get_or_create(
                username=spec['username'],
                defaults={
                    'email': spec['email'],
                    'first_name': spec['first_name'],
                    'last_name': spec['last_name'],
                },
            )
            # เติมข้อมูลที่ขาด (บัญชีเก่าอาจมีค่าเหลือเพียง email อย่างเดียว)
            changed = []
            for field in ('email', 'first_name', 'last_name'):
                value = spec[field]
                if getattr(user, field) != value:
                    setattr(user, field, value)
                    changed.append(field)
            if _password_missing(user):
                user.set_password(DEMO_PASSWORD)
                changed.append('password')
            if changed and not dry_run:
                user.save(update_fields=changed)
            if not dry_run:
                user.groups.add(member)

            if not dry_run:
                profile, _ = CustomerProfile.objects.get_or_create(user=user)
                profile.phone = spec['phone']
                profile.address = (f"{spec['address']['detail']} "
                                   f"{spec['address']['subdistrict']} "
                                   f"{spec['address']['district']} "
                                   f"{spec['address']['province']} "
                                   f"{spec['address']['zipcode']}")
                profile.save(update_fields=['phone', 'address'])

                CustomerAddress.objects.update_or_create(
                    user=user, label=spec['address']['label'],
                    defaults={**spec['address'], 'is_default': True},
                )

            # วันที่สมัคร — ต้องอัปเดตหลังสร้าง เพราะเป็น auto_now_add
            joined = timezone.make_aware(
                datetime.combine(date.fromisoformat(spec['member_since']),
                                 time(10, 30)))
            if not dry_run:
                User.objects.filter(pk=user.pk).update(date_joined=joined)
            out[spec['username']] = user
        return out

    def _seed_employees(self, dry_run):
        from myapp.models import Employee

        for code, name, gender, dept, phone, salary, hire, status in EMPLOYEES:
            email = f'{code.lower()}@thammathadshop.com'
            Employee.objects.update_or_create(
                emp_code=code,
                defaults={
                    'name': name, 'gender': gender, 'department': dept,
                    'phone': phone, 'email': email,
                    'salary': Decimal(salary),
                    'hire_date': date.fromisoformat(hire),
                    'status': status, 'address': EMPLOYEE_ADDRESS,
                },
            )
            if dry_run:
                continue
            # created_at เป็น auto_now_add → ย้อนกลับให้ดูเหมือนบันทึกพร้อมกันตอนรับเข้าก่อน
            Employee.objects.filter(emp_code=code).update(
                created_at=timezone.make_aware(
                    datetime.combine(date.fromisoformat(hire), time(9, 0))))

    def _seed_orders(self, customers, dry_run):
        """สร้างออเดอร์พร้อม Payment และประวัติการเดินสถานะ

        **`created_at` เป็น `auto_now_add`** = Django ทับค่าที่ส่งเข้าไปเสมอ
        การย้อนวันที่จึงต้องทำด้วย `.update()` หลังสร้าง ไม่ใช่ส่งเข้าไปกับ
        `create()` — และนี่คือคีย์ idempotency ด้วย เพราะรอบถัดไปเราค้นหา
        ออเดอร์ด้วย `created_at` ที่ย้อนแล้ว ถ้าไม่ย้อนจริงจะหาไม่เจอ
        แล้วสร้างซ้ำทุกครั้งที่รัน
        """
        from myapp.models import Order, OrderItem, Payment, Product

        products = list(Product.objects.order_by('id'))
        need = max(row[2] for row in ORDERS) + 1
        if len(products) < need:
            raise SystemExit(
                f'ต้องมีสินค้าอย่างน้อย {need} ชิ้น แต่มี {len(products)} ชิ้น\n'
                '  → รัน `python manage.py seed_catalog` (สร้าง 12 ชิ้น) ก่อน')

        out = {}
        for day, username, product_idx, method, status in ORDERS:
            ordered = timezone.make_aware(
                datetime.combine(date.fromisoformat(day), time(13, 45)))
            if dry_run:
                continue

            order = Order.objects.filter(created_at=ordered).first()
            if order is None:
                user = customers[username]
                product = products[product_idx]
                address = user.addresses.first()
                order = Order.objects.create(
                    user=user, customer_name=user.get_full_name(),
                    phone=user.customer_profile.phone,
                    address=(f'{address.detail} {address.subdistrict} '
                             f'{address.district} {address.province} '
                             f'{address.zipcode}'),
                    total=product.price, payment_method=method,
                    status=status,
                )
                Order.objects.filter(pk=order.pk).update(created_at=ordered)
                order.refresh_from_db()

                OrderItem.objects.create(
                    order=order, product=product, quantity=1,
                    price=product.price)
                self._pay(order, method, status, day, ordered)
                for prev, step in _status_path(status):
                    self._log_status(order, prev, step, username)

            out[order.pk] = order
        return out

    def _pay(self, order, method, status, day, ordered):
        """สร้าง Payment ให้สอดคล้องกับสถานะ — สถานะสูงกว่า pending = จ่ายครบ

        ถ้าสร้างออเดอร์สถานะ paid ขึ้นแต่ไม่มี Payment ระบบจะขัดกับเอง
        เพราะรายได้ในแดชบอร์ดอ่านจาก Payment ไม่ใช่จาก status
        """
        from myapp.models import Payment

        if status == 'pending':
            amount = PARTIAL_PAYMENT.get(day)
            if not amount:
                return
        else:
            amount = order.total

        payment = Payment.objects.create(
            order=order, name=order.customer_name, phone=order.phone,
            amount=amount,
            transfer_date=date.fromisoformat(day),
            note=PAYMENT_NOTES.get(method, ''),
            created_at=ordered + timedelta(minutes=3),
        )
        Payment.objects.filter(pk=payment.pk).update(
            created_at=ordered + timedelta(minutes=3))

    def _log_status(self, order, prev, step, username):
        """เขียน audit ให้เหมือนมีคนเดินบันไดสถานะจริง

        ตั้งใจเขียนตรง ๆ ไม่ผ่าน `OrderStatusService` เพราะเราแค่ประกอบ
        ประวัติย้อนหลังของข้อมูลตัวอย่าง ไม่ได้เดินสถานะจริง
        (ถ้าเดินผ่าน service จะแตะ payment/stock ของออเดอร์จริงด้วย)
        """
        from myapp.models import ActivityLog

        ActivityLog.objects.create(
            actor_name=username, action='order_status',
            summary=f'ออเดอร์ #{order.id}: {prev} → {step}',
            target_type='order', target_id=str(order.id),
            before={'status': prev}, after={'status': step},
        )
        # created_at เป็น auto_now_add → ต้องย้อนด้วย .update()
        ActivityLog.objects.filter(
            target_type='order', target_id=str(order.id),
            summary=f'ออเดอร์ #{order.id}: {prev} → {step}',
        ).update(created_at=order.created_at + timedelta(hours=20))

    def _seed_issues(self, customers, dry_run):
        from myapp.models import Order, OrderIssue

        if dry_run:
            return
        for (day, order_day, username, status, kind, subject, detail,
             resolution) in ISSUES:
            user = customers[username]
            ordered = timezone.make_aware(
                datetime.combine(date.fromisoformat(order_day), time(13, 45)))
            order = Order.objects.filter(created_at=ordered).first()
            if order is None:
                self.stdout.write(self.style.WARNING(
                    f'  · ข้ามเรื่อง "{subject}" — ไม่พบออเดอร์วันที่ {order_day}'))
                continue
            issue, created = OrderIssue.objects.get_or_create(
                order=order, subject=subject,
                defaults={
                    'user': user,
                    'name': user.get_full_name(),
                    'phone': user.customer_profile.phone,
                    'kind': kind, 'detail': detail,
                },
            )
            # อัปเดตสถานะ/ผลทุกครั้ง ไม่งั้นรันซ้ำแล้วแก้โค้ดจะไม่มีผล
            if issue.status != status or issue.resolution != resolution:
                issue.mark(status, None, resolution)
            reported = timezone.make_aware(
                datetime.combine(date.fromisoformat(day), time(16, 20)))
            OrderIssue.objects.filter(pk=issue.pk).update(
                created_at=reported,
                resolved_at=(reported + timedelta(days=1) if resolution else None),
            )


def _status_path(final):
    """เส้นทางบันไดสถานะถึงสถานะสุดท้าย — ใช้เขียน audit ให้เป็นประวัติจริง"""
    ladder = ['pending', 'paid', 'shipped', 'delivered']
    labels = {
        'pending': 'รอชำระเงิน', 'paid': 'ชำระเงินแล้ว',
        'shipped': 'จัดส่งแล้ว', 'delivered': 'ได้รับสินค้าแล้ว',
    }
    end = ladder.index(final)
    return [(labels[ladder[i]], labels[ladder[i + 1]])
            for i in range(end)]