"""ดึงข้อมูลโครงสร้างระบบจากโค้ดจริง เพื่อใช้สร้างเอกสารส่งอาจารย์

ทุกฟังก์ชันในไฟล์นี้อ่านจาก Django ตอนรัน ไม่มีตัวเลขตาย
ถ้าโค้ดเปลี่ยน เอกสารที่สร้างใหม่จะเปลี่ยนตามโดยอัตโนมัติ
"""

from dataclasses import dataclass, field
from typing import Any

from django.apps import apps
from django.db import models


# ---------------------------------------------------------------------------
# โครงสร้างข้อมูล
# ---------------------------------------------------------------------------
@dataclass
class FieldInfo:
    """คอลัมน์หนึ่งคอลัมน์ของตาราง พร้อมคำอธิบายภาษาไทยจาก `verbose_name`"""

    name: str
    kind: str          # ชนิดข้อมูลแบบอ่านง่าย เช่น 'ตัวเลขทศนิยม', 'ข้อความ'
    db_type: str       # ชนิดจริงในฐานข้อมูล เช่น 'decimal(10, 2)'
    nullable: bool
    primary_key: bool
    unique: bool
    is_fk: bool
    fk_target: str | None        # ชื่อ**คลาส**โมเดลที่อ้างถึง เช่น 'Order' (ใช้จับคู่วาด ER)
    verbose: str
    fk_label: str = ''           # ชื่อภาษาไทยของปลายทาง เช่น 'ออเดอร์'
    choices: list[tuple[str, str]] = field(default_factory=list)
    note: str = ''

    @property
    def short_type(self) -> str:
        """ชนิดย่อสำหรับวาดใน ER diagram เช่น `decimal(10, 2)` → `decimal`"""
        return self.db_type.split('(')[0].strip() if self.db_type else ''

    @property
    def flags(self) -> list[str]:
        """เครื่องหมายที่ต้องแสดงใน Data Dictionary"""
        out = []
        if self.primary_key:
            out.append('PK')
        if self.unique and not self.primary_key:
            out.append('UQ')
        if self.nullable:
            out.append('NULL')
        return out


#: ชื่อภาษาไทยของโมเดลที่มาจาก `django.contrib` — ค่า `verbose_name`
#: ของ Django เป็นภาษาอังกฤษ ("user") ซึ่งในเอกสารไทยอ่านสะดุด
FOREIGN_MODEL_LABELS = {
    'User': 'ผู้ใช้ (บัญชี)',
}


def _model_label(model: 'models.Model') -> str:
    """ชื่อโมเดลเป็นภาษาไทย สำหรับแสดงผลในเอกสาร"""
    return FOREIGN_MODEL_LABELS.get(
        model.__name__, str(model._meta.verbose_name))


#: แปลงชนิดฟิลด์ของ Django เป็นถ้อยคำที่คนอ่านรู้เรื่อง
KIND_LABELS = {
    models.AutoField: 'เลขจำนวนอัตโนมัติ',
    models.BigAutoField: 'เลขจำนวนอัตโนมัติ (ขนาดใหญ่)',
    models.CharField: 'ข้อความ',
    models.TextField: 'ข้อความยาว',
    models.EmailField: 'อีเมล',
    models.URLField: 'ลิงก์',
    models.IntegerField: 'จำนวนเต็ม',
    models.BigIntegerField: 'จำนวนเต็ม (ขนาดใหญ่)',
    models.PositiveIntegerField: 'จำนวนเต็มบวก',
    models.SmallIntegerField: 'จำนวนเต็มขนาดเล็ก',
    models.DecimalField: 'ทศนิยม',
    models.FloatField: 'ทศนิยม (ความละเอียดต่ำ)',
    models.BooleanField: 'ใช่/ไม่ใช่',
    models.DateField: 'วันที่',
    models.DateTimeField: 'วันและเวลา',
    models.TimeField: 'เวลา',
    models.DurationField: 'ระยะเวลา',
    models.ForeignKey: 'ความสัมพันธ์ (FK)',
    models.OneToOneField: 'ความสัมพันธ์ 1:1',
    models.ManyToManyField: 'ความสัมพันธ์หลายต่อหลาย',
    models.JSONField: 'ข้อมูล JSON',
    models.ImageField: 'ไฟล์รูปภาพ',
    models.FileField: 'ไฟล์',
    models.UUIDField: 'รหัส UUID',
    models.DurationField: 'ระยะเวลา',
    models.GenericIPAddressField: 'ที่อยู่ IP',
}


