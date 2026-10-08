"""เทสต์ระบบบทบาทผู้ใช้ (Django Groups & Permissions) และสิทธิ์การเข้าถึง.

ครอบคลุม:
- คำสั่ง management: setup_roles สร้างกลุ่ม Manager, Staff, Member พร้อม permissions
- เทมเพลตแท็ก user_role: แสดง badge ตามลำดับสิทธิ์ (Superuser, Manager, Staff, Member)
- เทมเพลตแท็ก user_groups: แสดงรายชื่อกลุ่มของผู้ใช้
- การบังคับใช้สิทธิ์ใน View: EmployeeDeleteView ปฏิเสธ staff ทั่วไปที่ไม่มี delete_employee
  แต่อนุญาตให้ Manager / Superuser ลบได้
- การสมัครสมาชิกใหม่ (Register): ได้รับกลุ่ม 'Member' อัตโนมัติ
"""
from io import StringIO
from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from myapp.forms import CustomerLoginForm, CustomerRegistrationForm, UserRoleChangeForm
from myapp.models import Employee
from myapp.templatetags.shop_extras import user_groups, user_role


class RolesAndPermissionsTest(TestCase):
    """ทดสอบระบบ Django Groups, Permissions และคำสั่ง setup_roles"""

    def setUp(self):
        # รัน setup_roles เพื่อสร้างกลุ่มและสิทธิ์ใน test database
        out = StringIO()
        call_command('setup_roles', stdout=out)

    def test_setup_roles_creates_groups(self):
        """คำสั่ง setup_roles ต้องสร้างกลุ่มครบทั้ง 3 กลุ่ม"""
        self.assertTrue(Group.objects.filter(name='Manager').exists())
        self.assertTrue(Group.objects.filter(name='Staff').exists())
        self.assertTrue(Group.objects.filter(name='Member').exists())

    def test_manager_has_full_permissions(self):
        """กลุ่ม Manager ต้องมีสิทธิ์ CRUD ใน myapp ครบทุกโมเดล รวม delete_employee"""
        manager_group = Group.objects.get(name='Manager')
        perms = manager_group.permissions.values_list('codename', flat=True)
        self.assertIn('add_employee', perms)
        self.assertIn('change_employee', perms)
        self.assertIn('delete_employee', perms)
        self.assertIn('view_employee', perms)
        self.assertIn('delete_product', perms)

    def test_staff_has_limited_permissions(self):
        """กลุ่ม Staff ต้องมีสิทธิ์ดู/แก้ แต่ไม่มีสิทธิ์ delete_employee หรือ delete_product"""
        staff_group = Group.objects.get(name='Staff')
        perms = staff_group.permissions.values_list('codename', flat=True)
        self.assertIn('view_employee', perms)
        self.assertIn('view_product', perms)
        self.assertIn('change_product', perms)
        self.assertNotIn('delete_employee', perms)
        self.assertNotIn('delete_product', perms)

    def test_member_has_customer_permissions(self):
        """กลุ่ม Member มีสิทธิ์สั่งซื้อและจัดการที่อยู่ของตนเอง"""
        member_group = Group.objects.get(name='Member')
        perms = member_group.permissions.values_list('codename', flat=True)
        self.assertIn('view_product', perms)
        self.assertIn('add_order', perms)
        self.assertIn('add_customeraddress', perms)
        self.assertNotIn('view_employee', perms)

    def test_user_role_template_tag(self):
        """user_role ต้องคืน badge ที่ถูกต้องตามระดับสิทธิ์"""
        # 1. Superuser -> ผู้ดูแลระบบ
        admin_user = User.objects.create_superuser('admin_t', 'a@t.com', 'pwd123')
        badge_admin = user_role(admin_user)
        self.assertIn('role-admin', badge_admin)
        self.assertIn('ผู้ดูแลระบบ', badge_admin)

        # 2. Manager -> ผู้จัดการร้าน
        manager_user = User.objects.create_user('mgr_t', 'm@t.com', 'pwd123', is_staff=True)
        manager_user.groups.add(Group.objects.get(name='Manager'))
        badge_mgr = user_role(manager_user)
        self.assertIn('role-manager', badge_mgr)
        self.assertIn('ผู้จัดการร้าน', badge_mgr)

        # 3. Staff -> เจ้าหน้าที่
        staff_user = User.objects.create_user('stf_t', 's@t.com', 'pwd123', is_staff=True)
        staff_user.groups.add(Group.objects.get(name='Staff'))
        badge_stf = user_role(staff_user)
        self.assertIn('role-staff', badge_stf)
        self.assertIn('เจ้าหน้าที่', badge_stf)

        # 4. Member / ปกติ -> สมาชิก
        member_user = User.objects.create_user('mem_t', 'mem@t.com', 'pwd123')
        member_user.groups.add(Group.objects.get(name='Member'))
        badge_mem = user_role(member_user)
        self.assertIn('role-member', badge_mem)
        self.assertIn('สมาชิก', badge_mem)

    def test_user_groups_template_tag(self):
        """user_groups ต้องคืนชื่อกลุ่มของผู้ใช้"""
        user = User.objects.create_user('grp_user', 'g@t.com', 'pwd123')
        self.assertEqual(user_groups(user), '-')

        user.groups.add(Group.objects.get(name='Member'))
        self.assertEqual(user_groups(user), 'Member')

        user.groups.add(Group.objects.get(name='Staff'))
        groups_str = user_groups(user)
        self.assertIn('Member', groups_str)
        self.assertIn('Staff', groups_str)

    def test_registration_assigns_member_group(self):
        """ลูกค้าที่สมัครใหม่ จะถูกผูกเข้ากลุ่ม Member โดยอัตโนมัติ"""
        data = {
            'name': 'กานต์ สดใส',
            'email': 'karn@test.com',
            'phone': '0855554433',
            'address': 'กรุงเทพฯ',
            'password1': 'secret123',
            'password2': 'secret123',
        }
        r = self.client.post(reverse('account_register'), data)
        self.assertRedirects(r, reverse('product'))

        user = User.objects.get(username='karn@test.com')
        self.assertTrue(user.groups.filter(name='Member').exists())


