"""เทสต์ fail-closed ของ settings — กัน "ลืมตั้ง env แล้วเว็บรั่วเงียบ ๆ"

เหตุผลที่สำคัญที่สุดของไฟล์นี้:
    เดิม `DEBUG = os.environ.get('DJANGO_DEBUG', '1') != '0'` = **fail-open**
    คือ "ลืมตั้ง env = เปิด debug = หน้า error สีเหลืองโชว์ GEMINI_API_KEY
    และ hardening 7 ข้อ (SSL/cookie/HSTS) ที่อยู่ใต้ `if not DEBUG` ไม่ทำงาน"
    ค่า default แบบนั้นอันตรายกว่าไม่มี default เลย เพราะ deploy ผิดจะไม่มีอาการ
    ให้เห็น — ระบบรันได้ปกติแต่ไม่ปลอดภัย (ตอนนี้เป็น fail-closed: boot ไม่ได้
    ถ้าตั้ง env ไม่ครบ ซึ่งดีกว่ารันแล้วรั่ว)

เทสต์ทั้งหมดรัน settings ใน **subprocess** เพราะ:
    - `override_settings(DATABASES=...)` ไม่สลับ connection ที่เปิดอยู่
    - การแก้ `os.environ` ใน process ที่รันเทสต์จะรั่วข้ามเทสต์อื่น
    - ทดสอบ "ตอน import settings" จริง ซึ่งคือจุดที่จะพังตอน deploy
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import TestCase

PROJECT_DIR = Path(settings.BASE_DIR)


def _make_clean_settings(tmp_dir: Path):
    """สร้าง settings ชั่วคราวที่ 'ไม่อ่าน .env' — เทสต์นี้ต้องควบคุม env เอง

    ทำไมต้องทำ: `load_dotenv()` ใน settings.py จะอ่านไฟล์ .env ของเครื่อง dev
    เสมอ แม้เราจะ "ลบ env ออก" จาก os.environ ของ subprocess — ค่าใน .env
    จะถูกโหลดกลับเข้ามาแล้วทำให้เทสต์ผ่านทั้งที่ production จะพัง
    วิธีนี้คือ "ตัดแหล่งรบกวนออก" แทนที่จะพยายามลบทีหลัง

    เขียนด้วย open(...,'wb') ไม่ใส่ BOM (recipe #1 — BOM ทำให้ settings
    แรกบรรทัดเป็น text ก่อนโค้ด แล้ว import ไม่ผ่าน)
    """
    src = (PROJECT_DIR / 'myproject' / 'settings.py').read_text(encoding='utf-8')
    # ตัดการโหลด .env ออก (แทนที่เป็น pass) — ให้ env ที่ test ส่งเข้าไปเป็นแหล่งเดียว
    src = src.replace('load_dotenv()', 'pass  # .env ถูกปิดโดยเทสต์')
    path = tmp_dir / 'test_settings_clean.py'
    with open(path, 'wb') as f:
        f.write(('# settings ชั่วคราวสำหรับ test_settings_hardening — ไม่อ่าน .env\n'
                 + src).encode('utf-8'))
    return path


def _boot_settings(env_overrides: dict, tmp_dir: Path):
    """import settings ใน subprocess พร้อม env ที่กำหนด → (returncode, stdout, stderr)"""
    env = {**os.environ}
    for key in ('DJANGO_DEBUG', 'DJANGO_SECRET_KEY', 'GEMINI_API_KEY', 'SLIPOK_API_KEY'):
        env.pop(key, None)
    env.update(env_overrides)
    env['DJANGO_SETTINGS_MODULE'] = 'test_settings_clean'
    env['PYTHONPATH'] = os.pathsep.join([str(tmp_dir), str(PROJECT_DIR)])

    code = (
        'import django; django.setup();'
        'from django.conf import settings as s;'
        "print('DEBUG=%s' % s.DEBUG);"
        "print('SECRET_SET=%s' % bool(s.SECRET_KEY));"
        "print('SSL_REDIRECT=%s' % getattr(s, 'SECURE_SSL_REDIRECT', False));"
        "print('HSTS=%s' % getattr(s, 'SECURE_HSTS_SECONDS', 0))"
    )
    proc = subprocess.run([sys.executable, '-c', code], cwd=str(PROJECT_DIR),
                          env=env, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


class DebugFailsClosedTest(TestCase):
    """DEBUG ต้องเป็น 'ปิด' เมื่อไม่ได้ประกาศค่า (fail-closed ไม่ใช่ fail-open)"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        _make_clean_settings(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_debug_off_when_env_missing(self):
        """ไม่ตั้ง DJANGO_DEBUG เลย → ต้อง DEBUG=False (ไม่ใช่ True แบบเดิม)

        ต้องใส่ SECRET_KEY ไปด้วย เพราะ "ไม่ประกาศ DEBUG" = production
        = ต้องมี key (ไม่มี key จะ error — ซึ่งถูกต้อง แต่ทำให้ทดสอบนี้วัด
        เรื่อง DEBUG ไม่ได้) — ดู test_missing_secret_in_production_raises
        สำหรับเคสที่ไม่มี key
        """
        rc, out, err = _boot_settings({'DJANGO_SECRET_KEY': 'b' * 50}, self.tmp)
        self.assertEqual(rc, 0, f'settings ต้อง boot ได้:\n{err}')
        self.assertIn('DEBUG=False', out,
                      'default ต้องเป็น DEBUG=False — ถ้าเป็น True = fail-open (รั่ว)')

    def test_debug_on_only_when_explicitly_enabled(self):
        """ประกาศ DJANGO_DEBUG=1 ชัดเจน → เปิดได้ (สำหรับ dev)"""
        rc, out, err = _boot_settings({'DJANGO_DEBUG': '1'}, self.tmp)
        self.assertEqual(rc, 0, f'{err}')
        self.assertIn('DEBUG=True', out)


