"""Management command: สำรองฐานข้อมูล SQLite อย่างปลอดภัย (ปิดช่องโหว่ "ข้อมูลหายกู้ไม่ได้").

ทำไมต้องมี:
    โปรเจกต์ใช้ SQLite ไฟล์เดียว (db.sqlite3) = ข้อมูลออเดอร์/ยอดเงิน/ลูกค้าทั้งหมด
    อยู่ในไฟล์เดียว ถ้าไฟล์เสียหรือถูกทับตอน deploy = กู้ไม่ได้เลย (ไม่มี DB อื่นสำรอง)

การใช้งาน:
    python manage.py backup_db                      # เก็บที่ backups/db-YYYYmmdd-HHMMSS.sqlite3
    python manage.py backup_db --keep 7             # เก็บล่าสุด 7 ไฟล์ (ลบที่เก่ากว่า)
    python manage.py backup_db --dir /home/tammatat/backups

เทคนิคที่สำคัญ (SQLite online backup):
    ใช้ sqlite3 ของ Python เรียก Connection.backup() — เป็น online backup ที่
    "ปลอดภัยแม้มี transaction กำลังวิ่ง" และได้ไฟล์ที่ไม่เสีย (consistent snapshot)
    ต่างจาก shutil.copy ที่ถ้าคัดลอกทับตอน write อยู่ อาจได้ไฟล์เสีย (torn page)
    ทางเลือกที่ปลอดภัยกว่าอีกคือ `VACUUM INTO` (ต้อง SQLite >= 3.27) แต่ backup()
    เข้ากับไฟล์ที่เปิดอยู่ได้เลย จึงเป็นค่าเริ่มต้น
"""
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'สำรองฐานข้อมูล SQLite เป็นไฟล์แยก (ป้องกันข้อมูลหาย)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dir', default=None,
            help='โฟลเดอร์ปลายทาง (default: <BASE_DIR>/backups)',
        )
        parser.add_argument(
            '--keep', type=int, default=7,
            help='เก็บล่าสุดกี่ไฟล์ ที่เหลือลบอัตโนมัติ (default: 7, ใส่ 0 = ไม่ลบ)',
        )
        parser.add_argument(
            '--verify', action='store_true',
            help='เปิดไฟล์สำรองตรวจ integrity หลังเขียนเสร็จ',
        )

    def handle(self, *args, **options):
        # settings ใช้ Path (BASE_DIR / 'db.sqlite3') ไม่ใช่ str — ต้องแปลงก่อน
        # เทียบสตริง ไม่งั้น WindowsPath ไม่มี .startswith() (เคยพังตรงนี้)
        db_name = str(settings.DATABASES['default']['NAME'])
        src_path = Path(db_name)

        # ตรวจไฟล์ก่อนแตะ connection — ถ้าเปิด connection ก่อน Django จะ
        # "สร้างไฟล์ว่างขึ้นมาให้เอง" ตอนเชื่อมต่อ แล้วเราจะสำรองของว่าง
        # ได้ไฟล์ที่ดูเหมือนสำเร็จแต่ไม่มีข้อมูล (อันตรายกว่าไม่สำรอง)
        is_disk_db = (db_name != ':memory:'
                      and not db_name.startswith('file:')
                      and 'mode=memory' not in db_name)
        if is_disk_db and not src_path.exists():
            raise CommandError(f'ไม่พบฐานข้อมูล: {src_path}')

        # เชื่อมผ่าน Django connection ที่เปิดอยู่แล้ว ไม่ต้องเปิดไฟล์ซ้ำ:
        # production ต้องเห็น transaction ที่กำลังวิ่งอยู่ (consistent snapshot)
        # และรองรับกรณี in-memory DB ที่ไม่มีไฟล์บนดิสก์ (ตอนรันเทสต์)
        from django.db import connections
        connections['default'].ensure_connection()   # manage.py ยังไม่เคยต่อ DB มาก่อน
        raw = connections['default'].connection
        if raw is None:
            raise CommandError('ยังไม่ได้เชื่อมต่อฐานข้อมูล — เรียกผิดวิธี?')

        # โฟลเดอร์ปลายทาง — อยู่นอก staticfiles/ เพื่อไม่ให้ collectstatic จับไปด้วย
        out_dir = Path(options['dir']) if options['dir'] else (Path(settings.BASE_DIR) / 'backups')
        out_dir.mkdir(parents=True, exist_ok=True)

        stamp = timezone.localtime().strftime('%Y%m%d-%H%M%S')
        dst = out_dir / f'db-{stamp}.sqlite3'

        # ---------- online backup ----------
        dst_conn = sqlite3.connect(dst)
        try:
            with dst_conn:
                raw.backup(dst_conn)   # สำเนา consistent แบบไม่ล็อก writer
        finally:
            dst_conn.close()

        size_mb = dst.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f'[OK] สำรองแล้ว: {dst} ({size_mb:.2f} MB)'
        ))

        # ---------- ตรวจ integrity (ไม่บังคับ แต่ควรใช้) ----------
        if options['verify']:
            conn = sqlite3.connect(dst)
            try:
                result = conn.execute('PRAGMA integrity_check').fetchone()[0]
            finally:
                conn.close()
            if result == 'ok':
                self.stdout.write(self.style.SUCCESS('[OK] integrity_check: ok'))
            else:
                raise CommandError(f'ไฟล์สำรองเสีย! integrity_check: {result}')

        # ---------- ลบไฟล์เก่า ----------
        keep = options['keep']
        if keep > 0:
            backups = sorted(
                out_dir.glob('db-*.sqlite3'),
                key=lambda p: p.name, reverse=True,
            )
            removed = 0
            for old in backups[keep:]:
                old.unlink()
                removed += 1
            if removed:
                self.stdout.write(f'[--] ลบไฟล์สำรองเก่า {removed} ไฟล์ (เก็บล่าสุด {keep})')

        self.stdout.write(self.style.SUCCESS(
            f'หมายเหตุ: ตั้ง cron บน PythonAnywhere เพื่อรันอัตโนมัติ — '
            f'0 2 * * * /home/tammatat/.virtualenvs/django-shop/bin/python '
            f'/home/tammatat/my_django_app/manage.py backup_db >> '
            f'{out_dir}/cron.log 2>&1'
        ))