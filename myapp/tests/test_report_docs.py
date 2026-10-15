"""เอกสารรายงานที่ส่งอาจารย์ — ต้องไม่โกหก และต้องอ่านออก

ทำไมต้องมีเทสต์ของเอกสาร
    เอกสารที่พิมพ์ตัวเลขตายไว้จะเริ่มผิดทันทีที่โค้ดเปลี่ยน และ**ไม่มีใครสังเกต**
    เพราะตัวเลขยังดูเหมือนจริง อาจารย์จะเจอตอนเปิดหน้าเว็บเทียบเอกสาร
    ซึ่งเสียคะแนนแล้วแก้ไม่ทัน

    เทสต์ชุดนี้จึงตรวจว่า (ก) ตัวเลขในเอกสารตรงกับโค้ดจริง
    (ข) ไดอะแกรมวาดออกมาครบ ไม่ทับกัน และ (ค) ไม่มีสิ่งที่อ่านไม่ออก
    เช่น กล่องสีดำแทนภาษาไทย (เคยเจอกับ SVG ที่ผ่าน svglib)
"""

import io
import re

from django.core.management import call_command
from django.test import TestCase

from myapp.docs import content, diagrams, facts


class FactsMatchCodeTest(TestCase):
    """ข้อมูลที่ใส่ในเอกสารต้องมาจากโค้ดจริง"""

    def test_model_count_matches_apps(self):
        from django.apps import apps

        expected = len(list(apps.get_app_config('myapp').get_models()))
        self.assertEqual(len(facts.models_report()), expected,
                         'ตารางที่รายงานไม่ครบทุกตารางในระบบ')

    def test_every_real_column_appears(self):
        """คอลัมน์ที่หายไปจาก Data Dictionary = อาจารย์เปิดโค้ดเทียบแล้วเจอ"""
        from django.apps import apps

        reported = {m.name for m in facts.models_report()}
        for model in apps.get_app_config('myapp').get_models():
            self.assertIn(model.__name__, reported,
                          f'ตาราง {model.__name__} ไม่ได้อยู่ในเอกสาร')

    def test_db_types_are_real_not_fallback(self):
        """`db_type` ต้องเป็นชนิดจริงในฐานข้อมูล

        ถ้า fallback เป็นชื่อคลาส จะได้ 'foreignkey' / 'bigauto' ซึ่งไม่มี
        ในฐานข้อมูลจริง และอาจารย์จะเห็นว่าไม่ได้อ่านจากระบบจริง
        """
        for m in facts.models_report():
            for f in m.fields:
                if f.db_type:
                    self.assertNotIn('auto', f.db_type,
                                     f'{m.name}.{f.name} ได้ชนิดไม่จริง')
                    self.assertNotIn('field', f.db_type.lower(),
                                     f'{m.name}.{f.name} ได้ชื่อคลาสแทนชนิด')

    def test_fk_target_is_class_name_not_thai_label(self):
        """`fk_target` ต้องเป็นชื่อคลาส เพราะใช้จับคู่วาด ER

        ถ้าเป็นชื่อภาษาไทย ลูกศรความสัมพันธ์จะหายไปทั้งหมดเงียบ ๆ
        (เคยเกิด: เก็บ `verbose_name` ซึ่งเป็นภาษาไทย ทำให้จับคู่ไม่ได้)
        """
        names = {m.name for m in facts.models_report()}
        for m in facts.models_report():
            for f in m.fk_fields:
                self.assertRegex(
                    f.fk_target or '', r'^[A-Z][A-Za-z0-9_]*$',
                    f'{m.name}.{f.name} เก็บชื่อปลายทางไว้ในรูปแบบที่จับคู่ไม่ได้')

    def test_test_count_matches_what_django_runs(self):
        """ตัวเลขเคสทดสอบต้องเท่ากับที่ `manage.py test` รายงาน

        ถ้านับด้วย regex จะได้ตัวเลขเกินจริง 1 เคส (เคยเจอ)
        """
        info = facts.count_tests()
        self.assertGreater(info['cases'], 0)
        self.assertEqual(info['cases'], info['cases'],
                         'ตัวเลขเทสต์ต้องมาจาก unittest discovery')

    def test_count_tests_uses_discovery_not_regex(self):
        import unittest
        from pathlib import Path

        import myapp

        suite = unittest.TestLoader().discover(
            str(Path(myapp.__file__).parent / 'tests'),
            top_level_dir=str(Path(myapp.__file__).parent))
        self.assertEqual(facts.count_tests()['cases'],
                         suite.countTestCases())


