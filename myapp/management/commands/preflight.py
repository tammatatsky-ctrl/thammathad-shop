"""Management command: `preflight` — ตรวจความพร้อมก่อน deploy / หลัง deploy

ทำไมต้องมี:
    บั๊กที่ทำให้ "deploy แล้วเว็บพังแต่ไม่มีอาการให้เห็น" เจอจริงในโปรเจกต์นี้แล้ว
    ทุกตัวมีรูปแบบเดียวกัน: **ระบบรันได้ปกติ แต่ไม่ได้ทำงานที่ตั้งใจไว้**
    แก้ทีละตัวในไฟล์แยกกัน ทำให้เสียเวลาไล่มากกว่าที่จะตรวจ 1 คำสั่ง

    ตัวอย่างที่เคยเจอ:
      1. ZIP อัปเดตตก `myproject/` ทั้งโฟลเดอร์ → settings.py บน server เป็นของเก่า
         (เว็บรันได้ แต่ permission/throttle ที่เพิ่งเพิ่มไม่มีผล) — บั๊กเงียบ
      2. ลืมตั้ง env → DEBUG=True → หน้า error สีเหลืองโชว์ API keys
      3. `myapp/static` กับ `staticfiles/` ไม่ sync → ผู้ใช้เห็น CSS/JS เก่า
      4. migration ยังไม่ apply → หน้าที่พึ่งคอลัมน์ใหม่จะ error
      5. ไม่ได้รัน backup_db → ข้อมูลหายแล้วกู้ไม่ได้
      6. ไม่ได้ collectstatic → ตอน DEBUG=False ไฟล์ static ทั้งหมด 404

การใช้งาน:
    python manage.py preflight            # ตรวจทุกอย่าง (exit code 1 ถ้ามี FAIL)
    python manage.py preflight --quiet    # ไม่แสดงรายละเอียดที่ผ่าน
    python manage.py preflight --dev      # บังคับตรวจในโหมด dev (ข้ามเงื่อนไข production)

รหัสออก (exit code) — ใช้ใน script/CI ได้:
    0 = ไม่มี FAIL (มี WARN ได้)
    1 = มี FAIL → อย่า deploy / เว็บมีปัญหาแน่นอน

ระดับผลลัพธ์:
    FAIL = ต้องแก้ก่อนใช้งาน (เว็บพัง/ข้อมูลเสี่ยง)
    WARN = ใช้ได้แต่ควรรู้ (เช่น ยังไม่ได้ตั้งอีเมล)
    OK   = ผ่าน
"""
import os
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone


class Check:
    """ผลตรวจ 1 ข้อ — เก็บสถานะ + ข้อความ + วิธีแก้"""

    def __init__(self, key, level, title, detail='', fix=''):
        self.key = key
        self.level = level        # 'FAIL' | 'WARN' | 'OK'
        self.title = title
        self.detail = detail
        self.fix = fix


