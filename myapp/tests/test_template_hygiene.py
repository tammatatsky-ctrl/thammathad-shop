"""เทสต์กัน "คอมเมนต์เทมเพลตหลุดไปแสดงบนหน้าเว็บ"

บั๊กที่เคยเกิดจริง (เจอจากการทำงานรอบสุดท้าย):
    Django แยกแท็กด้วย regex  r"({%.*?%}|{{.*?}}|{#.*?#})"  **โดยไม่มี DOTALL**
    → `.` ไม่จับขึ้นบรรทัดใหม่ → `{#` ที่ปิดด้วย `#}` ในบรรทัดถัดไป
      **ไม่ถูกมองเป็นคอมเมนต์** แล้วหลุดออกมาเป็นข้อความที่ผู้ใช้เห็นบนหน้าเว็บ

    แย่กว่านั้น: คอมเมนต์ที่ผิดพลาดคือใน `basetemplate.html` ซึ่ง**ทุกเทมเพลต
    extends อยู่** → ข้อความนั้นโผล่บนทุกหน้าของเว็บ

    วิธีแก้: ใช้ `{% comment %}...{% endcomment %}` (ข้ามบรรทัดได้)
    และต้องวาง**หลัง** `{% extends %}` เสมอ เพราะ Django บังคับว่า
    `{% extends %}` ต้องเป็นแท็กแรกในเทมเพลต
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from django.contrib.auth.models import User

TEMPLATE_DIR = Path(settings.BASE_DIR) / 'myapp' / 'templates'


def all_templates():
    return sorted(TEMPLATE_DIR.rglob('*.html'))


class NoMultilineHashCommentTest(TestCase):
    """กันที่ต้นเหตุ: ห้ามมี `{# ... #}` ข้ามหลายบรรทัดในเทมเพลตใด ๆ"""

    def test_no_multiline_brace_comment_in_any_template(self):
        offenders = []
        for path in all_templates():
            text = path.read_text(encoding='utf-8')
            for m in re.finditer(r'\{#', text):
                close = text.find('#}', m.end())
                if close == -1:
                    offenders.append(f'{path.name}: ไม่มีตัวปิดคอมเมนต์')
                    break
                if '\n' in text[m.end():close]:
                    offenders.append(
                        f'{path.name}:{text[:m.end()].count(chr(10)) + 1}')
        self.assertFalse(
            offenders,
            'คอมเมนต์ {# #} ข้ามหลายบรรทัดจะหลุดออกมาเป็นข้อความบนหน้าเว็บ\n'
            '  → เปลี่ยนเป็น {% comment %}...{% endcomment %}\n'
            f'  พบที่: {offenders}')

    def test_every_template_compiles(self):
        """กันว่าไม่มีเทมเพลตไหนพังจากการแก้คอมเมนต์ (เช่น extends ไม่ใช่แท็กแรก)"""
        from django.template.loader import get_template
        errors = []
        for path in all_templates():
            name = str(path.relative_to(TEMPLATE_DIR)).replace('\\', '/')
            try:
                get_template(name)
            except Exception as e:
                errors.append(f'{name}: {type(e).__name__}: {e}')
        self.assertFalse(errors, 'เทมเพลตบางไฟล์คอมไพล์ไม่ผ่าน:\n' + '\n'.join(errors))


class ExtendsMustBeFirstTest(TestCase):
    """`{% extends %}` ต้องเป็นแท็กแรก — คอมเมนต์บล็อกก่อนหน้าจะพังเว็บ"""

    def test_no_comment_before_extends(self):
        offenders = []
        for path in all_templates():
            lines = path.read_text(encoding='utf-8').splitlines()
            for i, line in enumerate(lines):
                if line.strip().startswith('{% extends'):
                    before = [l.strip() for l in lines[:i] if l.strip()]
                    if before:
                        offenders.append(f'{path.name} (บรรทัดก่อน: {before[0][:40]})')
                    break
        self.assertFalse(
            offenders,
            'Django error: "{% extends %} must be the first tag" — '
            'ต้องย้ายคอมเมนต์ไปไว้หลังบรรทัด extends\n'
            f'  พบที่: {offenders}')


class RenderedOutputHasNoTemplateSyntaxTest(TestCase):
    """กันที่ผลลัพธ์: หน้าเว็บที่เรนเดอร์แล้วต้องไม่มีซากเทมเพลตหลุดออกมา

    ชุดนี้สำคัญที่สุดเพราะจับอาการที่ผู้ใช้เห็นจริง ไม่ใช่แค่ดูโครงสร้างไฟล์
    """
    #: ข้อความที่เป็นลายเซ็นของ comment ที่หลุด (ดูค่าที่เรนเดอร์จริง)
    LEAK_MARKERS = ['# =====', '{% comment %}', '{% endcomment %}',
                    '{% extends', '{% load ', '=====#}']

    def setUp(self):
        self.staff = User.objects.create_user(
            username='boss', password='pw', is_staff=True)

    def _assert_clean(self, url):
        r = self.client.get(url)
        # 403 = หน้านั้นต้องการบทบาท Manager (เจ้าหน้าที่ธรรมดาโดนปฏิเสธ)
        # → ยังถือว่า "หน้าเรนเดอร์ได้ปกติ" ตรวจซากเทมเพลตเฉพาะตอน 200
        self.assertIn(r.status_code, (200, 302, 403), f'{url} → {r.status_code}')
        if r.status_code != 200:
            return
        html = r.content.decode('utf-8')
        for marker in self.LEAK_MARKERS:
            self.assertNotIn(marker, html,
                             f'หน้า {url} มีซากเทมเพลตหลุดออกมา: "{marker}"')

    def test_public_pages_clean(self):
        for url in ('/', '/product/', '/contact/', '/account/login/',
                    '/account/password-reset/', '/order/tracking/'):
            with self.subTest(url=url):
                self._assert_clean(url)

    def test_staff_pages_clean(self):
        """หน้าหลังบ้าน — คอมเมนต์ที่ผิดใน basetemplate จะโผล่ที่นี่ทั้งหมด"""
        self.client.force_login(self.staff)
        for url in ('/dashboard/', '/employees/', '/product/manage/', '/orders/',
                    '/customers/', '/payments/', '/reports/', '/staff/activity/',
                    '/staff/users/'):
            with self.subTest(url=url):
                self._assert_clean(url)

    def test_error_pages_clean(self):
        self.client.logout()
        r = self.client.get('/no-such-page-xyz/')
        self.assertEqual(r.status_code, 404)
        html = r.content.decode('utf-8')
        for marker in self.LEAK_MARKERS:
            self.assertNotIn(marker, html, f'หน้า 404 มีซากเทมเพลต: "{marker}"')