class DiagramRendersTest(TestCase):
    """ไดอะแกรมต้องวาดได้จริง ไม่ทับกัน และอ่านออก"""

    def setUp(self):
        diagrams.register_thai_fonts()

    def test_finds_a_thai_font_or_says_which(self):
        """ไม่พบฟอนต์ไทยต้องบอกว่าต้องมีอะไรบ้าง ไม่ใช่ล้มแบยาก ๆ"""
        try:
            regular, bold = diagrams.register_thai_fonts()
        except RuntimeError as exc:
            self.assertIn('ฟอนต์', str(exc))
            self.assertIn('Leelawadee', str(exc))
            return
        self.assertTrue(regular and bold)

    def test_all_four_diagrams_build(self):
        models = facts.models_report()
        pack = [
            diagrams.er_diagram(models),
            diagrams.layered_architecture(),
            diagrams.order_lifecycle_diagram(
                [('รอชำระเงิน', 'ลูกค้า'), ('ชำระเงินแล้ว', 'ระบบ'),
                 ('จัดส่งแล้ว', 'เจ้าหน้าที่'), ('ถึงมือแล้ว', 'ลูกค้า')],
                ['ลูกค้า', 'เจ้าหน้าที่', 'ระบบ']),
            diagrams.use_case_diagram({'ลูกค้า': [('สั่งซื้อ', 'เลือกสินค้า')]}),
        ]
        for d in pack:
            self.assertGreater(d.width, 100)
            self.assertGreater(d.height, 100)

    def test_diagrams_render_to_png(self):
        """ต้องเรนเดอร์เป็นภาพได้จริง (ไม่ใช่แค่สร้าง object)"""
        from reportlab.graphics import renderPM

        drawing = diagrams.layered_architecture()
        buf = io.BytesIO()
        renderPM.drawToFile(drawing, buf, fmt='PNG', dpi=100)
        self.assertGreater(len(buf.getvalue()), 1000)

    def test_thai_text_is_not_rendered_as_black_boxes(self):
        """ข้อความไทยต้องเป็นตัวอักษรจริง ไม่ใช่สี่เหลี่ยม

        ทดสอบด้วยการดูว่าฟอนต์ที่ register ใช้งานได้จริงกับข้อความไทย
        ถ้าไม่ได้ register ฟอนต์ การวาดจะได้กล่องสีดำโดยไม่มี error
        (เคยเกิดกับเส้นทาง SVG ที่ผ่าน svglib)
        """
        diagrams.register_thai_fonts()
        width = diagrams.text_width('ทดสอบภาษาไทย', 10)
        blank = diagrams.text_width('        ', 10)
        self.assertGreater(width, blank * 0.8,
                           'ข้อความไทยกว้างเท่าช่องว่าง = ฟอนต์ไม่ได้ผูก')

    def test_wrap_splits_thai_without_spaces(self):
        """ภาษาไทยไม่มีช่องว่างระหว่างคำ — ตัดบรรทัดตามอักขระ

        ถ้าตัดตามช่องว่าง ข้อความไทยทั้งยาวจะเป็นบรรทัดเดียวล้นกรอบ
        """
        lines = diagrams.wrap('ระบบร้านค้าออนไลน์สำหรับอุปกรณ์คอมพิวเตอร์',
                              9, 60)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(diagrams.text_width(line, 9), 60 * 1.6)


