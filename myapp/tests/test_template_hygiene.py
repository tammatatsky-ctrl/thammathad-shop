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
        for url in ('/', '/product/', '/contact/', '/issue/', '/account/login/',
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


class EffectAssetBaseUrlTest(TestCase):
    """กัน path ฐานของ effect พัง — อาการคือ "ทุกเอฟเฟกต์หายไปเงียบ ๆ"

    บั๊กที่เคยเกิดจริง:
        `basetemplate.html` เคยปั่น path ฐานด้วย `{% static 'css/effects/' %}`
        แต่ `VersionedStaticFilesStorage` จะเติม `?v=<STATIC_VERSION>` ต่อท้าย
        **แม้ทั้งที่เป็นโฟลเดอร์** → ได้ `FX_CSS_BASE = "/static/css/effects/?v=..."`
        แล้ว `fx-assets.js` เอาไปต่อชื่อไฟล์ ได้ URL ขยะแบบ
        `/static/css/effects/?v=2026...fx-glass.css` → 404

        ผลคือ ทุก effect (hero, ripple, glass, halo, liquid...) โหลดไม่ขึ้น
        แต่หน้าเว็บยัง "เปิดได้" → สังเกตยากมาก เพราะไม่มี error ที่ console

    กฎ: path ฐานต้อง**ไม่มี query** เด็ดขาด ให้ `stamp()` เป็นคนเติม `?v=` ทีหลัง
    """

    def _base(self, name):
        html = self.client.get('/').content.decode('utf-8')
        m = re.search(rf'{name} = "([^"]*)"', html)
        self.assertIsNotNone(m, f'ไม่พบ {name} ใน HTML ของหน้าแรก')
        return m.group(1)

    def test_css_and_js_base_have_no_query(self):
        for name in ('FX_CSS_BASE', 'FX_JS_BASE'):
            with self.subTest(base=name):
                base = self._base(name)
                self.assertNotIn('?', base,
                                 f'{name} มี query string ติดมา → URL ของ effect จะพัง')
                self.assertNotIn('#', base, f'{name} มี fragment ติดมา')
                self.assertTrue(base.endswith('/'),
                                f'{name} ต้องลงท้ายด้วย "/" เพราะ JS เอาไปต่อชื่อไฟล์')

    def test_static_version_is_exposed_for_cache_busting(self):
        """`window.FX_STATIC_V` ต้องมีค่า — ถ้าว่าง `stamp()` จะไม่เติม ?v=
        แล้วแก้ effect แล้วผู้ใช้ได้ไฟล์เก่าจาก cache (Bug Recipe #2)"""
        html = self.client.get('/').content.decode('utf-8')
        m = re.search(r'FX_STATIC_V = "([^"]*)"', html)
        self.assertIsNotNone(m, 'ไม่พบ FX_STATIC_V ใน HTML')
        self.assertTrue(m.group(1).strip(),
                        'FX_STATIC_V ว่าง → effect ที่โหลดตอน runtime ไม่มี cache-busting')
