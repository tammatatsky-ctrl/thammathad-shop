"""โมเดล + QuerySet/Manager — Rich Domain Model ตามหลัก OOP ของระบบ.

สถาปัตยกรรม:
- Product / Order / OrderItem / Payment : ฝั่งขาย (หน้าร้าน + สายเงินของใบงาน)
- Employee                            : ฝั่ง HR (หลังบ้าน)
- CustomerProfile / CustomerAddress   : บัญชีลูกค้า + สมุดที่อยู่จัดส่ง
- ActivityLog                         : บันทึก "ใครทำอะไร" — ตรวจสอบย้อนหลังได้
- แต่ละโมเดลมี QuerySet + Manager ของตัวเอง → "คิวรีของโดเมนอยู่กับโดเมน": view เรียก
  Employee.objects.search(...), Order.objects.revenue() โดยไม่ต้องรู้ว่า filter ข้างในเป็นยังไง
"""
import re
from decimal import Decimal

from django.conf import settings as dj_settings
from django.db import models
from django.db.models import Count, F, Q, Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone


# ==================== QuerySets: Encapsulation — คิวรีของโดเมนอยู่กับโดเมน ====================

class EmployeeQuerySet(models.QuerySet):
    """คิวรีพนักงานทั้งหมด: ค้นหา กรอง เรียงลำดับ สถิติ"""

    SEARCH_FIELDS = ('emp_code', 'name', 'department', 'email', 'phone')
    SORT_MAP = {
        'newest': '-created_at',
        'name': 'name',
        'salary_desc': '-salary',
        'salary_asc': 'salary',
        'tenure': 'hire_date',  # อายุงานมากสุดก่อน (เริ่มงานนานสุด)
    }
    DEFAULT_SORT = '-created_at'

    def search(self, term):
        """ค้นหาหลายฟิลด์พร้อมกัน (รหัส/ชื่อ/แผนก/อีเมล/เบอร์) — icontains รวม Q.

        Args:
            term: สตริงค้นหา (ว่าง/None = คืนทั้งชุดไม่กรอง)

        Returns:
            EmployeeQuerySet (chain ต่อได้)
        """
        if not term:
            return self
        conditions = Q()
        for field in self.SEARCH_FIELDS:
            conditions |= Q(**{f'{field}__icontains': term})
        return self.filter(conditions)

    def of_department(self, department):
        """กรองแผนก (case-insensitive) — ค่าว่าง/None = คืนทั้งชุด.

        Args:
            department: ชื่อแผนกจาก dropdown (normalize ด้วย iexact)

        Returns:
            EmployeeQuerySet
        """
        return self.filter(department__iexact=department) if department else self

    def with_gender(self, gender):
        """กรองเพศเฉพาะ 'M'/'F'/'O' — ค่านอกเหนือ = ไม่กรอง.

        Args:
            gender: ตัวกรองจาก select บนหน้า

        Returns:
            EmployeeQuerySet
        """
        return self.filter(gender=gender) if gender in ('M', 'F', 'O') else self

    def with_status(self, status):
        """กรองสถานะ (active/leave/resigned) — block ค่ามั่วจาก URL.

        Args:
            status: เฉพาะค่าที่ whitelist ไว้ มิฉะนั้นข้ามการกรอง

        Returns:
            EmployeeQuerySet
        """
        return self.filter(status=status) if status in ('active', 'leave', 'resigned') else self

    def sorted_by(self, key=None):
        """เรียงตาม SORT_MAP (เฉพาะคีย์ที่จัดไว้) — คีย์ไม่รู้จัก = default.

        Args:
            key: 'newest'/'name'/'salary_desc'/'salary_asc'/'tenure' (None = default)

        Returns:
            EmployeeQuerySet
        """
        return self.order_by(self.SORT_MAP.get(key, self.DEFAULT_SORT))

    def active(self):
        """เฉพาะพนักงานที่ยังทำงานอยู่ (ใช้หน้า dashboard/กราฟ)."""
        return self.filter(status='active')

    def recent(self, limit=5):
        """พนักงานล่าสุด N คน (เรียง created_at ล่าสุดก่อน).

        Args:
            limit: จำนวนที่ต้องการ (default 5)

        Returns:
            EmployeeQuerySet
        """
        return self.order_by('-created_at')[:limit]

    def department_choices(self):
        """รายชื่อแผนกที่มีจริง เรียง A-Z (สำหรับ dropdown ตัวกรอง)"""
        return (
            self.exclude(department='')
            .order_by('department')
            .values_list('department', flat=True)
            .distinct()
        )

    def department_distribution(self, limit=6):
        """จำนวนพนักงานต่อแผนก (กราฟแดชบอร์ด)"""
        return (
            self.values('department')
            .annotate(n=Count('id'))
            .order_by('-n')[:limit]
        )

    def stats(self):
        """ตัวเลขสรุปพนักงานสำหรับแดชบอร์ด.

        Returns:
            dict {total, active, leave}
        """
        return {
            'total': self.count(),
            'active': self.filter(status='active').count(),
            'leave': self.filter(status='leave').count(),
        }


