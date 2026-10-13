"""เทสต์รอบ 2 — หน้าข้อผิดพลาด 404/500 + `manage.py preflight` + ค่า hardening

กลุ่มนี้ล็อกงานที่ทำหลัง P0:
1. **404/500 ยังเป็นหน้าดิบของ Django** → ผู้ใช้เห็นข้อความอังกฤษยาว ๆ
   ไม่มีปุ่ม ไม่มีเมนู = ให้ความรู้สึกเหมือนเว็บพัง
2. **ไม่มี `manage.py preflight`** → บั๊กที่ทำให้ "deploy แล้วพังแต่ไม่มีอาการ"
   ต้องไล่ทีละไฟล์ (เคยเจอ 4 ตัว)
3. **HSTS 30 วันเปิดครั้งเดียว** → ถ้า https/cookie พัง ผู้ใช้ถูกล็อกยากแก้
4. **ไม่มี `CSRF_TRUSTED_ORIGINS`** → ผู้ใช้ส่งฟอร์มไม่ได้เมื่ออยู่หลัง proxy
"""
import sqlite3
import tempfile
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings


class ErrorPagesTest(TestCase):
    """404/500 ต้องเป็นหน้าของร้าน ไม่ใช่หน้าดิบของ Django"""

    def test_404_uses_branded_template(self):
        r = self.client.get('/no-such-page-xyz/')
        self.assertEqual(r.status_code, 404)
        self.assertTemplateUsed(r, '404.html')
        html = r.content.decode('utf-8')
        self.assertIn('ไม่พบหน้าที่คุณค้นหา', html)
        # ต้องมีทางออก ไม่ใช่ปล่อยให้ผู้ใช้นั่งตาคนจม
        self.assertIn('กลับหน้าหลัก', html)
        self.assertIn('ติดตามออเดอร์', html)

    def test_404_shows_requested_path(self):
        """ช่วยให้ผู้ใช้รู้ว่าพิมพ์ผิดตรงไหน"""
        r = self.client.get('/no-such-page-xyz/')
        self.assertIn('/no-such-page-xyz/', r.content.decode('utf-8'))

    def test_404_does_not_leak_exception_details(self):
        """DEBUG=False ต้องไม่มี traceback/DB ชื่อตารางโผล่"""
        html = self.client.get('/no-such-page-xyz/').content.decode('utf-8')
        for leak in ('Traceback', 'sqlite3', 'myapp_order', 'DJANGO_SETTINGS_MODULE'):
            self.assertNotIn(leak, html, f'ห้ามรั่ว: {leak}')

    def test_500_page_renders_without_external_css(self):
        """500 มักเกิดเพราะ static พัง → CSS ต้องฝังในไฟล์ ไม่พึ่งไฟล์ภายนอก

        ทดสอบโดยอ่านไฟล์ตรง ๆ เพราะการจะให้ Django render 500 จริงต้อง
        ทำให้ view พังซึ่งเป็นเรื่องที่ต้องกันไม่ให้เกิด
        """
        html = (Path(settings.BASE_DIR) / 'myapp' / 'templates' / '500.html').read_text(
            encoding='utf-8')
        self.assertIn('<style>', html, '500.html ต้องมี CSS ฝังในตัว')
        self.assertNotIn('{% extends', html,
                         '500.html ต้องไม่ extends (ถ้า base พังจะพังตาม)')
        self.assertNotIn("{% static", html, '500.html ต้องไม่พึ่ง static')
        self.assertIn('ระบบขัดข้องชั่วคราว', html)

    def test_500_page_tells_staff_to_run_preflight(self):
        """ช่วยเจ้าหน้าที่ให้รู้ว่าจะตรวจอะไรต่อ (ไม่ใช่แค่ขอโทษ)"""
        html = (Path(settings.BASE_DIR) / 'myapp' / 'templates' / '500.html').read_text(
            encoding='utf-8')
        self.assertIn('preflight', html)

    def test_500_handler_renders_without_session_or_context_processors(self):
        """หน้า 500 ต้องขึ้นได้แม้ session/DB พัง — ซึ่งมักคือสาเหตุที่ทำให้เกิด 500

        ⚠️ บั๊กที่เคยเกิดจริง: `render(request, ...)` เดินผ่าน context processor
        และ `cart_context` แตะ `request.session` → ถ้า session เป็นปัญหา
        หน้า 500 จะพังตามและผู้ใช้เห็นหน้าว่าง
        ทดสอบด้วย RequestFactory ที่ **ไม่มี session** (จำลองกรณีแย่สุด)
        """
        from django.test import RequestFactory

        from myapp.views import server_error_view

        request = RequestFactory().get('/boom/')
        self.assertFalse(hasattr(request, 'session'),
                         'เทสต์นี้ต้องใช้ request ที่ไม่มี session จริง ๆ')

        response = server_error_view(request)
        self.assertEqual(response.status_code, 500)
        body = response.content.decode('utf-8')
        self.assertIn('ระบบขัดข้องชั่วคราว', body)
        # ยังบอกได้ว่าข้อมูลไม่หาย (สำคัญกว่าหน้าสวย เพราะลูกค้ากำลังจ่ายเงิน)
        self.assertIn('ไม่ได้สูญหาย', body)

    def test_handlers_registered(self):
        """ทุก handler ต้องผูกไว้จริง ไม่ใช่ตั้งค่าไว้เฉย ๆ"""
        from django.urls import get_resolver
        resolver = get_resolver()
        self.assertTrue(callable(resolver.resolve_error_handler(404)))
        self.assertTrue(callable(resolver.resolve_error_handler(500)))