def _kind_label(field_obj: models.Field) -> str:
    for klass, label in KIND_LABELS.items():
        if isinstance(field_obj, klass):
            return label
    return type(field_obj).__name__


def _db_type(field_obj: models.Field) -> str:
    """ชนิดจริงในฐานข้อมูล เช่น `varchar(150)` `decimal(10, 2)`

    ต้องส่ง connection จริงเข้าไป — ถ้าใช้ `connection=None` จะได้ชนิดจาก
    `connection.ops` ที่คืนค่าว่าง แล้วตกไปใช้ชื่อคลาสแทน ซึ่งเขียนผิด
    เช่น ForeignKey แสดงเป็น "foreignkey" แทน "integer" ที่เก็บจริง
    """
    from django.db import connection

    try:
        return field_obj.db_type(connection) or ''
    except Exception:
        return ''


def _simple_db_type(field_obj: models.Field) -> str:
    """ชนิดย่อสำหรับวาดใน ER diagram (ตัดขนาดวงเล็บออก)

    ER diagram ที่เขียน `decimal(10, 2)` ยาวเท่า `varchar(150)` ทำให้กล่อง
    กว้างและอ่านยาก — ใช้แค่ชื่อชนิดพอ รายละเอียดขนาดอยู่ใน Data Dictionary
    """
    raw = _db_type(field_obj)
    if not raw:
        return ''
    return raw.split('(')[0].strip()


@dataclass
class ModelInfo:
    """ตารางหนึ่งตาราง พร้อมคอลัมน์และความสัมพันธ์"""

    name: str
    db_table: str
    verbose: str
    doc: str
    fields: list[FieldInfo]
    inbound: list[tuple[str, str]] = field(default_factory=list)

    @property
    def pk_name(self) -> str:
        return next((f.name for f in self.fields if f.primary_key), 'id')

    @property
    def fk_fields(self) -> list[FieldInfo]:
        return [f for f in self.fields if f.is_fk]


def _describe_model(model: models.Model) -> ModelInfo:
    fields: list[FieldInfo] = []
    for f in model._meta.concrete_fields:
        is_fk = isinstance(f, (models.ForeignKey, models.OneToOneField))
        fields.append(FieldInfo(
            name=f.name,
            kind=_kind_label(f),
            db_type=_db_type(f),
            nullable=bool(f.null),
            primary_key=bool(f.primary_key),
            unique=bool(f.unique),
            is_fk=is_fk,
            fk_target=(f.related_model.__name__
                       if is_fk and f.related_model else None),
            fk_label=(_model_label(f.related_model)
                      if is_fk and f.related_model else ''),
            verbose=str(f.verbose_name),
            choices=[(str(v), str(l)) for v, l in
                     getattr(f, 'choices', []) or []],
            note='',
        ))

    # ฟิลด์ที่คำนวณเป็น property (ไม่ใช่คอลัมน์) แต่มีค่าที่มีความหมายทางธุรกิจ
    for name in ('remaining', 'reported_total', 'paid_percent', 'line_total'):
        prop = getattr(model, name, None)
        if isinstance(prop, property):
            fields.append(FieldInfo(
                name=name,
                kind='ค่าที่คำนวณ (ไม่เก็บในฐานข้อมูล)',
                db_type='—',
                nullable=False, primary_key=False, unique=False,
                is_fk=False, fk_target=None, fk_label='',
                verbose='ค่าที่คำนวณในโค้ด',
                note='เป็น @property จึงไม่กินพื้นที่ในฐานข้อมูล',
            ))

    doc = (model.__doc__ or '').strip().splitlines()
    return ModelInfo(
        name=model.__name__,
        db_table=model._meta.db_table,
        verbose=_model_label(model),
        doc=doc[0] if doc else '',
        fields=fields,
    )


