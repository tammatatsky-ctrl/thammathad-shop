"""เทสต์ `manage.py backup_db` — ปิดช่องโหว่ "ข้อมูลหายกู้ไม่ได้".

เหตุผลที่ต้องมีเทสต์: สำรอง DB ที่ "ทำแล้วดูเหมือนสำเร็จ" แต่ไฟล์เสีย
หรือไม่มีตารางจริง = แย่กว่าไม่มี backup เลย (เจ้าของร้านเชื่อว่ามีสำรอง
แล้วพบว่ากู้ไม่ได้ตอนที่ต้องการที่สุด) — เทสต์นี้ยืนยันว่า
ไฟล์ที่ได้ "เปิดเป็นฐานข้อมูลจริง" ได้ ไม่ใช่แค่มีไฟล์เกิดขึ้น

บันทึกบั๊กจากการเขียนเทสต์นี้ (เคยทำให้ทั้งชุดเทสต์ค้าง):
    1) Django TestCase ห่อทุกเทสต์ด้วย transaction.atomic() ที่ยังไม่ commit
       → การเรียก sqlite3 backup() จาก connection ที่ค้างใน transaction แบบนั้น
       **ค้างถาวร** (deadlock บน shared-cache in-memory DB) ทำให้ทั้งชุดเทสต์
       ติด timeout ไม่ใช่แค่เทสต์นี้ fail
       แก้โดย: override_settings(DATABASES=...) อย่างเดียวไม่พอ เพราะ Django
       ไม่สลับ connection ที่เปิดอยู่ (settings_dict ถูก snapshot ตอนสร้าง)
       ต้องเรียก connections.close_all() ก่อน และยังช้าอยู่เพราะ test runner
       แชร์ in-memory DB — ทางที่ชัดเจนและเร็วที่สุดคือ **รันคำสั่งผ่าน subprocess**
       ใช้ settings ชั่วคราวของตัวเอง (จำลอง production ตรงที่สุด)
    2) sqlite3 ไม่รับ utf-8 BOM ของไฟล์ .py — เขียนไฟล์ settings ชั่วคราวด้วย
       Python (open(..., 'wb')) ห้ามใช้ PowerShell (recipe #1)
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import TestCase

PROJECT_DIR = Path(settings.BASE_DIR)


def _write_settings_module(path: Path, db_path: Path):
    """สร้าง settings ชั่วคราวที่ชี้ DB ไปไฟล์ทดสอบ (เขียนแบบไม่มี BOM)"""
    src = (PROJECT_DIR / 'myproject' / 'settings.py').read_text(encoding='utf-8')
    src = src.replace("load_dotenv()", "load_dotenv(override=True)")
    lines = [
        '"""settings ชั่วคราวสำหรับเทสต์ backup_db — ชี้ DB ไปไฟล์ทดสอบ."""',
        src,
        '',
        '# --- override จุดเดียว: ฐานข้อมูล ---',
        'DATABASES = {"default": {**DATABASES["default"], "NAME": %r}}' % str(db_path),
        '',
    ]
    with open(path, 'wb') as f:      # 'wb' = ไม่ใส่ BOM (sqlite3/import บางตัวอ่านไม่รับ)
        f.write('\n'.join(lines).encode('utf-8'))


class BackupDbCommandTest(TestCase):
    """สำรอง → เปิดตรวจว่ากู้ได้ → prune ไฟล์เก่า (รันผ่าน subprocess)"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.src = self.tmp / 'source.sqlite3'
        self.out_dir = self.tmp / 'backups'

        self.settings_mod = self.tmp / 'test_settings_backup.py'
        _write_settings_module(self.settings_mod, self.src)

        # migrate ไฟล์ทดสอบหนึ่งครั้ง แล้วใส่ข้อมูลจริง (ออเดอร์ + พนักงาน)
        self._manage('migrate', '--noinput')
        self._seed()

    def tearDown(self):
        self._tmp.cleanup()

    def _manage(self, *args):
        """เรียก manage.py ด้วย settings ชั่วคราว → (returncode, stdout, stderr)"""
        proc = subprocess.run(
            [sys.executable, 'manage.py', *args],
            cwd=str(PROJECT_DIR),
            env={
                **os.environ,
                'DJANGO_SETTINGS_MODULE': 'test_settings_backup',
                'PYTHONPATH': f'{PROJECT_DIR};{self.tmp}',
                'PYTHONIOENCODING': 'utf-8',   # ไม่งั้น stderr ภาษาไทยกลายเป็น mojibake
            },
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=180,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def _seed(self):
        """ใส่ข้อมูลตัวอย่างที่ 'กู้คืนแล้วต้องได้ครบ' (ใช้ raw sqlite3 ตรง ๆ)"""
        conn = sqlite3.connect(self.src)
        try:
            with conn:
                conn.execute(
                    'INSERT INTO myapp_employee (emp_code, name, gender, department,'
                    ' email, phone, status, salary, hire_date, address, avatar,'
                    ' created_at) VALUES (?,?,?,?,?,?,?,?,?,?,NULL,?)',
                    ('E-TEST', 'ทดสอบ สำรอง', 'M', 'ไอที', '', '0800000001',
                     'active', '25000.00', '2026-01-15', '', '2026-01-15 09:00:00'),
                )
                conn.execute(
                    'INSERT INTO myapp_order (customer_name, phone, address, total,'
                    ' status, payment_method, created_at) VALUES (?,?,?,?,?,?,?)',
                    ('ลูกค้า ทดสอบ', '0800000002', 'กรุงเทพฯ', 1234.00,
                     'pending', 'promptpay', '2026-01-15 09:00:00'),
                )
        finally:
            conn.close()

    def _backup(self, *extra):
        return self._manage('backup_db', '--dir', str(self.out_dir), '--verify', *extra)

    # ---------- หัวใจของเทสต์: ไฟล์ต้อง "กู้ได้จริง" ----------
    def test_backup_file_is_restorable_with_data(self):
        """ไฟล์สำรองต้องเปิดเป็น DB ได้ มีตารางครบ และมีข้อมูลจริง (ไม่ใช่ DB ว่าง)"""
        rc, out, err = self._backup()
        self.assertEqual(rc, 0, f'คำสั่งล้มเหลว:\n{out}\n{err}')

        files = list(self.out_dir.glob('db-*.sqlite3'))
        self.assertEqual(len(files), 1, 'ต้องได้ไฟล์สำรอง 1 ไฟล์')

        conn = sqlite3.connect(files[0])
        try:
            integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
            tables = conn.execute(
                "select count(*) from sqlite_master where type='table'").fetchone()[0]
            employees = conn.execute('select name from myapp_employee').fetchall()
            orders = conn.execute(
                'select customer_name, total from myapp_order').fetchall()
        finally:
            conn.close()

        self.assertEqual(integrity, 'ok', 'ไฟล์สำรองต้องผ่าน integrity_check')
        self.assertGreaterEqual(tables, 15, 'ต้องมีตารางครบ (auth/token รวม) ไม่ใช่ DB ว่าง')
        self.assertEqual(len(employees), 1, 'ข้อมูลพนักงานต้องถูกสำรอง')
        self.assertEqual(len(orders), 1, 'ข้อมูลออเดอร์/ยอดเงินต้องถูกสำรอง')
        self.assertEqual(orders[0][1], 1234.00, 'ยอดเงินต้องถูกต้อง ไม่ใช่ 0 หรือ NULL')

    def test_backup_is_read_only_on_source(self):
        """การสำรองต้องไม่แก้ไขไฟล์ต้นฉบับ (ถ้าผิด = ข้อมูลร้านเสี่ยง)"""
        before = self.src.read_bytes()
        rc, out, err = self._backup()
        self.assertEqual(rc, 0, f'{out}\n{err}')
        self.assertEqual(self.src.read_bytes(), before,
                         'ไฟล์ DB ต้นฉบับถูกแก้ระหว่างสำรอง — อันตรายมาก')

    # ---------- รูปแบบชื่อไฟล์ ----------
    def test_backup_name_is_timestamped_and_sortable(self):
        """ชื่อไฟล์เรียงตามเวลาได้ (Ymd-HMS) — สำคัญต่อการลบไฟล์เก่าแบบ --keep"""
        rc, out, err = self._backup()
        self.assertEqual(rc, 0, f'{out}\n{err}')
        stem = list(self.out_dir.glob('db-*.sqlite3'))[0].stem
        self.assertRegex(stem, r'^db-\d{8}-\d{6}$',
                         'ชื่อไฟล์ต้องเป็น db-YYYYmmdd-HHMMSS เพื่อ sort ตามเวลาได้')

    # ---------- prune ----------
    def test_keep_prunes_old_backups(self):
        """--keep N ต้องเหลือล่าสุด N ไฟล์ (กันพื้นที่เต็มบน PythonAnywhere)"""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        for extra in ('20200101-000000', '20200102-000000', '20200103-000000'):
            (self.out_dir / f'db-{extra}.sqlite3').write_bytes(b'')
        self.assertEqual(len(list(self.out_dir.glob('db-*.sqlite3'))), 3)

        rc, out, err = self._backup('--keep', '2')
        self.assertEqual(rc, 0, f'{out}\n{err}')
        remaining = sorted(p.name for p in self.out_dir.glob('db-*.sqlite3'))
        self.assertEqual(len(remaining), 2, f'--keep 2 ต้องเหลือ 2 ไฟล์ แต่ได้ {remaining}')
        self.assertTrue(any(n.endswith('20200103-000000.sqlite3') for n in remaining),
                        'ต้องเก็บไฟล์ที่ "ใหม่สุดตามชื่อ" ไว้')

    # ---------- พฤติกรรมเมื่อผิดพลาด ----------
    def test_missing_database_fails_loudly(self):
        """ไม่มีไฟล์ DB → ต้อง error ชัดเจน ไม่ใช่พิมพ์ว่า "สำรองสำเร็จ" ลอย ๆ"""
        missing = self.tmp / 'does_not_exist.sqlite3'
        mod = self.tmp / 'test_settings_missing.py'
        _write_settings_module(mod, missing)
        proc = subprocess.run(
            [sys.executable, 'manage.py', 'backup_db', '--dir', str(self.out_dir)],
            cwd=str(PROJECT_DIR),
            env={
                **os.environ,
                'DJANGO_SETTINGS_MODULE': 'test_settings_missing',
                'PYTHONPATH': f'{PROJECT_DIR};{self.tmp}',
                'PYTHONIOENCODING': 'utf-8',
            },
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=180,
        )
        self.assertNotEqual(proc.returncode, 0, 'ต้อง exit ไม่ 0')
        self.assertIn('ไม่พบฐานข้อมูล', proc.stderr + proc.stdout)
        self.assertFalse(self.out_dir.exists() and list(self.out_dir.glob('*.sqlite3')),
                         'ต้องไม่สร้างไฟล์สำรองปลอมเมื่อ source ไม่มี')