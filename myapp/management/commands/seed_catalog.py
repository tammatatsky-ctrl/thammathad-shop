"""คำสั่ง `manage.py seed_catalog` — เขียนชุดข้อมูลสินค้าตัวอย่างลงฐานข้อมูง

ทำไมต้องมี
    ข้อมูลสินค้าเดิมมี 3 ชิ้น และภาพไม่ตรงกับสินค้าที่ขายจริง
    (เมาส์ไร้สายเคยใช้รูปยางแก้ว, คีย์บอร์ดเคยใช้โมเดล 3D สุนัข)
    ตอนนี้เปลี่ยนมาใช้ภาพ SVG ชุดเดียวกันทั้ง 12 ชิ้น (ดู myapp/static/images)
    เพื่อให้หน้าร้านดูเป็นแบรนด์เดียวกัน ไม่มีภาพหลุดสไตล์

ความปลอดภัย
    - **upsert ตาม id คงที่** ไม่ลบอะไรทิ้ง → รันซ้ำกี่ครั้งผลเหมือนเดิม ไม่ทำข้อมูลเสีย
    - สินค้าที่สั่งซื้อไปแล้ว (มีออเดอร์ผูกอยู่) จะถูกอัปเดตราคา/ชื่อ/ภาพ
      แต่ **จำนวนใน OrderItem ที่เคยบันทึกไว้จะไม่ถูกแตะ** (เก็บราคาขายจริงไว้ตามหลักบัญชี)

หมวดหมู่
    `Product.category` เป็น CharField อิสระ ไม่ต้องแก้ migration
    หน้าร้านดึงหมวดจาก DISTINCT ของสินค้า (`Catalog.categories()`)
    และ signal post_save/post_delete ล้าง cache ให้อัตโนมัติ (ดู myapp/models.py)
"""

from django.core.management.base import BaseCommand
from django.db import transaction