class EmployeeManager(models.Manager.from_queryset(EmployeeQuerySet)):
    """Manager พนักงาน: เพิ่มโรงงานผู้ช่วยระดับตาราง"""

    CODE_PATTERN = re.compile(r'^EMP(\d+)$', re.IGNORECASE)

    def next_code(self):
        """รันเลขรหัสพนักงานอัตโนมัติ — หาเลข EMP### สูงสุดแล้ว +1.

        เช่น เจอ EMP013 สูงสุด → คืน 'EMP014'. ใช้ตอนสร้างพนักงาน (Unique
        กันซ้ำ) — เลขอาจไม่ต่อเนื่องถ้าเคยลบเลขกลางคัน ซึ่งไม่ใช่ปัญหา.

        Returns:
            str รหัสใหม่ฟอร์แมต 3 หลัก เช่น 'EMP014'
        """
        max_num = 0
        for code in self.values_list('emp_code', flat=True):
            m = self.CODE_PATTERN.match((code or '').strip())
            if m:
                max_num = max(max_num, int(m.group(1)))
        return f"EMP{max_num + 1:03d}"


class ProductQuerySet(models.QuerySet):
    """คิวรีสินค้า: หน้าร้าน หลังบ้าน และสต็อก"""

    SORT_MAP = {
        'newest': '-id',
        'name': 'name',
        'price_desc': '-price',
        'price_asc': 'price',
        'stock_asc': 'stock',   # ใกล้หมดก่อน
    }
    DEFAULT_SORT = '-id'
    LOW_STOCK_THRESHOLD = 5

    def search(self, term):
        """ค้นหาชื่อ/รายละเอียดสินค้า (icontains) — ว่าง = คืนทั้งชุด.

        Args:
            term: ข้อความค้นหา

        Returns:
            ProductQuerySet
        """
        if not term:
            return self
        return self.filter(Q(name__icontains=term) | Q(description__icontains=term))

    def of_category(self, category):
        """กรองตามหมวดหมู่ (ค่าว่าง = ทุกหมวด)"""
        return self.filter(category__iexact=category) if category else self

    def category_choices(self):
        """หมวดหมู่ที่มีสินค้าจริง เรียง A-Z (สำหรับ filter pills หน้าร้าน)"""
        return (
            self.exclude(category='')
            .order_by('category')
            .values_list('category', flat=True)
            .distinct()
        )

    def related_to(self, product, limit=3):
        """สินค้าที่เกี่ยวข้อง: หมวดเดียวกันก่อน แล้วตัวอื่น ไม่รวมตัวเอง"""
        same = []
        if product.category:
            same = list(self.filter(category__iexact=product.category).exclude(id=product.id)[:limit])
        remaining = limit - len(same)
        if remaining <= 0:
            return same
        others = self.exclude(id=product.id)
        if product.category:
            others = others.exclude(category__iexact=product.category)
        return same + list(others[:remaining])

    def listed(self):
        """สินค้าที่หน้าร้านแสดง"""
        return self.filter(is_active=True)

    def visibility(self, state):
        """กรองสถานะการแสดง: 'active'/'hidden' — ค่าอื่น = ไม่กรอง.

        Args:
            state: ตัวกรองจาก select หลังบ้าน (จัดการสินค้า)

        Returns:
            ProductQuerySet
        """
        if state == 'active':
            return self.filter(is_active=True)
        if state == 'hidden':
            return self.filter(is_active=False)
        return self

    def stock_state(self, state):
        """กรองตามสต็อก: 'out' = หมด, 'in' = มีของ — ค่าอื่น = ไม่กรอง.

        Args:
            state: 'out'/'in' จาก select

        Returns:
            ProductQuerySet
        """
        if state == 'out':
            return self.filter(stock__lte=0)
        if state == 'in':
            return self.filter(stock__gt=0)
        return self

    def low_stock(self, threshold=None):
        """สินค้าใกล้หมด (≤ threshold) เรียงของน้อยสุดก่อน — เตือนสต็อก.

        Args:
            threshold: เกณฑ์ (default = LOW_STOCK_THRESHOLD = 5)

        Returns:
            ProductQuerySet
        """
        threshold = self.LOW_STOCK_THRESHOLD if threshold is None else threshold
        return self.filter(stock__lte=threshold).order_by('stock', 'name')

    def sorted_by(self, key=None):
        """เรียงตาม SORT_MAP ของสินค้า — คีย์ไม่รู้จัก = default ล่าสุดก่อน.

        Args:
            key: 'newest'/'name'/'price_desc'/'price_asc'/'stock_asc'

        Returns:
            ProductQuerySet
        """
        return self.order_by(self.SORT_MAP.get(key, self.DEFAULT_SORT))

    def recent(self, limit=5):
        """สินค้าใหม่ล่าสุด N ชิ้น (เรียง created_at ล่าสุดก่อน).

        Args:
            limit: จำนวนที่ต้องการ (default 5)

        Returns:
            ProductQuerySet
        """
        return self.order_by('-created_at')[:limit]

    def inventory_value(self):
        """มูลค่าสต็อกรวม (ราคา × จำนวน)"""
        return self.aggregate(v=Sum(F('price') * F('stock')))['v'] or 0

    def stats(self):
        """ตัวเลขสรุปสินค้าสำหรับแดชบอร์ด.

        Returns:
            dict {total, active, out}
        """
        return {
            'total': self.count(),
            'active': self.filter(is_active=True).count(),
            'out': self.filter(stock__lte=0).count(),
        }


