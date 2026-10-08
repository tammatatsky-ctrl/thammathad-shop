"""Management command สำหรับสร้างกลุ่มและกำหนด Permissions ตามมาตรฐาน Django (C9 / Bonus Points).

การใช้งาน:
    python manage.py setup_roles
    python manage.py setup_roles --assign-admin
"""
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from myapp.models import (
    CustomerAddress,
    CustomerProfile,
    Employee,
    Order,
    OrderItem,
    Payment,
    Product,
)


class Command(BaseCommand):
    help = 'สร้างกลุ่มผู้ใช้งาน (Manager, Staff, Member) และกำหนด Permissions สำหรับแต่ละกลุ่ม'

    def add_arguments(self, parser):
        parser.add_argument(
            '--assign-admin',
            action='store_true',
            help='ผูกผู้ใช้ที่เป็น superuser/staff ทั้งหมดเข้ากลุ่ม Manager/Staff',
        )

    def handle(self, *args, **options):
        # 1. รวบรวม ContentType ของแอป myapp
        models = [Product, Order, OrderItem, Employee, Payment, CustomerProfile, CustomerAddress]
        cts = [ContentType.objects.get_for_model(m) for m in models]
        all_perms = Permission.objects.filter(content_type__in=cts)

        # 2. กลุ่ม Manager (ผู้จัดการ) — ได้สิทธิ์ CRUD ครบทุกโมเดลใน myapp
        manager_group, created_m = Group.objects.get_or_create(name='Manager')
        manager_group.permissions.set(all_perms)
        self.stdout.write(self.style.SUCCESS(
            f"[OK] กลุ่ม 'Manager' ({'สร้างใหม่' if created_m else 'มีอยู่แล้ว'}): "
            f"ผูก {manager_group.permissions.count()} สิทธิ์เรียบร้อย"
        ))

        # 3. กลุ่ม Staff (เจ้าหน้าที่) — ดูและแก้ไขสินค้า, ดูและจัดการออเดอร์, ดูและยืนยันเงิน, ดูพนักงาน
        staff_codenames = [
            'view_product', 'change_product',
            'view_order', 'change_order',
            'view_orderitem',
            'view_payment', 'change_payment',
            'view_employee',
            'view_customerprofile',
            'view_customeraddress',
        ]
        staff_perms = Permission.objects.filter(content_type__in=cts, codename__in=staff_codenames)
        staff_group, created_s = Group.objects.get_or_create(name='Staff')
        staff_group.permissions.set(staff_perms)
        self.stdout.write(self.style.SUCCESS(
            f"[OK] กลุ่ม 'Staff' ({'สร้างใหม่' if created_s else 'มีอยู่แล้ว'}): "
            f"ผูก {staff_group.permissions.count()} สิทธิ์เรียบร้อย"
        ))

        # 4. กลุ่ม Member (สมาชิกทั่วไป) — ดูสินค้า, เพิ่มและดูออเดอร์ของตน, จัดการที่อยู่ของตน
        member_codenames = [
            'view_product',
            'add_order', 'view_order',
            'view_orderitem',
            'add_customeraddress', 'change_customeraddress', 'delete_customeraddress', 'view_customeraddress',
            'add_customerprofile', 'change_customerprofile', 'view_customerprofile',
        ]
        member_perms = Permission.objects.filter(content_type__in=cts, codename__in=member_codenames)
        member_group, created_mem = Group.objects.get_or_create(name='Member')
        member_group.permissions.set(member_perms)
        self.stdout.write(self.style.SUCCESS(
            f"[OK] กลุ่ม 'Member' ({'สร้างใหม่' if created_mem else 'มีอยู่แล้ว'}): "
            f"ผูก {member_group.permissions.count()} สิทธิ์เรียบร้อย"
        ))

        # 5. ผูก staff/admin ที่มีอยู่ในระบบ — เฉพาะเมื่อระบุ --assign-admin
        #    (ไม่งั้นคำสั่งนี้จะไปแก้กลุ่มของผู้ใช้เดิมโดยไม่ตั้งใจ — ตรงข้ามกับ help)
        if options['assign_admin']:
            staff_users = User.objects.filter(is_staff=True)
            for u in staff_users:
                if u.is_superuser:
                    u.groups.add(manager_group)
                    self.stdout.write(f"  -> ผูก superuser '{u.username}' เข้ากลุ่ม Manager")
                else:
                    u.groups.add(staff_group)
                    self.stdout.write(f"  -> ผูก staff '{u.username}' เข้ากลุ่ม Staff")
        else:
            self.stdout.write("  (ข้ามการผูกผู้ใช้เดิม — ใส่ --assign-admin ถ้าต้องการผูก superuser/staff เข้ากลุ่ม)")

        # 6. ผูกลูกค้าทั่วไปที่ยังไม่มีกลุ่ม เข้ากลุ่ม Member
        non_staff = User.objects.filter(is_staff=False, groups__isnull=True)
        count_mem = 0
        for u in non_staff:
            u.groups.add(member_group)
            count_mem += 1
        if count_mem:
            self.stdout.write(f"  -> ผูกสมาชิกทั่วไป {count_mem} บัญชีเข้ากลุ่ม Member")

        self.stdout.write(self.style.SUCCESS("[OK] ตั้งค่า Django Groups & Permissions สมบูรณ์ครบถ้วน!"))