class SecretKeyFailsClosedTest(TestCase):
    """ไม่มี SECRET_KEY ตอน production → ต้อง error ไม่ใช่ใช้ค่า dev ฝังในโค้ด"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        _make_clean_settings(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_secret_in_production_raises(self):
        """DJANGO_DEBUG=0 + ไม่มี SECRET_KEY → RuntimeError (ป้องกัน session forge)"""
        rc, out, err = _boot_settings({'DJANGO_DEBUG': '0'}, self.tmp)
        self.assertNotEqual(rc, 0, 'ต้อง boot ไม่ได้ (fail-closed)')
        self.assertIn('DJANGO_SECRET_KEY', err + out,
                      'ข้อความ error ต้องบอกว่าต้องตั้ง env อะไร')

    def test_secret_key_present_in_production_boots(self):
        """ตั้งครบทั้งสองค่า → boot ได้และ hardening ต้องทำงาน"""
        rc, out, err = _boot_settings({
            'DJANGO_DEBUG': '0', 'DJANGO_SECRET_KEY': 'a' * 50,
        }, self.tmp)
        self.assertEqual(rc, 0, f'ตั้งครบแล้วต้องรันได้:\n{err}')
        self.assertIn('DEBUG=False', out)
        self.assertIn('SSL_REDIRECT=True', out,
                      'production ต้องบังคับ https (อยู่ใต้ if not DEBUG)')
        hsts = [ln for ln in out.splitlines() if ln.startswith('HSTS=')][0]
        self.assertNotEqual(hsts, 'HSTS=0', 'HSTS ต้องถูกตั้งใน production')


class NoHardcodedSecretInSourceTest(TestCase):
    """ไฟล์ settings ต้องไม่มี SECRET_KEY ฝังไว้แล้ว (เคยมี → ใครก็อ่านได้จาก git)"""

    def test_settings_has_no_literal_secret_key_fallback(self):
        src = (PROJECT_DIR / 'myproject' / 'settings.py').read_text(encoding='utf-8')
        self.assertNotIn('django-insecure-', src,
                         'ยังมี dev secret key ฝังอยู่ใน settings.py')
        self.assertNotIn('Shop2026!', src,
                         'ยังมีรหัสผ่านจริงฝังอยู่ใน settings.py')