#: โมเดลที่เป็น "ตารางแนบ" ไม่ต้องขึ้น ER หลัก (ล้วน ๆ ที่เป็นผลลัพธ์ของออเดอร์)
def _model_info(label: str) -> ModelInfo:
    model = apps.get_model('myapp', label)
    info = _describe_model(model)
    # ความสัมพันธ์ที่ "ชี้มาหา" เรา (reverse FK)
    for other in apps.get_models():
        if other._meta.app_label != 'myapp' or other is model:
            continue
        for f in other._meta.concrete_fields:
            if (isinstance(f, models.ForeignKey)
                    and f.related_model is model):
                info.inbound.append(
                    (other.__name__, f'{other._meta.verbose_name} '
                                     f'({f.name})'))
    return info


#: ลำดับที่อยากให้ปรากฏใน ER — อ่านจากซ้ายไปขวาตามลำดับการใช้งาน
MODEL_ORDER = [
    'CustomerProfile', 'CustomerAddress', 'Order', 'OrderItem', 'Payment',
    'OrderIssue', 'Product', 'Employee', 'ActivityLog',
]


def models_report() -> list[ModelInfo]:
    """ข้อมูลทุกตารางของแอป myapp เรียงตาม `MODEL_ORDER`

    ตารางที่ไม่ได้อยู่ในรายการจะต่อท้ายอัตโนมัติ (กันตารางใหม่หลุดจากเอกสาร)
    """
    known = [m for m in MODEL_ORDER
             if apps.get_model('myapp', m, require_ready=False)]
    extra = sorted(
        m.__name__ for m in apps.get_app_config('myapp').get_models()
        if m.__name__ not in MODEL_ORDER
    )
    return [_model_info(name) for name in known + extra]


# ---------------------------------------------------------------------------
# เส้นทาง URL
# ---------------------------------------------------------------------------
@dataclass
class RouteInfo:
    """เส้นทางหนึ่งเส้นทางของเว็บ"""

    pattern: str
    name: str
    methods: str          # 'GET, POST' หรือ 'POST'
    view: str
    zone: str             # 'ลูกค้า' / 'หลังบ้าน' / 'ทั้งสองฝั่ง'

    @property
    def is_post_only(self) -> bool:
        return self.methods.strip() == 'POST'


def routes_report() -> list[RouteInfo]:
    """อ่านเส้นทางทั้งหมดจาก URLconf จริง

    วิธีนี้ได้ข้อมูลตรงกับที่ระบบใช้งานจริง 100% (ต่างจากการคัดลอกรายการ
    มาเขียนเองในเอกสาร ซึ่งเมื่อมีการเพิ่ม URL ใหม่จะเงียบ ๆ ไม่อัปเดต)
    """
    from django.urls import get_resolver

    rows: list[RouteInfo] = []
    seen: set[tuple[str, str]] = set()

    def walk(resolver, prefix=''):
        for entry in resolver.url_patterns:
            if hasattr(entry, 'url_patterns'):          # include()
                walk(entry, prefix + str(entry.pattern))
                continue
            full = prefix + str(entry.pattern)
            methods = getattr(entry.callback, 'allowed_methods', None)
            if methods:
                verbs = ','.join(sorted(m for m in methods if m != 'HEAD'))
            else:
                verbs = 'POST' if _looks_post_only(entry.callback) else 'GET'
            view = getattr(entry.callback, 'view_class', None)
            view_name = view.__name__ if view else entry.callback.__name__
            key = (full, verbs)
            if key in seen:
                continue
            seen.add(key)
            rows.append(RouteInfo(
                pattern=full, name=entry.name or '',
                methods=verbs, view=view_name,
                zone=_zone_of(view_name, full),
            ))

    walk(get_resolver())
    return rows


#: ชื่อ view ที่ขึ้นต้นด้วยคำนี้ถือว่าอยู่โซนหลังบ้าน
STAFF_PREFIXES = (
    'Employee', 'ProductManage', 'ProductCreate', 'ProductUpdate',
    'OrderManage', 'OrderStatus', 'OrderExport', 'OrderIssue',
    'CustomerList', 'CustomerDetail', 'Payment', 'PaymentManual',
    'PaymentVerify', 'QuickPay', 'Reports', 'Dashboard',
    'ActivityLog', 'RoleManage', 'RoleUpdate', 'StaffLogin', 'StaffLogout',
    'SlipVerify', 'SlipUpload',
)


