"""ข้อมูลตัวอย่างสำหรับโชว์ระบบให้อาจารย์ — ไม่ต้องใช้ API key ไม่ต้องโอนเงินจริง

ทำไมต้องมีคำสั่งนี้
    ฟีเจอร์ "แจ้งปัญหา" เป็นฟีเจอร์ที่**พิสูจน์ตัวเองไม่ได้** ถ้าคิวว่าง
    อาจารย์เปิด `/orders/issues/` เจอคำว่า "ไม่มีการแจ้งปัญหา" แล้วสรุปว่า
    "ระบบนี้ไม่ได้ทำงาน" ทั้งที่มันทำงาน — แค่ยังไม่มีใครใช้
    คำสั่งนี้จึงสร้างเรื่องที่ "ค้างอยู่" 1 เรื่อง + "แก้แล้ว" 1 เรื่อง
    ให้เห็นทั้งสองสถานะในหน้าเดียว และให้กดปิดเรื่องค้างสด ๆ ได้

หลักการเดียวกับ `seed_catalog`
    - **upsert ตามเงื่อนไขที่ชัดเจน** ไม่ใช่ `delete()` ทั้งตาราง
    - รันซ้ำกี่ครั้งก็ไม่ทำให้มีข้อมูลซ้ำ
    - **ไม่แตะ** `ohm` / พนักงาน / ออเดอร์ที่มีอยู่ — แค่สร้าง `OrderIssue`
      ที่ผูกกับออเดอร์ตัวอย่าง ถ้าออเดอร์ไม่มีจะสร้างให้เอง (ต้องมีสินค้าในระบบ)

คำสั่ง
    python manage.py seed_demo_issues
    python manage.py seed_demo_issues --quiet
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


#: เบอร์และชื่อของออเดอร์ตัวอย่างที่จะผูกปัญหาเข้าไป
DEMO_CUSTOMERS = [
    {
        'phone': '0812345678', 'name': 'ลูกค้า สาธิต',
        'issues': [
            {
                'kind': 'damaged',
                'subject': 'เมาส์ที่ได้รับชำรุดตรงปุ่มซ้าย',
                'detail': 'แกะออกจากกล่องแล้วเห็นว่าปุ่มซ้ายหลุดออกจากตัวเรื่อย '
                          'เปิดใช้งานไม่ได้ครับ รบกวนช่วยเปลี่ยนให้ด้วยครับ',
                'status': 'open',
            },
            {
                'kind': 'late',
                'subject': 'ขอเช็คสถานะการจัดส่ง',
                'detail': 'สั่งไปสามวันแล้วยังไม่เห็นเลขพัสดุครับ อยากทราบว่าติดขัดตรงไหน',
                'status': 'resolved',
                'resolution': 'ติดต่อไปร้านขนส่งแล้วครับ ของเข้าสู่ระบบเมื่อวาน '
                             'คาดว่าถึงพรุ่งนี้',
            },
        ],
    },
    {
        'phone': '0897654321', 'name': 'ลูกค้า ทดสอบ',
        'issues': [
            {
                'kind': 'payment',
                'subject': 'โอนยอดเกินไป 100 บาท',
                'detail': 'ผมโอนผิด โอนไป 1390 แต่ยอดจริง 1290 รบกวนคืนส่วนเกินครับ',
                'status': 'open',
            },
        ],
    },
]


class Command(BaseCommand):
    """สร้างการแจ้งปัญหาตัวอย่าง 3 เรื่อง (2 ค้าง / 1 แก้แล้ว)"""

    help = 'สร้างข้อมูลตัวอย่างสำหรับหน้า "การแจ้งปัญหา" (รันซ้ำได้ ไม่ลบข้อมูลอื่น)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--quiet', action='store_true',
            help='ไม่พิมพ์รายเรื่องทีละเรื่อง (พิมพ์สรุปอย่างเดียว)',
        )

    def handle(self, *args, **options):
        from myapp.models import Order, OrderIssue, OrderItem, Product

        if not Product.objects.exists():
            raise CommandError(
                'ยังไม่มีสินค้าในระบบ — รัน `python manage.py seed_catalog` ก่อน')

        quiet = options['quiet']
        created = skipped = 0

        with transaction.atomic():
            for customer in DEMO_CUSTOMERS:
                order = (Order.objects
                         .filter(phone=customer['phone'])
                         .order_by('-created_at')
                         .first())
                if order is None:
                    # ไม่มีออเดอร์ตัวอย่างของเบอร์นี้ — สร้างให้ 1 ใบ
                    # (ใช้สินค้าตัวแรกในระบบ เพื่อให้ปุ่ม "เปิดออเดอร์" ใช้ได้จริง)
                    product = Product.objects.order_by('id').first()
                    order = Order.objects.create(
                        customer_name=customer['name'],
                        phone=customer['phone'],
                        address='123 ถนนตัวอย่าง ต.เมือง จ.ราชบุรี',
                        total=product.price,
                        payment_method='bank',
                        status='shipped',
                    )
                    OrderItem.objects.create(
                        order=order, product=product, quantity=1,
                        price=product.price)

                for row in customer['issues']:
                    # เงื่อนไขเดียวกันทุกครั้ง → รันซ้ำไม่เกิดซ้ำ
                    _, was_created = OrderIssue.objects.get_or_create(
                        order=order,
                        subject=row['subject'],
                        defaults={
                            'name': customer['name'],
                            'phone': customer['phone'],
                            'kind': row['kind'],
                            'detail': row['detail'],
                            'status': row['status'],
                            'resolution': row.get('resolution', ''),
                            'resolved_at': (timezone.now()
                                            if row['status'] in ('resolved', 'closed')
                                            else None),
                        },
                    )
                    if was_created:
                        created += 1
                    else:
                        skipped += 1

        total = OrderIssue.objects.count()
        pending = OrderIssue.objects.open_ones().count()
        self.stdout.write(self.style.SUCCESS(
            'การแจ้งปัญหา: เพิ่มใหม่ {c} · มีอยู่แล้วข้าม {s} | ทั้งหมด {t} (ค้าง {p})'.format(
                c=created, s=skipped, t=total, p=pending)))
        if not quiet:
            for i in OrderIssue.objects.order_by('-created_at'):
                self.stdout.write(
                    '  #{pk:<3} {status:<22} {kind:<16} {subject}'.format(
                        pk=i.pk, status=i.get_status_display(),
                        kind=i.get_kind_display(), subject=i.subject))
        self.stdout.write('เปิดดูได้ที่ /orders/issues/ (ต้องล็อกอินเป็น staff)')