ProductManager = models.Manager.from_queryset(ProductQuerySet)


class OrderQuerySet(models.QuerySet):
    """คิวรีออเดอร์: สายเงิน + สถานะ — ใช้หลังบ้านและหน้าแจ้งชำระ"""

    PAID_STATUSES_EXCLUDE = ('pending',)

    def recent(self, limit=5):
        """ออเดอร์ล่าสุด N ใบ (เรียง created_at ล่าสุดก่อน).

        Args:
            limit: จำนวนที่ต้องการ (default 5)

        Returns:
            OrderQuerySet
        """
        return self.order_by('-created_at')[:limit]

    def awaiting_action(self):
        """ออเดอร์ที่ยังไม่จบ (ยกเว้น delivered) — หน้าแจ้งชำระเงิน"""
        return self.exclude(status='delivered').order_by('-id')

    def revenue(self):
        """รายได้รวมเฉพาะออเดอร์ที่เกิน pending"""
        return (
            self.exclude(status='pending').aggregate(s=Sum('total'))['s']
            or 0
        )

    def stats(self):
        """ตัวเลขสรุปออเดอร์: จำนวนใบ/ค้างชำระ/ชำระแล้ว/รายได้ (ไม่นับ pending).

        Returns:
            dict {total, pending, paid, revenue}
        """
        return {
            'total': self.count(),
            'pending': self.filter(status='pending').count(),
            'paid': self.filter(status='paid').count(),
            'revenue': self.revenue(),
        }


OrderManager = models.Manager.from_queryset(OrderQuerySet)


# ==================== Models: Rich domain objects ====================

class Product(models.Model):
    """สินค้าในร้าน — แสดงหน้าร้าน + ใช้ในตะกร้า/ใบสั่งซื้อ.

    - is_active=False → ซ่อนจากหน้าร้าน (product_grid ยังใช้จัดการหลังบ้านได้)
    - image เก็บเป็น static path (images/...) ไม่ใช่ไฟล์อัปโหลด (ตั้งค่าใน static)
    """
    name = models.CharField(max_length=200, verbose_name="ชื่อสินค้า")
    category = models.CharField(max_length=60, blank=True, default='', verbose_name="หมวดหมู่")
    description = models.TextField(blank=True, verbose_name="รายละเอียด")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ราคา (บาท)")
    stock = models.IntegerField(default=0, verbose_name="จำนวนคงเหลือ")
    image = models.CharField(max_length=200, blank=True, default='images/prod1.jpg', verbose_name="ที่อยู่รูปภาพ (static)")
    model_3d = models.CharField(max_length=200, blank=True, default='', verbose_name="ที่อยู่โมเดล 3D (static)")
    is_active = models.BooleanField(default=True, verbose_name="แสดงสินค้า")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="วันที่เพิ่ม")

    objects = ProductManager()

    DEFAULT_IMAGE = 'images/prod1.jpg'

    def __str__(self):
        return self.name

    @property
    def stock_value(self):
        """มูลค่าสต็อกของสินค้าชิ้นนี้"""
        return self.price * self.stock

    @property
    def stock_status(self):
        """in = มีสินค้า, out = หมด"""
        return 'in' if self.stock > 0 else 'out'

    def apply_form_data(self, data, image_fallback=DEFAULT_IMAGE):
        """ผูกข้อมูลจากฟอร์ม manual (product_form.html เรนเดอร์ input เอง ไม่ได้ใช้ {{ form }})
        image_fallback: ค่าที่ใช้เมื่อฟอร์มไม่ส่งฟิลด์ image มา (create=default, edit=ค่าเดิม)"""
        self.name = data.get('name', '')
        self.category = data.get('category', '').strip()
        self.description = data.get('description', '')
        self.price = data.get('price', '')
        self.stock = data.get('stock', '')
        self.image = data['image'] if 'image' in data else image_fallback
        self.model_3d = data.get('model_3d', '').strip()
        self.is_active = data.get('is_active') == 'on'
        return self