def _looks_post_only(callback) -> bool:
    """เดาว่า view นี้รับเฉพาะ POST

    ดูจาก docstring/ชื่อไม่ได้แน่นอน 100% — ใช้เป็นข้อมูลประกอบเท่านั้น
    ถ้าสร้าง `get` ไม่ได้ แปลว่า POST-only (ซึ่งถูกต้องสำหรับ view
    ที่แก้ข้อมูล เช่น ลบพนักงาน)
    """
    cls = getattr(callback, 'view_class', None)
    return bool(cls) and not hasattr(cls, 'get')


def _zone_of(view_name: str, pattern: str) -> str:
    if any(view_name.startswith(p) for p in STAFF_PREFIXES):
        return 'หลังบ้าน'
    if pattern.startswith('staff') or pattern.startswith('api'):
        return 'หลังบ้าน'
    return 'ลูกค้า'


# ---------------------------------------------------------------------------
# ชั้นบริการ (services.py)
# ---------------------------------------------------------------------------
@dataclass
class ServiceInfo:
    """service หนึ่งตัวใน services.py"""

    name: str
    doc: str
    methods: list[str] = field(default_factory=list)
    docstrings: dict[str, str] = field(default_factory=dict)

    @property
    def public_methods(self) -> list[str]:
        """เมธอดสาธารณะที่ไม่ขึ้นต้นด้วย `_` (คือ API ที่ view เรียกใช้)"""
        return [m for m in self.methods if not m.startswith('_')]


def services_report() -> list[ServiceInfo]:
    """อ่านคลาสที่ประกาศใน `services.py` พร้อม docstring ของแต่ละตัว"""
    import inspect

    from myapp import services as services_module

    out: list[ServiceInfo] = []
    for name, obj in vars(services_module).items():
        if not inspect.isclass(obj) or obj.__module__ != services_module.__name__:
            continue
        doc_lines = (obj.__doc__ or '').strip().splitlines()
        methods, docs = [], {}
        for attr in dir(obj):
            if attr.startswith('__'):
                continue
            member = getattr(obj, attr, None)
            if callable(member) or isinstance(member, property):
                methods.append(attr)
                if isinstance(member, property):
                    docs[attr] = (member.fget.__doc__ or '').strip()
                else:
                    docs[attr] = (getattr(member, '__doc__', '') or '').strip()
        out.append(ServiceInfo(
            name=name,
            doc=doc_lines[0] if doc_lines else '',
            methods=methods,
            docstrings=docs,
        ))
    return sorted(out, key=lambda s: s.name)


# ---------------------------------------------------------------------------
# สถิติโปรเจกต์
# ---------------------------------------------------------------------------
def count_source_lines() -> dict[str, Any]:
    """นับบรรทัดโค้ดจริงของแต่ละไฟล์

    นับเฉพาะโค้ดที่รันจริง ไม่รวมไฟล์ว่างและไม่รวมบรรทัดว่าง
    เพื่อให้ตัวเลขที่ใส่ในเอกสารไม่เกินจริง
    """
    from pathlib import Path

    import myapp

    root = Path(myapp.__file__).parent
    groups = {
        'Python (โมเดล/วิว/เซอร์วิส)': [
            'models.py', 'views.py', 'services.py', 'urls.py',
            'serializers.py', 'api.py', 'forms.py',
        ],
        'Python (อื่น ๆ)': [
            'admin.py', 'context_processors.py', 'models_qs.py',
            'templatetags', 'management', 'migrations', 'tests',
        ],
        'เทมเพลต': ['templates'],
        'ไฟล์คงที่ (CSS/JS)': ['static/css', 'static/js'],
    }

    result: dict[str, Any] = {}
    for label, names in groups.items():
        total = files = 0
        for name in names:
            p = root / name
            if p.is_file() and p.suffix == '.py':
                files += 1
                total += _count_code_lines(p)
            elif p.is_dir():
                for f in p.rglob('*'):
                    if f.is_file() and f.suffix in ('.py', '.html', '.css',
                                                    '.js'):
                        files += 1
                        total += _count_code_lines(f)
        if files:
            result[label] = {'files': files, 'lines': total}
    return result