class PreflightCommandTest(TestCase):
    """`manage.py preflight` — เครื่องมือกันบั๊กตอน deploy"""

    def _run(self, *args):
        out = StringIO()
        call_command('preflight', *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_runs_and_reports_every_check(self):
        """ต้องรายงานครบทุกหัวข้อ ไม่ใช่ error ลอย ๆ"""
        text = self._run()
        for expect in ('DEBUG', 'ALLOWED_HOSTS', 'CSRF', 'HSTS', 'staticfiles',
                       'migration', 'ฐานข้อมูล', 'สำรอง'):
            self.assertIn(expect, text, f'รายงานต้องมีหัวข้อ "{expect}"')

    def test_exit_code_nonzero_on_fail(self):
        """FAIL ต้อง exit 1 เพื่อให้ใช้ใน script/CI ได้ (0 = ปลอดภัย)"""
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / 'staticfiles-does-not-exist'
            with override_settings(STATIC_ROOT=missing):
                with self.assertRaises(SystemExit) as ctx:
                    self._run()
                self.assertEqual(ctx.exception.code, 1, 'FAIL ต้อง exit 1')

    def test_exit_zero_when_all_green(self):
        """ทุกอย่างปกติ → exit 0 (ปล่อยให้ deploy ได้)"""
    def test_exit_zero_when_all_green(self):
        """ทุกอย่างปกติ (ใช้ staticfiles จริงของโปรเจกต์) → exit 0 = ปล่อย deploy ได้"""
        try:
            self._run()          # ไม่ override STATIC_ROOT — ตรวจของจริง
        except SystemExit as e:
            self.fail(f'ไม่ควร FAIL เมื่อทุกอย่างปกติ (exit={e.code}) '
                      '— รัน collectstatic ก่อน')

    def test_detects_missing_collectstatic(self):
        """บั๊กอันดับ 1: ไม่ได้ collectstatic → ตอน DEBUG=False static ทั้งหมด 404"""
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(STATIC_ROOT=Path(tmp) / 'nothing-here'):
                try:
                    self._run()
                    self.fail('ควรรายงาน FAIL เมื่อไม่มี staticfiles')
                except SystemExit:
                    pass

    def test_detects_static_out_of_sync(self):
        """บั๊กอันดับ 2: staticfiles เก่ากว่า myapp/static → ผู้ใช้เห็นของเก่า"""
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / 'staticfiles'
            dst.mkdir()
            # สร้าง staticfiles ที่ขาดไฟล์เกือบทั้งหมด
            (dst / 'vendor').mkdir()
            with override_settings(STATIC_ROOT=dst):
                try:
                    self._run()
                    self.fail('ควรรายงาน FAIL เมื่อ staticfiles ไม่ครบ')
                except SystemExit:
                    pass

    def test_quiet_hides_passing_checks(self):
        out = StringIO()
        call_command('preflight', '--quiet', stdout=out, stderr=out)
        text = out.getvalue()
        self.assertIn('ระบบพร้อมใช้งาน', text)   # ยังเห็นสรุป
        self.assertNotIn('ALLOWED_HOSTS', text)   # ไม่เห็นของที่ผ่าน

    def test_warns_when_debug_on(self):
        """DEBUG=True ต้องเตือน (ไม่ใช่ผ่านเงียบ ๆ)"""
        with override_settings(DEBUG=True):
            text = self._run()
        self.assertIn('DEBUG = True', text)
        self.assertIn('WARN', text)

    def test_detects_stale_backup(self):
        """บั๊กอันดับ 3: ไม่มีไฟล์สำรองเลย → ข้อมูลหายแล้วกู้ไม่ได้"""
        # ใช้ BASE_DIR ปลอมที่ไม่มีโฟลเดอร์ backups/
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(BASE_DIR=Path(tmp), STATIC_ROOT=tmp):
                text = self._run()
        self.assertIn('สำรอง', text)


class BackupCommandRegressionsTest(TestCase):
    """กันบั๊กที่เคยเกิดกับ backup_db

    เคยพัง: `db_name.startswith('file:')` → AttributeError เพราะ settings ให้
    `DATABASES['NAME']` เป็น `Path` (BASE_DIR / 'db.sqlite3') ไม่ใช่ str
    ผลคือ **คำสั่งสำรองล้มทุกครั้งที่รัน** แต่ไม่มีใครรู้จนกว่า preflight จะบอก
    ว่าไฟล์สำรองเก่า — เทสต์การรันคำสั่งจริงอยู่ใน test_backup.py (ต้องใช้
    subprocess เพราะ TestCase ห่อ transaction ที่ไม่ commit แล้ว sqlite3
    backup() จะ deadlock — recipe ที่เคยเสียเวลาไล่)
    """

    def test_backup_db_accepts_path_database_name(self):
        """settings ใช้ `DATABASES['NAME']` เป็น `Path` — คำสั่งสำรองต้องรันได้

        รันผ่าน subprocess ด้วย settings จริงของโปรเจกต์ (ซึ่งประกาศ NAME เป็น
        `BASE_DIR / 'db.sqlite3'`) เพราะ TestCase ห่อ transaction ที่ยังไม่ commit
        แล้ว sqlite3 `backup()` จะ deadlock — เคยเสียเวลาไล่บั๊กนี้ไปแล้ว
        """
        import os
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, 'manage.py', 'backup_db', '--dir', tmp],
                cwd=str(settings.BASE_DIR),
                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=180,
            )
        self.assertEqual(
            proc.returncode, 0,
            f'backup_db ล้มเมื่อชื่อฐานข้อมูลเป็น Path:\n{proc.stderr[-800:]}')
        self.assertIn('สำรองแล้ว', proc.stdout)