class Order(models.Model):
    """ใบสั่งซื้อ — ตัวเดินเรื่อง "สายเงินและสถานะ" ของใบงาน.

    สถานะเป็นบันไดขั้นเดียว (pending → paid → shipped → delivered):
    - ขั้น 'paid' ขึ้นอัตโนมัติเมื่อจ่ายครบผ่าน PaymentService (เจ้าหน้าที่ตั้งไม่ได้)
    - ห้ามข้ามขั้น/ถอยหลัง (บังคับใน OrderStatusService.move)
    total = snapshot ยอดตอนสั่ง; reported_total = ยอดที่จ่ายสะสม →
    เอามาเทียบกันเพื่อบอก "จ่ายครบยัง" (จ่ายบางส่วนหลายครั้งได้).
    """
    PAYMENT_METHODS = [
        ('promptpay', 'พร้อมเพย์ / QR'),
        ('bank', 'โอนผ่านธนาคาร'),
        ('cod', 'เก็บเงินปลายทาง'),
    ]
    #: ป้าย `pending` เดิมคือ "รอดำเนินการ" ซึ่งหลอกทั้งสองฝั่ง —
    #:   ลูกค้าอ่านแล้วเข้าใจว่าร้านกำลังดำเนินการอยู่ (ทั้งที่รอเขาจ่ายเงิน)
    #:   เจ้าหน้าที่อ่านแล้วเข้าใจว่าต้องรอตรวจสอบอะไร (แต่ขั้น 'ชำระเงินแล้ว'
    #:   ขึ้นอัตโนมัติทันทีที่ยอดครบ จึงไม่มีอะไรให้ตรวจ)
    #: ความจริงคือ `pending` = ยังชำระไม่ครบ เพราะนั่นคือเงื่อนไขเดียวที่ทำให้ยัง pending
    STATUS_CHOICES = [
        ('pending', 'รอชำระเงิน'),
        ('paid', 'ชำระเงินแล้ว'),
        ('shipped', 'จัดส่งแล้ว'),
        ('delivered', 'ได้รับสินค้าแล้ว'),
    ]
    user = models.ForeignKey(
        dj_settings.AUTH_USER_MODEL, verbose_name='บัญชีผู้ซื้อ',
        null=True, blank=True, on_delete=models.SET_NULL, related_name='orders',
    )
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHODS, default='promptpay',
        verbose_name='วิธีชำระเงิน',
    )
    customer_name = models.CharField(max_length=100, verbose_name="ชื่อผู้สั่งซื้อ")
    phone = models.CharField(max_length=20, verbose_name="เบอร์โทรศัพท์")
    address = models.TextField(verbose_name="ที่อยู่จัดส่ง")
    total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ยอดรวม")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="สถานะ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="วันที่สั่งซื้อ")

    objects = OrderManager()

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"

    @property
    def reported_total(self):
        """ยอดที่ลูกค้าแจ้งโอนมาแล้ว (รวมทุกครั้ง — โอนแบ่งหลายครั้งก็นับรวม)

        เป็น **property** (ไม่ใช่ method) โดยตั้งใจ เพราะใช้ในเทมเพลตด้วย:
        `{{ order.reported_total }}` ถ้าเป็น method Django จะเรนเดอร์เป็น
        `<bound method ...>` และเงื่อนไข `{% if order.reported_total > 0 %}`
        จะได้ False ทุกครั้ง (เทียบ method กับตัวเลข = TypeError)
        → กล่อง "แจ้งมาแล้ว ฿... เหลืออีก ฿..." จะหายไปเฉย ๆ
        ในออเดอร์ที่จ่ายบางส่วน ซึ่งเป็นกรณีที่ลูกค้าต้องการข้อมูลนี้ที่สุด
        """
        return self.payments.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    @property
    def remaining(self):
        """ยอดที่ยังขาด (ยอดเต็ม − เงินที่แจ้งแล้ว) — ไม่ติดลบ"""
        return max(self.total - self.reported_total, Decimal('0'))

    @property
    def paid_percent(self):
        """ความคืบหน้าการชำระเป็นเปอร์เซ็นต์ (0–100) สำหรับแถบในหน้าลูกค้า

        ทำเป็น property แทน `{% widthratio %}` ในเทมเพลตเพราะ:
          - ออเดอร์ยอด 0 (ส่งฟรี/ใช้ส่วนลดเต็ม) แล้ว `widthratio` คืนค่าว่าง
            → `style="width: %"` = CSS พัง แถบกลายเป็นความกว้างแปลก ๆ
          - ชำระเกินยอดได้ (โอนเผลอเกิน) → ต้อง clamp ไว้ที่ 100 ไม่ให้ล้นแถบ
        """
        if not self.total:
            return 100
        return min(int(self.reported_total / self.total * 100), 100)


