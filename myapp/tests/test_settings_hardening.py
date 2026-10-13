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
        "print('HSTS=%s' % getattr(s, 'SECURE_HSTS_SECONDS', 0));"
        "print('CSRF_ORIGINS=%s' % ','.join(getattr(s, 'CSRF_TRUSTED_ORIGINS', None) or []));"
        "print('EMAIL_CONFIGURED=%s' % getattr(s, 'EMAIL_CONFIGURED', False));"
        "print('REFERER=%s' % getattr(s, 'SECURE_REFERRER_POLICY', ''))"
    )
    proc = subprocess.run([sys.executable, '-c', code], cwd=str(PROJECT_DIR),
                          env=env, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


def _value(out: str, key: str) -> str:
    """ดึงค่าจากบรรทัด `KEY=value` ที่ subprocess พิมพ์มา"""
    for line in out.splitlines():
        if line.startswith(f'{key}='):
            return line.split('=', 1)[1]
    raise AssertionError(f'ไม่พบ "{key}" ในผลลัพธ์:\n{out}')


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
        hsts = _value(out, 'HSTS')
        self.assertNotEqual(hsts, '0', 'HSTS ต้องถูกตั้งใน production')


class ProductionHstsPolicyTest(TestCase):
    """HSTS ต้อง "ไล่ระดับ" ไม่ใช่เปิด 30 วันทันที

    HSTS ผูก browser แบบย้อนกลับไม่ได้: ถ้าเปิด 30 วันแล้ว https/cookie พัง
    ผู้ใช้จะกู้ได้ยากมาก (ต้องเปิด devtools ล้าง header) → จึงเริ่มจาก 1 วัน
    แล้วค่อยขยายผ่าน env `HSTS_DAYS` เมื่อมั่นใจ
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        _make_clean_settings(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _prod(self, **extra):
        env = {'DJANGO_DEBUG': '0', 'DJANGO_SECRET_KEY': 'c' * 50, **extra}
        return _boot_settings(env, self.tmp)

    def test_default_is_one_day_not_thirty(self):
        rc, out, err = self._prod()
        self.assertEqual(rc, 0, f'{err}')
        self.assertEqual(_value(out, 'HSTS'), str(86400),
                         'ค่าเริ่มต้นต้องเป็น 1 วัน ไม่ใช่ 30 วัน')

    def test_hsts_days_env_can_extend_it(self):
        """ยืนยันว่ากลไกขยายใช้งานได้จริง ไม่ใช่แค่ค่าตาย"""
        rc, out, err = self._prod(HSTS_DAYS='7')
        self.assertEqual(rc, 0, f'{err}')
        self.assertEqual(_value(out, 'HSTS'), str(7 * 86400))

    def test_invalid_hsts_days_falls_back_to_one_day(self):
        """ค่าผิดพลาดต้อง fallback ไปค่าปลอดภัย ไม่ใช่พังหรือใช้ค่าใหญ่"""
        rc, out, err = self._prod(HSTS_DAYS='ไม่ใช่ตัวเลข')
        self.assertEqual(rc, 0, f'ค่าผิดต้องไม่ควรทำให้เว็บพัง:\n{err}')
        self.assertEqual(_value(out, 'HSTS'), str(86400))


class ProductionCsrfOriginTest(TestCase):
    """ต้องมี CSRF_TRUSTED_ORIGINS ครอบคลุมโดเมนจริง

    เว็บอยู่หลัง proxy ของ PythonAnywhere ถ้า origin ไม่ตรง Django จะตอบ
    "CSRF verification failed" โดยผู้ใช้ไม่มีทางแก้ = ส่งฟอร์มไม่ได้เลย
    (โดยเฉพาะการสั่งซื้อ / login / เปลี่ยนรหัสผ่าน)
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        _make_clean_settings(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _prod(self, **extra):
        env = {'DJANGO_DEBUG': '0', 'DJANGO_SECRET_KEY': 'd' * 50, **extra}
        return _boot_settings(env, self.tmp)

    def test_origin_derived_from_allowed_hosts(self):
        rc, out, err = self._prod()
        self.assertEqual(rc, 0, f'{err}')
        origins = _value(out, 'CSRF_ORIGINS')
        self.assertIn('tammatat.pythonanywhere.com', origins,
                      f'ต้องครอบคลุมโดเมนจริง ได้ "{origins}"')

    def test_localhost_and_ip_are_excluded(self):
        """127.0.0.1/localhost ไม่มีความหมายในเว็บจริง — ไม่ควรอยู่ในรายการ"""
        rc, out, err = self._prod()
        self.assertEqual(rc, 0, f'{err}')
        origins = _value(out, 'CSRF_ORIGINS')
        self.assertNotIn('127.0.0.1', origins)
        self.assertNotIn('localhost', origins)

    def test_env_override_wins(self):
        """deployer ต้อง override ได้เมื่อเว็บอยู่โดเมนอื่น (เช่น www)"""
        rc, out, err = self._prod(
            CSRF_TRUSTED_ORIGINS='https://www.example.com,https://example.com')
        self.assertEqual(rc, 0, f'{err}')
        origins = _value(out, 'CSRF_ORIGINS')
        self.assertIn('www.example.com', origins)
        self.assertNotIn('tammatat', origins)

    def test_referrer_policy_set(self):
        """ป้องกัน path ของหน้าหลุดไปกับ referrer ไปยังเว็บอื่น"""
        rc, out, err = self._prod()
        self.assertEqual(rc, 0, f'{err}')
        self.assertEqual(_value(out, 'REFERER'), 'same-origin')


class ProductionEmailConfigTest(TestCase):
    """EMAIL_URL ต้องเปิด SMTP จริงเมื่อตั้งค่า (ไม่ใช่แค่ผ่านฉาก)"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        _make_clean_settings(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _prod(self, **extra):
        env = {'DJANGO_DEBUG': '0', 'DJANGO_SECRET_KEY': 'e' * 50, **extra}
        return _boot_settings(env, self.tmp)

    def test_email_unconfigured_by_default(self):
        rc, out, err = self._prod()
        self.assertEqual(rc, 0, f'{err}')
        self.assertIn('EMAIL_CONFIGURED=False', out,
                      'ไม่มี EMAIL_URL ต้องรายงานว่ายังไม่ได้ตั้ง (ไม่ใช่ค่าเริ่มต้นที่โกหก)')

    def test_email_url_enables_backend(self):
        rc, out, err = self._prod(
            EMAIL_URL='smtp://user:pass@smtp.example.com:587/?starttls=1')
        self.assertEqual(rc, 0, f'{err}')
        self.assertIn('EMAIL_CONFIGURED=True', out,
                      'ตั้ง EMAIL_URL แล้วต้องรายงานว่าเปิดใช้งาน')


class NoHardcodedSecretInSourceTest(TestCase):
    """ไฟล์ settings ต้องไม่มี SECRET_KEY ฝังไว้แล้ว (เคยมี → ใครก็อ่านได้จาก git)"""

    def test_settings_has_no_literal_secret_key_fallback(self):
        src = (PROJECT_DIR / 'myproject' / 'settings.py').read_text(encoding='utf-8')
        self.assertNotIn('django-insecure-', src,
                         'ยังมี dev secret key ฝังอยู่ใน settings.py')
        self.assertNotIn('Shop2026!', src,
                         'ยังมีรหัสผ่านจริงฝังอยู่ใน settings.py')