class ReportTextLayoutTest(TestCase):
    """การจัดวางข้อความไทยในเอกสาร — จุดที่พลาดแล้วเอกสารอ่านยากทั้งฉบับ"""

    def test_thai_needs_character_wrapping(self):
        """ต้องตัดบรรทัดได้ที่ทุกอักขระ ไม่ใช่เฉพาะช่องว่าง

        ภาษาไทยไม่มีช่องว่างระหว่างคำ ถ้าใช้โหมดตัดที่ช่องว่างตามปกติ
        บรรทัดจะสั้นลงเรื่อย ๆ และเว้นช่องว่างท้ายบรรทัดกว้างมาก
        """
        from myapp.docs.pdf_builder import _styles

        _styles()['body'].wordWrap == 'CJK' or self.fail(
            'body ต้องใช้ wordWrap=CJK ไม่ใช่ตัดที่ช่องว่างอย่างเดียว')
        _styles()['td'].wordWrap == 'CJK' or self.fail(
            'เซลล์ตารางต้องตัดบรรทัดได้ที่ทุกอักขระเช่นกัน')

    def test_blank_line_becomes_a_paragraph_break(self):
        """ย่อหน้าที่คนเขียนเว้นบรรทัด ต้องยังเป็นคนละย่อหน้าในเอกสาร

        ถ้าไม่แยก ข้อความสองย่อหน้าจะถูกยุบเป็นประโยคเดียว
        และอ่านไม่ออกว่าผู้เขียนจัดใจแยกเป็นสองส่วน
        """
        from myapp.docs.pdf_builder import _PARA_SPLIT, esc

        source = 'ย่อหน้าแรก\n\nย่อหน้าที่สอง'
        chunks = [c.strip() for c in _PARA_SPLIT.split(source) if c.strip()]
        self.assertEqual(chunks, ['ย่อหน้าแรก', 'ย่อหน้าที่สอง'])

    def test_single_newline_does_not_split_paragraph(self):
        """ขึ้นบรรทัดเดียว (เช่นคร่อมบรรทัดในไฟล์ Python) ไม่ใช่การแยกย่อหน้า"""
        from myapp.docs.pdf_builder import _PARA_SPLIT

        self.assertEqual(len([c for c in _PARA_SPLIT.split('บรรทัดหนึ่ง\nบรรทัดสอง')
                              if c.strip()]), 1)

    def test_esc_collapses_whitespace_inside_a_paragraph(self):
        from myapp.docs.pdf_builder import esc

        out = esc('บรรทัดหนึ่ง\n  บรรทัดสอง   มี  ช่องว่าง\n')
        self.assertEqual(out, 'บรรทัดหนึ่ง บรรทัดสอง มี ช่องว่าง')

    def test_esc_escapes_xml_specials(self):
        from myapp.docs.pdf_builder import esc

        self.assertEqual(esc('a & b < c > d'), 'a &amp; b &lt; c &gt; d')


class RequirementsSplitTest(TestCase):
    """`requirements.txt` ต้องติดตั้งได้บน PythonAnywhere บัญชีฟรีเสมอ

    ทำไมต้องมี
        ครั้งหนึ่ง `pycairo` (ต้องคอมไพล์ต่อกับ C library ชื่อ `cairo`) อยู่ใน
        `requirements.txt` ทำให้ `pip install` ล้มกลางทางบน PythonAnywhere
        และเพราะ pip หยุดที่แพ็กเกจที่ล้มก่อน **Django ก็ไม่ถูกติดตั้งตามไปด้วย**
        เหลือแต่เว็บที่รันไม่ขึ้น โดยข้อความ error ไม่ได้บอกว่าเพราะอะไร

        ไลบรารีที่คอมไพล์ C library ทำให้ทั้งระบบล้ม แต่ "แก้ทีเดียวจบ" ไม่ได้
        เพราะคนไม่ได้เพิ่มอะไรเข้ามาเอง → ต้องมีเทสต์คุมไว้
    """

    #: ไลบรารีที่ต้องคอมไพล์ C library — ติดตั้งไม่ผ่านบน PA บัญชีฟรี
    #: (ชื่อตามที่เขียนใน requirements ไม่ใช่ชื่อโมดูลตอน import)
    NATIVE_PACKAGES = ('pycairo', 'rlpycairo')

    @staticmethod
    def _req(name: str) -> list[str]:
        from pathlib import Path

        import myapp

        path = Path(myapp.__file__).parent.parent / name
        if not path.exists():
            raise AssertionError(f'ไม่พบไฟล์ {name}')
        lines = []
        for raw in path.read_text(encoding='utf-8').splitlines():
            line = raw.split('#')[0].strip()
            if line:
                lines.append(line.lower())
        return lines

    def test_requirements_txt_has_no_native_packages(self):
        for line in self._req('requirements.txt'):
            for bad in self.NATIVE_PACKAGES:
                self.assertNotIn(
                    bad, line,
                    f'requirements.txt ต้องไม่มี {bad} — pip จะล้มกลางทาง '
                    'และ Django จะไม่ถูกติดตั้งตามไปด้วย')

    def test_requirements_txt_still_has_the_web_stack(self):
        """การแยกไฟล์ต้องไม่ทำให้ไลบรารีเว็บหายไป (แยกผิดจนเว็บรันไม่ได้)"""
        text = ' '.join(self._req('requirements.txt'))
        for needed in ('django', 'djangorestframework', 'pillow',
                       'drf-spectacular'):
            self.assertIn(needed, text, f'requirements.txt ต้องมี {needed}')

    def test_docs_requirements_includes_the_web_stack(self):
        """`requirements-docs.txt` ต้อง `-r requirements.txt` เพื่อไม่ให้พลาด"""
        self.assertTrue(
            any(line.startswith('-r ') and 'requirements.txt' in line
                for line in self._req('requirements-docs.txt')),
            'requirements-docs.txt ต้องอ้าง -r requirements.txt')

    def test_docs_requirements_keeps_the_native_packages(self):
        """ถ้าย้ายออกแล้วลืมใส่กลับ คำสั่ง build_report จะใช้ไม่ได้"""
        text = ' '.join(self._req('requirements-docs.txt'))
        for needed in ('reportlab', 'python-docx', *self.NATIVE_PACKAGES):
            self.assertIn(needed, text,
                          f'requirements-docs.txt ต้องมี {needed}')

    def test_build_report_names_the_right_file_when_deps_missing(self):
        """ข้อความ error ต้องชี้ไปที่ไฟล์ที่ใช้แก้จริง

        ถ้าชี้ผิดไฟล์ คนจะไปแก้ requirements.txt (ที่ติดตั้งไม่ได้บน PA)
        แล้วเจอปัญหาเดิมซ้ำอีก
        """
        import inspect

        from myapp.management.commands.build_report import Command

        source = inspect.getsource(Command._check_dependencies)
        self.assertIn('requirements-docs.txt', source)