class OrderItem(models.Model):
    """แถวสินค้าในใบสั่งซื้อ — snapshot ราคา/ชิ้นตอนสั่ง (ไม่ผูกกับราคาสินค้าปัจจุบัน)."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1, verbose_name="จำนวน")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ราคาต่อชิ้น")

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    @property
    def line_total(self):
        """ยอดแถวนี้ = ราคาต่อชิ้น (snapshot) × จำนวน.

        Returns:
            Decimal
        """
        return self.price * self.quantity


class Payment(models.Model):
    """บิลยอดจ่ายแต่ละครั้งของออเดอร์ — สร้างผ่าน PaymentService.record_payment().

    ต่อออเดอร์หนึ่งใบได้หลายบิล (จ่ายบางส่วนหลายรอบ) → นับรวมเป็น reported_total
    เพื่อให้ระบบรู้ว่าเมื่อไรครบยอด แล้วค่อยยกสถานะเป็น paid อัตโนมัติ.
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    name = models.CharField(max_length=100, verbose_name="ชื่อผู้แจ้งชำระ")
    phone = models.CharField(max_length=20, verbose_name="เบอร์โทรศัพท์")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="ยอดโอน")
    transfer_date = models.DateField(verbose_name="วันที่โอนเงิน")
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="วันที่แจ้ง")

    def __str__(self):
        return f"Payment for Order #{self.order_id} - {self.amount} บาท"


class Employee(models.Model):
    """พนักงาน — โมเดลฝั่ง HR สำหรับหลังบ้าน.

    emp_code รันอัตโนมัติผ่าน Employee.objects.next_code() (ฟอร์แมต EMP###).
    avatar อัปโหลดได้ไปที่ media/employees/ — หน้าแสดงผลมี fallback หากไม่มีรูป.
    """
    GENDER_CHOICES = [
        ('M', 'ชาย'),
        ('F', 'หญิง'),
        ('O', 'อื่นๆ'),
    ]
    STATUS_CHOICES = [
        ('active', 'ทำงานอยู่'),
        ('leave', 'ลาพัก'),
        ('resigned', 'ลาออกแล้ว'),
    ]
    emp_code = models.CharField(max_length=20, unique=True, verbose_name="รหัสพนักงาน")
    name = models.CharField(max_length=150, verbose_name="ชื่อ-นามสกุล")
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='M', verbose_name="เพศ")
    department = models.CharField(max_length=100, verbose_name="แผนก")
    email = models.EmailField(blank=True, verbose_name="อีเมล")
    phone = models.CharField(max_length=25, blank=True, verbose_name="เบอร์โทรศัพท์")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active', verbose_name="สถานะ")
    salary = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="เงินเดือน (บาท)")
    hire_date = models.DateField(verbose_name="วันที่เริ่มงาน")
    address = models.TextField(blank=True, verbose_name="ที่อยู่")
    avatar = models.ImageField(upload_to='employees/', blank=True, null=True, verbose_name="รูปถ่ายพนักงาน")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="วันที่บันทึก")

    objects = EmployeeManager()

    def __str__(self):
        return f"{self.emp_code} - {self.name}"

    @property
    def years_of_service(self):
        """อายุงานเป็นจำนวนเต็มปี นับจากวันเริ่มงาน"""
        return (timezone.localdate() - self.hire_date).days // 365


class CustomerProfile(models.Model):
    """ข้อมูลจัดส่งของลูกค้าที่สมัครบัญชี — ใช้ prefill หน้า checkout ให้อัตโนมัติ"""
    user = models.OneToOneField(
        dj_settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='customer_profile', verbose_name='บัญชี',
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name='เบอร์โทรศัพท์')
    address = models.TextField(blank=True, verbose_name='ที่อยู่จัดส่ง')
    avatar = models.ImageField(
        upload_to='customers/avatars/', blank=True, null=True,
        verbose_name='รูปโปรไฟล์ (รองรับ GIF/PNG/JPG)',
    )
    cover = models.ImageField(
        upload_to='customers/covers/', blank=True, null=True,
        verbose_name='ภาพพื้นหลัง/หน้าปก (รองรับ GIF/PNG/JPG)',
    )

    class Meta:
        verbose_name = 'โปรไฟล์ลูกค้า'
        verbose_name_plural = 'โปรไฟล์ลูกค้า'

    def __str__(self):
        return f'Profile: {self.user.username}'


class CustomerAddress(models.Model):
    """สมุดที่อยู่จัดส่ง — 1 บัญชี เพิ่มได้หลายที่อยู่ (บ้าน/ที่ทำงาน/...)"""

    user = models.ForeignKey(
        dj_settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='addresses', verbose_name='เจ้าของ',
    )
    label = models.CharField(max_length=40, default='บ้าน', verbose_name='ชื่อที่อยู่')
    receiver_name = models.CharField(max_length=150, verbose_name='ชื่อผู้รับ')
    phone = models.CharField(max_length=20, verbose_name='เบอร์โทรศัพท์')
    detail = models.TextField(verbose_name='บ้านเลขที่/ซอย/ถนน')
    province = models.CharField(max_length=80, verbose_name='จังหวัด')
    district = models.CharField(max_length=80, verbose_name='อำเภอ/เขต')
    subdistrict = models.CharField(max_length=80, verbose_name='ตำบล/แขวง')
    zipcode = models.CharField(max_length=5, verbose_name='รหัสไปรษณีย์')
    is_default = models.BooleanField(default=False, verbose_name='ค่าเริ่มต้น')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'ที่อยู่จัดส่ง'
        verbose_name_plural = 'สมุดที่อยู่จัดส่ง'
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f'{self.label}: {self.receiver_name} ({self.province})'

    @property
    def full_address(self):
        """ที่อยู่บรรทัดเดียว — ใช้ snapshot ลง Order.address"""
        return (f'{self.detail} {self.subdistrict} {self.district} '
                f'{self.province} {self.zipcode}')


