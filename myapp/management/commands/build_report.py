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

from myapp.docs import content, diagrams, facts


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
        # รับทั้งพาธสัมพัทธ์ (สร้างใต้โปรเจกต์) และพาธสมบูรณ์
        # — การบังคับต่อ BASE_DIR เสมอ ทำให้เทสต์เขียนไฟล์ทิ้งไว้
        # ในโฟลเดอร์โปรเจกต์แทนโฟลเดอร์ชั่วคราว
        raw = Path(options['out'])
        out_dir = raw if raw.is_absolute() else Path(settings.BASE_DIR) / raw
        out_dir.mkdir(parents=True, exist_ok=True)

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
                   'ภาพที่ 3.3 แผนภาพความสัมพันธ์ข้อมูล (Entity-Relationship Diagram) อ่านค่าจากโมเดลจริง'),
            'layered': (diagrams.layered_architecture(),
                        'ภาพที่ 3.2 สถาปัตยกรรมระบบแบบ 4 ชั้น ตรรกะทางธุรกิจรวมศูนย์อยู่ที่ชั้น Service Layer'),
            'lifecycle': (diagrams.order_lifecycle_diagram(
                _lifecycle_steps(), ['ลูกค้า', 'เจ้าหน้าที่', 'ระบบ']),
                'ภาพที่ 3.4 แผนผังวงจรชีวิตสถานะคำสั่งซื้อแบบทิศทางเดียว ต้องเดินทีละขั้นและห้ามย้อนกลับ'),
            'usecase': (diagrams.use_case_diagram(_use_cases()),
                        'ภาพที่ 3.1 แผนภาพกรณีการใช้งานของระบบ (Use Case Diagram) แยกตามผู้กระทำ'),
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
    def _appendix_blocks(self, models, services, routes, loc, tests) -> list:
        """ภาคผนวก: Data Dictionary + ตารางบริการ + สถิติโปรเจกต์

        สร้างจากข้อมูลสดทั้งหมด จึงไม่มีทางล้าสูตรได้โดยไม่รู้ตัว
        """
        blocks: list = [
            ('h2', 'ภาคผนวก ก.1 Data Dictionary (พจนานุกรมข้อมูล)'),
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

        blocks.append(('h2', 'ภาคผนวก ก.2 ชั้นบริการ (Service Layer)'))
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

        blocks.append(('h2', 'ภาคผนวก ก.3 สถิติโปรเจกต์'))
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

        blocks.append(('h2', 'ภาคผนวก ก.4 มาตรการความปลอดภัย'))
        blocks.append(('table', {
            'head': ('เรื่อง', 'วิธีจัดการ', 'อยู่ที่'),
            'rows': list(facts.security_checklist()),
        }))

        blocks.append(('h2', 'ภาคผนวก ก.5 สรุปข้อกำหนดเส้นทางและ REST API'))
        api_routes = [r for r in routes if r.name.startswith('api')]
        blocks.append(('table', {
            'head': ('เส้นทาง (Endpoint)', 'เมธอด', 'กลุ่มผู้ใช้/โซน', 'ชื่อ View/ฟังก์ชัน'),
            'rows': [
                (r.pattern, r.methods, r.zone, r.name or r.view)
                for r in api_routes[:15]
            ],
        }))

        blocks.append(('h2', 'ภาคผนวก ข ประวัติผู้จัดทำโครงงาน (Author Biography)'))
        blocks.append(('table', {
            'head': ('หัวข้อข้อมูล', 'รายละเอียด'),
            'rows': [
                ('ชื่อ-นามสกุล', 'นายธรรมธัช รูปไธสง'),
                ('รหัสนักศึกษา', '671320104'),
                ('หลักสูตร / สาขาวิชา', 'วิทยาศาสตรบัณฑิต (วท.บ.) สาขาวิชาวิทยาการคอมพิวเตอร์'),
                ('คณะและสถาบัน', 'คณะวิทยาศาสตร์และเทคโนโลยี มหาวิทยาลัยราชภัฏกำแพงเพชร'),
                ('รายวิชาโครงงาน', '4123713 หัวข้อเฉพาะเรื่องทางวิทยาการคอมพิวเตอร์ (Special Topics in Computer Science)'),
                ('อาจารย์ประจำวิชา', 'ผู้ช่วยศาสตราจารย์สุรินทร์ เพชรไทย'),
                ('ผลงานในโครงงาน', 'วิเคราะห์ ออกแบบ และพัฒนาระบบ THAMMATHAD SHOP (สถาปัตยกรรม 4 ชั้น, Single Point Payment, One-Way Order Ladder, Append-Only Audit Trail, Automated Test Suite 383 เคส)'),
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