# ชุดข้อมูลตัวอย่าง: 12 ชิ้น / 4 หมวด
# (ภาพทุกไฟล์เป็น SVG ชุดเดียวกัน — เปลี่ยนภาพต้องแก้ไฟล์ใน myapp/static/images ด้วย)
CATALOG = [
    # --- อุปกรณ์ต่อพ่วง ---
    {
        'id': 1, 'name': 'เมาส์ไร้สาย Glide', 'category': 'อุปกรณ์ต่อพ่วง',
        'price': 450, 'stock': 49, 'image': 'images/mouse.svg',
        'description': 'เมาส์ไร้สายน้ำหนักเบา เชื่อมต่อด้วย Bluetooth แบตเตอรี่ทนทาน',
    },
    {
        'id': 2, 'name': 'คีย์บอร์ด Mechanical RGB', 'category': 'อุปกรณ์ต่อพ่วง',
        'price': 1290, 'stock': 28, 'image': 'images/keyboard.svg',
        'description': 'คีย์บอร์ดพร้อมไฟ RGB สวิตช์ Blue กดแน่น พิมพ์งานมั่นสุด',
    },
    {
        'id': 3, 'name': 'คีย์แพดเกมมิง Wireless', 'category': 'อุปกรณ์ต่อพ่วง',
        'price': 2190, 'stock': 14, 'image': 'images/gamepad.svg',
        'description': 'คีย์แพดไร้สาย สติ๊กแม่นระดับเกม และปุ่มที่ปรับแรงกดได้',
    },
    {
        'id': 4, 'name': 'เมาส์เกมมิง 58g Honeycomb', 'category': 'อุปกรณ์ต่อพ่วง',
        'price': 1790, 'stock': 9, 'image': 'images/mouse-gaming.svg',
        'description': 'เมาส์เกมมิงน้ำหนักเบาเพียง 58 กรัม ตะแกรงระบายอากาศ สายถักในตัว',
    },
    {
        'id': 5, 'name': 'ฮับ USB-C 7-in-1', 'category': 'อุปกรณ์ต่อพ่วง',
        'price': 890, 'stock': 22, 'image': 'images/hub.svg',
        'description': 'ฮับขยายพอร์ตสำหรับแล็ปท็อปบาง มี HDMI สองช่อง USB และพอร์ตชาร์จ',
    },

    # --- เครื่องเสียง ---
    {
        'id': 6, 'name': 'หูฟังเกมมิ่ง 7.1', 'category': 'เครื่องเสียง',
        'price': 890, 'stock': 20, 'image': 'images/headset.svg',
        'description': 'หูฟังเกมมิ่งคุณภาพสูง ให้ระบบเสียงสมจริงรอบทิศทาง พร้อมไมโครโฟนตัดเสียงรบกวน',
    },
    {
        'id': 7, 'name': 'ลำโพง Bluetooth กำลัง 20W', 'category': 'เครื่องเสียง',
        'price': 1290, 'stock': 16, 'image': 'images/speaker.svg',
        'description': 'ลำโพงพกพาเสียงรอบทิศทาง กำลัง 20 วัตต์ แบตเตอรี่อยู่ได้ 12 ชั่วโมง',
    },
    {
        'id': 8, 'name': 'ไมโครโฟน USB สำหรับสตรีม', 'category': 'เครื่องเสียง',
        'price': 1690, 'stock': 11, 'image': 'images/microphone.svg',
        'description': 'ไมโครโฟนคอนเดนเซอร์ต่อ USB ตัดเสียงรบกวนได้ ปรับความไวตอนสตรีมได้',
    },

    # --- จอภาพ ---
    {
        'id': 9, 'name': 'จอมอนิเตอร์ 27" IPS 4K', 'category': 'จอภาพ',
        'price': 8990, 'stock': 6, 'image': 'images/monitor.svg',
        'description': 'จอ IPS ความละเอียด 4K ขอบบาง สีตรง เหมาะกับงานออกแบบและเล่นเกม',
    },
    {
        'id': 10, 'name': 'แขนตั้งจอโต๊ะปรับระดับได้', 'category': 'จอภาพ',
        'price': 1890, 'stock': 13, 'image': 'images/monitor-arm.svg',
        'description': 'แขนตั้งจอแบบหนีบโต๊ะ ปรับความสูงและระยะได้ คลิปแข็งแรง ไม่ต้องเจาะโต๊ะ',
    },

    # --- สายและอุปกรณ์ชาร์จ ---
    {
        'id': 11, 'name': 'สาย USB-C ถัก 100W 2 เมตร', 'category': 'สายและเครื่องชาร์จ',
        'price': 290, 'stock': 64, 'image': 'images/cable.svg',
        'description': 'สายถักทนทาน รองรับการจ่ายไฟ 100 วัตต์ ใช้ชาร์จและถ่ายโอนข้อมูลได้ในเส้นเดียว',
    },
    {
        'id': 12, 'name': 'พาวเวอร์แบงก์ 20000mAh 65W', 'category': 'สายและเครื่องชาร์จ',
        'price': 1490, 'stock': 25, 'image': 'images/powerbank.svg',
        'description': 'พาวเวอร์แบงก์จ่ายไฟได้ถึง 65 วัตต์ มีจอแสดงเปอร์เซ็นต์แบตและพอร์ต USB-C สองช่อง',
    },
]


class Command(BaseCommand):
    """เขียนชุดข้อมูลสินค้าตัวอย่าง — ปลอดภัยเมื่อรันซ้ำ (upsert ตาม id)"""

    help = 'เขียนชุดข้อมูลสินค้าตัวอย่าง 12 ชิ้น (4 หมวด) ลงฐานข้อมูล — รันซ้ำได้'

    def add_arguments(self, parser):
        parser.add_argument(
            '--quiet', action='store_true',
            help='ไม่พิมพ์รายการสินค้าทีละชิ้น (ทำงานเสร็จแล้วพิมพ์สรุปอย่างเดียว)',
        )

    def handle(self, *args, **options):
        from myapp.models import Product

        quiet = options['quiet']
        with transaction.atomic():
            for row in CATALOG:
                defaults = {k: v for k, v in row.items() if k != 'id'}
                Product.objects.update_or_create(id=row['id'], defaults=defaults)

        cats = ' · '.join(Product.objects.category_choices())
        self.stdout.write(self.style.SUCCESS(
            'เขียนสินค้า {n} ชิ้น | หมวด: {cats}'.format(
                n=Product.objects.count(), cats=cats)))
        if not quiet:
            for p in Product.objects.order_by('id'):
                self.stdout.write('  {id:>2}  {name:<32} {price:>9,.0f}  สต็อก {stock:>3}  {image}'.format(
                    id=p.id, name=p.name, price=p.price, stock=p.stock, image=p.image))