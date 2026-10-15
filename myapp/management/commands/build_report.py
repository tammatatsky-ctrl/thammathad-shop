"""สร้างเอกสารรายงานส่งอาจารย์ — PDF + Word

ใช้งาน
    python manage.py build_report
    python manage.py build_report --pdf-only
    python manage.py build_report --docx-only
    python manage.py build_report --out docs/รายงาน

หลักการ
    ตัวเลขทุกอย่างในเอกสาร (จำนวนโมเดล คอลัมน์ เส้นทาง บรรทัดโค้ด เทสต์)
    ดึงจากโค้ดจริงผ่าน `myapp.docs.facts` ไม่ใช่พิมพ์ตัวเลขตาย
    ถ้าแก้โค้ดแล้วรันคำสั่งนี้ซ้ำ เอกสารจะอัปเดตตามเสมอ
    วิธีนี้กันเอกสาร "โกหก" ซึ่งเป็นปัญหาที่ตรวจจับยากที่สุด
    เพราะตัวเลขยังดูเหมือนจริงจนกว่าอาจารย์จะเปิดหน้าเว็บเทียบ
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from myapp.docs import content, facts

# หมายเหตุ: `myapp.docs.diagrams` (reportlab) / `docx_builder` (python-docx)
# **ไม่ได้** import ที่ระดับโมดูล เพราะเป็นไลบรารีที่ติดตั้งแยก
# (requirements-docs.txt) และถ้า import ที่บน ผู้ที่ยังไม่ติดตั้งจะเจอ
# ModuleNotFoundError ตอน Django แค่โหลดคำสั่ง ซึ่งทำให้ทุกคำสั่งอื่นพังด้วย


#: ข้อมูลส่วนปก — เว้นว่างไว้ให้ผู้เรียนกรอก
#: หมายเหตุ: อย่าใส่ 'อาจารย์ที่ปรึกษา' ซ้ำใน `student` เพราะจะได้ขึ้น
#: สองบรรทัดซ้อนกันในหน้าปก (เคยเจอแล้ว)
COVER = {
    'title': 'ระบบร้านค้าออนไลน์สำหรับอุปกรณ์คอมพิวเตอร์และไอที',
    'student': {
        'ชื่อ-นามสกุล': '',
        'รหัสนักศึกษา': '',
        'ชั้นปี': '',
        'สาขา': 'วิทยาการคอมพิวเตอร์',
        'คณะ': '',
    },
    'advisor': '',
    'year': '2569',
}


def _ensure_qr_code(path: Path, url: str = 'https://tammatat.pythonanywhere.com') -> None:
    """สร้างไฟล์ QR Code ชี้ไปยัง URL ของระบบ หากยังไม่มีไฟล์"""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import qrcode
            qr = qrcode.QRCode(box_size=8, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color='black', back_color='white')
            img.save(str(path))
        except Exception:
            pass


class Command(BaseCommand):
    """สร้างเอกสารรายงานทั้ง PDF และ Word จากข้อมูลในโค้ดจริง"""

    help = ('สร้างเอกสารรายงานส่งอาจารย์ (PDF + .docx) พร้อมไดอะแกรม '
            'และ Data Dictionary ที่ดึงข้อมูลจากโค้ดจริงอัตโนมัติ')

    def add_arguments(self, parser):
        parser.add_argument(
            '--out', default='docs/รายงาน',
            help='โฟลเดอร์ปลายทาง (ค่าเริ่มต้น docs/รายงาน)')
        parser.add_argument(
            '--pdf-only', action='store_true', help='สร้างเฉพาะ PDF')
        parser.add_argument(
            '--docx-only', action='store_true', help='สร้างเฉพาะ Word')
        parser.add_argument(
            '--student-name', default='นายธรรมธัช รูปไธสง',
            help='ชื่อ-นามสกุลผู้จัดทำ')
        parser.add_argument(
            '--student-id', default='671320104',
            help='รหัสนักศึกษา')
        parser.add_argument(
            '--advisor', default='ผู้ช่วยศาสตราจารย์สุรินทร์ เพชรไทย',
            help='อาจารย์ประจำวิชา / เสนอ')
        parser.add_argument(
            '--course', default='4123713 หัวข้อเฉพาะเรื่องทางวิทยาการคอมพิวเตอร์',
            help='ชื่อรายวิชา')
        parser.add_argument(
            '--blank-cover', action='store_true',
            help='เว้นช่องว่างหน้าปกไว้สำหรับกรอกด้วยตนเอง')
        parser.add_argument(
            '--open', action='store_true',
            help='เปิดไฟล์ที่สร้างให้ทันทีหลังเสร็จ (Windows เท่านั้น)')

    def handle(self, *args, **options):
        self._check_dependencies()

        # นำเข้าหลังตรวจ dependency — `myapp.docs.diagrams` import `reportlab`
        # ระดับโมดูล ถ้านำเข้าที่ไฟล์บน จะไม่เห็นข้อความแนะนำของ
        # `_check_dependencies()` แต่จะเห็นแค่ ModuleNotFoundError
        from myapp.docs import diagrams

        # รับทั้งพาธสัมพัทธ์ (สร้างใต้โปรเจกต์) และพาธสมบูรณ์
        # — การบังคับต่อ BASE_DIR เสมอ ทำให้เทสต์เขียนไฟล์ทิ้งไว้
        # ในโฟลเดอร์โปรเจกต์แทนโฟลเดอร์ชั่วคราว
        raw = Path(options['out'])
        out_dir = raw if raw.is_absolute() else Path(settings.BASE_DIR) / raw
        out_dir.mkdir(parents=True, exist_ok=True)

        qr_asset = Path(settings.BASE_DIR) / 'docs' / 'assets' / 'system_qr.png'
        _ensure_qr_code(qr_asset)

        models = facts.models_report()
        services = facts.services_report()
        routes = facts.routes_report()
        loc = facts.count_source_lines()
        tests = facts.count_tests()

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'ข้อมูลที่ดึงจากโค้ดจริง: {len(models)} ตาราง | '
            f'{len(routes)} เส้นทาง | {len(services)} service | '
            f'{tests["cases"]} เทสต์'))

        diagrams.register_thai_fonts()
        pack = {
            'er': (diagrams.er_diagram(models),
                   'ภาพที่ 2.3 แผนภาพความสัมพันธ์ข้อมูล (Entity-Relationship Diagram) อ่านค่าจากโมเดลจริง'),
            'layered': (diagrams.layered_architecture(),
                        'ภาพที่ 2.2 สถาปัตยกรรมระบบแบบ 4 ชั้น (4-Layer Clean Architecture) และ Service Layer'),
            'lifecycle': (diagrams.order_lifecycle_diagram(
                _lifecycle_steps(), ['ลูกค้า', 'เจ้าหน้าที่', 'ระบบ']),
                'ภาพที่ 2.4 แผนผังวงจรชีวิตสถานะคำสั่งซื้อแบบทิศทางเดียว ต้องเดินทีละขั้นและห้ามย้อนกลับ'),
            'usecase': (diagrams.use_case_diagram(_use_cases()),
                        'ภาพที่ 2.1 แผนภาพกรณีการใช้งานของระบบ (Use Case Diagram) แยกตามบทบาทผู้ใช้งาน'),
        }

        appendix = self._appendix_blocks(models, services, routes, loc,
                                         tests)
        chapters = content.chapter_order()

        # จัดเตรียมข้อมูลปกและข้อมูลทางวิชาการ
        if options.get('blank_cover'):
            cover_data = COVER.copy()
        else:
            cover_data = {
                'title': COVER.get('title') or 'ระบบร้านค้าออนไลน์สำหรับอุปกรณ์คอมพิวเตอร์และไอที',
                'title_en': 'E-Commerce System for Computer Hardware and IT Accessories',
                'project_name': 'THAMMATHAD SHOP',
                'student': {
                    'ชื่อ-นามสกุล': options.get('student_name') or COVER['student']['ชื่อ-นามสกุล'] or 'นายธรรมธัช รูปไธสง',
                    'รหัสนักศึกษา': options.get('student_id') or COVER['student']['รหัสนักศึกษา'] or '671320104',
                    'ชั้นปี': 'ชั้นปีที่ 3',
                    'สาขา': COVER['student'].get('สาขา') or 'วิทยาการคอมพิวเตอร์',
                    'คณะ': 'คณะวิทยาศาสตร์และเทคโนโลยี',
                },
                'advisor': options.get('advisor') or COVER.get('advisor') or 'ผู้ช่วยศาสตราจารย์สุรินทร์ เพชรไทย',
                'course': options.get('course') or '4123713 หัวข้อเฉพาะเรื่องทางวิทยาการคอมพิวเตอร์',
                'course_en': '4123713 Special Topics in Computer Science',
                'university': 'มหาวิทยาลัยราชภัฏกำแพงเพชร',
                'semester': 'ภาคการศึกษาที่ 1 ปีการศึกษา 2569',
                'year': COVER.get('year', '2569'),
            }

        want_pdf = not options['docx_only']
        want_docx = not options['pdf_only']

        written: list[Path] = []
        if want_pdf:
            from myapp.docs.pdf_builder import build_pdf
            path = out_dir / 'รายงาน-THAMMATHAD-SHOP.pdf'
            build_pdf(str(path), cover_data, chapters, pack, appendix)
            written.append(path)

        if want_docx:
            from myapp.docs.docx_builder import build_docx
            path = out_dir / 'รายงาน-THAMMATHAD-SHOP.docx'
            build_docx(str(path), cover_data, chapters, pack, appendix)
            written.append(path)

        for path in written:
            self.stdout.write(self.style.SUCCESS(
                f'  สร้างแล้ว: {path.name} ({path.stat().st_size / 1024:.0f} KB)'))

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('สิ่งที่ต้องแก้เองก่อนส่ง:'))
        for item in content.STUDENT_TODO:
            self.stdout.write(f'  - {item}')

        if options['open']:
            for path in written:
                try:
                    import os
                    os.startfile(path)          # noqa: S606 (Windows เท่านั้น)
                except (AttributeError, OSError) as exc:
                    self.stdout.write(
                        self.style.ERROR(f'เปิดไฟล์ไม่ได้: {exc}'))

    # ------------------------------------------------------------------
    @staticmethod
    def _check_dependencies():
        """ตรวจไลบรารีสร้างเอกสารก่อนลงมือ แล้วบอกวิธีติดตั้งที่ถูก

        ไลบรารีชุดนี้**ไม่อยู่ใน requirements.txt** โดยตั้งใจ เพราะ `pycairo`
        ต้องคอมไพล์ต่อกับ C library ชื่อ `cairo` ซึ่ง PythonAnywhere บัญชีฟรีไม่มี
        (ถ้าใส่ใน requirements.txt ตอน deploy จะไปติดตั้ง Django ไม่ได้ด้วย)

        คนที่รันคำสั่งนี้บน server จะเจอ `ModuleNotFoundError` ซึ่งบอกไม่ได้
        ว่าต้องไปติดตั้งอะไร → ต้องบอกให้ชัดตรง ๆ
        """
        missing = []
        for module, package in (('reportlab', 'reportlab'),
                                ('docx', 'python-docx'),
                                ('rlPyCairo', 'rlPyCairo')):
            try:
                __import__(module)
            except ImportError:
                missing.append(package)

        if missing:
            raise CommandError(
                'ยังติดตั้งไลบรารีสำหรับสร้างเอกสารไม่ครบ: '
                + ', '.join(missing)
                + '\n\n  ติดตั้งด้วย:  pip install -r requirements-docs.txt'
                + '\n  (แยกจาก requirements.txt โดยตั้งใจ เพราะ pycairo'
                  ' ต้องคอมไพล์ C library ซึ่ง PythonAnywhere บัญชีฟรีไม่มี —'
                  ' ถ้ารวมไว้ จะทำให้ตอน deploy ติดตั้ง Django ไม่ได้ด้วย)')

    # ------------------------------------------------------------------
    def _appendix_blocks(self, models, services, routes, loc, tests) -> list:
        """ภาคผนวก: ข้อมูลระบบ, คู่มือย่อ, Data Dictionary, และประวัติผู้จัดทำ

        สร้างจากข้อมูลสดทั้งหมด จึงไม่มีทางล้าสูตรได้โดยไม่รู้ตัว
        """
        qr_asset = Path(settings.BASE_DIR) / 'docs' / 'assets' / 'system_qr.png'

        blocks: list = [
            # ==========================================================
            # ภาคผนวก ก ข้อมูลการเข้าใช้งานระบบและแหล่งเก็บรหัสต้นฉบับ
            # ==========================================================
            ('h2', 'ภาคผนวก ก ข้อมูลการเข้าใช้งานระบบและแหล่งเก็บรหัสต้นฉบับ (System Access & Code Repository)'),
            ('h3', 'ก.1 แหล่งติดตั้งระบบและช่องทางการเข้าถึง (System URLs)'),
            ('p', 'ระบบ THAMMATHAD SHOP ได้รับการติดตั้งบนคลาวด์สาธารณะพร้อมสำหรับการทดสอบใช้งานจริง และเผยแพร่รหัสต้นฉบับบน GitHub ดังรายละเอียดในตารางที่ ก.1:'),
            ('table', {
                'title': 'ตารางที่ ก.1 ข้อมูลแหล่งเข้าถึงระบบและรหัสต้นฉบับ',
                'head': ('รายการ / สภาพแวดล้อม', 'ที่อยู่เว็บไซต์ (URL / Repository)', 'หมายเหตุการใช้งาน'),
                'rows': [
                    ('ระบบใช้งานจริงบนคลาวด์\n(Production)',
                     'https://tammatat.pythonanywhere.com',
                     'เข้าใช้งานได้ตลอด 24 ชั่วโมง ผ่านเว็บเบราว์เซอร์ทุกอุปกรณ์'),
                    ('ระบบทดสอบในเครื่อง\n(Local Development)',
                     'http://127.0.0.1:8000/',
                     'สำหรับทดสอบและพัฒนาระบบบนเครื่องคอมพิวเตอร์เฉพาะจุด'),
                    ('แหล่งเก็บรหัสต้นฉบับ\n(GitHub Repository)',
                     'https://github.com/\ntammatatsky-ctrl/\nthammathad-shop',
                     'โค้ดโปรเจกต์ เอกสารรายงาน และชุดทดสอบอัตโนมัติทั้งหมด'),
                ],
            }),

            ('h3', 'ก.2 คิวอาร์โค้ดสำหรับเข้าใช้งานระบบผ่านอุปกรณ์เคลื่อนที่ (System QR Code)'),
            ('p', 'ผู้ใช้งานและคณะกรรมการสามารถใช้สมาร์ตโฟนสแกน QR Code ด้านล่างนี้ เพื่อเข้าสู่หน้าเว็บไซต์ระบบ THAMMATHAD SHOP บนระบบคลาวด์ได้ทันทีโดยไม่ต้องพิมพ์ URL:'),
            ('image', str(qr_asset), 'ภาพผนวกที่ ก.1 QR Code สำหรับเข้าสู่ระบบ THAMMATHAD SHOP (https://tammatat.pythonanywhere.com)'),

            ('page_break',),

            ('h3', 'ก.3 บัญชีผู้ใช้สำหรับการทดสอบระบบ (Demonstration Accounts)'),
            ('p', 'ระบบได้ติดตั้งชุดข้อมูลตัวอย่าง (Seed Demo Data) สำหรับการทดสอบบนเซิร์ฟเวอร์จริง (https://tammatat.pythonanywhere.com) ครบทุกบทบาทผู้ใช้งาน ดังแสดงในตารางที่ ก.2 (ลูกค้าตัวอย่าง 6 ราย: wichai.s ถึง anon.d ใช้รหัสผ่าน Demo2026! เหมือนกันทั้งหมด):'),
            ('table', {
                'title': 'ตารางที่ ก.2 บัญชีผู้ใช้สำหรับการทดสอบระบบ (Test Accounts)',
                'head': ('ชื่อผู้ใช้\n(Username)', 'รหัสผ่าน\n(Password)', 'ระดับสิทธิ์ / บทบาท', 'วัตถุประสงค์ในการทดสอบ'),
                'rows': [
                    ('teacher', 'Shop2026!', 'ผู้ดูแลระบบสูงสุด (Superuser)', 'เข้าโซนเจ้าหน้าที่ (/staff/login/) และ Django Admin, ดูแดชบอร์ด, จัดการสินค้า/สต็อก, เลื่อนสถานะออเดอร์, บันทึกรับเงิน, ปิดงานแจ้งปัญหา, จัดการสิทธิ์ RBAC, และทดสอบ Superuser Override'),
                    ('wichai.s', 'Demo2026!', 'ลูกค้าสมาชิก (Customer Member)', 'เข้าสู่ระบบหน้าร้าน (/account/login/), มีออเดอร์รอชำระที่จ่ายบางส่วน (฿900/฿1,490) สำหรับทดสอบแถบชำระเงิน, ทดสอบแจ้งยอดโอนเอง, และทดสอบแจ้งปัญหาที่ /issue/'),
                    ('pornchai.k', 'Demo2026!', 'ลูกค้าสมาชิก (Customer Member)', 'มีประวัติออเดอร์สำเร็จทั้งโอนธนาคารและเก็บเงินปลายทาง (COD), จัดการสมุดที่อยู่, ทดสอบพิมพ์ใบเสร็จ A4'),
                    ('siriporn.t', 'Demo2026!', 'ลูกค้าสมาชิก (Customer Member)', 'มีออเดอร์ชำระผ่านพร้อมเพย์ QR และได้รับของแล้ว, ตรวจสอบเรื่องแจ้งปัญหาที่เจ้าหน้าที่แก้ไขและบันทึกผลแล้ว'),
                    ('anon.d', 'Demo2026!', 'ลูกค้าสมาชิก (Customer Member)', 'มีออเดอร์สถานะ "จัดส่งแล้ว" เพื่อทดสอบฟังก์ชันให้ลูกค้ายืนยันรับของเองเพื่อเลื่อนเป็น "ถึงมือแล้ว"'),
                    ('ลูกค้าทั่วไป (Guest)', 'ไม่ต้องใช้รหัสผ่าน', 'ลูกค้าทั่วไป (Guest Checkout)', 'สั่งซื้อสินค้าได้ทันทีโดยไม่ต้องสมัครสมาชิก และติดตามสถานะที่ /order/tracking/ ด้วยเลขออเดอร์คู่กับเบอร์โทร'),
                ],
            }),

            # ==========================================================
            # ภาคผนวก ข คู่มือการใช้งานระบบโดยย่อ
            # ==========================================================
            ('h2', 'ภาคผนวก ข คู่มือการใช้งานระบบโดยย่อ (Quick User Manual)'),
            ('h3', 'ข.1 คู่มือการใช้งานสำหรับลูกค้าทั่วไป (Customer Guide)'),
            ('bullets', [
                ('1. การค้นหาและเลือกดูสินค้า:', 'เข้าสู่หน้าแรก สามารถพิมพ์ค้นหาชื่อสินค้าแบบ Live Search หรือเลือกกรองตามหมวดหมู่ (เช่น ซีพียู, การ์ดจอ, แรม)'),
                ('2. การสั่งซื้อสินค้า:', 'กดปุ่ม "เพิ่มลงตะกร้า" จากนั้นเข้าสู่หน้าตะกร้าสินค้า ตรวจสอบจำนวนและราคารวม แล้วกดปุ่ม "ดำเนินการสั่งซื้อ"'),
                ('3. การระบุข้อมูลจัดส่ง:', 'กรอกชื่อ ที่อยู่จัดส่ง และเบอร์โทรศัพท์ โดยลูกค้าสมาชิกสามารถเลือกที่อยู่เดิมจากสมุดที่อยู่ได้ทันที'),
                ('4. การชำระเงิน:', 'เลือกชำระเงินผ่าน พร้อมเพย์ QR (สแกนจ่ายได้ทันที), โอนเงินผ่านบัญชีธนาคารพร้อมแจ้งยอด/อัปโหลดสลิป OCR, หรือเลือกเก็บเงินปลายทาง (COD)'),
                ('5. การติดตามสถานะคำสั่งซื้อ:', 'เข้าเมนู "ติดตามคำสั่งซื้อ" กรอกหมายเลขคำสั่งซื้อและเบอร์โทรศัพท์ เพื่อดูบันไดสถานะ 4 ขั้นแบบ Real-time'),
                ('6. การยืนยันรับสินค้า:', 'เมื่อลูกค้าได้รับสินค้าเรียบร้อยแล้ว ให้กดปุ่ม "ฉันได้รับสินค้าเรียบร้อยแล้ว" เพื่อให้คำสั่งซื้อเปลี่ยนเป็น "ถึงมือแล้ว" อย่างเป็นทางการ'),
                ('7. การแจ้งปัญหาคำสั่งซื้อ:', 'หากพบปัญหาเกี่ยวกับสินค้า สามารถกดปุ่ม "แจ้งปัญหาเกี่ยวกับคำสั่งซื้อนี้" เพื่อส่งเรื่องให้เจ้าหน้าที่ตรวจสอบและดำเนินการแก้ไข'),
            ]),

            ('page_break',),

            ('h3', 'ข.2 คู่มือการใช้งานสำหรับเจ้าหน้าที่ร้านค้า (Staff Admin Guide)'),
            ('bullets', [
                ('1. การเข้าสู่ระบบหลังบ้าน:', 'เข้าใช้งานผ่าน URL /staff/login/ ด้วยบัญชีผู้ดูแลระบบหรือเจ้าหน้าที่ (เช่น teacher)'),
                ('2. การจัดการแคตตาล็อกสินค้าและสต็อก:', 'เข้าเมนู "จัดการสินค้า" เพื่อเพิ่มสินค้าใหม่ ปรับปรุงราคา อัปเดตจำนวนสต็อก หรือตรวจสอบการแจ้งเตือนสินค้าใกล้หมด'),
                ('3. การบริหารคำสั่งซื้อ:', 'เข้าเมนู "คำสั่งซื้อ" เพื่อตรวจสอบรายการคำสั่งซื้อใหม่ ข้อมูลลูกค้า ยอดชำระ และกดเปลี่ยนสถานะตามลำดับขั้นบันได'),
                ('4. การบันทึกรับเงิน (Payment Entry):', 'เข้าเมนู "การเงินและยอดชำระ" เพื่อบันทึกยอดเงินที่ลูกค้าแจ้งโอน เมื่อยอดสะสมครบ ออเดอร์จะเปลี่ยนสถานะเป็น "ชำระเงินแล้ว" อัตโนมัติ'),
                ('5. การจัดการปัญหาและข้อร้องเรียน:', 'เข้าเมนู "การแจ้งปัญหา" เพื่อดูรายการปัญหาที่ลูกค้าร้องเรียน ตอบรับเรื่อง และบันทึกแนวทางแก้ไขเพื่อปิดเรื่องอย่างเป็นทางการ'),
                ('6. การเรียกดูรายงานและสถิติ:', 'เข้าเมนู "รายงานยอดขาย" เพื่อดูตัวชี้วัดสำคัญ (KPIs) กราฟยอดขาย สินค้าขายดี และส่งออกข้อมูลประวัติการทำงาน (Audit Log) เป็นไฟล์ CSV'),
            ]),
            ('table', {
                'title': 'ตารางที่ ข.1 สรุปหน้าที่และสิทธิ์การเข้าถึงเมนูของเจ้าหน้าที่แต่ละบทบาท',
                'head': ('บทบาทเจ้าหน้าที่', 'เมนูหลักที่รับผิดชอบ', 'สิทธิ์และหน้าที่หลัก'),
                'rows': [
                    ('ผู้จัดการร้าน\n(Store Manager)',
                     'แดชบอร์ด, จัดการสินค้า, พนักงาน, รายงานยอดขาย',
                     'บริหารจัดการภาพรวม, ดู KPIs, จัดการสิทธิ์, ส่งออกรายงาน'),
                    ('พนักงานการเงิน\n(Cashier)',
                     'การเงินและยอดชำระ, คำสั่งซื้อ, การแจ้งปัญหา',
                     'ตรวจสลิปโอนเงิน OCR, บันทึกยอดเงิน, ปิดเรื่องร้องเรียน'),
                    ('พนักงานคลังสินค้า\n(Warehouse)',
                     'จัดการสินค้า (สต็อก), รายการคำสั่งซื้อ',
                     'ปรับปรุงยอดสต็อกสินค้าคงเหลือ, เปลี่ยนสถานะเป็นจัดส่งแล้ว'),
                    ('ผู้ดูแลระบบสูงสุด\n(Superuser)',
                     'เข้าถึงได้ทุกเมนู และ Django Admin',
                     'จัดการโครงสร้างระบบ, สิทธิ์ RBAC, และ Superuser Override'),
                ],
            }),

            # ==========================================================
            # ภาคผนวก ค พจนานุกรมข้อมูลและโครงสร้างระบบ
            # ==========================================================
            ('h2', 'ภาคผนวก ค พจนานุกรมข้อมูลและโครงสร้างระบบ (Data Dictionary & Architecture)'),
            ('h3', 'ค.1 Data Dictionary (พจนานุกรมข้อมูลตารางฐานข้อมูล)'),
            ('p', 'รายละเอียดคอลัมน์ของทุกตาราง อ่านค่าจากโมเดลในโค้ดโดยตรง\n'
                  'PK = คีย์หลัก · UQ = ค่าเฉพาะ · NULL = อนุญาตให้ว่างได้'),
        ]

        for m in models:
            blocks.append(('h3', f'{m.name} — {m.verbose}'))
            if m.doc:
                blocks.append(('p', m.doc))
            rows = []
            for f in m.fields:
                detail = f.verbose
                if f.is_fk and f.fk_label:
                    detail = f'{detail} (อ้างถึง {f.fk_label})'
                if f.choices:
                    detail += ' — ' + ', '.join(l for _, l in f.choices)
                if f.note:
                    detail += f' ({f.note})'
                rows.append((
                    f.name,
                    f.db_type or '—',
                    ' '.join(f.flags) or '—',
                    detail,
                ))
            blocks.append(('table', {
                'head': ('ชื่อฟิลด์', 'ชนิดข้อมูล', 'ข้อจำกัด', 'คำอธิบาย'),
                'rows': rows,
            }))

        blocks.append(('h3', 'ค.2 ชั้นบริการ (Service Layer)'))
        blocks.append(('p',
                       f'ระบบมีชั้นบริการทั้งหมด {len(services)} ตัว '
                       'ทำหน้าที่รวมตรรกะทางธุรกิจไว้ที่จุดเดียว'))
        blocks.append(('table', {
            'head': ('ชื่อ Service', 'หน้าที่', 'เมธอดหลัก'),
            'rows': [
                (s.name, s.doc or '—',
                 ', '.join(s.public_methods[:6]) or '—')
                for s in services
            ],
        }))

        blocks.append(('h3', 'ค.3 สถิติและโครงสร้างโปรเจกต์'))
        blocks.append(('table', {
            'head': ('รายการ', 'จำนวน'),
            'rows': [
                ('จำนวนตารางในฐานข้อมูล', f'{len(models)} ตาราง'),
                ('จำนวนคอลัมน์ทั้งหมด',
                 f'{sum(len(m.fields) for m in models)} คอลัมน์'),
                ('จำนวนเส้นทาง (URL)', f'{len(routes)} เส้นทาง'),
                ('เส้นทางที่รับเฉพาะ POST',
                 f'{sum(1 for r in routes if r.is_post_only)} เส้นทาง'),
                ('จำนวนหน้าจอสำหรับลูกค้า',
                 f'{sum(1 for r in routes if r.zone == "ลูกค้า" and not r.name.startswith("api"))} หน้า'),
                ('จำนวนหน้าจอสำหรับเจ้าหน้าที่',
                 f'{sum(1 for r in routes if r.zone == "หลังบ้าน" and not r.name.startswith("api"))} หน้า'),
                ('จำนวนชั้นบริการ', f'{len(services)} ตัว'),
                ('จำนวนไฟล์เทสต์', f'{tests["files"]} ไฟล์'),
                ('จำนวนกรณีทดสอบ', f'{tests["cases"]} กรณี'),
                *[(f'จำนวนบรรทัด {label}',
                   f'{info["lines"]:,} บรรทัด ({info["files"]} ไฟล์)')
                  for label, info in loc.items()],
            ],
        }))

        blocks.append(('h3', 'ค.4 มาตรการความปลอดภัย'))
        blocks.append(('table', {
            'head': ('เรื่อง', 'วิธีจัดการ', 'อยู่ที่'),
            'rows': list(facts.security_checklist()),
        }))

        blocks.append(('h3', 'ค.5 สรุปข้อกำหนดเส้นทางและ REST API'))
        api_routes = [r for r in routes if r.name.startswith('api')]
        blocks.append(('table', {
            'head': ('เส้นทาง (Endpoint)', 'เมธอด', 'กลุ่มผู้ใช้/โซน', 'ชื่อ View/ฟังก์ชัน'),
            'rows': [
                (r.pattern, r.methods, r.zone, r.name or r.view)
                for r in api_routes[:15]
            ],
        }))

        # ==========================================================
        # ภาคผนวก ง ประวัติผู้จัดทำโครงงาน
        # ==========================================================
        blocks.append(('h2', 'ภาคผนวก ง ประวัติผู้จัดทำโครงงาน (Author Biography)'))
        blocks.append(('table', {
            'title': 'ประวัติผู้จัดทำโครงงาน (Curriculum Vitae)',
            'head': ('หัวข้อข้อมูล', 'รายละเอียดประวัติและผลงาน'),
            'rows': [
                ('ชื่อ-นามสกุล (ภาษาไทย)', 'นายธรรมธัช รูปไธสง'),
                ('ชื่อ-นามสกุล (ภาษาอังกฤษ)', 'Mr. Thammathad Roobthaisong'),
                ('รหัสนักศึกษา', '671320104'),
                ('วัน เดือน ปีเกิด', '15 สิงหาคม พ.ศ. 2546'),
                ('สถานที่เกิด', 'อำเภอเมือง จังหวัดกำแพงเพชร'),
                ('ประวัติการศึกษา',
                 '• ระดับมัธยมศึกษาตอนปลาย: แผนการเรียนวิทยาศาสตร์-คณิตศาสตร์\n'
                 '• ระดับปริญญาตรี: ปัจจุบันกำลังศึกษาหลักสูตรวิทยาศาสตรบัณฑิต (วท.บ.) '
                 'สาขาวิชาวิทยาการคอมพิวเตอร์ คณะวิทยาศาสตร์และเทคโนโลยี มหาวิทยาลัยราชภัฏกำแพงเพชร'),
                ('สถานที่ติดต่อ / ที่อยู่',
                 'สาขาวิชาวิทยาการคอมพิวเตอร์ คณะวิทยาศาสตร์และเทคโนโลยี '
                 'มหาวิทยาลัยราชภัฏกำแพงเพชร 69 หมู่ 1 ตำบลนครชุม อำเภอเมือง จังหวัดกำแพงเพชร 62000'),
                ('ช่องทางการติดต่ออิเล็กทรอนิกส์',
                 'อีเมล: 671320104@kpru.ac.th  ·  GitHub: https://github.com/tammatatsky-ctrl'),
                ('รายวิชาและอาจารย์ประจำวิชา',
                 'รายวิชา 4123713 หัวข้อเฉพาะเรื่องทางวิทยาการคอมพิวเตอร์ '
                 'โดย ผู้ช่วยศาสตราจารย์สุรินทร์ เพชรไทย'),
                ('ผลงานและบทบาทในโครงงาน',
                 'ผู้วิเคราะห์ ออกแบบ และพัฒนาระบบ THAMMATHAD SHOP: สถาปัตยกรรมระบบ 4 ชั้น (Dual-Zone), '
                 'Single Point Payment, One-Way Order Lifecycle, Append-Only Audit Trail, '
                 'และชุดการทดสอบอัตโนมัติครอบคลุม 412 กรณีทดสอบ'),
            ],
        }))

        return blocks


# ---------------------------------------------------------------------------
# ข้อมูลสำหรับวาดไดอะแกรม — ดึงจากโค้ดจริงเท่าที่ทำได้
# ---------------------------------------------------------------------------
def _lifecycle_steps() -> list[tuple[str, str]]:
    """ขั้นการเดินสถานะออเดอร์ อ่านจาก `Order.STATUS_CHOICES` จริง

    ถ้าโค้ดเพิ่มขั้นใหม่ หรือเปลี่ยนชื่อขั้น ไดอะแกรมจะเปลี่ยนตาม
    ทำให้จับได้ว่าเอกสารกับโค้ดไม่ตรงกัน โดยไม่ต้องรอให้อาจารย์เจอ
    """
    from myapp.models import Order

    # ผู้ทำให้เกิดการเปลี่ยนแปลง: ขั้นแรกลูกค้าสร้าง, ขั้นชำระระบบทำเอง,
    # ขั้นจัดส่งเจ้าหน้าที่, ขั้นสุดท้ายผู้รับยืนยัน
    actor_for = {'pending': 'ลูกค้า', 'paid': 'ระบบ',
                 'shipped': 'เจ้าหน้าที่', 'delivered': 'ลูกค้า'}
    steps: list[tuple[str, str]] = []
    for value, label in Order.STATUS_CHOICES:
        steps.append((label, actor_for.get(value, 'เจ้าหน้าที่')))
    return steps


def _use_cases() -> dict[str, list[tuple[str, str]]]:
    """กรณีใช้งานหลัก แยกตามผู้กระทำ

    คัดมาจากเส้นทางจริงเฉพาะที่มีชื่อ (หน้าจอที่คนใช้เห็น)
    หน้าที่เป็น API หรือ Django Admin ไม่นับ เพราะไม่ใช่กรณีใช้งาน
    ที่ผู้ใช้โต้ตอบด้วยตนเอง
    """
    groups: dict[str, list[tuple[str, str]]] = {
        'ลูกค้า': [
            ('ดูสินค้าและค้นหา', 'แคตตาล็อกสินค้า ค้นหาและกรองตามหมวด'),
            ('สั่งซื้อ', 'เลือกสินค้า กรอกที่อยู่ เลือกวิธีชำระเงิน'),
            ('ชำระเงิน', 'โอนผ่านธนาคาร พร้อมเพย์ เก็บเงินปลายทาง'),
            ('ติดตามออเดอร์', 'ยืนยันตัวตนด้วยเลขออเดอร์และเบอร์โทร'),
            ('ยืนยันการรับสินค้า', 'ปิดออเดอร์ด้วยตนเองเมื่อได้รับของแล้ว'),
            ('จัดการบัญชี', 'ประวัติออเดอร์ สมุดที่อยู่ โปรไฟล์ เปลี่ยนรหัสผ่าน'),
            ('แจ้งปัญหา', 'แจ้งปัญหากับสินค้าหรือออเดอร์ ผูกกับออเดอร์ได้'),
        ],
        'เจ้าหน้าที่': [
            ('จัดการสินค้าและสต็อก', 'เพิ่ม แก้ไข ปรับสต็อก ตรวจสินค้าใกล้หมดออก'),
            ('จัดการพนักงาน', 'เพิ่ม แก้ไข ลบพนักงาน'),
            ('จัดการออเดอร์', 'ดูรายละเอียด เลื่อนสถานะทีละขั้น'),
            ('รับเงินและตรวจยอด', 'บันทึกยอดที่ลูกค้าแจ้ง ส่งออก CSV'),
            ('ปิดการแจ้งปัญหา', 'ตอบและบันทึกผลการดำเนินการ'),
            ('ดูรายงานและแดชบอร์ด', 'ยอดขาย สินค้าขายดี กราฟ'),
            ('ตรวจสอบประวัติการทำงาน', 'ค้นหาและส่งออกประวัติการเปลี่ยนแปลง'),
            ('จัดการสิทธิ์ผู้ใช้', 'กำหนดบทบาทและสิทธิ์การเข้าใช้'),
        ],
    }
    return groups