# ==================== ActivityLog: คำตอบ "ใครทำอะไร เมื่อไหร่" ====================
# เหตุผลที่ต้องมี: ระบบร้านมีการกระทำที่กระทบเงิน/ของจริง (เติมสต็อก เปลี่ยนสถานะ
# ออเดอร์ ยืนยันยอด ลบพนักงาน เปลี่ยนสิทธิ์บัญชี) ถ้าไม่มีบันทึก เมื่อมีปัญหา
# จะตอบคำถาม "ใครทำ?" ไม่ได้เลย — ซึ่งเป็นข้อร้องขาดของการตรวจงานทุกแบบ
#
# ออกแบบให้ "ใช้แรงน้อย": การเขียน log ต้องไม่ทำให้ผู้ใช้งานต้องคิดอะไรเพิ่ม
#   - `record()` เป็น no-op (ไม่เขียนอะไร) ถ้า settings.ACTIVITY_LOG_ENABLED = False
#     หรือถ้าเรียกนอก request (เช่น task/cron) ที่ไม่มี user → ไม่มี actor
#   - เก็บ before/after เป็น JSON สั้น ๆ เฉพาะฟิลด์ที่สำคัญ ไม่ dump ทั้งออบเจกต์
#   - ถ้าการเขียน log พัง ต้องไม่ทำให้ธุรกรรมหลักพังตาม (กันด้วย try/except)


class ActivityLogQuerySet(models.QuerySet):
    """คิวรีบันทึกการกระทำ: ค้นหา (ใคร/ทำอะไร/กับอะไร) + กรองตามประเภท"""

    SEARCH_FIELDS = ('actor__username', 'action', 'summary', 'target_label')
    SORT_MAP = {
        'newest': '-created_at',
        'oldest': 'created_at',
        'actor': 'actor__username',
        'action': 'action',
    }
    DEFAULT_SORT = '-created_at'

    def search(self, term):
        """ค้นหาจากผู้ทำ / ประเภทการกระทำ / คำอธิบาย / ชื่อสิ่งที่ถูกแก้

        Args:
            term: คำค้น (ว่าง = คืนทั้งหมด)

        Returns:
            ActivityLogQuerySet (chain ต่อได้)
        """
        if not term:
            return self
        term = term.strip()
        return self.filter(
            Q(actor__username__icontains=term)
            | Q(action__icontains=term)
            | Q(summary__icontains=term)
            | Q(target_label__icontains=term)
        )

    def sorted_by(self, key):
        """เรียงผลตามคีย์ที่กำหนด (ป้องกันคีย์แปลกปลอมจาก query string)

        Args:
            key: คีย์ใน SORT_MAP

        Returns:
            QuerySet
        """
        return self.order_by(self.SORT_MAP.get(key or '', self.DEFAULT_SORT))

    def for_target(self, obj_type, obj_id):
        """ดึงประวัติทั้งหมดของวัตถุหนึ่ง (ใช้แสดงในหน้ารายละเอียด)

        Args:
            obj_type: ชื่อโมเดล เช่น 'order'
            obj_id: pk ของวัตถุ

        Returns:
            QuerySet (เรียงใหม่สุดก่อน)
        """
        return self.filter(target_type=obj_type, target_id=str(obj_id)).order_by('-created_at')