def _count_code_lines(path) -> int:
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        return 0
    return sum(1 for line in text.splitlines() if line.strip())


def count_tests() -> dict[str, int]:
    """นับไฟล์และจำนวนเทสต์ที่ Django จะ**รันจริง**

    ใช้ `unittest.TestLoader().discover()` ไม่ใช่นับ `def test_` ด้วย regex
    เพราะ regex นับเมธอดที่ประกาศไว้แต่ไม่ได้ถูกรัน (คลาสที่ไม่ได้สืบทอด
    `TestCase` หรือเมธอดที่ถูก override ทิ้ง) ทำให้ตัวเลขในเอกสารไม่ตรงกับ
    ที่แสดงตอนรัน `manage.py test` ซึ่งอาจารย์จะเทียบดู
    """
    from pathlib import Path

    import myapp

    tests_dir = Path(myapp.__file__).parent / 'tests'
    if not tests_dir.is_dir():
        return {'files': 0, 'cases': 0}

    import unittest

    suite = unittest.TestLoader().discover(
        str(tests_dir), top_level_dir=str(Path(myapp.__file__).parent))
    return {
        'files': len(list(tests_dir.glob('test_*.py'))),
        'cases': suite.countTestCases(),
    }


def security_checklist() -> list[tuple[str, str]]:
    """รายการมาตรการความปลอดภัยที่ระบบมี พร้อมที่มาของข้อมูล

    ดึงจาก `settings.py` จริงเท่าที่เป็นไปได้ เพื่อไม่ให้เอกสารอ้างสิ่งที่ไม่ได้ตั้ง
    """
    from django.conf import settings

    rows = [
        ('CSRF', 'เปิดใช้ CSRF protection ทุกฟอร์ม POST ผ่าน `{% csrf_token %}`',
         'django.middleware.csrf.CsrfViewMiddleware'),
        ('XSS', 'Escape ค่าจากฐานข้อมูลอัตโนมัติในเทมเพลต (ไม่ใช้ `|safe`)',
         'การ escape ของ Django template engine'),
        ('SQL Injection', 'ใช้ Django ORM ทั้งหมด ไม่มี SQL string เดิม',
         'django.db.models'),
        ('ดึงข้อมูลของคนอื่น', 'ช่องทางลูกค้าทุกจุดยืนยันด้วย "เลขออเดอร์ + เบอร์โทร"',
         'myapp/views.py — `_authed_order()`'),
        ('เดารหัสผ่าน', 'จำกัด 3 ชั้น (ต่อ IP / ต่อ IP+ชื่อ / ต่อบัญชี) พร้อมข้อความเดียวกัน',
         'myapp/services.py — `LoginThrottle`'),
        ('DEBUG', 'ไม่มีค่าเริ่มต้นเป็นเปิด — ถ้าลืมตั้ง env ระบบจะไม่ขึ้นพร้อมบอก',
         'myproject/settings.py — fail-closed'),
        ('SECRET_KEY', 'ไม่มีค่า default ฝังในโค้ด production ต้องตั้งเอง',
         'myproject/settings.py — fail-closed'),
        ('ALLOWED_HOSTS', 'ตรวจสอบใน preflight ว่าไม่มี `*`',
         'manage.py preflight'),
        ('ความปลอดภัยของข้อมูล', 'ปลอดภัยขณะพักการผลิตเปิดอัตโนมัติเมื่อ DEBUG ปิด',
         'SECURE_SSL_REDIRECT / HSTS / cookie flags'),
        ('สูตรแย่งใน CSV', 'escape เซลล์ที่ขึ้นต้นด้วย `= - + @`',
         'myapp/views.py — ฟังก์ชัน export'),
        ('อัปโหลดไฟล์', 'จำกัดขนาด + ตรวจชนิดไฟล์ + rate limit',
         'myapp/views.py — การอัปโหลดรูป/สลิป'),
    ]
    if settings.DEBUG:
        rows.append(('หมายเหตุ', 'ระบบรันอยู่ในโหมด DEBUG (ต้องปิดก่อนใช้งานจริง)', '—'))
    return rows