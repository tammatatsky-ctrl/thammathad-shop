"""บัญชีตัวอย่างต้องเข้าสู่ระบบได้จริงตามที่เอกสารบอก

ทำไมต้องมีชุดนี้
    `seed_demo_data` ตั้งรหัสให้เฉพาะบัญชีที่ยังไม่มีรหัส โดยตั้งใจไม่ทับ
    รหัสที่คนไปเปลี่ยนเอง ผลคือเอกสารอาจบอกรหัสผ่านที่ใช้ไม่ได้จริง

    เคยเกิดจริง: บัญชีลูกค้าตัวอย่างทั้ง 6 รายเข้าไม่ได้ แต่ `DEMO.md` ยัง
    เขียนว่าเข้าด้วย `Demo2026!` — ไม่มี error ไม่มีอาการ อาจารย์ที่ทำตาม
    เอกสารจะเข้าไม่ได้แล้วสงสัยว่าระบบเสีย

    ชุดนี้กันไม่ให้เอกสารกับความจริงหลุดจากกันอีก
"""

from io import StringIO

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import TestCase


class SeedPasswordMatchesDocsTest(TestCase):
    """บัญชีที่คำสั่ง seed สร้าง ต้องเข้าด้วยรหัสที่เอกสารระบุ"""

    def test_seed_creates_accounts_that_match_the_documented_password(self):
        from myapp.management.commands.seed_demo_data import (
            CUSTOMERS, DEMO_PASSWORD)

        call_command('seed_catalog', verbosity=0)   # seed_demo_data ต้องพึ่ง
        call_command('seed_demo_data', verbosity=0)   # ให้มีสินค้าก่อน

        for spec in CUSTOMERS:
            with self.subTest(username=spec['username']):
                user = User.objects.get(username=spec['username'])
                self.assertTrue(
                    user.check_password(DEMO_PASSWORD),
                    f'บัญชี {spec["username"]} ต้องเข้าด้วยรหัสที่เอกสารระบุ')

    def test_documented_password_matches_what_demo_md_says(self):
        """ค่าที่โค้ดใช้ ต้องตรงกับที่เขียนไว้ใน DEMO.md จริง ๆ

        กันกรณีแก้รหัสในโค้ดแล้วลืมแก้เอกสาร (หรือกลับกัน)
        """
        from pathlib import Path

        import myapp
        from myapp.management.commands.seed_demo_data import DEMO_PASSWORD

        demo_md = (Path(myapp.__file__).parent.parent / 'DEMO.md').read_text(
            encoding='utf-8')
        self.assertIn(DEMO_PASSWORD, demo_md,
                      'DEMO.md ต้องระบุรหัสผ่านให้ตรงกับที่โค้ดใช้จริง')

    def test_seed_warns_when_an_existing_password_differs(self):
        """บัญชีที่เคยเปลี่ยนรหัสแล้ว ต้องมีคำเตือน ไม่ใช่เงียบ ๆ

        การทับรหัสเงียบ ๆ แย่กว่าการเตือน เพราะมันไปทับบัญชีจริง
        แต่การเงียบก็แย่เช่นกัน เพราะเอกสารจะโกหกโดยไม่มีใครสังเกต
        """
        call_command('seed_catalog', verbosity=0)   # ต้องมีสินค้าก่อน
        call_command('seed_demo_data', verbosity=0)
        # จำลองว่าคนไปเปลี่ยนรหัสผ่านผ่านหน้าเว็บ
        user = User.objects.get(username='wichai.s')
        user.set_password('SomethingElse')
        user.save(update_fields=['password'])

        out = StringIO()
        call_command('seed_demo_data', verbosity=0, stdout=out)
        text = out.getvalue()

        self.assertIn('wichai.s', text)
        self.assertIn('Demo2026!', text)
        self.assertIn('reset_demo_password', text,
                      'คำเตือนต้องบอกวิธีแก้ด้วย ไม่ใช่แค่บอกว่ามีปัญหา')
        # ต้องไม่ทับรหัสที่ตั้งไว้
        user.refresh_from_db()
        self.assertTrue(user.check_password('SomethingElse'),
                        'คำสั่ง seed ต้องไม่ทับรหัสที่คนตั้งเอง')


class ResetDemoPasswordCommandTest(TestCase):
    """คำสั่ง reset_demo_password — ต้องบังคับให้ระบุชื่อชัดเจน"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='wichai.s', password='SomethingElse')

    def test_requires_explicit_usernames(self):
        """ไม่ระบุชื่อ = ไม่ทำอะไร (ป้องกันการทับรหัสทั้งระบบ)

        ถ้าคำสั่งนี้ยอมรับการกวาด วันหนึ่งบัญชีของคนจริงที่ชื่อคล้าย ๆ
        จะถูกตั้งรหัสผ่านทับโดยไม่มีใครสังเกต
        """
        with self.assertRaises(CommandError):
            call_command('reset_demo_password', verbosity=0)

    def test_sets_only_the_named_accounts(self):
        other = User.objects.create_user(
            username='anon.d', password='Untouched')

        call_command('reset_demo_password', 'wichai.s', verbosity=0)

        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(self.user.check_password('Demo2026!'))
        self.assertTrue(other.check_password('Untouched'),
                        'บัญชีที่ไม่ได้ระบุชื่อต้องไม่ถูกแตะ')

    def test_dry_run_changes_nothing(self):
        call_command('reset_demo_password', 'wichai.s', '--dry-run',
                     verbosity=0)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('SomethingElse'))

    def test_unknown_username_is_reported_not_fatal(self):
        out = StringIO()
        call_command('reset_demo_password', 'wichai.s', 'no_such_user',
                     stdout=out, verbosity=0)
        self.assertIn('no_such_user', out.getvalue())

    def test_actually_authenticates_after_reset(self):
        """ยืนยันด้วยการล็อกอินจริง ไม่ใช่แค่เชื่อว่า set_password สำเร็จ"""
        call_command('reset_demo_password', 'wichai.s', verbosity=0)
        self.assertTrue(
            self.client.login(username='wichai.s', password='Demo2026!'),
            'หลังตั้งรหัสแล้วต้องล็อกอินได้จริงผ่าน Django auth')

    def test_warns_when_resetting_a_superuser(self):
        """`ohm` เป็น superuser — ต้องเตือนเรื่องสิทธิ์เต็ม"""
        User.objects.create_superuser(username='ohm', password='x')
        out = StringIO()
        call_command('reset_demo_password', 'ohm', stdout=out, verbosity=0)
        self.assertIn('superuser', out.getvalue())