class ActivityLog(models.Model):
    """บันทึกการกระทำสำคัญของเจ้าหน้าที่ — ตรวจสอบย้อนหลังได้

    ตัวอย่างที่บันทึก: เติม/ตัดสต็อก, เปลี่ยนสถานะออเดอร์, ยืนยันยอดชำระ,
    สร้าง/แก้/ลบพนักงาน, สร้าง/แก้/ลบสินค้า, เปลี่ยนบทบาทบัญชี staff,
    ล็อกบัญชีจากการเดารหัสผิดเกินโควตา
    """

    ACTION_CHOICES = [
        ('stock', 'ปรับสต็อก'),
        ('order_status', 'เปลี่ยนสถานะออเดอร์'),
        ('payment', 'รับเงิน / ยืนยันยอด'),
        ('employee', 'จัดการพนักงาน'),
        ('product', 'จัดการสินค้า'),
        ('role', 'เปลี่ยนสิทธิ์บัญชี'),
        ('security', 'ความปลอดภัย'),
        ('order', 'ออเดอร์'),
    ]

    actor = models.ForeignKey(
        dj_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='activity_logs',
        verbose_name='ผู้ทำ',
    )
    # เก็บชื่อผู้ใช้เป็นข้อความด้วย เผื่อบัญชีถูกลบทีหลัง (SET_NULL) ต้องยังรู้ว่าใคร
    actor_name = models.CharField(max_length=150, blank=True, verbose_name='ชื่อผู้ทำ (สำเนา)')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, db_index=True,
                              verbose_name='ประเภทการกระทำ')
    summary = models.CharField(max_length=300, verbose_name='คำอธิบาย')
    target_type = models.CharField(max_length=30, blank=True, db_index=True,
                                   verbose_name='ชนิดของสิ่งที่ถูกแก้')
    target_id = models.CharField(max_length=30, blank=True, verbose_name='รหัสสิ่งที่ถูกแก้')
    target_label = models.CharField(max_length=150, blank=True,
                                    verbose_name='ชื่อสิ่งที่ถูกแก้')
    before = models.JSONField(null=True, blank=True, verbose_name='ค่าเดิม')
    after = models.JSONField(null=True, blank=True, verbose_name='ค่าใหม่')
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP ผู้ทำ')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True,
                                      verbose_name='เวลาที่ทำ')

    objects = ActivityLogQuerySet.as_manager()

    class Meta:
        verbose_name = 'บันทึกการกระทำ'
        verbose_name_plural = 'บันทึกการกระทำ'
        ordering = ['-created_at']

    def __str__(self):
        who = self.actor_name or self.actor.username if self.actor_id else 'ระบบ'
        return f'[{self.get_action_display()}] {who}: {self.summary}'


class OrderIssueQuerySet(models.QuerySet):
    """ตัวช่วยอ่านรายการแจ้งปัญหา — คิวของเจ้าหน้าที่ + ประวัติของลูกค้าคนเดียว

    `search()` / `sorted_by()` ต้องมีครบ เพราะ `LiveSearchListView`
    เรียกใช้ตะไบนั้นทุกหน้า (ถ้าไม่มีจะ AttributeError ตอนเปิดหน้าเท่านั้น
    ไม่ใช่ตอนรันเทสต์ที่ไม่ได้แตะ)
    """

    #: คีย์เรียงที่อนุญาต — ป้องกันคีย์แปลกปลอมจาก query string
    SORT_MAP = {
        'newest': '-created_at',
        'oldest': 'created_at',
        'status': 'status',
    }
    DEFAULT_SORT = '-created_at'

    def open_ones(self):
        """เฉพาะที่ยังไม่ปิดการแจ้ง (กดจัดการก่อน)"""
        return self.exclude(status__in=['resolved', 'closed'])

    def for_customer(self, user):
        """รายการแจ้งปัญหาของลูกค้าคนนั้น (ใช้หน้าบัญชี)"""
        return self.filter(user=user)

    def for_order(self, order):
        """รายการแจ้งปัญหาที่ผูกกับออเดอร์หนึ่งใบ"""
        return self.filter(order=order)

    def search(self, term):
        """ค้นหาจากหัวข้อ / รายละเอียด / ชื่อผู้แจ้ง / เบอร์ / หมายเลขออเดอร์

        ค้นด้วยหมายเลขออเดอร์ด้วย เพราะเจ้าหน้าที่ที่รับเรื่องโทรศัพท์มา
        มีแต่เลขออเดอร์ในมือ ไม่ได้จำชื่อลูกค้า

        Args:
            term: คำค้น (ว่าง = คืนทั้งหมด)

        Returns:
            OrderIssueQuerySet (chain ต่อได้)
        """
        if not term:
            return self
        term = term.strip()
        # ค้นด้วยตัวเลขทั้งเลข: `0812345678` ในช่องค้นหาเข้าใจว่า "หาเบอร์"
        # ถ้า strip ทิ้งจะเหลือ "815345678" ซึ่งแมตช์ไม่พบเลย
        clauses = (Q(subject__icontains=term) | Q(detail__icontains=term)
                   | Q(name__icontains=term) | Q(phone__icontains=term))
        if term.isdigit():
            clauses |= (Q(order_id=term) | Q(phone__icontains=term.lstrip('0')))
        return self.filter(clauses)

    def sorted_by(self, key):
        """เรียงผลตามคีย์ที่กำหนด (ป้องกันคีย์แปลกปลอมจาก query string)

        Args:
            key: คีย์ใน SORT_MAP

        Returns:
            QuerySet
        """
        return self.order_by(self.SORT_MAP.get(key or '', self.DEFAULT_SORT))


