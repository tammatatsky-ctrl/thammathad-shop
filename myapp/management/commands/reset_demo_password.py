"""ตั้งรหัสผ่านบัญชีลูกค้าตัวอย่างกลับเป็นรหัสที่เอกสารระบุ

ใช้เมื่อ
    คำสั่ง `seed_demo_data` ตั้งรหัสให้เฉพาะบัญชีที่ "ยังไม่มีรหัส" โดยตั้งใจ
    ไม่ทับรหัสที่คนไปเปลี่ยนเอง ผลคือ `DEMO.md` อาจบอกรหัสผ่านที่ใช้ไม่ได้
    แล้ว (เอกสารโกหกโดยไม่มีใครสังเกต) คำสั่งนี้คือทางแก้ที่จงใจ

ใช้งาน
    python manage.py reset_demo_password wichai.s pornchai.k
    python manage.py reset_demo_password wichai.s --dry-run

ทำไมต้องระบุชื่อบัญชีทีละราย
    ถ้าคำสั่งนี้รับรูปแบบกวาด เช่น `--pattern customer` หรือยิงทุกบัญชีที่ไม่ใช่ staff
    วันหนึ่งมีบัญชีของคนจริงที่ชื่อคล้าย ๆ รหัสผ่านจะถูกทับโดยไม่มีใครสังเกต
    และเจ้าของบัญชีจะตามหารหัสไม่ได้ — นี่คือบัชคุณที่แพงกว่าที่คิด
    การบังคับให้พิมพ์ชื่อเองทำให้ผู้รันคำสั่งต้องตัดสินใจอย่างรู้ตัว
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """ตั้งรหัสผ่านบัญชีที่ระบุชื่อ ให้ตรงกับที่ระบุในเอกสาร"""

    help = ('ตั้งรหัสผ่านบัญชีที่ระบุชื่อให้ตรงกับ DEMO.md '
            '(ต้องระบุชื่อทีละราย — ไม่รองรับการกวาด)')

    def add_arguments(self, parser):
        parser.add_argument(
            'usernames', nargs='*',
            help='ชื่อผู้ใช้ที่ต้องการตั้งรหัสผ่านใหม่ (ระบุชัดเจนทีละราย)')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='แสดงผลว่าจะทำอะไร โดยไม่เขียนจริง')

    def handle(self, *args, **options):
        # นำเข้าช้ากว่าโมเดลเพื่อให้ค่าคงที่อยู่ที่จุดเดียว
        from myapp.management.commands.seed_demo_data import DEMO_PASSWORD

        usernames = options['usernames']
        if not usernames:
            raise CommandError(
                'ต้องระบุชื่อผู้ใช้อย่างน้อยหนึ่งราย\n'
                '  ตัวอย่าง: python manage.py reset_demo_password wichai.s\n'
                '  คำสั่งนี้ไม่รองรับการกวาดทั้งระบบโดยตั้งใจ — '
                'การทับรหัสผ่านบัญชีที่ไม่ใช่บัญชีทดสอบ '
                'ทำให้เจ้าของบัญชีตามหารหัสไม่ได้')

        dry_run = options['dry_run']
        # เก็บลำดับตามที่ผู้ใช้พิมพ์ พร้อมตัดชื่อซ้ำออก
        wanted: list[str] = []
        for name in usernames:
            if name not in wanted:
                wanted.append(name)

        found, missing = [], []
        for name in wanted:
            user = User.objects.filter(username=name).first()
            if user:
                found.append(user)
            else:
                missing.append(name)

        for name in missing:
            self.stdout.write(self.style.WARNING(f'ไม่พบผู้ใช้: {name} — ข้าม'))

        if not found:
            raise CommandError('ไม่พบผู้ใช้ที่ระบุเลย ไม่ได้ทำอะไร')

        for user in found:
            already = user.check_password(DEMO_PASSWORD)
            if already and not dry_run:
                self.stdout.write(
                    f'  = {user.username}  รหัสตรงอยู่แล้ว ไม่เปลี่ยน')
                continue
            if dry_run:
                self.stdout.write(
                    f'  - จะตั้งรหัส "{DEMO_PASSWORD}" ให้ {user.username}')
                continue
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=['password'])
            self.stdout.write(self.style.SUCCESS(
                f'  ✓ ตั้งรหัส "{DEMO_PASSWORD}" ให้ {user.username} แล้ว'))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                'โหมด DRY RUN — ไม่ได้เขียนอะไรจริง'))
            return

        # ยืนยันด้วยการตรวจจริงว่าเข้าได้ ไม่ใช่แค่เชื่อว่า set_password สำเร็จ
        for user in found:
            user.refresh_from_db()
            ok = user.check_password(DEMO_PASSWORD)
            self.stdout.write(
                f'  {"✓" if ok else "✗"} ตรวจซ้ำ {user.username}: '
                f'{"เข้าด้วยรหัสที่เอกสารระบุ" if ok else "ยังเข้าไม่ได้!"}')

        self.stdout.write('')
        self.stdout.write('ลองเข้า: /account/login/ แล้วล็อกอินด้วยบัญชีข้างบน')
        if 'ohm' in wanted:
            self.stdout.write(
                self.style.WARNING(
                    'เตือน: บัญชี ohm เป็น superuser — '
                    'การตั้งรหัสผ่านตัวอย่างทำให้สิทธิ์เต็มเปิดสาธารณะ '
                    'อย่าลืมเปลี่ยนกลับก่อนส่งงานจริง'))