class PermissionEnforcementViewTest(TestCase):
    """ทดสอบการตรวจสอบสิทธิ์ในระดับ View (View Permission Enforcement)"""

    def setUp(self):
        out = StringIO()
        call_command('setup_roles', stdout=out)

        self.employee = Employee.objects.create(
            emp_code='EMP999',
            name='ทดสอบ พนักงาน',
            department='ไอที',
            salary=30000,
            hire_date='2026-01-01',
            status='active',
        )

        self.staff_user = User.objects.create_user('normal_staff', 'stf@test.com', 'pwd123', is_staff=True)
        self.staff_user.groups.add(Group.objects.get(name='Staff'))

        self.manager_user = User.objects.create_user('manager_user', 'mgr@test.com', 'pwd123', is_staff=True)
        self.manager_user.groups.add(Group.objects.get(name='Manager'))

    def test_staff_without_delete_permission_is_denied(self):
        """Staff ที่ไม่มีสิทธิ์ delete_employee ไม่สามารถลบพนักงานได้"""
        self.client.force_login(self.staff_user)
        r = self.client.post(reverse('employee_delete', kwargs={'pk': self.employee.pk}))
        self.assertRedirects(r, reverse('employee_list'))
        self.assertTrue(Employee.objects.filter(pk=self.employee.pk).exists())

    def test_manager_with_delete_permission_can_delete(self):
        """Manager ที่มีสิทธิ์ delete_employee สามารถลบพนักงานได้สำเร็จ"""
        self.client.force_login(self.manager_user)
        r = self.client.post(reverse('employee_delete', kwargs={'pk': self.employee.pk}))
        self.assertRedirects(r, reverse('employee_list'))
        self.assertFalse(Employee.objects.filter(pk=self.employee.pk).exists())