class OrderIssue(models.Model):
    """การแจ้งปัญหาจากลูกค้า — ผูกกับออเดอร์ (ถ้ามี) เพื่อให้ตามรอยได้

    ทำไมต้องมี
        หน้า `/contact/` เดิมมีแต่ข้อมูลติดต่อ ไม่มีทางให้ลูกค้าแจ้งอะไรได้เลย
        พอมีปัญหาจริง (ของเสียหาย / ส่งผิด / ยอดชำระไม่ตรง) ลูกค้ามีทางเดียวคือ
        "ไม่รู้จะบอกใคร" และเจ้าหน้าที่ไม่มีคิวงานที่จะเห็น

        ผูกกับ `Order` เพื่อให้ตอบคำถามได้ว่า "เรื่องนี้เกี่ยวกับออเดอร์ไหน
        และแก้ไปแล้วหรือยัง" โดยไม่ต้องเดา

    หมายเหตุเรื่องสิทธิ์
        ลูกค้าแจ้งได้เฉพาะออเดอร์ของตัวเอง (เช็คใน view) — ไม่ใช่แค่เชื่อ `user`
        เพราะออเดอร์เก่าอาจเป็นของ guest ที่ยังไม่มีบัญชีผูกไว้
    """

    KIND_CHOICES = [
        ('damaged', 'ของเสียหาย / ชำรุด'),
        ('wrong_item', 'ส่งสินค้าผิดชิ้น'),
        ('missing', 'ของไม่ครบ / ไม่ได้รับ'),
        ('payment', 'ยอดชำระไม่ตรง'),
        ('late', 'ส่งล่าช้า'),
        ('other', 'เรื่องอื่น ๆ'),
    ]
    STATUS_CHOICES = [
        ('open', 'รอเจ้าหน้าที่ดำเนินการ'),
        ('in_progress', 'กำลังดำเนินการ'),
        ('resolved', 'แก้ไขแล้ว'),
        ('closed', 'ปิดเรื่อง'),
    ]

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='issues',
        null=True, blank=True, verbose_name='ออเดอร์ที่เกี่ยวข้อง',
    )
    user = models.ForeignKey(
        dj_settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='order_issues', null=True, blank=True,
        verbose_name='ผู้แจ้ง',
    )
    name = models.CharField(max_length=150, verbose_name='ชื่อผู้แจ้ง')
    phone = models.CharField(max_length=20, verbose_name='เบอร์โทรที่ติดต่อ')
    email = models.EmailField(blank=True, verbose_name='อีเมล (ถ้ามี)')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='other',
                            verbose_name='ประเภทปัญหา')
    subject = models.CharField(max_length=200, verbose_name='หัวข้อ')
    detail = models.TextField(verbose_name='รายละเอียด')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                              default='open', db_index=True, verbose_name='สถานะ')
    resolution = models.TextField(blank=True, verbose_name='ผลการดำเนินการ')
    handled_by = models.ForeignKey(
        dj_settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='handled_issues', null=True, blank=True,
        verbose_name='ผู้ดำเนินการ',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True,
                                      verbose_name='เวลาที่แจ้ง')
    resolved_at = models.DateTimeField(null=True, blank=True,
                                       verbose_name='เวลาที่แก้ไข')

    objects = OrderIssueQuerySet.as_manager()

    class Meta:
        verbose_name = 'การแจ้งปัญหา'
        verbose_name_plural = 'การแจ้งปัญหา'
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.get_kind_display()}] #{self.pk} {self.subject}'

    def mark(self, status, staff, resolution=''):
        """เจ้าหน้าที่อัปเดตสถานะ + บันทึกว่าใคร/เมื่อไรทำ

        Args:
            status: สถานะใหม่จาก STATUS_CHOICES
            staff: User ผู้ดำเนินการ
            resolution: ผลการดำเนินการ (บังคับเมื่อปิดเรื่อง)

        Returns:
            bool — True = อัปเดตสำเร็จ, False = ปฏิเสธพร้อมเหตุผล
        """
        if status not in dict(self.STATUS_CHOICES):
            return False
        if status in ('resolved', 'closed') and not (resolution or '').strip():
            # ปิดเรื่องโดยไม่บอกว่าทำอะไร = ลูกค้าต้องถามซ้ำ
            return False
        self.status = status
        self.handled_by = staff
        self.resolution = (resolution or self.resolution).strip()
        self.resolved_at = (timezone.now()
                            if status in ('resolved', 'closed') else None)
        self.save(update_fields=['status', 'handled_by', 'resolution',
                                 'resolved_at'])
        return True


# ==================== Signals: ล้างแคชแคตตาล็อกเมื่อสินค้าเปลี่ยน ====================

@receiver([post_save, post_delete], sender=Product)
def _invalidate_catalog_cache(sender, **kwargs):
    """ล้างแคชหมวดหมู่ของ Catalog ทุกครั้งที่สินค้าถูกสร้าง/แก้ไข/ลบ.

    ทำเป็น signal เพื่อครอบทุกทางที่ข้อมูลเปลี่ยน (หน้าจัดการสินค้า, Django admin,
    shell) โดยไม่ต้องพึ่งการเรียกใน view — import ในฟังก์ชันกัน circular import
    (services.py import models อยู่แล้ว).
    """
    from .services import Catalog
    Catalog.invalidate()