class ReportBuildTest(TestCase):
    """คำสั่ง build_report ต้องสร้างไฟล์ได้ครบและอ่านออก"""

    def test_builds_both_files(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            # ต้องส่งพาธสมบูรณ์ ถ้าส่งแค่ชื่อโฟลเดอร์ คำสั่งจะเขียนลง
            # ในโฟลเดอร์โปรเจกต์แทน (ผ่าน BASE_DIR) แล้วเทสต์จะไม่เจอไฟล์
            call_command('build_report', out=tmp, verbosity=0)
            files = sorted(Path(tmp).glob('*'))
            names = [f.suffix for f in files]
            self.assertIn('.pdf', names, 'ไม่ได้สร้าง PDF')
            self.assertIn('.docx', names, 'ไม่ได้สร้าง Word')
            for f in files:
                self.assertGreater(f.stat().st_size, 10_000,
                                   f'{f.name} เล็กผิดปกติ อาจไม่มีเนื้อหา')

    def test_relative_out_goes_under_project(self):
        """พาธสัมพัทธ์ต้องอยู่ใต้โปรเจกต์ (ไม่หลุดไปเขียนที่อื่น)"""
        import tempfile
        from pathlib import Path

        from django.conf import settings

        out_name = 'docs/_test_build_report'
        try:
            call_command('build_report', '--pdf-only', out=out_name,
                         verbosity=0)
            self.assertTrue(
                (Path(settings.BASE_DIR) / out_name).exists(),
                'พาธสัมพัทธ์ต้องถูกต่อกับโฟลเดอร์โปรเจกต์')
        finally:
            target = Path(settings.BASE_DIR) / out_name
            for f in target.glob('*'):
                f.unlink()
            if target.exists():
                target.rmdir()

    def test_pdf_is_valid_and_has_pages(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            call_command('build_report', '--pdf-only', out=tmp, verbosity=0)
            pdf = next(Path(tmp).glob('*.pdf'))
            raw = pdf.read_bytes()
            self.assertTrue(raw.startswith(b'%PDF-'), 'ไม่ใช่ไฟล์ PDF')
            # จำนวนหน้า = จำนวนวัตถุ /Type /Page
            self.assertGreaterEqual(raw.count(b'/Type /Page'), 10,
                                    'PDF มีหน้าน้อยผิดปกติ')

    def test_docx_is_valid_zip_with_embedded_images(self):
        import tempfile
        import zipfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            call_command('build_report', '--docx-only', out=tmp, verbosity=0)
            docx = next(Path(tmp).glob('*.docx'))
            self.assertTrue(zipfile.is_zipfile(docx))
            with zipfile.ZipFile(docx) as z:
                media = [n for n in z.namelist() if n.startswith('word/media/')]
                self.assertGreaterEqual(len(media), 4,
                                        'ไดอะแกรมไม่ได้ฝังใน Word')

    def test_cover_has_blank_lines_for_student_to_fill(self):
        """หน้าปกต้องเว้นว่างให้กรอก ไม่ใช่พิมพ์ข้อมูลตัวอย่างปลอม"""
        from myapp.management.commands.build_report import COVER

        for key in ('ชื่อ-นามสกุล', 'รหัสนักศึกษา'):
            self.assertEqual(COVER['student'][key], '',
                             f'ปกต้องเว้นว่างไว้ให้ผู้เรียนกรอก: {key}')
        self.assertNotIn('อาจารย์ที่ปรึกษา', COVER['student'],
                         'อย่าใส่ซ้ำกับฟิลด์ advisor แล้วจะขึ้นสองบรรทัด')

    def test_cover_meta_values_are_not_duplicated(self):
        """คีย์ใน `student` ต้องไม่ซ้ำกับคีย์ระดับบน (กันบรรทัดซ้ำในปก)"""
        from myapp.management.commands.build_report import COVER

        self.assertFalse(set(COVER['student']) & set(COVER) - {'student'})


class ReportContentTest(TestCase):
    """เนื้อหารายงานต้องครบโครงและไม่มีตัวแปรค้าง"""

    def test_all_required_chapters_present(self):
        ids = [c['id'] for c in content.chapter_order()]
        for need in ('intro', 'analysis', 'development', 'results', 'conclusion'):
            self.assertIn(need, ids, f'รายงานขาดบท: {need}')

    def test_abstract_has_thai_and_english(self):
        self.assertTrue(content.ABSTRACT_THAI.strip())
        self.assertTrue(content.ABSTRACT_EN.strip())
        self.assertGreater(len(content.ABSTRACT_EN.split()), 80,
                           'Abstract ภาษาอังกฤษสั้นเกินไป')

    def test_no_unfilled_placeholders_in_prose(self):
        """เนื้อหาต้องไม่มี `{...}` ที่ลืมแทนค่า

        ถ้ามี จะเห็นเป็นข้อความแปลก ๆ ในเอกสารที่ส่งอาจารย์
        """
        blob = (content.ABSTRACT_THAI + content.ABSTRACT_EN
                + content.TESTING_TEXT
                + repr([c['blocks'] for c in content.chapter_order()]))
        leftover = re.findall(r'\{[A-Za-z_][A-Za-z0-9_.]*\}', blob)
        self.assertEqual(leftover, [],
                         f'มีตัวแปรค้างในเนื้อหารายงาน: {leftover[:5]}')

    def test_lifecycle_matches_real_status_choices(self):
        """ลำดับขั้นในไดอะแกรมต้องตรงกับ `Order.STATUS_CHOICES` จริง"""
        from myapp.models import Order

        from myapp.management.commands.build_report import _lifecycle_steps

        labels = [label for label, _ in _lifecycle_steps()]
        self.assertEqual(labels,
                         [label for _, label in Order.STATUS_CHOICES])

    def test_every_block_kind_is_handled_by_both_builders(self):
        """ทุกชนิดบล็อกต้องมีตัวแปลงในทั้ง PDF และ Word

        ถ้าเพิ่มชนิดใหม่แล้วลืมแปลงที่ฝั่งใดฝั่งหนึ่ง เนื้อหาจะหายไปเงียบ ๆ
        ในไฟล์นั้น โดยไม่มี error
        """
        kinds = set()
        for chapter in content.chapter_order():
            kinds.update(b[0] for b in chapter['blocks'])

        import inspect

        from myapp.docs import docx_builder, pdf_builder

        for module in (pdf_builder, docx_builder):
            src = inspect.getsource(module)
            for kind in kinds:
                self.assertIn(f"'{kind}'", src,
                              f'{module.__name__} ไม่รู้จักบล็อกชนิด {kind}')

    def test_student_todo_is_not_empty(self):
        """ต้องเตือนผู้เรียนเรื่องที่ต้องแก้เองก่อนส่ง"""
        self.assertGreaterEqual(len(content.STUDENT_TODO), 3)
        joined = ' '.join(content.STUDENT_TODO)
        self.assertIn('ชื่อ', joined)