class UserRegistrationAndAuthEnhancementTest(TestCase):
    """ทดสอบการตรวจสอบความถูกต้องฟอร์ม (Validation) และระบบจดจำการล็อกอิน (Remember Me)"""

    def setUp(self):
        out = StringIO()
        call_command('setup_roles', stdout=out)
        self.user = User.objects.create_user('testauth@test.com', 'testauth@test.com', 'oldsecret123')

    def test_registration_form_valid(self):
        """ฟอร์มสมัครสมาชิกผ่านเมื่อข้อมูลครบถ้วนถูกต้อง"""
        form_data = {
            'name': 'สมชาย ใจดี',
            'email': 'somchai@test.com',
            'phone': '0812345678',
            'address': 'กรุงเทพฯ',
            'password1': 'mypassword123',
            'password2': 'mypassword123',
            'agree_terms': True,
        }
        form = CustomerRegistrationForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_registration_form_password_mismatch(self):
        """ฟอร์มสมัครสมาชิกไม่ผ่านถ้ารหัสผ่านสองช่องไม่ตรงกัน"""
        form_data = {
            'name': 'สมชาย ใจดี',
            'email': 'somchai2@test.com',
            'phone': '0812345678',
            'address': 'กรุงเทพฯ',
            'password1': 'mypassword123',
            'password2': 'differentpassword',
            'agree_terms': True,
        }
        form = CustomerRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)

    def test_registration_form_short_password(self):
        """รหัสผ่านสั้นกว่า 6 ตัวอักษรต้องไม่ผ่าน"""
        form_data = {
            'name': 'สมชาย ใจดี',
            'email': 'somchai3@test.com',
            'phone': '0812345678',
            'address': 'กรุงเทพฯ',
            'password1': '12345',
            'password2': '12345',
            'agree_terms': True,
        }
        form = CustomerRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('password1', form.errors)

    def test_registration_form_invalid_email(self):
        """อีเมลรูปแบบไม่ถูกต้องต้องไม่ผ่าน"""
        form_data = {
            'name': 'สมชาย ใจดี',
            'email': 'invalid-email-string',
            'phone': '0812345678',
            'address': 'กรุงเทพฯ',
            'password1': 'mypassword123',
            'password2': 'mypassword123',
            'agree_terms': True,
        }
        form = CustomerRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_login_remember_me_session_expiry(self):
        """ล็อกอินพร้อมติ๊กจดจำฉัน ต้องตั้งเวลา Session 14 วัน (1209600 วิ)"""
        r = self.client.post(reverse('account_login'), {
            'username': 'testauth@test.com',
            'password': 'oldsecret123',
            'remember_me': 'on',
        })
        self.assertEqual(self.client.session.get_expiry_age(), 1209600)

    def test_login_normal_session_expiry_on_close(self):
        """ล็อกอินแบบปกติ ไม่ติ๊กจดจำฉัน Session ต้องหมดอายุเมื่อปิดเบราว์เซอร์ (expiry_age=0)"""
        r = self.client.post(reverse('account_login'), {
            'username': 'testauth@test.com',
            'password': 'oldsecret123',
        })
        self.assertEqual(self.client.session.get_expire_at_browser_close(), True)

    def test_password_change_view_requires_login(self):
        """หน้าที่เปลี่ยนรหัสผ่านต้องล็อกอินก่อนเสมอ"""
        r = self.client.get(reverse('account_password_change'))
        self.assertRedirects(r, f"{reverse('account_login')}?next={reverse('account_password_change')}")

    def test_password_change_successful(self):
        """ผู้ใช้ล็อกอินสามารถเปลี่ยนรหัสผ่านได้สำเร็จ"""
        self.client.force_login(self.user)
        r = self.client.post(reverse('account_password_change'), {
            'old_password': 'oldsecret123',
            'new_password1': 'brandnewsecret456',
            'new_password2': 'brandnewsecret456',
        })
        self.assertRedirects(r, reverse('account'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('brandnewsecret456'))


class StaffUserManagementAndRBACTest(TestCase):
    """ทดสอบหน้ารายชื่อและจัดการสิทธิ์ผู้ใช้ของเจ้าหน้าที่ (/staff/users/)"""

    def setUp(self):
        out = StringIO()
        call_command('setup_roles', stdout=out)

        self.manager_user = User.objects.create_user('admin_mgr', 'mgr@shop.com', 'pwd123', is_staff=True)
        self.manager_user.groups.add(Group.objects.get(name='Manager'))

        self.staff_user = User.objects.create_user('general_staff', 'staff@shop.com', 'pwd123', is_staff=True)
        self.staff_user.groups.add(Group.objects.get(name='Staff'))

        self.member_user = User.objects.create_user('normal_member', 'member@shop.com', 'pwd123', is_staff=False)
        self.member_user.groups.add(Group.objects.get(name='Member'))

    def test_staff_user_manage_denies_unauthenticated(self):
        """ผู้ใช้ที่ยังไม่ล็อกอินจะถูกพาไปหน้าเข้าสู่ระบบเจ้าหน้าที่"""
        r = self.client.get(reverse('staff_users'))
        self.assertRedirects(r, f"{reverse('staff_login')}?next={reverse('staff_users')}")

    def test_staff_user_manage_denies_normal_member(self):
        """สมาชิกธรรมดาไม่มีสิทธิ์เข้าหน้าจัดการผู้ใช้ (ได้ 403 Forbidden)"""
        self.client.force_login(self.member_user)
        r = self.client.get(reverse('staff_users'))
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, '403', status_code=403)
        self.assertContains(r, 'ไม่มีสิทธิ์ในการเข้าถึงหน้านี้', status_code=403)

    def test_staff_user_manage_denies_general_staff(self):
        """Staff ทั่วไปไม่มีสิทธิ์เข้าหน้าจัดการบทบาท (ได้ 403 Forbidden)"""
        self.client.force_login(self.staff_user)
        r = self.client.get(reverse('staff_users'))
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, '403', status_code=403)

    def test_staff_user_manage_allows_manager(self):
        """Manager สามารถเข้าดูหน้ารายชื่อผู้ใช้และการจัดการสิทธิ์ได้ 200 OK"""
        self.client.force_login(self.manager_user)
        r = self.client.get(reverse('staff_users'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'จัดการบทบาทและสิทธิ์ผู้ใช้')
        self.assertContains(r, 'normal_member')
        self.assertContains(r, 'general_staff')

    def test_manager_promotes_member_to_staff(self):
        """Manager สามารถปรับสิทธิ์ Member เป็น Staff ได้ (is_staff กลายเป็น True)"""
        self.client.force_login(self.manager_user)
        r = self.client.post(reverse('staff_user_role_update', kwargs={'user_id': self.member_user.id}), {
            'role': 'Staff',
        })
        self.assertRedirects(r, reverse('staff_users'))
        self.member_user.refresh_from_db()
        self.assertTrue(self.member_user.is_staff)
        self.assertTrue(self.member_user.groups.filter(name='Staff').exists())
        self.assertFalse(self.member_user.groups.filter(name='Member').exists())

    def test_manager_demotes_staff_to_member(self):
        """Manager สามารถปรับลดสิทธิ์ Staff กลับเป็น Member (is_staff กลายเป็น False)"""
        self.client.force_login(self.manager_user)
        r = self.client.post(reverse('staff_user_role_update', kwargs={'user_id': self.staff_user.id}), {
            'role': 'Member',
        })
        self.assertRedirects(r, reverse('staff_users'))
        self.staff_user.refresh_from_db()
        self.assertFalse(self.staff_user.is_staff)
        self.assertTrue(self.staff_user.groups.filter(name='Member').exists())
        self.assertFalse(self.staff_user.groups.filter(name='Staff').exists())

    def test_cannot_demote_self_if_not_superuser(self):
        """Manager ทั่วไปไม่สามารถปลดสิทธิ์ตนเองได้ เพื่อความปลอดภัย"""
        self.client.force_login(self.manager_user)
        r = self.client.post(reverse('staff_user_role_update', kwargs={'user_id': self.manager_user.id}), {
            'role': 'Member',
        })
        self.assertRedirects(r, reverse('staff_users'))
        self.manager_user.refresh_from_db()
        self.assertTrue(self.manager_user.is_staff)
        self.assertTrue(self.manager_user.groups.filter(name='Manager').exists())