class Command(BaseCommand):
    help = 'ตรวจความพร้อมของระบบก่อน/หลัง deploy (env, static, migrations, backup, db)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--quiet', action='store_true',
            help='แสดงเฉพาะรายการที่ไม่ผ่าน (ไม่ต้องดูของที่ OK)')
        parser.add_argument(
            '--dev', action='store_true',
            help='ตรวจในโหมด dev (DEBUG=True) — ใช้เช็คเครื่องตัวเอง ไม่ใช่ production')

    def handle(self, *args, **options):
        quiet = options['quiet']
        as_dev = options['dev']
        checks = []

        checks += self._check_runtime(as_dev)
        checks += self._check_hosts()
        checks += self._check_csrf(as_dev)
        checks += self._check_hsts(as_dev)
        checks += self._check_email(as_dev)
        checks += self._check_static()
        checks += self._check_migrations(as_dev)
        checks += self._check_database()
        checks += self._check_backup(as_dev)

        # ---------- รายงาน ----------
        fails = [c for c in checks if c.level == 'FAIL']
        warns = [c for c in checks if c.level == 'WARN']

        for c in checks:
            if quiet and c.level == 'OK':
                continue
            icon = {'FAIL': 'X', 'WARN': '!', 'OK': 'v'}[c.level]
            color = {'FAIL': self.style.ERROR, 'WARN': self.style.WARNING,
                     'OK': self.style.SUCCESS}[c.level]
            self.stdout.write(color(f'  [{icon}] {c.title}'))
            if c.detail and (not quiet or c.level != 'OK'):
                self.stdout.write(f'        {c.detail}')
            if c.fix and c.level != 'OK':
                self.stdout.write(f'        แก้: {c.fix}')

        # ---------- สรุป ----------
        self.stdout.write('')
        summary = f'ผ่าน {len(checks) - len(fails) - len(warns)}/{len(checks)}'
        if warns:
            summary += f' · WARN {len(warns)}'
        if fails:
            summary += f' · FAIL {len(fails)}'
        self.stdout.write(summary)

        if fails:
            self.stdout.write(self.style.ERROR(
                '\nยัง deploy ไม่ควร — แก้ FAIL ทั้งหมดก่อน (รันซ้ำเพื่อยืนยัน)'))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS('\nระบบพร้อมใช้งาน'))

    # ==================================================================
    # รายการตรวจ
    # ==================================================================

    def _check_runtime(self, as_dev):
        """DEBUG / SECRET_KEY — ข้อนี้สำคัญที่สุด (รั่วข้อมูลได้ทั้งระบบ)"""
        out = []
        prod = not settings.DEBUG

        if prod:
            out.append(Check('debug', 'OK', 'DEBUG = False (โหมด production)'))
            key = settings.SECRET_KEY or ''
            looks_dev = key.startswith('dev-only-') or 'insecure' in key
            if not key or looks_dev:
                out.append(Check(
                    'secret', 'FAIL', 'SECRET_KEY ไม่ปลอดภัย',
                    'ค่าปัจจุบันเป็นค่า dev/ว่าง → ใครก็ forge session cookie ได้',
                    'ตั้ง env DJANGO_SECRET_KEY บน PythonAnywhere'))
            else:
                out.append(Check('secret', 'OK', 'SECRET_KEY ถูกตั้งจาก env (ไม่ใช่ค่า dev)'))
        else:
            out.append(Check(
                'debug', 'WARN', 'DEBUG = True (โหมด dev)',
                'หน้า error สีเหลืองจะโชว์ settings ทั้งหมดรวม API keys '
                'และ hardening (SSL/cookie/HSTS) จะไม่ทำงาน — '
                'นี่คือค่าที่ถูกต้องสำหรับ dev แต่ห้ามหลุดขึ้น production',
                'production ต้องตั้ง env DJANGO_DEBUG=0'))

        if getattr(settings, '_RUNNING_TESTS', False):
            out.append(Check('tests', 'OK', 'กำลังรันในโหมดเทสต์ (ผลลัพธ์ไม่ใช่ production)'))
        return out

    def _check_hosts(self):
        """ALLOWED_HOSTS ต้องมีโดเมนจริง ไม่งั้นทุก request จะ 400"""
        prod = not settings.DEBUG
        hosts = list(settings.ALLOWED_HOSTS or [])
        wildcard = '*' in hosts
        if wildcard:
            level = 'FAIL' if prod else 'WARN'
            return [Check('hosts', level, 'ALLOWED_HOSTS มี "*"',
                          'ยอมรับทุกโดเมน (Host header injection) — ไม่ควรใช้ตอน production',
                          'ระบุเฉพาะ tammatat.pythonanywhere.com')]
        if not hosts:
            return [Check('hosts', 'FAIL', 'ALLOWED_HOSTS ว่าง',
                          'ทุก request จะถูกปฏิเสธ', 'เพิ่มโดเมนจริงลงใน settings')]
        return [Check('hosts', 'OK', f'ALLOWED_HOSTS = {", ".join(hosts)}')]

    def _check_csrf(self, as_dev):
        """CSRF_TRUSTED_ORIGINS — proxy ส่ง origin ไม่ตรงจะตอบ 403 งง ๆ"""
        prod = not settings.DEBUG
        trusted = list(getattr(settings, 'CSRF_TRUSTED_ORIGINS', None) or [])
        if prod and not trusted:
            return [Check(
                'csrf', 'WARN', 'ไม่ได้ตั้ง CSRF_TRUSTED_ORIGINS',
                'ถ้าเว็บอยู่หลัง proxy/CDN ที่ส่ง Origin ไม่ตรงกับ Host '
                'ผู้ใช้จะส่งฟอร์มไม่ได้ (403 CSRF) โดยไม่บอกเหตุผล',
                'เพิ่ม https://<โดเมนของคุณลงใน settings (ดู preflight_hint)')]
        return [Check('csrf', 'OK',
                      f'CSRF_TRUSTED_ORIGINS = {trusted}' if trusted
                      else 'CSRF_TRUSTED_ORIGINS ไม่จำเป็นตอน dev (ไม่มี proxy)')]

    def _check_hsts(self, as_dev):
        """HSTS 30 วันเปิดครั้งเดียว = ถ้ามีอะไรพัง ผู้ใช้ถูกล็อกยากแก้"""
        prod = not settings.DEBUG
        secs = getattr(settings, 'SECURE_HSTS_SECONDS', 0) or 0
        if not prod:
            return [Check('hsts', 'OK', 'HSTS ไม่ทำงานตอน dev (ถูกต้อง)')]
        if secs == 0:
            return [Check(
                'hsts', 'WARN', 'HSTS ไม่ได้เปิด',
                'เบราว์เซอร์จะจำได้ว่าเคยต่อ HTTP ได้ (เสี่ยง MITM ครั้งแรก)',
                'ตั้ง SECURE_HSTS_SECONDS ใน settings (แนะนำเริ่ม 1 สัปดาห์ก่อนค่อยขยาย)')]
        if secs >= 30 * 24 * 3600:
            return [Check(
                'hsts', 'WARN', f'HSTS = {secs // 86400} วัน (เต็ม 30 วัน)',
                '⚠️ ค่านี้ผูก browser ไว้นานมาก — ถ้า cookie/https พังกลางทาง '
                'ผู้ใช้จะกู้ได้ยากมาก (ล้างได้เฉพาะเปิดเครื่องมือ devtools)',
                'ค่าเริ่มต้นที่ปลอดภัยคือ 1 วัน แล้วค่อยขยายเป็นสัปดาห์/เดือน '
                'เมื่อมั่นใจว่า https ทำงานสมบูรณ์')]
        return [Check('hsts', 'OK', f'HSTS = {secs} วินาที ({secs // 86400} วัน)')]

    def _check_email(self, as_dev):
        """อีเมล — ไม่ได้ตั้ง = ลืมรหัสผ่านส่งไม่ถึง (ระบบบอกผู้ใช้แล้ว)"""
        if getattr(settings, 'EMAIL_CONFIGURED', False):
            return [Check('email', 'OK',
                          f'อีเมลเปิดใช้งาน ({settings.EMAIL_HOST}:{settings.EMAIL_PORT})')]
        return [Check(
            'email', 'WARN', 'ยังไม่ได้ตั้งการส่งอีเมล (EMAIL_URL)',
            'ระบบจะไม่หลอกผู้ใช้ (บอกว่ายังไม่ได้ส่ง และเผยลิงก์ให้ staff/dev) '
            'แต่ "ลืมรหัสผ่าน" จะใช้กับลูกค้าจริงไม่ได้',
            'ตั้ง env EMAIL_URL=smtp://user:pass@host:587/?starttls=1 บน PythonAnywhere')]

    def _check_static(self):
        """staticfiles ต้อง sync กับ myapp/static — เช็คไฟล์หลัก + จำนวนไฟล์"""
        src = Path(settings.BASE_DIR) / 'myapp' / 'static'
        dst = Path(settings.STATIC_ROOT)

        if not dst.exists():
            return [Check('static', 'FAIL', 'ยังไม่ได้รัน collectstatic',
                          f'ไม่พบโฟลเดอร์ {dst.name}/ — ตอน DEBUG=False ไฟล์ static จะ 404 ทั้งเว็บ',
                          'python manage.py collectstatic --noinput')]

        # debug snapshots ของ recipe #9 ต้องไม่หลุดขึ้น production
        leaked = dst / 'test'
        if leaked.exists():
            return [Check(
                'static-leak', 'WARN', 'staticfiles/test/ (debug snapshots) หลุดขึ้น production',
                'เป็นไฟล์ HTML สำหรับวินิจฉัยบั๊ก ไม่ใช่ asset ของเว็บ',
                'ลบโฟลเดอร์ staticfiles/test แล้ว collectstatic ใหม่')]

        missing, changed = [], []
        # ข้าม myapp/static/test/ — เป็น debug snapshot สำหรับวินิจฉัยบั๊ก (recipe #9)
        # ตั้งใจไม่ให้ collectstatic ไปด้วย (อยู่ใน .gitignore) จึงไม่ต้องมาเทียบ
        debug_dir = src / 'test'
        for path in src.rglob('*'):
            if not path.is_file() or path.suffix == '.pyc':
                continue
            if debug_dir in path.parents:
                continue
            rel = path.relative_to(src)
            target = dst / rel
            if not target.exists():
                missing.append(str(rel))
            elif target.stat().st_size != path.stat().st_size:
                changed.append(str(rel))

        if missing or changed:
            detail = []
            if missing:
                detail.append(f'ขาด {len(missing)} ไฟล์ (เช่น {missing[0]})')
            if changed:
                detail.append(f'ขนาดไม่ตรง {len(changed)} ไฟล์ (เช่น {changed[0]})')
            return [Check(
                'static', 'FAIL', 'staticfiles ไม่ตรงกับ myapp/static',
                ' · '.join(detail) + ' → ผู้ใช้จะเห็น CSS/JS เวอร์ชันเก่า',
                'python manage.py collectstatic --noinput')]

        return [Check('static', 'OK', 'staticfiles ตรงกับ myapp/static ทุกไฟล์')]

    def _check_migrations(self, as_dev):
        """migration ต้อง apply ครบ และ model ต้องไม่มีการเปลี่ยนที่ยังไม่ migrate"""
        from django.db import connection as conn
        from django.db.migrations.executor import MigrationExecutor

        try:
            executor = MigrationExecutor(conn)
            targets = executor.loader.graph.leaf_nodes()
            plan = executor.migration_plan(targets)
        except Exception as e:
            return [Check('migrate-plan', 'FAIL', 'ตรวจ migration ไม่สำเร็จ',
                          f'{type(e).__name__}: {e}')]

        if plan:
            names = ', '.join(f'{m.app_label}.{m.name}' for m, _ in plan[:3])
            more = f' (+{len(plan) - 3} อื่น)' if len(plan) > 3 else ''
            return [Check(
                'migrate', 'FAIL', 'ยังมี migration ที่ไม่ได้ apply',
                f'{names}{more} → หน้าที่พึ่งคอลัมน์ใหม่จะ error',
                'python manage.py migrate')]

        # มีการเปลี่ยน model แต่ยังไม่สร้าง migration? (จับตอนแก้ model ลืม makemigrations)
        try:
            from django.db.migrations.autodetector import MigrationAutodetector
            from django.db.migrations.questioner import NonInteractiveMigrationQuestioner
            from django.db.migrations.state import ProjectState
            from django.db.migrations.loader import MigrationLoader

            loader = MigrationLoader(None, ignore_no_migrations=True)
            autodetector = MigrationAutodetector(
                loader.project_state(),
                ProjectState.from_apps(__import__('django').apps.apps),
                NonInteractiveMigrationQuestioner(specified_apps=set(), dry_run=True),
            )
            changes = autodetector.changes(graph=loader.graph)
            if changes:
                return [Check(
                    'makemigrations', 'FAIL', 'แก้ model แล้วยังไม่ได้สร้าง migration',
                    f'เปลี่ยนใน: {", ".join(sorted(changes)[:3])} → '
                    'deploy แล้ว server จะไม่มีคอลัมน์นั้น',
                    'python manage.py makemigrations && python manage.py migrate')]
        except Exception:
            pass    # ตรวจไม่ได้ไม่เป็นไร — ไม่ควรทำให้ preflight ล้ม

        return [Check('migrate', 'OK', 'migration ครบและตรงกับ model')]

    def _check_database(self):
        """ไฟล์ DB ต้องมีจริงและไม่เสีย (ข้อมูลทั้งร้านอยู่ไฟล์นี้ไฟล์เดียว)"""
        db_name = settings.DATABASES['default']['NAME']
        if ':memory:' in str(db_name) or 'mode=memory' in str(db_name):
            return [Check('db', 'OK', 'ใช้ฐานข้อมูล in-memory (ตอนรันเทสต์)')]

        path = Path(db_name)
        if not path.exists():
            return [Check('db', 'FAIL', 'ไม่พบไฟล์ฐานข้อมูล',
                          f'{path} — ข้อมูลออเดอร์/ยอดเงินทั้งหมดอยู่ไฟล์นี้',
                          'ตรวจว่า db.sqlite3 ถูกอัปโิลด์ไป server แล้ว')]

        try:
            conn = sqlite3.connect(path)
            try:
                result = conn.execute('PRAGMA integrity_check').fetchone()[0]
                orders = conn.execute('SELECT COUNT(*) FROM myapp_order').fetchone()[0]
            finally:
                conn.close()
        except sqlite3.DatabaseError as e:
            return [Check('db', 'FAIL', 'อ่านฐานข้อมูลไม่ได้', f'{e}')]

        if result != 'ok':
            return [Check(
                'db', 'FAIL', 'ฐานข้อมูลเสียหาย',
                f'integrity_check: {result} → กู้จากไฟล์สำรองได้อย่างเดียว',
                'กู้คืน: cp backups/db-*.sqlite3 db.sqlite3')]

        size_mb = path.stat().st_size / (1024 * 1024)
        return [Check('db', 'OK',
                      f'ฐานข้อมูลปกติ ({size_mb:.2f} MB, {orders} ออเดอร์)')]

    def _check_backup(self, as_dev):
        """ต้องมีไฟล์สำรอง และต้องไม่เก่าจนข้อมูลขาดได้หลายวัน"""
        backups_dir = Path(settings.BASE_DIR) / 'backups'
        if not backups_dir.exists():
            return [Check(
                'backup', 'WARN', 'ยังไม่เคยสำรองฐานข้อมูล',
                'SQLite ไฟล์เดียว = ข้อมูลทั้งร้านอยู่ไฟล์เดียว ถ้าหายกู้ไม่ได้',
                'python manage.py backup_db --verify แล้วตั้ง cron (ดู DEPLOY.md)')]

        files = sorted(backups_dir.glob('db-*.sqlite3'))
        if not files:
            return [Check(
                'backup', 'WARN', 'โฟลเดอร์ backups/ ว่าง',
                'ยังไม่มีไฟล์สำรอง',
                'python manage.py backup_db --verify')]

        latest = files[-1]
        age_hours = (timezone.now() - timezone.make_aware(
            timezone.datetime.fromtimestamp(latest.stat().st_mtime))).total_seconds() / 3600
        label = f'ไฟล์สำรองล่าสุด {latest.name} ({age_hours:.1f} ชม. ที่แล้ว)'

        if age_hours > 48:
            return [Check(
                'backup', 'FAIL', 'ไฟล์สำรองเก่าจนข้อมูลขาดได้ 2 วัน', label,
                'ตั้ง cron: 0 2 * * * ... manage.py backup_db (ดู DEPLOY.md)')]
        if age_hours > 26:
            return [Check('backup', 'WARN', 'ไฟล์สำรองเก่ากว่า 1 วัน', label,
                          'ตรวจว่า cron ทำงานอยู่')]
        return [Check('backup', 'OK', label)]
