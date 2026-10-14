"""Views แบบ Class-Based ทั้งหมด — ใช้หลัก OOP:
- Inheritance   : LiveSearchListView เป็น base ให้ตารางค้นหาเรียลไทม์ทุกหน้า
- Polymorphism  : subclass override filter_queryset / get_product / ข้อความ โดย base คุมโฟลว์
- Encapsulation : ตรรกะโดเมนอยู่ที่ models (QuerySet/Manager) และ services (Cart)
- Abstraction   : StaffRequiredMixin ซ่อนรายละเอียดการตรวจสิทธิ์จากทุก view

- Ajax          : is_ajax(request) — จุดเดียวที่ตัดสินคำขอ AJAX/partial (JSON vs redirect)
"""
import csv
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.views import PasswordChangeView, PasswordResetView
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from .forms import (
    CustomerLoginForm,
    CustomerRegistrationForm,
    EmployeeForm,
    ProfileEditForm,
    StaffLoginForm,
    UserRoleChangeForm,
)
from .models import (ActivityLog, CustomerAddress, CustomerProfile, Employee, Order,
                    OrderIssue, OrderItem, Payment, Product)
from .services import (Audit, Cart, Catalog, GeoIP, GeminiAI, LoginThrottle,
                      OrderStatusService, PaymentService, ProductDescription,
                      PromptPay, QrCode, RateLimit,
                      SlipOK, ThaiCalendar, Translate, Validators)


# ==================== Permissions: Mixin แทน decorator ====================

class StaffRequiredMixin(AccessMixin):
    """ผสมกับ View คลาสไหนก็ได้เพื่อบังคับสิทธิ์ผู้ดูแล (แทน @staff_required เดิม)"""

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_login_url(self):
        return reverse('staff_login')


class ManagerRequiredMixin(AccessMixin):
    """ผสมกับ View ที่สงวนเฉพาะ Manager หรือ Superuser — หากไม่มีสิทธิ์จะเกิด 403 Forbidden"""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or request.user.groups.filter(name='Manager').exists()):
            raise PermissionDenied('หน้านี้สงวนสิทธิ์เฉพาะผู้จัดการร้าน (Manager) หรือผู้ดูแลระบบเท่านั้น')
        return super().dispatch(request, *args, **kwargs)

    def get_login_url(self):
        return reverse('staff_login')


class CsvSafeMixin:
    """กัน CSV formula injection ให้ทุก view ที่ส่งออก CSV — รวม _safe_cell ไว้ที่เดียว.

    cell ที่ขึ้นต้นด้วย = + - @ หรือ tab จะถูกเติม ' นำหน้า เพื่อให้ Excel/Sheets
    มองเป็นข้อความ ไม่ประมวลผลเป็นสูตร (ข้อมูลลูกค้า/พนักงานมาจากผู้ใช้).
    """

    _FORMULA_CHARS = ('=', '+', '-', '@', '\t')

    @classmethod
    def _safe_cell(cls, value):
        """คืนค่า cell ที่ปลอดภัยสำหรับ CSV — None → '' และกัน formula injection."""
        text = '' if value is None else str(value)
        if text.startswith(cls._FORMULA_CHARS):
            return "'" + text
        return text


# ==================== Auth ====================

class CustomerRegisterView(View):
    """สมัครบัญชีลูกค้า — ใช้ Django Form Validation ครบทุกฟิลด์ + กำหนดกลุ่ม Member อัตโนมัติ"""
    template_name = 'account_register.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(reverse('account'))
        form = CustomerRegistrationForm()
        return render(request, self.template_name, {
            'form': form,
            'next': request.GET.get('next', ''),
        })

    def post(self, request, *args, **kwargs):
        from django.contrib.auth.models import Group, User
        form = CustomerRegistrationForm(request.POST)
        if not form.is_valid():
            first_err = ''
            for field, errs in form.errors.items():
                if errs:
                    first_err = errs[0]
                    break
            return render(request, self.template_name, {
                'form': form,
                'error': first_err,
                'next': request.POST.get('next', ''),
                'v_name': request.POST.get('name', ''),
                'v_email': request.POST.get('email', ''),
                'v_phone': request.POST.get('phone', ''),
                'v_address': request.POST.get('address', ''),
            })

        data = form.cleaned_data
        name = data['name']
        email = data['email']
        phone = data['phone']
        address = data['address']
        pw1 = data['password1']

        user = User.objects.create_user(
            username=email,
            email=email,
            password=pw1,
            first_name=name.split(' ')[0][:30],
            last_name=' '.join(name.split(' ')[1:])[:150],
        )
        member_grp = Group.objects.filter(name='Member').first()
        if member_grp:
            user.groups.add(member_grp)
        CustomerProfile.objects.create(user=user, phone=phone, address=address)
        login(request, user)
        messages.success(request, f'สมัครบัญชีสำเร็จ ยินดีต้อนรับคุณ {name}!')
        nxt = request.POST.get('next', '')
        if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
            return redirect(nxt)
        return redirect(reverse('product'))


class CustomerLoginView(View):
    """เข้าสู่ระบบลูกค้า พร้อม Remember Me และความปลอดภัย redirect"""
    template_name = 'account_login.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(reverse('account'))
        form = CustomerLoginForm()
        return render(request, self.template_name, {
            'form': form,
            'next': request.GET.get('next', ''),
        })

    def post(self, request, *args, **kwargs):
        form = CustomerLoginForm(request.POST)
        username = request.POST.get('username', '').strip().lower()
        password = request.POST.get('password', '')
        remember_me = request.POST.get('remember_me')
        client_ip = request.META.get('REMOTE_ADDR', '0.0.0.0')

        # กัน brute force ก่อน authenticate — ข้อความเดียวกันทุกกรณีที่โดนจำกัด
        if not LoginThrottle.check(client_ip, username):
            return render(request, self.template_name, {
                'form': form,
                'error': LoginThrottle.MESSAGE,
                'next': request.POST.get('next', ''),
                'v_username': username,
            }, status=429)

        user = authenticate(request, username=username, password=password)
        if not user:
            LoginThrottle.fail(username)
            return render(request, self.template_name, {
                'form': form,
                'error': 'อีเมลหรือรหัสผ่านไม่ถูกต้อง',
                'next': request.POST.get('next', ''),
                'v_username': username,
            })

        LoginThrottle.success(username)
        login(request, user)
        if remember_me:
            request.session.set_expiry(1209600)  # 14 วัน
        else:
            request.session.set_expiry(0)  # ปิด browser แล้วหมดอายุ

        messages.success(request, f'ยินดีต้อนรับคุณ {user.first_name or user.username}!')
        nxt = request.POST.get('next', '')
        if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
            return redirect(nxt)
        return redirect(reverse('account') if not user.is_staff else reverse('dashboard'))


class CustomerRequiredMixin(AccessMixin):
    """บังคับล็อกอิน (ลูกค้าหรือ staff) — redirect ไปหน้า login ลูกค้า"""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_login_url(self):
        return reverse('account_login')


class LinkOnlyPasswordResetForm(PasswordResetForm):
    """ฟอร์มรีเซ็ตที่ "สร้างลิงก์แต่ไม่ส่ง" — ใช้ตอนร้านยังไม่ได้ตั้ง SMTP

    เหตุผลที่ต้องมีคลาสนี้ (แทนกี่เรียก `form.save()` แล้วเก็บผล):
        `PasswordResetForm.save()` **ส่งอีเมลจริงเสมอ** — ถ้าเรียกมันแล้วบอก
        ผู้ใช้ว่า "ไม่ได้ส่ง" ก็โกหกไปแล้ว (และถ้า backend เป็น locmem/console
        จะมีอีเมลหลุดออกไปจริง ทำให้เทสต์จับไม่ได้ว่าเราส่งหรือไม่)
        คลาสนี้ override `save()` ให้คืน token ที่สร้างจริง โดยไม่ติดต่อ backend

    Attributes:
        reset_links: list[dict] — {user, uid, token} ของผู้ใช้ที่อีเมลถูกต้อง
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset_links = []

    def save(self, request=None, **kwargs):
        """สร้าง token ให้ผู้ใช้ที่อีเมลถูกต้อง — โดยไม่ส่งอีเมล

        Args:
            request: request ปัจจุบัน (ใช้หาโดเมนในกรณี request ไม่มี)
            **kwargs: รับทิ้งเพื่อให้เข้ากับช่องทางของ PasswordResetForm

        Returns:
            list[str] — อีเมลของผู้ใช้ที่ token ถูกสร้างจริง
        """
        current_site = get_current_site(request)
        email = self.cleaned_data['email']
        token_generator = kwargs.get('token_generator') or default_token_generator
        for user in self.get_users(email):
            temp_token = token_generator.make_token(user)
            self.reset_links.append({
                'user': user,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': temp_token,
            })
        # ไม่เรียก self.send_mail(...) — จุดที่ตั้งใจไม่ส่ง
        del current_site   # ไม่ได้ใช้ แต่คงไว้ให้สัญญาเหมือนของ Django
        return [u.email for u in self.get_users(email)]


class CustomerPasswordResetView(PasswordResetView):
    """ลืมรหัสผ่าน — Django 6.x อ่าน template อีเมลจาก class attribute ของ view เอง
    (form_valid ส่ง self.email_template_name ให้ form.save) → override เป็น class attr
    เพื่อบังคับใช้ template ภาษาไทยของเรา (ไม่พึ่งตัว default ของ contrib.auth).

    **ห้ามหลอกผู้ใช้ว่าส่งอีเมลแล้ว** (บั๊กที่เจอ — EMAIL_BACKEND=console ทำให้
    ลิงก์รีเซ็ตไปโผล่ใน console ของเซิร์ฟเวอร์ ซึ่งลูกค้าเข้าไม่ถึง แต่ Django
    ยังพาไปหน้า "ส่งลิงก์ไปทางอีเมลแล้ว" ตามปกติ):

    - `settings.EMAIL_CONFIGURED` = True  → ส่งอีเมลจริง พฤติกรรมปกติ
    - `settings.EMAIL_CONFIGURED` = False → ยังสร้าง token จริง (ไม่ใช่ของปลอม)
      แต่แสดง "ร้านยังไม่ได้ตั้งค่าอีเมล" + ลิงก์รีเซ็ตให้ผู้ใช้กดเลย ถ้าเป็น staff
      หรืออยู่ใน DEBUG (การส่งงาน/สาธิตให้อาจารย์) — ไม่งั้นบอกให้ติดต่อเจ้าหน้าที่
    """

    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_subject.txt'
    from_email = settings.DEFAULT_FROM_EMAIL
    success_url = reverse_lazy('password_reset_done')

    def get_context_data(self, **kwargs):
        """เพิ่มสถานะการตั้งค่าอีเมลให้เทมเพลตแสดงคำเตือนตามความจริง"""
        ctx = super().get_context_data(**kwargs)
        ctx['email_configured'] = settings.EMAIL_CONFIGURED
        return ctx

    def get_form(self, form_class=None):
        """เวลาร้านยังไม่ได้ตั้ง SMTP ให้ใช้ฟอร์มที่สร้างลิงก์แต่ไม่ส่ง"""
        if not settings.EMAIL_CONFIGURED:
            return LinkOnlyPasswordResetForm(**self.get_form_kwargs())
        return super().get_form(form_class)

    def form_valid(self, form):
        if settings.EMAIL_CONFIGURED:
            return super().form_valid(form)

        # ยังไม่ได้ตั้ง SMTP -> สร้าง token จริง แต่ไม่ส่ง (ไม่หลอกว่าส่งแล้ว)
        form.save(request=self.request)

        if not form.reset_links:
            # ไม่บอกว่าอีเมลนี้มี/ไม่มีบัญชี (user enumeration) -> ตอบเหมือนกันเสมอ
            messages.info(self.request,
                          'ถ้าอีเมลนี้มีบัญชีในระบบ เราจะส่งขั้นตอนถัดไปให้')
            return redirect(self.success_url)

        link = form.reset_links[0]
        user = link['user']
        reveal = settings.DEBUG or (
            self.request.user.is_authenticated and self.request.user.is_staff)

        return render(self.request, 'registration/password_reset_email_unconfigured.html', {
            'email': user.email,
            'reset_url': reverse('password_reset_confirm',
                                 kwargs={'uidb64': link['uid'], 'token': link['token']}),
            'can_reveal': reveal,
        })


class CustomerPasswordChangeView(CustomerRequiredMixin, PasswordChangeView):
    """เปลี่ยนรหัสผ่านสำหรับสมาชิกลูกค้า — ใช้ Django PasswordChangeView + ฟอร์มภาษาไทย"""
    template_name = 'account_password_change.html'
    success_url = reverse_lazy('account')

    def form_valid(self, form):
        messages.success(self.request, 'เปลี่ยนรหัสผ่านสำเร็จเรียบร้อยแล้ว')
        return super().form_valid(form)


class AccountView(CustomerRequiredMixin, TemplateView):
    """โปรไฟล์ + ออเดอร์ของฉัน (ไม่ต้องจำ order id / เบอร์) พร้อมสถิติความปลอดภัยและกิจกรรม"""
    template_name = 'account.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        profile = getattr(self.request.user, 'customer_profile', None)
        orders = (self.request.user.orders
                  .prefetch_related('items__product')
                  .order_by('-created_at'))
        total_spent = sum(o.total for o in orders)
        pending_count = orders.filter(status='pending').count()
        joined_thai = ThaiCalendar.format(self.request.user.date_joined) if hasattr(self.request.user, 'date_joined') and self.request.user.date_joined else ''
        ctx.update({
            'profile': profile,
            'display_name': (self.request.user.get_full_name()
                             or self.request.user.username),
            'orders': orders,
            # ปัญหาที่ลูกค้าเคยแจ้ง ผูกไว้กับออเดอร์แต่ละใบเป็น `my_issues`
            # (Django template ดึง dict ด้วยคีย์ตัวแปรไม่ได้ และถ้าไล่ query
            #  ใน `{% for %}` จะกลายเป็น N+1 — เตรียมมาให้เลยตรงจุดเดียว)
            'issues_by_order': self._issues_by_order(self.request.user, orders),
            'addresses': self.request.user.addresses.all(),
            'orders_count': orders.count(),
            'orders_total': total_spent,
            'orders_pending': pending_count,
            'joined_thai': joined_thai,
            'last_login': self.request.user.last_login,
        })
        return ctx

    @staticmethod
    def _issues_by_order(user, orders):
        """ผูกรายการแจ้งปัญหาของลูกค้าไว้กับออเดอร์แต่ละใบ (`order.my_issues`)

        ทำเป็น dict แล้วใช้ฟิลเตอร์ในเทมเพลตแทนไม่ได้ 2 เหตุผล:
          1. Django template ดึงค่า dict ด้วยคีย์ที่เป็นตัวแปรไม่ได้
             (ต้องเขียน `{{ d|get_item:key }}` = ฟิลเตอร์ใหม่ที่ไม่คุ้ม)
          2. ถ้าไล่ `order.issues.all` ใน `{% for %}` = N+1 query
             ยิ่งลูกค้ามีออเดอร์เยอะ หน้าบัญชียิ่งช้าลงเงียบ ๆ

        Args:
            user: ลูกค้าคนนี้
            orders: QuerySet ออเดอร์ของเขา (ถูก iterate ไปแล้วใน get_context_data
                จึงเป็น object เดิม — ตั้ง attribute แล้วเทมเพลตเห็นค่าเดียวกัน)

        Returns:
            dict[int, list[OrderIssue]] — คีย์คือ order_id (เก็บไว้เผื่อจุดอื่นใช้)
        """
        order_ids = [o.id for o in orders]
        grouped = {}
        if order_ids:
            for issue in OrderIssue.objects.for_customer(user).filter(
                    order_id__in=order_ids):
                grouped.setdefault(issue.order_id, []).append(issue)
        for order in orders:
            order.my_issues = grouped.get(order.id, [])
        return grouped


class ProfileEditView(CustomerRequiredMixin, View):
    """แก้ไขข้อมูลส่วนตัวของลูกค้า — ชื่อ, นามสกุล, อีเมล, เบอร์โทร, ที่อยู่หลัก, รูปโปรไฟล์ และภาพหน้าปก"""
    template_name = 'account_profile_edit.html'

    def get(self, request, *args, **kwargs):
        profile = getattr(request.user, 'customer_profile', None)
        initial = {
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'email': request.user.email or request.user.username,
            'phone': profile.phone if profile else '',
            'address': profile.address if profile else '',
            'avatar': profile.avatar if profile else None,
            'cover': profile.cover if profile else None,
        }
        form = ProfileEditForm(initial=initial, user=request.user)
        return render(request, self.template_name, {
            'form': form,
            'profile': profile,
        })

    def post(self, request, *args, **kwargs):
        form = ProfileEditForm(request.POST, request.FILES, user=request.user)
        if not form.is_valid():
            profile = getattr(request.user, 'customer_profile', None)
            return render(request, self.template_name, {
                'form': form,
                'profile': profile,
            })

        user = request.user
        cd = form.cleaned_data
        user.first_name = cd['first_name']
        user.last_name = cd['last_name']
        user.email = cd['email']
        user.username = cd['email']
        user.save()

        profile, _ = CustomerProfile.objects.get_or_create(user=user)
        profile.phone = cd['phone']
        profile.address = cd['address']

        # จัดการรูปโปรไฟล์ (อัปโหลดใหม่ / ลบทิ้ง)
        if request.POST.get('avatar_clear') or cd.get('avatar') is False:
            if profile.avatar:
                profile.avatar.delete(save=False)
                profile.avatar = None
        elif cd.get('avatar'):
            if profile.avatar:
                profile.avatar.delete(save=False)
            profile.avatar = cd['avatar']

        # จัดการภาพหน้าปก (อัปโหลดใหม่ / ลบทิ้ง)
        if request.POST.get('cover_clear') or cd.get('cover') is False:
            if profile.cover:
                profile.cover.delete(save=False)
                profile.cover = None
        elif cd.get('cover'):
            if profile.cover:
                profile.cover.delete(save=False)
            profile.cover = cd['cover']

        profile.save()

        messages.success(request, 'บันทึกข้อมูลส่วนตัวเรียบร้อยแล้ว')
        return redirect(reverse('account'))


class CustomerLogoutView(View):
    """ออกจากระบบลูกค้า — POST เท่านั้น (GET = 405 ให้แคช/crawler ไม่ล็อกเอาต์เอง)"""

    def post(self, request, *args, **kwargs):
        logout(request)
        messages.success(request, 'ออกจากระบบแล้ว')
        return redirect(reverse('product'))


# ==================== สมุดที่อยู่จัดส่ง ====================

class AddressBookMixin:
    """ฟอร์มที่อยู่ร่วม add/edit — geo cascade ฝั่ง client"""

    @staticmethod
    def _clean(request):
        data = {
            'label': (request.POST.get('label', '').strip() or 'บ้าน')[:40],
            'receiver_name': request.POST.get('receiver_name', '').strip()[:150],
            'phone': Validators.normalize_phone(request.POST.get('phone', ''))[:20],
            'detail': request.POST.get('detail', '').strip(),
            'province': request.POST.get('province', '').strip()[:80],
            'district': request.POST.get('district', '').strip()[:80],
            'subdistrict': request.POST.get('subdistrict', '').strip()[:80],
            'zipcode': request.POST.get('zipcode', '').strip()[:5],
        }
        missing = [k for k in ('receiver_name', 'detail', 'province',
                               'district', 'subdistrict') if not data[k]]
        if missing:
            return None, 'กรุณากรอกข้อมูลให้ครบ (รวมถึงเลือกจังหวัด/อำเภอ/ตำบล)'
        if not Validators.valid_phone(data['phone']):
            return None, 'เบอร์โทรศัพท์ไม่ถูกต้อง (0XXXXXXXXX)'
        if not data['zipcode'].isdigit() or len(data['zipcode']) != 5:
            return None, 'รหัสไปรษณีย์ต้องเป็นตัวเลข 5 หลัก'
        return data, None


class AddressCreateView(CustomerRequiredMixin, AddressBookMixin, View):
    """เพิ่มที่อยู่จัดส่งใหม่ — ที่อยู่แรกของบัญชีจะถูกตั้งเป็นค่าเริ่มต้นอัตโนมัติ."""
    template_name = 'address_form.html'

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {
            'address': None,
            'geo': {'province': '', 'district': '', 'subdistrict': '', 'zipcode': ''},
            # คำใบ้ระดับประเทศจาก IP (ไม่ prefill จังหวัด — GeoIP แม่นแค่ระดับประเทศ)
            'geo_hint': GeoIP.visitor(request),
        })

    def post(self, request, *args, **kwargs):
        data, err = self._clean(request)
        if err:
            return render(request, self.template_name, {'error': err, 'address': None, 'geo': data or {}})
        CustomerAddress.objects.create(
            user=request.user, is_default=not request.user.addresses.exists(), **data)
        messages.success(request, 'เพิ่มที่อยู่ใหม่แล้ว')
        return redirect(reverse('account'))


class AddressUpdateView(CustomerRequiredMixin, AddressBookMixin, View):
    """แก้ไขที่อยู่ — ตรวจว่าเป็นเจ้าของจริง (filter user=request.user) ไม่งั้น 404."""
    template_name = 'address_form.html'

    def _get(self, request):
        return get_object_or_404(CustomerAddress, id=self.kwargs['addr_id'],
                                 user=request.user)

    def get(self, request, *args, **kwargs):
        a = self._get(request)
        return render(request, self.template_name, {
            'address': a,
            'geo': {'province': a.province, 'district': a.district,
                    'subdistrict': a.subdistrict, 'zipcode': a.zipcode},
        })

    def post(self, request, *args, **kwargs):
        a = self._get(request)
        data, err = self._clean(request)
        if err:
            return render(request, self.template_name,
                          {'error': err, 'address': a, 'geo': data or {}})
        for k, v in data.items():
            setattr(a, k, v)
        a.save()
        messages.success(request, 'แก้ไขที่อยู่แล้ว')
        return redirect(reverse('account'))


class AddressDeleteView(CustomerRequiredMixin, View):
    """ลบที่อยู่ (POST เท่านั้น) — ถ้าลบตัว default จะเลื่อนค่าเริ่มต้นให้ที่อยู่ถัดไป."""

    def post(self, request, *args, **kwargs):
        a = get_object_or_404(CustomerAddress, id=self.kwargs['addr_id'],
                              user=request.user)
        was_default = a.is_default
        a.delete()
        if was_default:
            nxt = request.user.addresses.first()
            if nxt:
                nxt.is_default = True
                nxt.save(update_fields=['is_default'])
        messages.success(request, 'ลบที่อยู่แล้ว')
        return redirect(reverse('account'))


class AddressSetDefaultView(CustomerRequiredMixin, View):
    """ตั้งที่อยู่ที่เลือกเป็นค่าเริ่มต้น (POST เท่านั้น) — ล้าง default ตัวอื่นก่อน."""

    def post(self, request, *args, **kwargs):
        a = get_object_or_404(CustomerAddress, id=self.kwargs['addr_id'],
                              user=request.user)
        request.user.addresses.exclude(id=a.id).update(is_default=False)
        a.is_default = True
        a.save(update_fields=['is_default'])
        messages.success(request, f'ตั้ง "{a.label}" เป็นที่อยู่ค่าเริ่มต้นแล้ว')
        return redirect(reverse('account'))

class StaffLoginView(View):
    """เข้าสู่ระบบผู้ดูแล (/staff/login/) — staff ที่ล็อกอินอยู่แล้วโดนพาไป /employees/.

    ใช้ StaffLoginForm (AuthenticationForm) และกัน open redirect ผ่าน _safe_next.
    """
    template_name = 'staff_login.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            return redirect(reverse('employee_list'))
        return super().dispatch(request, *args, **kwargs)

    def _safe_next(self):
        """ดึง next จาก POST/GET แต่ตัดทิ้งถ้าเป็น URL นอก host (กัน open redirect)."""
        next_url = self.request.POST.get('next') or self.request.GET.get('next', '')
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}):
            return ''
        return next_url

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {
            'form': StaffLoginForm(request),
            'next': self._safe_next(),
        })

    def post(self, request, *args, **kwargs):
        next_url = self._safe_next()
        username = request.POST.get('username', '').strip()
        client_ip = request.META.get('REMOTE_ADDR', '0.0.0.0')

        # กัน brute force ก่อนตรวจรหัสผ่าน — หน้านี้คือประตูหลังของระบบทั้งหมด
        # ข้อความเดียวกับ CustomerLoginView โดยเจตนา (ไม่บอกว่าโดนชั้นไหน)
        if not LoginThrottle.check(client_ip, username):
            return render(request, self.template_name, {
                'form': StaffLoginForm(request),
                'next': next_url,
                'error': LoginThrottle.MESSAGE,
            }, status=429)

        form = StaffLoginForm(request, data=request.POST)
        if form.is_valid():
            LoginThrottle.success(form.get_user().get_username())
            login(request, form.get_user())
            messages.success(request, 'เข้าสู่ระบบผู้ดูแลเรียบร้อยแล้ว')
            return redirect(next_url or reverse('employee_list'))

        LoginThrottle.fail(username)
        return render(request, self.template_name, {'form': form, 'next': next_url})


class StaffLogoutView(View):
    """ออกจากระบบผู้ดูแล — POST เท่านั้น (GET = 405)."""

    def post(self, request, *args, **kwargs):
        logout(request)
        messages.success(request, 'ออกจากระบบผู้ดูแลเรียบร้อยแล้ว')
        return redirect(reverse('index'))


# ==================== หน้าร้าน (Public) ====================

class IndexView(TemplateView):
    """หน้าแรกของร้าน — โครงแบบ "หน้าร้านจริง" (แก้จากเดิมที่เป็น hero การ์ดเดียว + lab 2142px)

    หลักการ: ผู้มาแรกต้อง **เห็นสินค้าและทางเลือกภายในหน้าจอแรก**
    ตอนนี้หน้าเดิมยาว 5120px และ "ห้องทดสอบสวิตช์" กิน 42% ของหน้า
    ทำให้ต้องเลื่อน 4 จอถึงจะเจอของที่ขายได้ — จึงรื้อเป็น
    hero แบบแยกสองคอลัมน์ (ซ้ายคำโปรย+ปุ่ม / ขวาสินค้า 4 ใบ) → แถบหมวด 4 อัน → สินค้า

    Attributes:
        featured: สินค้าเพดาน 8 ชิ้น สำหรับกริด "สินค้าทั้งหมด" ด้านล่าง
        hero_picks: 4 ชิ้นแรก สำหรับตารางโชว์ฝั่งขวาของ hero
        categories: หมวดหมู่ที่ยังมีสินค้าแสดงอยู่ (ถ้าว่าง template ซ่อนแถวหมวดเอง)
        cat_tiles: รายการ {name, icon, count} สำหรับแถบหมวด — ค่า icon จับคู่จาก
            CAT_ICONS, count คือจำนวนสินค้าจริงในหมวดนั้น (ไม่ใช่ตัวเลขประดับ)
    """
    template_name = 'index.html'

    #: ไอคอนประจำหมวด — ถ้าหมวดใหม่ไม่อยู่ในนี้จะใช้ไอคอนกลางแทน
    CAT_ICONS = {
        'อุปกรณ์ต่อพ่วง': 'bi-keyboard',
        'เครื่องเสียง': 'bi-headphones',
        'จอภาพ': 'bi-display',
        'สายและเครื่องชาร์จ': 'bi-lightning-charge',
    }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        listed = Product.objects.listed()
        featured = list(listed[:8])
        ctx['featured'] = featured
        ctx['hero_picks'] = featured[:4]

        cats = Catalog.categories(only_listed=True)
        ctx['categories'] = cats
        # นับต่อหมวดใน Python แทน extra() — แคตตาล็อกเล็ก (สินค้าร้อยระดับ)
        # และโค้ดสั้นกว่า aggregation ที่ต้อง import อย่าง QuerySet เพิ่ม
        counts = dict.fromkeys(cats, 0)
        for name in listed.values_list('category', flat=True):
            if name in counts:
                counts[name] += 1

        # แปลงเป็นรายการ {name, icon, count} ให้ template วนได้ตรง ๆ
        # (Django ไม่รองรับ {{ dict[key_var] }} — ต้องเตรียมมาให้ใน view)
        ctx['cat_tiles'] = [
            {'name': name, 'icon': self.CAT_ICONS.get(name, 'bi-tag'), 'count': counts[name]}
            for name in cats
        ]
        return ctx


class ProductPublicListView(ListView):
    """หน้าร้าน: ค้นหา + กรองหมวดหมู่ + เรียงลำดับ (GET — แชร์ลิงก์/กดถอยหลังได้)"""
    template_name = 'product.html'
    partial_template_name = 'product_grid.html'
    context_object_name = 'all_products'
    paginate_by = 9

    def get_template_names(self):
        """AJAX live search → คืนเฉพาะ partial grid (ไม่รีทั้งหน้า)"""
        if is_ajax(self.request):
            return [self.partial_template_name]
        return [self.template_name]

    def get_queryset(self):
        params = self.request.GET
        return (
            Product.objects.listed()
            .search(params.get('q', '').strip())
            .of_category(params.get('cat', '').strip())
            .sorted_by(params.get('sort', 'newest'))
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'query': self.request.GET.get('q', '').strip(),
            'active_cat': self.request.GET.get('cat', '').strip(),
            'sort': self.request.GET.get('sort', 'newest'),
            'categories': Catalog.categories(only_listed=True),
        })
        return ctx


class ProductDetailView(DetailView):
    """รายละเอียดสินค้า + สินค้าที่เกี่ยวข้อง — ใช้ queryset.listed() → ของที่ซ่อนหาไม่เจอ."""
    model = Product
    template_name = 'product_detail.html'
    context_object_name = 'product'
    pk_url_kwarg = 'product_id'
    queryset = Product.objects.listed()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['related'] = Product.objects.listed().related_to(self.object, limit=3)
        return ctx


# ==================== ตะกร้า + การสั่งซื้อ (ใช้ Cart service) ====================

class CartMixin:
    """Mixin เปิดทางให้แต่ละ view สร้าง Cart service จาก session ของ request."""

    def get_cart(self):
        return Cart(self.request.session)


class CartView(CartMixin, View):
    """หน้าตะกร้า — รองรับ AJAX (?partial=1) สำหรับปุ่ม +/-/ลบ ไม่ต้องรีหน้า"""

    def get(self, request, *args, **kwargs):
        cart = self.get_cart()
        threshold = Decimal('1500.00')
        free_shipping_needed = max(Decimal('0'), threshold - cart.total)
        free_shipping_percent = min(100, int((cart.total / threshold) * 100)) if threshold > 0 else 100
        ctx = {
            'items': cart.lines(),
            'total': cart.total,
            'cart_count': cart.count,
            'free_shipping_threshold': threshold,
            'free_shipping_needed': free_shipping_needed,
            'free_shipping_percent': free_shipping_percent,
        }
        if is_ajax(request):
            html = render(request, 'cart_area.html', ctx).content.decode('utf-8')
            return JsonResponse({'html': html, 'count': cart.count})
        return render(request, 'cart.html', ctx)


class CartAddView(CartMixin, View):
    """เพิ่มสินค้าในตะกร้า — POST เท่านั้น (GET = 405 กัน crawler กดใส่ตะกร้าเอง).
    เกินสต็อก → HTTP 409 (AJAX) หรือ flash message (form submit ปกติ).
    """

    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product.objects.listed(), id=kwargs['product_id'])
        cart = self.get_cart()
        if not cart.add(product, request.POST.get('quantity', 1)):
            if is_ajax(request):
                return JsonResponse({'ok': False, 'error': f"จำนวนเกินสต็อก (เหลือ {product.stock} ชิ้น)"}, status=409)
            messages.error(request, f"จำนวนเกินสต็อก (เหลือ {product.stock} ชิ้น)")
            return redirect(reverse('product_detail', args=[product.id]))
        if is_ajax(request):
            return JsonResponse({'ok': True, 'count': cart.count, 'message': f"เพิ่ม {product.name} ลงตะกร้าแล้ว!"})
        messages.success(request, f"เพิ่ม {product.name} ลงตะกร้าแล้ว!")
        return redirect(reverse('cart'))


class CartRemoveView(CartMixin, View):
    """ลบสินค้าออกจากตะกร้า — POST เท่านั้น (GET = 405)."""

    def post(self, request, *args, **kwargs):
        self.get_cart().remove(kwargs['product_id'])
        cart = self.get_cart()
        if is_ajax(request):
            return JsonResponse({'ok': True, 'count': cart.count})
        messages.success(request, 'ลบสินค้าออกจากตะกร้าแล้ว!')
        return redirect(reverse('cart'))


class CartUpdateView(CartMixin, View):
    """แก้จำนวนสินค้าในตะกร้า — POST เท่านั้น (GET = 405)."""

    def post(self, request, *args, **kwargs):
        self.get_cart().update(kwargs['product_id'], request.POST.get('quantity', 1))
        if is_ajax(request):
            return JsonResponse({'ok': True, 'count': self.get_cart().count})
        return redirect(reverse('cart'))


def is_ajax(request):
    """ตรวจคำขอ AJAX/partial — จุดเดียวของทั้งโปรเจกต์ (ตาม AGENTS.md).

    ช่องทางที่รองรับ (เรียงตามที่ใช้จริง):
    1. Header `X-Requested-With: fetch` (มาตรฐานของโปรเจกต์) หรือ `XMLHttpRequest` (ไลบรารี/legacy)
    2. `X-Drawer: true` · query `?drawer=1` · ฟิลด์ฟอร์ม `ajax=1` — เปิด order drawer เป็น fragment
    3. Query `?partial=1` — fragment สาธารณะที่ต้องแชร์ URL ได้ (product grid, cart panel)

    ทุก view ที่ต้องเลือก "คืน JSON/partial หรือ redirect เต็มหน้า" ต้องเรียกฟังก์ชันนี้เท่านั้น
    (เดิมมี 4 กลไกกระจัดกระจายตาม view ต่าง ๆ — รวมมาไว้ที่เดียว).
    """
    if request.headers.get('X-Requested-With') in ('fetch', 'XMLHttpRequest'):
        return True
    if request.headers.get('X-Drawer') == 'true':
        return True
    if request.POST.get('ajax') == '1':
        return True
    return request.GET.get('partial') == '1' or request.GET.get('drawer') == '1'


class InsufficientStock(Exception):
    """สต็อกไม่พอระหว่าง checkout (ใช้กับ transaction.atomic)"""

    def __init__(self, product):
        self.product = product
        super().__init__(product.name)


class CheckoutView(CartMixin, View):
    """Checkout: สร้างออเดอร์ + หักสต็อกใน transaction เดียว (กัน oversell).

    - select_for_update ล็อกแถวสินค้าก่อนเช็คสต็อก → ลูกค้า 2 คนกดพร้อมกัน
      ไม่มีใครได้ของเกินสต็อก
    - ผู้ใช้ล็อกอิน: prefill จากที่อยู่ค่าเริ่มต้น/โปรไฟล์, เลือกผ่านสมุดที่อยู่ได้
      (address_id → snapshot จาก DB ไม่เชื่อฟอร์ม)
    - สำเร็จ → ล้างตะกร้า ไป order_success; guest ได้ ?phone= ติดไว้ใช้ยืนยันตัวตน
    """
    template_name = 'checkout.html'

    def _base_ctx(self, cart):
        """Context พื้นฐานของหน้า checkout (รายการสินค้าในตะกร้า + ยอดรวม)."""
        return {'items': cart.lines(), 'total': cart.total}

    def get(self, request, *args, **kwargs):
        ctx = self._base_ctx(self.get_cart())
        if request.user.is_authenticated:
            default_addr = request.user.addresses.filter(is_default=True).first() \
                or request.user.addresses.first()
            profile = getattr(request.user, 'customer_profile', None)
            ctx['prefill'] = {
                'name': (request.user.get_full_name() or request.user.username),
                'phone': (default_addr.phone if default_addr
                          else (profile.phone if profile else '')),
                'detail': default_addr.detail if default_addr else '',
                'province': default_addr.province if default_addr else '',
                'district': default_addr.district if default_addr else '',
                'subdistrict': default_addr.subdistrict if default_addr else '',
                'zipcode': default_addr.zipcode if default_addr else '',
                'address': profile.address if (profile and not default_addr) else '',
            }
            ctx['saved_addresses'] = request.user.addresses.all()
        return render(request, self.template_name, ctx)

    def post(self, request, *args, **kwargs):
        cart = self.get_cart()
        name = request.POST.get('customer_name', '').strip()
        phone_raw = request.POST.get('phone', '').strip()
        detail = request.POST.get('detail', '').strip()
        province = request.POST.get('province', '').strip()
        district = request.POST.get('district', '').strip()
        subdistrict = request.POST.get('subdistrict', '').strip()
        zipcode = request.POST.get('zipcode', '').strip()
        method = request.POST.get('payment_method', 'promptpay')
        if method not in {m[0] for m in Order.PAYMENT_METHODS}:
            method = 'promptpay'

        # สมุดที่อยู่: ถ้าส่ง address_id ของที่อยู่ที่บันทึกไว้ → snapshot จาก DB (เชื่อถือได้)
        addr_id = request.POST.get('address_id', '')
        if request.user.is_authenticated and addr_id.isdigit():
            saved = request.user.addresses.filter(id=int(addr_id)).first()
            if saved:
                name = saved.receiver_name
                phone_raw = saved.phone
                detail, province = saved.detail, saved.province
                district, subdistrict = saved.district, saved.subdistrict
                zipcode = saved.zipcode

        def ctx_error(msg):
            base = self._base_ctx(cart)
            base.update({
                'form_name': name, 'form_phone': phone_raw, 'form_method': method,
                'form_detail': detail, 'f_province': province, 'f_district': district,
                'f_subdistrict': subdistrict, 'f_zipcode': zipcode,
            })
            if request.user.is_authenticated:
                base['saved_addresses'] = request.user.addresses.all()
                base['prefill'] = {}
            if msg:
                messages.error(request, msg)
            return render(request, self.template_name, base)

        if not name or not phone_raw or not detail or not province \
                or not district or not subdistrict or not zipcode:
            return ctx_error('กรุณากรอกข้อมูลและเลือกที่อยู่ให้ครบทุกช่อง')
        if not Validators.valid_phone(phone_raw):
            return ctx_error('เบอร์โทรศัพท์ไม่ถูกต้อง (ต้องเป็นเบอร์ไทย 0XXXXXXXXX)')
        if not zipcode.isdigit() or len(zipcode) != 5:
            return ctx_error('รหัสไปรษณีย์ไม่ถูกต้อง (5 หลัก)')

        address_full = f'{detail} {subdistrict} {district} {province} {zipcode}'
        name = name[:100]   # ตรง max_length ของ Order.customer_name (SQLite ไม่ enforce เอง)
        items = cart.lines()
        total = cart.total
        if cart.is_empty or not items:
            messages.error(request, 'ตะกร้าของคุณว่างเปล่า กรุณาเลือกสินค้าก่อน')
            return redirect(reverse('product'))

        # Atomic: สั่งซื้อ+หักสต็อกสำเร็จพร้อมกันทั้งก้อน หรือไม่เกิดอะไรเลย
        # select_for_update ล็อกแถวสินค้า → กัน oversell เมื่อลูกค้าหลายคนจ่ายพร้อมกัน
        try:
            with transaction.atomic():
                locked_items = []
                for item in items:
                    p = Product.objects.select_for_update().get(id=item['product'].id)
                    if item['quantity'] > p.stock:
                        raise InsufficientStock(p)
                    locked_items.append((p, item))

                order = Order.objects.create(
                    customer_name=name,
                    phone=Validators.normalize_phone(phone_raw),
                    address=address_full,
                    total=sum((p.price * it['quantity'] for p, it in locked_items), Decimal('0')),
                    payment_method=method,
                    user=request.user if request.user.is_authenticated else None,
                )
                for p, item in locked_items:
                    OrderItem.objects.create(
                        order=order, product=p,
                        quantity=item['quantity'], price=p.price,
                    )
                    Product.objects.filter(id=p.id).update(stock=p.stock - item['quantity'])
        except InsufficientStock as e:
            messages.error(request, f"สินค้า {e.product.name} มีเหลือไม่พอ (เหลือ {e.product.stock} ชิ้น) กรุณาปรับจำนวนในตะกร้า")
            return ctx_error('')

        # บัญชี: ติ๊ก "จำที่อยู่" → เพิ่มเข้าสมุดที่อยู่ (ตั้งเป็นค่าเริ่มต้นถ้ายังไม่มี)
        if request.user.is_authenticated and request.POST.get('save_info') \
                and not request.POST.get('address_id'):
            is_first = not request.user.addresses.exists()
            CustomerAddress.objects.create(
                user=request.user,
                label=f'บ้าน ({subdistrict})' if is_first else 'ที่อยู่จากคำสั่งซื้อ',
                receiver_name=name,
                phone=Validators.normalize_phone(phone_raw),
                detail=detail, province=province, district=district,
                subdistrict=subdistrict, zipcode=zipcode,
                is_default=is_first,
            )
            messages.success(request, 'บันทึกที่อยู่เข้าสมุดที่อยู่แล้ว — ครั้งหน้าเลือกใช้ได้เลย')

        cart.clear()
        success_url = reverse('order_success', args=[order.id])
        if not request.user.is_authenticated:
            success_url += f'?phone={order.phone}'
        return redirect(success_url)


class OrderSuccessView(TemplateView):
    """หน้าสำเร็จหลังสั่งซื้อ — แสดง QR พร้อมเพย์ + ปุ่มอัปโหลดสลิป.

    เข้าถึงได้เฉพาะเจ้าของ (ล็อกอิน) / staff / guest ที่ส่ง ?phone ตรงกับออเดอร์ —
    คนอื่นโดน Http404 (ไม่อยากบอกใบ้ว่ามีออเดอร์นี้อยู่จริง).
    """
    template_name = 'order_success.html'

    def get(self, request, *args, **kwargs):
        order_id = int(kwargs['order_id'])
        order = get_object_or_404(Order, id=order_id)
        if request.user.is_authenticated:
            # staff ตรวจสอบได้ทุกออเดอร์ — ลูกค้าเห็นได้เฉพาะของตัวเอง
            if not request.user.is_staff and order.user_id != request.user.id:
                from django.http import Http404
                raise Http404
        else:
            phone_raw = request.GET.get('phone', '')
            if not phone_raw or Validators.normalize_phone(phone_raw) != Validators.normalize_phone(order.phone):
                return redirect(f"{reverse('order_tracking')}?order={order_id}&phone={phone_raw}")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        order = get_object_or_404(Order, id=int(self.kwargs['order_id']))
        ctx['order'] = order
        ctx['promptpay_display'] = settings.PROMPTPAY_ID
        ctx['slip_enabled'] = SlipOK.enabled()
        # ประเมินกำหนดจัดส่งด้วยปฏิทินไทย (ข้ามเสาร์/อาทิตย์ + วันหยุดนักขัตฤกษ์ — Google ICS, keyless)
        eta = ThaiCalendar.next_business_day()
        ctx['delivery_eta'] = eta
        ctx['delivery_eta_display'] = ThaiCalendar.format(eta)
        ctx['pp_payload'] = PromptPay.qr_payload(order.total) or ''
        try:
            ctx['qr'] = PromptPay.qr_data_uri(order.total)
        except Exception:
            ctx['qr'] = None
        return ctx


class ProductDescribeAIView(StaffRequiredMixin, View):
    """POST /product/describe-ai/ — ช่วยเขียนคำอธิบายสินค้า (staff only)

    เดิมบั๊กหนัก: `return JsonResponse({'description': text})` อยู่**ในบล็อก except
    หลัง return** → เส้นทางสำเร็จไม่มีการคืนค่าเลย (Django ตอบ 500 "view didn't
    return an HttpResponse") และบรรทัดนั้นเป็นโค้ดตาย
    = ปุ่มนี้พังทุกครั้ง แม้ตั้ง API key ถูกต้องแล้ว

    ตอนนี้: มี key → ใช้ Gemini · ไม่มี key → ใช้ตัวสำรองแบบกฎ (`ProductDescription`)
    และตอบ `source` กลับไปให้ UI แสดงว่าได้ข้อความมาจากทางไหน (ไม่หลอกว่าเป็น AI)
    """

    def post(self, request, *args, **kwargs):
        name = request.POST.get('name', '').strip()
        if not name:
            return JsonResponse({'error': 'กรอกชื่อสินค้าก่อน แล้วกดปุ่มช่วยเขียน'}, status=400)
        category = request.POST.get('category', '').strip()

        if not GeminiAI.enabled():
            # ไม่มี key: ยังให้ผลลัพธ์ใช้ได้ เพื่อให้ฟีเจอร์นี้ทดสอบได้จริง
            return JsonResponse({
                'description': ProductDescription.suggest(name, category),
                'source': 'rule',
                'notice': 'สร้างจากแม่แบบตามชื่อ/หมวด — ไม่ได้ใช้ AI '
                          '(ยังไม่ได้ตั้ง GEMINI_API_KEY) ผู้ดูแลต้องตรวจทานก่อนใช้จริง',
            })

        try:
            text = GeminiAI.describe_product(name, category)
        except Exception as exc:
            detail = f' — {exc}' if settings.DEBUG else ''
            return JsonResponse({'error': f'AI ขัดข้องหรือตอบไม่สำเร็จ{detail}'}, status=502)
        return JsonResponse({'description': text, 'source': 'ai'})


class ProductTranslateView(StaffRequiredMixin, View):
    """POST /product/translate/ — แปลคำอธิบายสินค้า (EN→TH / TH→EN) ด้วย MyMemory (staff only).

    ทำงานได้โดยไม่ต้องมี API key ใด ๆ — คู่กับปุ่ม "AI ช่วยเขียน" (Gemini ที่ต้องมี key):
    ใช้เมื่อสตาฟวางสเปก/คำอธิบายภาษาอังกฤษจากผู้ผลิตแล้วอยากได้คำอธิบายไทย.
    """

    def post(self, request, *args, **kwargs):
        text = (request.POST.get('text') or request.POST.get('description') or '').strip()
        if not text:
            return JsonResponse({'error': 'พิมพ์ข้อความที่ต้องการแปลก่อน'}, status=400)
        target = 'en' if request.POST.get('target') == 'en' else 'th'
        source = 'en' if target == 'th' else 'th'
        translated = Translate.text(text, source=source, target=target)
        if not translated:
            return JsonResponse({
                'error': 'แปลไม่สำเร็จ — ข้อความยาวเกิน 500 ตัวอักษร หรือโควตาการแปลฟรีหมดชั่วคราว'
            }, status=502)
        return JsonResponse({'text': translated})


class OrderTrackingView(View):
    template_name = 'order_tracking.html'

    def get(self, request, *args, **kwargs):
        """ผู้ใช้ที่ล็อกอิน: แสดงออเดอร์ของตัวเองให้เลือกดูได้ทันที (ไม่ต้องพิมพ์ id/เบอร์)
        มี ?order=&phone= → ค้นให้เลย | ไม่ล็อกอิน → ฟอร์มค้นหาสำหรับ guest"""
        if request.user.is_authenticated:
            base = {
                # (Perf A2) prefetch items__product — template วน o.items.all.0.product.name
                # เดิม N+1 → ตอนนี้ 2 query (orders + items/products)
                'my_orders': (request.user.orders
                              .select_related('user')
                              .prefetch_related('items__product')
                              .order_by('-created_at')[:12]),
                'is_account_mode': True,
            }
            oid = request.GET.get('order')
            phone = request.GET.get('phone')
            if oid and phone:
                base.update(self._find(oid, phone, request))
            else:
                base['order'] = None
            return render(request, self.template_name, base)
        oid = request.GET.get('order')
        phone = request.GET.get('phone')
        if oid and phone:
            return render(request, self.template_name, self._find(oid, phone, request))
        return render(request, self.template_name, {'order': None})

    def post(self, request, *args, **kwargs):
        ctx = self._find(request.POST.get('order_id', ''), request.POST.get('phone', ''), request)
        if request.user.is_authenticated:
            ctx.update({
                'my_orders': (request.user.orders
                              .select_related('user')
                              .prefetch_related('items__product')
                              .order_by('-created_at')[:12]),
                'is_account_mode': True,
            })
        return render(request, self.template_name, ctx)

    @staticmethod
    def _find(order_id, phone_raw, request=None):
        try:
            oid = int(order_id)
        except (ValueError, TypeError):
            oid = 0
        phone = (phone_raw or '').strip()
        # ออเดอร์ใหม่เก็บเบอร์แบบตัวเลขล้วน — รองรับออเดอร์เก่าที่มี - / ช่องว่าง ด้วย
        candidates = {phone, Validators.normalize_phone(phone)}
        order = Order.objects.filter(id=oid, phone__in=candidates).first()
        ctx = {'order': order}
        if order:
            reported = order.reported_total
            ctx['payments'] = order.payments.order_by('-created_at')
            ctx['reported'] = reported
            ctx['remaining'] = order.remaining
            ctx['slip_enabled'] = SlipOK.enabled()
            ctx['issues'] = order.issues.order_by('-created_at')
        elif request is not None:
            messages.error(request, 'ไม่พบออเดอร์ กรุณาตรวจสอบหมายเลขออเดอร์และเบอร์โทรศัพท์')
        return ctx


def _authed_order(request, order_id, phone_raw):
    """หาออเดอร์ + ยืนยันเจ้าของด้วยเบอร์โทร (ใช้ร่วม payment/tracking/quick-pay/slip)
    คืน (order, error_message) — order=None เมื่อไม่ผ่าน"""
    try:
        oid = int(order_id)
    except (ValueError, TypeError):
        return None, 'หมายเลขออเดอร์ไม่ถูกต้อง'
    order = Order.objects.filter(id=oid).first()
    if not order:
        return None, 'ไม่พบหมายเลขออเดอร์นี้ กรุณาตรวจสอบอีกครั้ง'
    input_phone = Validators.normalize_phone(phone_raw)
    if not Validators.valid_phone(input_phone):
        return None, 'เบอร์โทรศัพท์ไม่ถูกต้อง (ต้องเป็นเบอร์ไทย 0XXXXXXXXX)'
    if input_phone != Validators.normalize_phone(order.phone):
        return None, f'เบอร์โทรไม่ตรงกับออเดอร์ #{order.id} — กรุณาใช้เบอร์ที่ใช้สั่งซื้อ'
    return order, None


class PaymentRedirectView(View):
    """หน้า /payment/ ถูกยุบรวมเข้า checkout + success + tracking แล้ว
    เก็บ URL เดิมไว้เป็น redirect เพื่อไม่ให้ลิงก์เก่าพัง"""

    def get(self, request, *args, **kwargs):
        oid = request.GET.get('order')
        phone = request.GET.get('phone')
        if oid and phone:
            return redirect(f"{reverse('order_tracking')}?order={oid}&phone={phone}")
        return redirect(reverse('product') if not request.user.is_authenticated else reverse('account'))


class QuickPayView(View):
    """POST /payment/quick/ — "ฉันโอนยอดเต็มแล้ว" 1 คลิก:
    บันทึก Payment(ยอดคงเหลือทั้งหมด, วันที่วันนี้) ผ่าน PaymentService
    — พอยอดครบ สถานะจะขึ้น "ชำระแล้ว" อัตโนมัติ"""

    def post(self, request, *args, **kwargs):
        order, err = _authed_order(request, request.POST.get('order_id'), request.POST.get('phone'))
        back = request.POST.get('back') or reverse('order_tracking')
        if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
            back = reverse('order_tracking')
        if err:
            messages.error(request, err)
            return redirect(back)
        if order.status != 'pending':
            messages.info(request, f'ออเดอร์ #{order.id} ไม่ได้อยู่ในสถานะรอชำระเงิน')
            return redirect(back)
        remaining = order.remaining
        if remaining <= 0:
            messages.info(request, f'ออเดอร์ #{order.id} มียอดแจ้งครบแล้ว')
            return redirect(back)
        result = PaymentService.record_payment(
            order=order, name=order.customer_name, phone=order.phone,
            amount=remaining, transfer_date=timezone.localtime().date(),
            note='ยืนยันโอนยอดเต็มจากหน้าเว็บ (1-คลิก)', source='quickpay',
            request=request,
        )
        if not result['ok']:
            # ออเดอร์ถูกจ่ายครบจาก request อื่นระหว่างที่กด (race) — บอกตามจริง
            messages.info(request, result['error'])
            return redirect(back)
        if result['just_paid']:
            messages.success(request, f'ออเดอร์ #{order.id} รับยอดโอนครบแล้ว — ชำระเงินเรียบร้อย!')
        else:
            messages.success(request, f'บันทึกการแจ้งชำระออเดอร์ #{order.id} เรียบร้อย!')
        return redirect(back)


class PaymentManualView(View):
    """POST /payment/manual/ — ลูกค้ากรอกยอดที่โอนเอง (ไม่ต้องพึ่ง OCR)

    ทำไมต้องมี
        เดิมมีแค่ 2 ทาง: อัปโหลดสลิป (ต้องมี `SLIPOK_API_KEY`) หรือกดปุ่ม
        1-คลิก (สมมติว่าจ่ายเต็ม) — ถ้าไม่มี key จะ**ไม่เหลือทางให้ลูกค้าแจ้งยอด**
        และข้อความ error ของ OCR ยังบอกลูกค้าว่า "หรือกรอกแบบฟอร์มด้านล่าง"
        ทั้งที่ไม่มีฟอร์มนั้นอยู่จริง → ระบบหลอกผู้ใช้เรื่องที่ควรห้ามหลอก

        ฟอร์มนี้ปิดช่องโหว่นั้น และทำให้ขั้น "ชำระเงิน" โชว์ได้ครบทุกกรณี
        ไม่ว่าจะมี OCR หรือไม่ — รวมถึงกรณีจ่ายบางส่วน

    ความปลอดภัย
        ใช้ `_authed_order` ยืนยันเจ้าของออเดอร์ด้วยเบอร์โทร เหมือนทางอื่น
        ทุกอย่างเดินผ่าน `PaymentService.record_payment()` จุดเดียวเดียวกัน
        → ยอดเกิน/จ่ายซ้ำ/ออเดอร์ที่ปิดแล้ว ถูกปฏิเสธที่ service อยู่แล้ว
    """

    def post(self, request, *args, **kwargs):
        order, err = _authed_order(request, request.POST.get('order_id'),
                                   request.POST.get('phone'))
        back = request.POST.get('back') or reverse('order_tracking')
        if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
            back = reverse('order_tracking')
        if err:
            messages.error(request, err)
            return redirect(back)

        # เขียนยอดก่อนข้างบน (เช่น 500) เพื่อกันพิมพ์ผิดเป็นจำนวนมหศาล
        try:
            amount = Decimal(request.POST.get('amount', '').replace(',', '').strip())
        except (InvalidOperation, ValueError, TypeError):
            messages.error(request, 'ยอดที่โอนไม่ถูกต้อง — กรอกเป็นตัวเลข เช่น 1290')
            return redirect(back)
        if amount <= 0:
            messages.error(request, 'ยอดที่โอนต้องมากกว่า 0')
            return redirect(back)

        raw_date = request.POST.get('transfer_date', '').strip()
        try:
            transfer_date = (datetime.strptime(raw_date, '%Y-%m-%d').date()
                             if raw_date else timezone.localtime().date())
        except ValueError:
            messages.error(request, 'วันที่โอนไม่ถูกต้อง')
            return redirect(back)

        result = PaymentService.record_payment(
            order=order, name=order.customer_name, phone=order.phone,
            amount=amount, transfer_date=transfer_date,
            note=(request.POST.get('note', '') or 'กรอกยอดเองจากหน้าเว็บ').strip()[:200],
            source='manual',
            request=request,
        )
        if not result['ok']:
            messages.info(request, result['error'])
        elif result['just_paid']:
            messages.success(request,
                             f'ออเดอร์ #{order.id} รับยอดโอนครบแล้ว — ชำระเงินเรียบร้อย!')
        else:
            messages.success(
                request,
                f'บันทึกยอด ฿{amount:,.2f} แล้ว — ยังขาดอีก '
                f'฿{result["remaining"]:,.2f} ยอดรวม ฿{order.total:,.2f}')
        return redirect(back)


class OrderConfirmReceivedView(View):
    """POST /order/<id>/confirm-received/ — **ลูกค้า**ยืนยันว่าได้รับสินค้าแล้ว

    ทำไมต้องมี
        ขั้น 'delivered' เดิมให้เฉพาะเจ้าหน้าที่กด → สถานะไม่ได้สะท้อนความจริง
        ถ้าของยังไม่ถึงมือจริง แต่เจ้าหน้าที่เผลอกดปุ่ม ระบบก็บันทึกว่า"ถึงมือแล้ว"
        ซึ่งเป็นข้อมูลผิดที่ยากแก้ทีหลังเพราะระบบเชื่อว่าของถึงแล้ว

        การให้ลูกค้ายืนยันเองตรงกับความจริงของการส่งของ: ของถึงมือก็ต่อเมื่อ
        **ผู้รับ**บอกว่าได้รับแล้ว ไม่ใช่เมื่อผู้ส่งกดว่าส่งแล้ว

    กติกา
        - ต้องเป็นเจ้าของออเดอร์ (ยืนยันด้วยเบอร์โทรเหมือนช่องทางอื่นของลูกค้า)
        - เดินบันไดถูกต้อง: ต้องเป็น 'shipped' เท่านั้น (ห้ามข้ามจาก pending)
        - ยังอนุญาตให้เจ้าหน้าที่กดได้สำหรับกรณีลูกค้าติดต่อไม่ได้
          (เช่น เก็บเงินปลายทาง) — ดู `OrderStatusService.staff_options()`
        - ทั้งสองทางถูกบันทึก audit แยกกัน บอกได้ว่าใครยืนยัน
    """

    def post(self, request, *args, **kwargs):
        order, err = _authed_order(request, request.POST.get('order_id'),
                                   request.POST.get('phone'))
        back = request.POST.get('back') or reverse('order_tracking')
        if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
            back = reverse('order_tracking')
        if err:
            messages.error(request, err)
            return redirect(back)

        if order.status == 'delivered':
            messages.info(request, f'ออเดอร์ #{order.id} ยืนยันรับสินค้าแล้วอยู่')
            return redirect(back)
        if order.status != 'shipped':
            messages.error(
                request,
                f'ออเดอร์ #{order.id} ยังไม่ได้จัดส่ง (ตอนนี้คือ "{order.get_status_display()}") '
                f'— ยืนยันรับสินค้าได้ต่อเมื่อร้านกดจัดส่งแล้วเท่านั้น')
            return redirect(back)

        OrderStatusService.auto_move(order, 'delivered', actor='customer:confirm-received')
        Audit.record(
            request.user, 'order_status',
            summary=(f'ออเดอร์ #{order.id}: ลูกค้ายืนยันได้รับสินค้าแล้ว '
                     f'({order.customer_name})'),
            target=order,
            before={'status': 'shipped'}, after={'status': 'delivered'},
            request=request,
        )
        messages.success(request,
                         f'ขอบคุณครับ ยืนยันรับสินค้าออเดอร์ #{order.id} เรียบร้อยแล้ว')
        return redirect(back)


class SlipVerifyView(View):
    """POST /payment/slip/ — อัปโหลดสลิป → SlipOK OCR → สร้าง Payment อัตโนมัติ
    คืน JSON สำหรับ fetch (X-Requested-With)

    จำกัดอัตรา 10 ครั้ง/นาที ต่อ IP (RateLimit service) — endpoint สาธารณะที่เรียก
    OCR ภายนอกทุกครั้ง จึงมีต้นทุนจริงและต้องกันการยิงรัว.
    """

    MAX_MB = 5
    ALLOWED_EXT = {'.jpg', '.jpeg', '.png', '.webp'}

    def post(self, request, *args, **kwargs):
        # throttle ก่อนทุกอย่าง — กัน abuse แม้ฟีเจอร์ OCR ปิดอยู่
        client_ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
        if not RateLimit.allow('slip', client_ip, limit=10, window=60):
            return JsonResponse({'ok': False, 'error': 'ตรวจสลิปบ่อยเกินไป กรุณารอสักครู่แล้วลองใหม่'}, status=429)
        if not SlipOK.enabled():
            return JsonResponse({'ok': False, 'error': 'ระบบอ่านสลิปยังไม่เปิดใช้งาน'}, status=503)
        order, err = _authed_order(request, request.POST.get('order_id'), request.POST.get('phone'))
        if err:
            return JsonResponse({'ok': False, 'error': err}, status=403)

        upload = request.FILES.get('slip')
        if not upload:
            return JsonResponse({'ok': False, 'error': 'กรุณาแนบรูปสลิป'}, status=400)
        if upload.size > self.MAX_MB * 1024 * 1024:
            return JsonResponse({'ok': False, 'error': f'ไฟล์ใหญ่เกิน {self.MAX_MB}MB'}, status=400)
        ext = os.path.splitext(upload.name or '')[1].lower()
        if ext not in self.ALLOWED_EXT:
            return JsonResponse({'ok': False, 'error': 'รองรับเฉพาะ JPG/PNG/WebP'}, status=400)

        try:
            parsed = SlipOK.verify(upload.read(), filename='slip' + ext)
        except RuntimeError as e:
            msg = {
                'no-api-key': 'ระบบยังไม่เปิดใช้งาน',
            }.get(str(e), 'อ่านสลิปไม่สำเร็จ — ลองถ่ายใหม่ให้ชัด หรือใช้ช่อง "แจ้งยอดโอนเอง" ด้านล่าง')
            detail = str(e) if settings.DEBUG else ''
            return JsonResponse({'ok': False, 'error': msg + (f' ({detail})' if detail else '')}, status=502)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'เชื่อมต่อระบบตรวจสลิปไม่ได้ ลองอีกครั้ง'}, status=502)

        if parsed['amount'] <= 0:
            return JsonResponse({'ok': False, 'error': 'อ่านยอดเงินจากสลิปไม่ได้'}, status=422)

        # ออเดอร์ต้องยังรอชำระ — เช็คก่อนยิง OCR ประหยัดค่าใช้จ่ายภายนอก
        # (service กันซ้ำอีกชั้น แต่ถ้ารอถึงตรงนั้นเราจะเสียเงินค่า OCR ไปเปล่า ๆ)
        # เคยพลาดตรงนี้: QuickPayView มีการเช็ค แต่หน้านี้ไม่มี → อัปโหลดสลิปใส่
        # ออเดอร์ที่จ่ายแล้วได้ → Payment ยอดเกิน → รายงานการเงินเพี้ยน
        if order.status != 'pending':
            return JsonResponse({
                'ok': False,
                'error': f'ออเดอร์ #{order.id} ไม่ได้อยู่ในสถานะรอชำระเงิน '
                         f'(ตอนนี้คือ "{order.get_status_display()}") — ไม่ต้องส่งสลิปแล้ว',
            }, status=409)

        result = PaymentService.record_payment(
            order=order, name=order.customer_name, phone=order.phone,
            amount=parsed['amount'],
            transfer_date=parsed['transfer_date'] or timezone.localtime().date(),
            note=parsed['note'], source='slip',
            request=request,
        )
        # ชั้น service อาจปฏิเสธ (เช่น อีก request เข้ามาจ่ายครบพอดีระหว่าง OCR)
        if not result['ok']:
            return JsonResponse({'ok': False, 'error': result['error']}, status=409)
        return JsonResponse({
            'ok': True,
            'amount': str(parsed['amount']),
            'remaining': str(result['remaining']),
            'paid': result['paid'],
            'just_paid': result['just_paid'],
            'message': (
                f'ตรวจสลิปสำเร็จ {parsed["amount"]} บาท — ชำระครบแล้ว!'
                if result['just_paid'] else
                f'ตรวจสลิปสำเร็จ {parsed["amount"]} บาท — ยังขาดอีก {result["remaining"]} บาท'
            ),
        })


class ContactView(TemplateView):
    """หน้าติดต่อผู้จัดทำ + ข้อมูลติดต่อร้าน + แผนที่.

    ส่วนฟอร์มแจ้งปัญหาแยกออกไปอยู่หน้า `/issue/` (`IssueReportView`) แล้ว
    เพื่อให้หน้าติดต่อมีหน้าที่เดียวชัดเจน และมีปุ่มลัดพาไปหน้าแจ้งปัญหาแทน.
    """

    template_name = 'contact.html'


class IssueReportView(TemplateView):
    """หน้าแจ้งปัญหาสำหรับลูกค้า (`/issue/`) — แยกออกจาก `/contact/` เป็นหน้าเฉพาะ.

    ทำไมต้องแยกเป็นหน้าเฉพาะ
        หน้าติดต่อ (`/contact/`) คือข้อมูลร้าน + แผนที่ ส่วนการแจ้งปัญหาคืองานบริการลูกค้า
        ที่ผูกกับออเดอร์ได้และตรวจสถานะย้อนหลังได้ การแยกออกทำให้:
          1. มีลิงก์ตรงในเมนู/ปุ่มจากหน้าติดตามออเดอร์และหน้าบัญชีผู้ใช้ (`/issue/?order=...&phone=...`)
          2. ลูกค้าที่ล็อกอินอยู่เห็นประวัติเรื่องที่ตัวเองเคยแจ้งและผลการดำเนินการในหน้าเดียวกันทันที
          3. ถ้าส่งมาจากปุ่มในออเดอร์ (`?order=&phone=`) ระบบตรวจสิทธิ์ด้วย `_authed_order`
             ก่อนผูกออเดอร์ให้อัตโนมัติ (แจ้งแทนออเดอร์คนอื่นไม่ได้)
    """

    template_name = 'issue_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['kinds'] = OrderIssue.KIND_CHOICES
        # มาจากปุ่ม "พบปัญหากับออเดอร์นี้" หรือการ์ดในหน้าบัญชี → ?order=&phone=
        # ยืนยันตัวตนด้วยเลขออเดอร์ + เบอร์โทรเหมือนทุกช่องทางของลูกค้าก่อนผูกกับออเดอร์
        if self.request.GET.get('order'):
            order, err = _authed_order(
                self.request,
                self.request.GET.get('order'),
                self.request.GET.get('phone'),
            )
            ctx['order'] = order
            ctx['order_err'] = err
        if self.request.user.is_authenticated:
            ctx['my_issues'] = (
                OrderIssue.objects.for_customer(self.request.user)
                .select_related('order')[:10]
            )
        return ctx


# ==================== Base: ตารางค้นหาเรียลไทม์ (Template Method Pattern) ====================

class LiveSearchListView(StaffRequiredMixin, ListView):
    """Base ของหน้าตารางที่มีค้นหา + ตัวกรอง + เรียงลำดับ + แบ่งหน้า + partial fetch
    Subclass กำหนด model/partial/filter_params และ override filter_queryset() ได้"""

    paginate_by = 5
    partial_template_name = None   # template สำหรับ fetch (เฉพาะแถวตาราง)
    filter_params = ()             # ชื่อพารามิเตอร์ตัวกรองที่ใช้ใน has_filter/context
    default_sort = 'newest'

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get('q', '').strip()
        queryset = queryset.search(query)
        queryset = self.filter_queryset(queryset)
        sort = self.request.GET.get('sort', self.default_sort)
        return queryset.sorted_by(sort)

    def filter_queryset(self, queryset):
        """Hook สำหรับ subclass: เพิ่มตัวกรองเฉพาะหน้า"""
        return queryset

    def render_to_response(self, context):
        # Live search: คืนเฉพาะส่วนตาราง + ตัวนับ + แบ่งหน้า สำหรับ fetch
        if self.partial_template_name and is_ajax(self.request):
            return render(self.request, self.partial_template_name, context)
        return super().render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get('q', '').strip()
        values = {param: self.request.GET.get(param, '').strip() for param in self.filter_params}
        context.update(values)
        context.update({
            'query': query,
            'sort': self.request.GET.get('sort', self.default_sort),
            'has_filter': bool(query or any(values.values())),
            'total': context['paginator'].count,
        })
        return context


# ==================== Workshop 4: Employee Management (Admin Zone) ====================

class DashboardView(StaffRequiredMixin, TemplateView):
    """หน้าแดชบอร์ดผู้ดูแล: สรุปข้อมูลจริงจากฐานข้อมูลทุกโมดูล"""
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        emp_stats = Employee.objects.stats()
        prod_stats = Product.objects.stats()
        order_stats = Order.objects.stats()
        departments = Employee.objects.department_distribution(limit=6)
        context.update({
            'emp_total': emp_stats['total'], 'emp_active': emp_stats['active'],
            'emp_leave': emp_stats['leave'],
            'prod_total': prod_stats['total'], 'prod_active': prod_stats['active'],
            'prod_out': prod_stats['out'],
            'stock_value': Product.objects.inventory_value(),
            'low_stock': Product.objects.low_stock()[:5],
            'recent_emps': Employee.objects.recent(limit=5),
            'recent_orders': Order.objects.recent(limit=5),
            'order_total': order_stats['total'], 'order_pending': order_stats['pending'],
            'order_paid': order_stats.get('paid', 0),
            'revenue': order_stats['revenue'],
            'departments': departments,
            'dept_max': max([d['n'] for d in departments], default=1) or 1,
            'greeting': ThaiCalendar.greeting(),
            'thai_date': ThaiCalendar.full_date(),
            'pending_reports': self._pending_reports(),
        })
        # QR มือถือสำหรับสแกนเปิดระบบพนักงาน — สร้างฝั่งเซิร์ฟเวอร์จาก URL จริง
        # (ไม่โหลดไลบรารี QR จาก CDN; ผู้ใช้ที่ไม่มี JS ก็ยังเห็น QR)
        mobile_url = self.request.build_absolute_uri('/employees/')
        context['mobile_qr_target'] = mobile_url
        context['mobile_qr_display'] = mobile_url.replace('https://', '').replace('http://', '')
        context['mobile_qr_uri'] = QrCode.data_uri(mobile_url)
        return context

    @staticmethod
    def _pending_reports():
        """คิวตรวจการแจ้งชำระ: รายการล่าสุดของออเดอร์ที่ยัง pending.
        (Perf A1) เคยวน p.order.reported_total + p.order.remaining (= เรียก reported_total
        ซ้ำ) ต่อแถว = ~2 aggregate query/แถว → ~20 query/หน้า. แก้: annotate ยอดสะสมต่อ
        order ครั้งเดียวแล้วคำนวณ remaining ใน Python = รวม 2 query เสมอ."""
        rows = []
        payments = (Payment.objects
                    .filter(order__status='pending')
                    .select_related('order')
                    .order_by('-created_at')[:10])
        if not payments:
            return rows
        from django.db.models import Sum
        reported_map = dict(
            Order.objects.filter(id__in=[p.order_id for p in payments])
            .annotate(reported=Sum('payments__amount'))
            .values_list('id', 'reported')
        )
        for p in payments:
            reported = reported_map.get(p.order_id) or Decimal('0')
            remaining = max(p.order.total - reported, Decimal('0'))
            rows.append({
                'payment': p,
                'reported': reported,
                'remaining': remaining,
                # ยอดที่แจ้งมา "ครบ" เท่ากับออเดอร์ถูกปิดอัตโนมัติแล้ว
                # (PaymentService.record_payment เลื่อนสถานะทันทีที่ครบยอด)
                # → คิวนี้เหลือได้แต่รายการที่ **ยังขาดอยู่** เท่านั้น
                'short': remaining > 0,
            })
        return rows


class PaymentVerifyView(StaffRequiredMixin, View):
    """POST /dashboard/payment/<id>/verify/ — บันทึกว่าเจ้าหน้าที่ตรวจบัญชีแล้ว

    ⚠️ ข้อจำกัดที่ต้องรู้ (และเป็นเหตุผลที่ UI ไม่มีปุ่มนี้แล้ว)
        ออเดอร์จะถูกปิดเป็น 'paid' **อัตโนมัติ** ใน `PaymentService.record_payment()`
        เมื่อยอดที่แจ้งครบยอดรวม ดังนั้นออเดอร์ที่ยังเป็น 'pending'
        (คิวนี้คือคิวนี้) หมายความว่า **ยอดยังไม่ครบเสมอ**
        → view นี้จึงปฏิเสธไปทางเดียว ไม่มีทางสำเร็จ

        คงไว้เพราะยังเป็นชั้นป้องกันที่ถูกต้อง (ถ้ามีทางอื่นเรียกเข้ามา
        ต้องได้ผลเป็นการปฏิเสธ + บอกเหตุผล ไม่ใช่เงียบๆ ไป)
        คำสั่งซื้อซ้ำ/แก้ไขอาจารย์ยังเรียกซ้ำได้ และถ้าวันหนึ่งกติกาการชำระ
        เปลี่ยน (เช่น ต้องให้เจ้าหน้าที่ยืนยันก่อนจึงจะปิดออเดอร์) จุดนี้คือ
        ที่ที่ต้องแก้ — ไม่ใช่แก้ที่ template
    """

    def post(self, request, *args, **kwargs):
        payment = get_object_or_404(Payment.objects.select_related('order'), id=kwargs['payment_id'])
        order = payment.order
        if order.status == 'pending':
            reported = order.reported_total
            if reported < order.total:
                messages.error(request,
                               f'ยังยืนยันไม่ได้ — ออเดอร์ #{order.id} แจ้งมา {reported} บาท '
                               f'จากยอดรวม {order.total} บาท (ขาดอีก {order.total - reported} บาท)')
            else:
                OrderStatusService.auto_move(order, 'paid', actor='staff:payment_verify')
                messages.success(request, f'ยืนยันการชำระออเดอร์ #{order.id} ({payment.amount} บาท) แล้ว')
                # ยืนยันเงิน = กระทำที่กระทบตัวเงินโดยตรง ต้องตรวจสอบย้อนหลังได้
                Audit.record(
                    request.user, 'payment',
                    summary=f'ยืนยันยอด ฿{payment.amount} ออเดอร์ #{order.id} '
                            f'(ยอดสะสม ฿{reported})',
                    target=order,
                    after={'status': order.status, 'total': str(reported)},
                    request=request,
                )
        else:
            messages.info(request, f'ออเดอร์ #{order.id} ถูกดำเนินการไปแล้ว ({order.get_status_display()})')
        return redirect(reverse('dashboard') + '#reports')


class ActivityLogListView(LiveSearchListView):
    """หน้า "ประวัติการทำงาน" — ตอบคำถาม "ใครทำอะไร เมื่อไหร่"

    ออกแบบตามหลัก UX ของคนทำงานจริง (user-centric):
    - ค้นหาได้ทันที (live search ผ่าน partial fetch) ด้วยชื่อคน/คำอธิบาย/สิ่งที่แก้
    - กรองตามประเภทการกระทำได้ — เพราะ "เงิน" กับ "สินค้า" คนละเรื่องกัน
    - แสดง before → after ในตาราง เพื่อไม่ต้องเปิดรายละเอียดอีกชั้น
    - เรียงตามเวลาล่าสุดก่อน (เรื่องที่เพิ่งเกิดสำคัญที่สุด)
    """

    model = ActivityLog
    template_name = 'activity_log.html'
    partial_template_name = 'activity_log_rows.html'
    context_object_name = 'logs'
    paginate_by = 15
    filter_params = ('action',)

    def filter_queryset(self, queryset):
        action = self.request.GET.get('action', '').strip()
        return queryset.filter(action=action) if action else queryset

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # ตัวเลือก dropdown + ป้ายสีสำหรับแต่ละประเภท (ใช้ร่วมกันทั้งหน้า)
        ctx['action_choices'] = ActivityLog.ACTION_CHOICES
        return ctx


class ActivityLogExportCsvView(CsvSafeMixin, StaffRequiredMixin, View):
    """ส่งออกประวัติเป็น CSV — ใช้เมื่อต้องส่งรายงานให้ผู้ใหญ่/อาจารย์"""

    HEADERS = ['เวลา', 'ผู้ทำ', 'ประเภท', 'คำอธิบาย', 'สิ่งที่ถูกแก้',
               'ค่าเดิม', 'ค่าใหม่', 'IP']

    MAX_ROWS = 20000      # กัน export กิน memory จน process ตาย

    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        filename = f"activity_{timezone.localdate().isoformat()}.csv"
        response['Content-Disposition'] = f'attachment; filename={filename}'
        response.write('﻿')   # BOM กัน Excel อ่านไทยเพี้ยน
        writer = csv.writer(response)
        writer.writerow(self.HEADERS)

        qs = ActivityLog.objects.select_related('actor').order_by('-created_at')
        action = request.GET.get('action', '').strip()
        query = request.GET.get('q', '').strip()
        if action:
            qs = qs.filter(action=action)
        if query:
            qs = qs.search(query)

        for log in qs[:self.MAX_ROWS]:
            writer.writerow([
                timezone.localtime(log.created_at).strftime('%d/%m/%Y %H:%M:%S'),
                self._safe_cell(log.actor_name or (log.actor.username if log.actor else 'ระบบ')),
                self._safe_cell(log.get_action_display()),
                self._safe_cell(log.summary),
                self._safe_cell(log.target_label or log.target_id),
                self._safe_cell(self._fmt(log.before)),
                self._safe_cell(self._fmt(log.after)),
                self._safe_cell(log.ip or ''),
            ])
        return response

    @staticmethod
    def _fmt(payload):
        """แปลง dict before/after เป็นข้อความอ่านง่าย"""
        if not payload:
            return ''
        return ', '.join(f'{k}={v}' for k, v in payload.items())


class EmployeeExportCsvView(CsvSafeMixin, StaffRequiredMixin, View):
    """ส่งออกข้อมูลพนักงานทั้งหมดเป็น CSV (เปิดใน Excel ได้ทันที รองรับภาษาไทย)"""

    HEADERS = ['รหัสพนักงาน', 'ชื่อ-นามสกุล', 'เพศ', 'แผนก', 'เบอร์โทรศัพท์', 'อีเมล',
               'สถานะ', 'เงินเดือน', 'วันที่เริ่มงาน', 'ที่อยู่']

    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        filename = timezone.localdate().isoformat()
        response['Content-Disposition'] = f'attachment; filename=employees_{filename}.csv'
        response.write('\ufeff')  # BOM สำหรับ Excel
        writer = csv.writer(response)
        writer.writerow(self.HEADERS)
        for emp in Employee.objects.order_by('emp_code'):
            writer.writerow([
                self._safe_cell(emp.emp_code), self._safe_cell(emp.name),
                emp.get_gender_display(), self._safe_cell(emp.department),
                self._safe_cell(emp.phone), self._safe_cell(emp.email),
                emp.get_status_display(), emp.salary, emp.hire_date,
                self._safe_cell(emp.address),
            ])
        return response


class EmployeeListView(LiveSearchListView):
    """รายชื่อพนักงาน: ค้นหาเรียลไทม์ + ตัวกรองแผนก/เพศ/สถานะ + เรียงลำดับ"""
    model = Employee
    template_name = 'employee_list.html'
    partial_template_name = 'employee_rows.html'
    filter_params = ('department', 'gender', 'status')

    def filter_queryset(self, queryset):
        params = self.request.GET
        return (
            queryset
            .of_department(params.get('department', '').strip())
            .with_gender(params.get('gender', '').strip())
            .with_status(params.get('status', '').strip())
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['departments'] = Employee.objects.department_choices()
        return context


class EmployeeFormBaseView(StaffRequiredMixin):
    """Base ฟอร์มพนักงาน: คุมเรื่องรหัสอัตโนมัติ + ข้อความสำเร็จ (Polymorphic hooks)"""
    model = Employee
    form_class = EmployeeForm
    template_name = 'employee_form.html'
    success_message = ''

    def get_success_url(self):
        return reverse('employee_list')

    def form_valid(self, form):
        # snapshot ค่าเดิมจาก `form.initial` — ไม่ใช่ `form.instance`
        # เพราะ ModelForm จะเขียน cleaned_data ทับลง instance ตั้งแต่ตอน
        # `is_valid()` แล้ว (ถ้าอ่าน instance ตอนนี้จะได้ค่าใหม่ทั้งหมด
        # ทำให้ log ไม่บอกว่าอะไรเปลี่ยน) ส่วน `initial` เก็บค่าจาก DB ไว้ก่อน
        before = None
        if form.instance and form.instance.pk:
            before = {f: form.initial.get(f)
                      for f in ('salary', 'department', 'status', 'name')
                      if f in form.initial}

        emp = form.save(commit=False)
        if not emp.emp_code:
            emp.emp_code = self.resolve_missing_code(emp)
        emp.save()

        # บันทึกเฉพาะฟิลด์ที่เปลี่ยนจริง — ตอน "สร้างใหม่" ไม่มีค่าเดิมให้เทียบ
        # จึงไม่ต้องคำนวณ diff (ไม่งั้นทุกฟิลด์จะถูกรายงานว่า "เปลี่ยน")
        after = Audit.diff(emp, ['salary', 'department', 'status', 'name'], before) if before else None
        Audit.record(
            self.request.user, 'employee',
            summary=f'{"แก้ไข" if before else "เพิ่ม"}พนักงาน {emp.emp_code} — {emp.name}'
                    + (f' (เปลี่ยน: {", ".join(after)})' if after else ''),
            target=emp, before=before, after=after, request=self.request,
        )
        messages.success(self.request, self.success_message.format(name=emp.name))
        return HttpResponseRedirect(self.get_success_url())

    def resolve_missing_code(self, employee):
        """Hook polymorphism: คืนรหัสพนักงานเมื่อฟอร์มส่งช่องว่างมา — subclass กำหนดเอง.

        Args:
            employee: instance Employee ที่ form สร้างไว้ (ยังไม่ save)

        Returns:
            str รหัสพนักงานที่จะใช้กับพนักงานคนนี้
        """
        raise NotImplementedError


class EmployeeCreateView(EmployeeFormBaseView, CreateView):
    """สร้างพนักงานใหม่ — prefill รหัสอัตโนมัติ (next_code) + วันที่เริ่มงาน = วันนี้."""
    success_message = 'เพิ่มพนักงาน {name} เรียบร้อยแล้ว!'

    def get_initial(self):
        initial = super().get_initial()
        initial.update({
            'emp_code': Employee.objects.next_code(),
            'hire_date': timezone.localdate(),
        })
        return initial

    def resolve_missing_code(self, employee):
        return Employee.objects.next_code()


class EmployeeUpdateView(EmployeeFormBaseView, UpdateView):
    """แก้ไขพนักงาน — เก็บโค้ดเดิมก่อน form แตะ instance กันรหัส EMP### เผลอว่าง.
    (รหัสเป็น Unique — ตันให้คงเดิมเสมอ เพราะ hidden field อาจถูกส่งเป็นค่าว่างได้)
    """
    success_message = 'แก้ไขข้อมูล {name} เรียบร้อยแล้ว!'

    def get_object(self, queryset=None):
        employee = super().get_object(queryset)
        # เก็บรหัสเดิมก่อน form แตะ instance — ห้ามเว้นว่างตอนแก้ไข
        self.original_code = employee.emp_code
        return employee

    def resolve_missing_code(self, employee):
        return getattr(self, 'original_code', '') or Employee.objects.next_code()


class EmployeeDeleteView(StaffRequiredMixin, View):
    """ลบพนักงาน (POST เท่านั้น — ปุ่มในหน้าเว็บส่ง form) พร้อมลบไฟล์รูปเดิม — บังคับสิทธิ์ delete_employee"""

    def post(self, request, *args, **kwargs):
        if not request.user.has_perm('myapp.delete_employee'):
            messages.error(request, 'คุณไม่มีสิทธิ์ลบข้อมูลพนักงาน (เฉพาะระดับผู้จัดการหรือผู้ดูแลระบบ)')
            return redirect(reverse('employee_list'))
        employee = get_object_or_404(Employee, pk=kwargs['pk'])
        name = employee.name
        if employee.avatar:
            employee.avatar.delete(save=False)  # ลบไฟล์รูปออกจากดิสก์ด้วย
        # บันทึก "ก่อน" ลบ — เพราะหลังลบแล้ว target_label จะหายไป
        Audit.record(
            request.user, 'employee',
            summary=f'ลบพนักงาน {employee.emp_code} — {name}',
            target=employee, before={'department': employee.department,
                                     'status': employee.status},
            request=request,
        )
        employee.delete()
        messages.error(request, f'ลบข้อมูลพนักงาน {name} เรียบร้อยแล้ว!')
        return redirect(reverse('employee_list'))

    def get(self, request, *args, **kwargs):
        # พฤติกรรมเดิม: เข้าตรงด้วย GET ไม่ลบ — กลับหน้ารายการ
        return redirect(reverse('employee_list'))


# ==================== Product Management (Admin Zone) ====================

class ProductManageView(LiveSearchListView):
    """โซนผู้ดูแล: ตารางจัดการสินค้าทั้งหมด (เทียบเท่าหน้าพนักงาน)"""
    model = Product
    template_name = 'product_manage.html'
    partial_template_name = 'product_rows.html'
    filter_params = ('show', 'stock')

    def filter_queryset(self, queryset):
        params = self.request.GET
        return (
            queryset
            .visibility(params.get('show', '').strip())
            .stock_state(params.get('stock', '').strip())
        )


class ProductFormBaseView(StaffRequiredMixin, View):
    """Base ฟอร์มสินค้า manual (product_form.html เรนเดอร์ input เอง)
    Subclass กำหนด get_product() กับ success_message — โฟลว์ save/redirect อยู่ที่เดียว"""
    template_name = 'product_form.html'
    success_message = ''

    def get_product(self):
        """create → None (สร้าง instance ใหม่ตอน POST), edit → สินค้าที่จะแก้"""
        raise NotImplementedError

    def get_image_fallback(self, product):
        raise NotImplementedError

    def get(self, request, *args, **kwargs):
        product = self.get_product()
        context = {'product': product} if product else {}
        context['all_categories'] = Catalog.categories(only_listed=False)
        context['ai_enabled'] = GeminiAI.enabled()
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        product = self.get_product()
        if product is None:
            product = Product()

        # ตรวจค่าที่แปลงไม่ได้ก่อนแตะ DB — ไม่งั้น Decimal/IntError เด้ง 500
        name = request.POST.get('name', '').strip()
        price_raw = (request.POST.get('price', '') or '').strip()
        stock_raw = (request.POST.get('stock', '') or '').strip()
        if not name:
            messages.error(request, 'กรุณากรอกชื่อสินค้า')
            return self._render_error(request, product)
        try:
            price_val = Decimal(price_raw)
            stock_val = int(stock_raw)
        except (InvalidOperation, ValueError):
            messages.error(request, 'ราคา/จำนวนต้องเป็นตัวเลขที่ถูกต้อง')
            return self._render_error(request, product)
        if price_val < 0 or stock_val < 0:
            messages.error(request, 'ราคาและจำนวนต้องไม่ติดลบ')
            return self._render_error(request, product)

        # snapshot ก่อน apply_form_data (ซึ่งเขียนทับ field บน instance เดิม)
        was_existing = product.pk is not None
        before = ({f: getattr(product, f, None)
                   for f in ('price', 'stock', 'is_active', 'category', 'name')}
                  if was_existing else None)

        product.apply_form_data(request.POST, image_fallback=self.get_image_fallback(product))
        product.save()

        # ตอนสร้างใหม่ไม่มีค่าเดิมให้เทียบ → ไม่ต้องคำนวณ diff
        after = (Audit.diff(product, ['price', 'stock', 'is_active', 'category', 'name'],
                            before) if before else None)
        Audit.record(
            request.user, 'product',
            summary=f'{"แก้ไข" if was_existing else "เพิ่ม"}สินค้า "{product.name}"'
                    + (f' (เปลี่ยน: {", ".join(after)})' if after else ''),
            target=product, before=before, after=after, request=request,
        )
        messages.success(request, self.success_message)
        return redirect(reverse('product_manage'))

    def _render_error(self, request, product=None):
        context = {'all_categories': Catalog.categories(only_listed=False),
                   'ai_enabled': GeminiAI.enabled()}
        if product is not None and product.pk:
            context['product'] = product
        return render(request, self.template_name, context)


class ProductCreateView(ProductFormBaseView):
    """สร้างสินค้าใหม่ (ฟอร์ม manual) — รูป default ถ้าไม่ส่งมา."""
    success_message = 'เพิ่มสินค้าเรียบร้อยแล้ว!'

    def get_product(self):
        return None

    def get_image_fallback(self, product):
        return Product.DEFAULT_IMAGE


class ProductUpdateView(ProductFormBaseView):
    """แก้ไขสินค้า — กันหารูปเปล่าโดย fallback เป็นรูปเดิมของสินค้า."""
    success_message = 'แก้ไขสินค้าเรียบร้อยแล้ว!'

    def get_product(self):
        return get_object_or_404(Product, id=self.kwargs['product_id'])

    def get_image_fallback(self, product):
        return product.image


class ProductDeleteView(StaffRequiredMixin, View):
    """ลบสินค้า — GET redirect กลับ (ป้องกัน prefetch/crawler), POST เท่านั้นจึงลบจริง"""

    def get(self, request, *args, **kwargs):
        return redirect(reverse('product_manage'))

    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, id=kwargs['product_id'])
        Audit.record(
            request.user, 'product',
            summary=f'ลบสินค้า "{product.name}" (สต็อก {product.stock} ชิ้น)',
            target=product, before={'price': str(product.price), 'stock': product.stock,
                                   'is_active': product.is_active},
            request=request,
        )
        product.delete()
        messages.error(request, 'ลบสินค้าเรียบร้อยแล้ว!')
        return redirect(reverse('product_manage'))


# ==================== Admin: Order Management ====================

class OrderManageView(StaffRequiredMixin, ListView):
    """ตารางจัดการออเดอร์: search + filter status + live update สถานะ"""
    model = Order
    template_name = 'order_manage.html'
    partial_template_name = 'order_manage_rows.html'
    context_object_name = 'orders'
    paginate_by = 10

    STATUS_CHOICES = [('', 'ทั้งหมด')] + list(Order.STATUS_CHOICES)

    def get_queryset(self):
        from django.db.models import Count, Q
        qs = (Order.objects
              .select_related('user')
              .prefetch_related('items__product')
              .annotate(
                  open_issues_count=Count(
                      'issues',
                      filter=Q(issues__status__in=['open', 'in_progress']),
                      distinct=True
                  )
              )
              .order_by('-created_at'))
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(id__icontains=q) |
                Q(customer_name__icontains=q) |
                Q(phone__icontains=q)
            )
        status = self.request.GET.get('status', '').strip()
        if status and status in dict(Order.STATUS_CHOICES):
            qs = qs.filter(status=status)
        return qs

    def get_template_names(self):
        if is_ajax(self.request):
            return [self.partial_template_name]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        ctx['query'] = q
        ctx['status_choices'] = self.STATUS_CHOICES
        ctx['selected_status'] = status
        ctx['has_filter'] = bool(q or status)
        ctx['total'] = self.get_queryset().count()
        return ctx


class OrderDetailView(StaffRequiredMixin, TemplateView):
    """ดูรายละเอียดออเดอร์ + เปลี่ยนสถานะ + ประวัติการชำระ"""
    template_name = 'order_detail.html'
    drawer_template_name = 'order_drawer_content.html'

    def get_template_names(self):
        if is_ajax(self.request):
            return [self.drawer_template_name]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        oid = int(self.kwargs['order_id'])
        order = get_object_or_404(Order.objects.select_related('user').prefetch_related('items__product', 'issues'), id=oid)
        reported = order.reported_total
        issues = list(order.issues.order_by('-created_at'))
        unresolved_issues = [i for i in issues if i.status in ('open', 'in_progress')]
        ctx.update({
            'order': order,
            'items': order.items.select_related('product').all(),
            'payments': order.payments.order_by('-created_at'),
            'issues': issues,
            'unresolved_issues': unresolved_issues,
            'unresolved_issues_count': len(unresolved_issues),
            'reported': reported,
            'remaining': order.remaining,
            'allowed_statuses': self._status_options(order),
            # ปุ่มบังคับสถานะสำหรับ superuser เท่านั้น (can_override ตรวจ is_superuser
            # เองอีกชั้น) — staff ธรรมดาจะไม่เห็นเลย ไม่ใช่แค่กดไม่ได้
            'can_override_paid': OrderStatusService.can_override(order, self.request.user),
        })
        return ctx

    @staticmethod
    def _status_options(order):
        """ป้ายปุ่มสถานะที่เจ้าหน้าที่เลื่อนได้

        ขั้น 'ถึงมือแล้ว' เป็นขั้นที่ **ลูกค้าควรเป็นคนยืนยัน** (ดู
        `OrderConfirmReceivedView`) เจ้าหน้าที่ยังกดได้สำหรับกรณีที่
        ติดต่อลูกค้าไม่ได้ เช่น เก็บเงินปลายทาง — ป้ายจึงต้องบอกความต่างนี้
        ไม่ใช่แสดง "ถึงมือ" เฉย ๆ เหมือนเป็นทางปกติ
        """
        labels = dict(Order.STATUS_CHOICES)
        out = []
        for value in OrderStatusService.staff_options(order):
            if value == 'delivered':
                out.append((value, 'ถึงมือแล้ว (กรณีลูกค้าติดต่อไม่ได้)'))
            else:
                out.append((value, labels.get(value, value)))
        return out


class OrderStatusView(StaffRequiredMixin, View):
    """POST /orders/<id>/status/ — เปลี่ยนสถานะออเดอร์"""

    def post(self, request, *args, **kwargs):
        order = get_object_or_404(Order, id=int(kwargs['order_id']))
        new_status = request.POST.get('status', '').strip()
        ajax = is_ajax(request)
        if new_status not in dict(Order.STATUS_CHOICES):
            if ajax:
                return JsonResponse({'ok': False, 'msg': 'สถานะไม่ถูกต้อง'}, status=400)
            messages.error(request, 'สถานะไม่ถูกต้อง')
            return redirect(reverse('order_manage'))
        old_status = order.status

        # --- ทางพิเศษ: superuser บังคับขั้นอัตโนมัติ ('paid') ด้วยเหตุผล ---
        # จุดนี้อยู่ "เหนือ" OrderStatusService.move() ที่ปฏิเสธไว้เสมอ
        # เพื่อให้กติกาของระบบปกติยังอยู่ครบ ส่วนกรณีผิดปกติมีทางออก
        # ที่ถูกต้องและตรวจสอบย้อนหลังได้ แทนการแก้ข้อมูลตรง DB
        if new_status in OrderStatusService.AUTOMATIC:
            if not OrderStatusService.can_override(order, request.user):
                reason_txt = ('ต้องเป็น superuser เท่านั้น'
                              if not getattr(request.user, 'is_superuser', False)
                              else OrderStatusService.move(order, new_status)[1])
                if ajax:
                    return JsonResponse({'ok': False, 'msg': reason_txt}, status=403)
                messages.error(request, reason_txt)
                return redirect(reverse('order_detail', args=[order.id]))

            try:
                result = PaymentService.override_mark_paid(
                    order, request.user, request.POST.get('reason', ''))
            except PermissionError:
                result = {'ok': False, 'error': 'บังคับสถานะได้เฉพาะ superuser เท่านั้น'}
            if not result['ok']:
                if ajax:
                    return JsonResponse({'ok': False, 'msg': result['error']}, status=400)
                messages.error(request, result['error'])
            else:
                msg = f'บังคับออเดอร์ #{order.id} เป็น "ชำระแล้ว" แล้ว (superuser override)'
                if ajax:
                    return JsonResponse({
                        'ok': True, 'msg': msg,
                        'status': order.status,
                        'status_display': order.get_status_display(),
                    })
                messages.success(request, msg)
            return redirect(reverse('order_detail', args=[order.id]))

        ok, msg = OrderStatusService.move(order, new_status)
        if ok:
            # บันทึกการกระทำ: เปลี่ยนสถานะออเดอร์ = กระทำที่กระทบลูกค้าโดยตรง
            Audit.record(
                request.user, 'order_status',
                summary=f'ออเดอร์ #{order.id}: {old_status} → {order.status}',
                target=order,
                before={'status': old_status}, after={'status': order.status},
                request=request,
            )
            if ajax:
                return JsonResponse({
                    'ok': True,
                    'msg': msg,
                    'status': order.status,
                    'status_display': order.get_status_display()
                })
            messages.success(request, f'ออเดอร์ #{order.id}: {msg}')
        else:
            if ajax:
                return JsonResponse({'ok': False, 'msg': msg}, status=400)
            messages.error(request, f'ออเดอร์ #{order.id}: {msg}')
        return redirect(reverse('order_detail', args=[order.id]))


class OrderExportCsvView(CsvSafeMixin, StaffRequiredMixin, View):
    """ส่งออกข้อมูลคำสั่งซื้อทั้งหมดเป็น CSV (เปิดใน Excel ได้ทันที รองรับภาษาไทย)"""

    HEADERS = [
        'เลขออเดอร์', 'ชื่อผู้สั่งซื้อ', 'เบอร์โทร', 'ที่อยู่จัดส่ง',
        'วิธีชำระเงิน', 'ยอดรวม (บาท)', 'ยอดชำระแล้ว (บาท)', 'ยอดคงเหลือ (บาท)',
        'สถานะ', 'วันที่สั่งซื้อ',
    ]

    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        filename = timezone.localdate().isoformat()
        response['Content-Disposition'] = f'attachment; filename=orders_{filename}.csv'
        response.write('\ufeff')  # BOM สำหรับ Excel ภาษาไทย
        writer = csv.writer(response)
        writer.writerow(self.HEADERS)

        from django.db.models import Sum
        reported_map = dict(
            Order.objects.annotate(reported=Sum('payments__amount'))
            .values_list('id', 'reported')
        )
        orders = (Order.objects
                  .select_related('user')
                  .order_by('-created_at'))
        for o in orders:
            rep = reported_map.get(o.id) or Decimal('0')
            rem = max(o.total - rep, Decimal('0'))
            writer.writerow([
                o.id,
                self._safe_cell(o.customer_name),
                self._safe_cell(o.phone),
                self._safe_cell(o.address),
                o.get_payment_method_display(),
                float(o.total),
                float(rep),
                float(rem),
                o.get_status_display(),
                o.created_at.strftime('%d/%m/%Y %H:%M'),
            ])
        return response


class OrderIssueCreateView(View):
    """POST /order/<id>/issue/ (หรือ /issue/) — ลูกค้าแจ้งปัญหา

    กติกาความปลอดภัย
        - แนบออเดอร์ได้ → เช็คด้วย `_authed_order` (เลขออเดอร์ + เบอร์โทร)
          จึงแจ้งแทนออเดอร์คนอื่นไม่ได้ แม้เดาเลขออเดอร์ถูก
        - ล็อกอินแล้ว → ผูก `user` เพื่อให้เห็นในหน้าบัญชี
        - guest → เก็บเฉพาะชื่อ/เบอร์/อีเมล ไม่มีบัญชีผูก
    """

    #: เดินจากหน้าแจ้งปัญหา/ติดตาม → กลับที่มาหลังแจ้งเสร็จ (default ไปหน้า `/issue/`)
    def post(self, request, *args, **kwargs):
        back = request.POST.get('back') or reverse('issue_report')
        if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
            back = reverse('issue_report')

        order = None
        order_id = request.POST.get('order_id', '').strip()
        if order_id:
            order, err = _authed_order(request, order_id, request.POST.get('phone'))
            if err:
                messages.error(request, err)
                return redirect(back)

        subject = (request.POST.get('subject') or '').strip()
        detail = (request.POST.get('detail') or '').strip()
        if not subject or not detail:
            messages.error(request, 'กรอกหัวข้อและรายละเอียดปัญหาให้ครบ')
            return redirect(back)
        if len(detail) > 2000:
            detail = detail[:2000]

        name = (request.POST.get('name') or '').strip() or getattr(
            request.user, 'get_full_name', lambda: '')() or getattr(
            request.user, 'username', '') or 'ไม่ระบุ'
        phone = (request.POST.get('phone') or '').strip() or (
            order.phone if order else '')
        if not Validators.valid_phone(Validators.normalize_phone(phone or '')):
            messages.error(request, 'ต้องระบุเบอร์โทรที่ติดต่อได้ (เช่น 0812345678)')
            return redirect(back)

        issue = OrderIssue.objects.create(
            order=order,
            user=request.user if request.user.is_authenticated else None,
            name=name[:150],
            phone=(order.phone if order else phone)[:20],
            email=(request.POST.get('email') or '').strip()[:254],
            kind=request.POST.get('kind', 'other'),
            subject=subject[:200],
            detail=detail,
        )
        Audit.record(
            request.user, 'order',
            summary=(f'ลูกค้าแจ้งปัญหา: {issue.subject} (#{issue.pk})'
                     + (f' — ออเดอร์ #{order.id}' if order else '')),
            target=issue, request=request,
        )
        messages.success(
            request,
            f'รับเรื่องแล้วครับ (เลขที่ #{issue.pk}) เจ้าหน้าที่จะติดต่อกลับทางเบอร์โทร'
        )
        return redirect(back)


class OrderIssueListView(LiveSearchListView):
    """หลังบ้าน: คิวการแจ้งปัญหาทั้งหมด — ค้นหา/กรองตามสถานะ"""

    model = OrderIssue
    template_name = 'issue_list.html'
    partial_template_name = 'issue_rows.html'
    context_object_name = 'issues'
    paginate_by = 15
    filter_params = ('status',)

    def filter_queryset(self, queryset):
        status = self.request.GET.get('status', '').strip()
        return queryset.filter(status=status) if status else queryset

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = [('', 'ทั้งหมด')] + list(
            OrderIssue.STATUS_CHOICES)
        ctx['selected_status'] = self.request.GET.get('status', '').strip()
        ctx['open_count'] = OrderIssue.objects.open_ones().count()
        return ctx


class OrderIssueUpdateView(StaffRequiredMixin, View):
    """POST /orders/issues/<id>/ — เจ้าหน้าที่อัปเดตสถานะ + ผลการแก้ไข"""

    def post(self, request, *args, **kwargs):
        issue = get_object_or_404(OrderIssue, pk=kwargs['issue_id'])
        status = request.POST.get('status', '').strip()
        resolution = (request.POST.get('resolution') or '').strip()
        old = issue.status
        back = request.POST.get('back') or reverse('issue_list')

        if not issue.mark(status, request.user, resolution):
            reason = ('สถานะไม่ถูกต้อง' if status not in dict(OrderIssue.STATUS_CHOICES)
                      else 'ต้องเขียนผลการดำเนินการก่อนปิดเรื่อง')
            messages.error(request, reason)
            return redirect(back)

        Audit.record(
            request.user, 'order',
            summary=(f'แจ้งปัญหา #{issue.pk}: {dict(OrderIssue.STATUS_CHOICES)[old]}'
                     f' → {dict(OrderIssue.STATUS_CHOICES)[status]}'),
            target=issue, before={'status': old}, after={'status': status},
            request=request,
        )
        messages.success(request, f'อัปเดตการแจ้งปัญหา #{issue.pk} แล้ว')
        return redirect(back)


class OrderInvoiceView(View):
    """หน้าพิมพ์ใบเสร็จ/ใบกำกับภาษีอย่างย่อ (A4 Print-Ready):
    เข้าถึงได้โดย:
    1. เจ้าหน้าที่ (Staff)
    2. ลูกค้าที่เป็นเจ้าของออเดอร์ (request.user == order.user)
    3. ลูกค้าที่ระบุเบอร์โทรถูกต้องผ่าน GET param ?phone= (กรณี guest)
    """
    template_name = 'order_invoice.html'

    def get(self, request, order_id, *args, **kwargs):
        order = get_object_or_404(
            Order.objects.select_related('user').prefetch_related('items__product'),
            id=order_id
        )
        # ตรวจสิทธิ์การเข้าถึง
        is_staff = request.user.is_authenticated and request.user.is_staff
        is_owner = request.user.is_authenticated and order.user_id == request.user.id
        phone_param = request.GET.get('phone', '').strip().replace('-', '').replace(' ', '')
        clean_order_phone = (order.phone or '').replace('-', '').replace(' ', '')
        phone_match = bool(phone_param and clean_order_phone and phone_param == clean_order_phone)

        if not (is_staff or is_owner or phone_match):
            if not request.user.is_authenticated:
                return redirect(f"{reverse('account_login')}?next={request.path}")
            raise Http404("ไม่พบคำสั่งซื้อ หรือคุณไม่มีสิทธิ์เข้าถึงเอกสารนี้")

        reported = order.reported_total
        remaining = max(order.total - reported, Decimal('0'))
        is_paid = order.status in ('paid', 'shipped', 'delivered')

        context = {
            'order': order,
            'items': order.items.all(),
            'reported': reported,
            'remaining': remaining,
            'is_paid': is_paid,
            'is_staff': is_staff,
            'today': timezone.localdate(),
        }
        return render(request, self.template_name, context)


# ==================== Admin: Customer Management ====================

class CustomerListView(StaffRequiredMixin, ListView):
    """รายชื่อลูกค้าที่มีบัญชี — search name/email/phone"""
    template_name = 'customer_list.html'
    context_object_name = 'customers'
    paginate_by = 10

    def get_queryset(self):
        from django.contrib.auth.models import User
        qs = (User.objects.filter(customer_profile__isnull=False)
              .select_related('customer_profile')
              .prefetch_related('orders')
              .order_by('-date_joined'))
        q = self.request.GET.get('q', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(username__icontains=q) |
                Q(customer_profile__phone__icontains=q)
            )
        return qs

    def get_template_names(self):
        if is_ajax(self.request):
            return ['customer_list_rows.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['query'] = self.request.GET.get('q', '').strip()
        return ctx


class CustomerDetailView(StaffRequiredMixin, TemplateView):
    """ดูรายละเอียดลูกค้า: profile + ที่อยู่ + ประวัติออเดอร์"""
    template_name = 'customer_detail.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = get_object_or_404(
            __import__('django.contrib.auth.models', fromlist=['User']).User.objects.select_related('customer_profile').prefetch_related('addresses', 'orders__items__product'),
            id=int(self.kwargs['user_id'])
        )
        ctx['customer'] = user
        ctx['profile'] = getattr(user, 'customer_profile', None)
        ctx['addresses'] = user.addresses.all()
        ctx['orders'] = user.orders.prefetch_related('items__product').order_by('-created_at')
        return ctx


# ==================== Admin: Sales Reports ====================

class SalesReportView(StaffRequiredMixin, TemplateView):
    """รายงานขาย: revenue, top products, chart data"""
    template_name = 'reports.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        period = self.request.GET.get('period', 'month')
        from datetime import timedelta
        today = timezone.localdate()
        if period == 'today':
            start = today
            label = 'วันนี้'
        elif period == 'week':
            start = today - timedelta(days=today.weekday())
            label = 'สัปดาห์นี้'
        elif period == 'year':
            start = today.replace(month=1, day=1)
            label = 'ปีนี้'
        else:  # month
            start = today.replace(day=1)
            label = 'เดือนนี้'

        from django.db.models import Sum, Count, F
        orders = Order.objects.filter(created_at__date__gte=start, status__in=['paid', 'shipped', 'delivered'])
        agg = orders.aggregate(total_revenue=Sum('total'), total_orders=Count('id'))
        revenue = agg['total_revenue'] or Decimal('0')
        order_count = agg['total_orders'] or 0

        # Top 5 สินค้าขายดี
        top_products = (
            OrderItem.objects
            .filter(order__created_at__date__gte=start, order__status__in=['paid', 'shipped', 'delivered'])
            .values('product__name')
            .annotate(total_qty=Sum('quantity'), total_revenue=Sum(F('price') * F('quantity')))
            .order_by('-total_qty')[:5]
        )

        # Revenue chart — data depends on period
        import json
        chart_labels = []
        chart_data = []

        if period == 'today':
            # Hourly breakdown (today 00:00–23:00)
            for h in range(24):
                hour_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()) + timedelta(hours=h))
                hour_end = hour_start + timedelta(hours=1)
                day_total = orders.filter(created_at__gte=hour_start, created_at__lt=hour_end).aggregate(s=Sum('total'))['s'] or 0
                chart_labels.append(f'{h:02d}:00')
                chart_data.append(float(day_total))
        elif period == 'week':
            # Daily breakdown (7 days)
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                day_total = orders.filter(created_at__date=d).aggregate(s=Sum('total'))['s'] or 0
                thai_weekdays = ['จ.', 'อ.', 'พ.', 'พฤ.', 'ศ.', 'ส.', 'อา.']
                chart_labels.append(f'{thai_weekdays[d.weekday()]} {d.day}')
                chart_data.append(float(day_total))
        elif period == 'year':
            # Monthly breakdown (12 months)
            thai_months = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
            for m in range(1, 13):
                month_total = orders.filter(created_at__year=today.year, created_at__month=m).aggregate(s=Sum('total'))['s'] or 0
                chart_labels.append(thai_months[m - 1])
                chart_data.append(float(month_total))
        else:
            # month: daily breakdown (days in month)
            import calendar
            days_in_month = calendar.monthrange(today.year, today.month)[1]
            for d in range(1, days_in_month + 1):
                day_total = orders.filter(created_at__year=today.year, created_at__month=today.month, created_at__day=d).aggregate(s=Sum('total'))['s'] or 0
                chart_labels.append(str(d))
                chart_data.append(float(day_total))
        ctx.update({
            'period': period,
            'period_label': label,
            'revenue': revenue,
            'order_count': order_count,
            'avg_order': revenue / order_count if order_count else Decimal('0'),
            'top_products': top_products,
            'chart_labels': json.dumps(chart_labels),
            'chart_data': json.dumps(chart_data),
        })
        return ctx


# ==================== Admin: Payment History ====================

class PaymentListView(StaffRequiredMixin, ListView):
    """ประวัติการชำระเงินทั้งหมด — search + filter + export"""
    template_name = 'payment_list.html'
    context_object_name = 'payments'
    paginate_by = 15

    def get_queryset(self):
        qs = Payment.objects.select_related('order').order_by('-created_at')
        q = self.request.GET.get('q', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(name__icontains=q) |
                Q(phone__icontains=q) |
                Q(order__id__icontains=q) |
                Q(note__icontains=q)
            )
        return qs

    def get_template_names(self):
        if is_ajax(self.request):
            return ['payment_list_rows.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['query'] = self.request.GET.get('q', '').strip()
        from django.db.models import Sum
        ctx['total_amount'] = self.get_queryset().aggregate(s=Sum('amount'))['s'] or Decimal('0')
        return ctx


class PaymentExportCsvView(CsvSafeMixin, StaffRequiredMixin, View):
    """ส่งออกประวัติการชำระเงินเป็น CSV — ข้อความจากลูกค้า/OCR ผ่าน _safe_cell กัน formula injection"""

    HEADERS = ['เลขออเดอร์', 'ชื่อผู้แจ้ง', 'เบอร์โทร', 'จำนวนเงิน', 'วันที่โอน', 'หมายเหตุ', 'วันที่บันทึก']

    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        filename = timezone.localdate().isoformat()
        response['Content-Disposition'] = f'attachment; filename=payments_{filename}.csv'
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow(self.HEADERS)
        for p in Payment.objects.select_related('order').order_by('-created_at'):
            writer.writerow([
                p.order_id, self._safe_cell(p.name), self._safe_cell(p.phone), p.amount,
                p.transfer_date or '', self._safe_cell(p.note), p.created_at.strftime('%d/%m/%Y %H:%M'),
            ])
        return response


# ==================== Admin: Stock Adjust ====================

class ProductStockAdjustView(StaffRequiredMixin, View):
    """POST /product/<id>/stock-adjust/ — ปรับ stock ด่วน +/- จากหน้าตาราง"""

    def post(self, request, *args, **kwargs):
        product = get_object_or_404(Product, id=int(kwargs['product_id']))
        try:
            delta = int(request.POST.get('delta', 0))
        except (ValueError, TypeError):
            delta = 0
        old_stock = product.stock
        new_stock = max(0, product.stock + delta)
        product.stock = new_stock
        product.save(update_fields=['stock'])
        # ปรับสต็อก = กระทำที่กระทบของจริง + กระทบยอดขาย → ต้องมีประวัติ
        Audit.record(
            request.user, 'stock',
            summary=f'ปรับสต็อก "{product.name}" {old_stock} → {new_stock} '
                    f'({delta:+d})',
            target=product,
            before={'stock': old_stock}, after={'stock': new_stock},
            request=request,
        )
        if is_ajax(request):
            return JsonResponse({'ok': True, 'stock': product.stock, 'name': product.name})
        messages.success(request, f'ปรับ stock {product.name} เป็น {product.stock} ชิ้นแล้ว')
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or ''
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            next_url = reverse('product_manage')
        return redirect(next_url)


# ==================== RBAC: User & Role Management ====================

class StaffUserManageView(ManagerRequiredMixin, ListView):
    """หน้าจัดการผู้ใช้และสิทธิ์บทบาท — สำหรับผู้จัดการร้าน/แอดมิน (RBAC Management)"""
    template_name = 'staff_users.html'
    context_object_name = 'user_list'
    paginate_by = 15

    def get_queryset(self):
        from django.contrib.auth.models import User
        qs = User.objects.all().select_related('customer_profile').prefetch_related('groups').order_by('-date_joined')
        q = self.request.GET.get('q', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(username__icontains=q) |
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(email__icontains=q)
            )
        role_filter = self.request.GET.get('role', '').strip()
        if role_filter in ['Manager', 'Staff', 'Member']:
            qs = qs.filter(groups__name=role_filter)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['query'] = self.request.GET.get('q', '').strip()
        ctx['role_filter'] = self.request.GET.get('role', '').strip()
        ctx['role_form'] = UserRoleChangeForm()
        return ctx


class StaffUserRoleUpdateView(ManagerRequiredMixin, View):
    """เปลี่ยนบทบาทผู้ใช้ (Manager / Staff / Member) แบบ 1 คลิก"""

    def post(self, request, user_id, *args, **kwargs):
        from django.contrib.auth.models import Group, User

        target_user = get_object_or_404(User, pk=user_id)
        if target_user == request.user and not request.user.is_superuser:
            messages.warning(request, 'คุณไม่สามารถเปลี่ยนบทบาทของตนเองได้')
            return redirect(reverse('staff_users'))
        if target_user.is_superuser and not request.user.is_superuser:
            messages.error(request, 'ไม่สามารถเปลี่ยนบทบาทของผู้ดูแลระบบ (superuser) ได้ — สงวนสิทธิ์เฉพาะ superuser ด้วยกัน')
            return redirect(reverse('staff_users'))

        new_role = request.POST.get('role', '').strip()
        if new_role not in ['Manager', 'Staff', 'Member']:
            messages.error(request, 'บทบาทที่ระบุไม่ถูกต้อง')
            return redirect(reverse('staff_users'))

        # ล้างกลุ่มเดิมใน 3 บทบาทหลัก
        old_groups = list(target_user.groups.values_list('name', flat=True))
        old_role = next((r for r in ('Manager', 'Staff', 'Member') if r in old_groups), '')
        for gname in ['Manager', 'Staff', 'Member']:
            g = Group.objects.filter(name=gname).first()
            if g:
                target_user.groups.remove(g)

        # กำหนดกลุ่มใหม่ + สิทธิ์ is_staff
        target_group, _ = Group.objects.get_or_create(name=new_role)
        target_user.groups.add(target_group)
        if new_role in ['Manager', 'Staff']:
            target_user.is_staff = True
        else:
            target_user.is_staff = False
        target_user.save()

        # เปลี่ยนสิทธิ์บัญชี = กระทำที่ต้องตรวจสอบย้อนหลังได้เสมอ
        # (เป็นเส้นทางสู่การเข้าถึงข้อมูลทั้งระบบ)
        Audit.record(
            request.user, 'role',
            summary=f'เปลี่ยนบทบาท {target_user.username}: '
                    f'{"Manager" if old_role == "Manager" else ("Staff" if old_role == "Staff" else "Member")}'
                    f' → {new_role}'
                    + (' (เปิดสิทธิ์ staff)' if target_user.is_staff else ''),
            target=target_user, request=request,
        )
        messages.success(request, f'เปลี่ยนบทบาทของ {target_user.username} เป็น "{new_role}" เรียบร้อยแล้ว')
        return redirect(reverse('staff_users'))


def permission_denied_view(request, exception=None):
    """หน้า 403 Forbidden แบบ Apple Liquid Glass สวยงาม อธิบายภาษาไทยชัดเจน"""
    return render(request, '403.html', {
        'exception': exception,
        'user': request.user,
    }, status=403)


def page_not_found_view(request, exception=None):
    """หน้า 404 Not Found — ชี้ทางออกให้ผู้ใช้ (หน้าหลัก / สินค้า / ติดตามออเดอร์)

    ทำไมต้องมี: เดิม Django แสดงหน้า 404 ดิบของตัวเอง (ข้อความอังกฤษยาว ๆ
    ไม่มีปุ่ม ไม่มีเมนู) ซึ่งเป็นความรู้สึกเหมือนเว็บพัง ไม่ใช่ "หาไม่เจอ"

    Args:
        request: HttpRequest
        exception: Http404 ที่ Django ส่งมา (เก็บไว้ debug/วิเคราะห์)

    Returns:
        HttpResponse: status 404 พร้อมเทมเพลต 404.html
    """
    return render(request, '404.html', {
        'exception': exception,
        'request_path': request.path[:200],
    }, status=404)


def server_error_view(request):
    """หน้า 500 — ต้อง render ได้แม้ session/DB/static พัง

    ⚠️ กฎสำคัญของ handler 500 (เคยพลาดในโปรเจกต์นี้แล้ว — เจอตอนทดสอบ):
        ห้ามเรียก `render(request, ...)` แบบปกติ เพราะมันจะเดินผ่าน **context
        processor ทั้งหมด** และ `cart_context` ของโปรเจกต์แตะ `request.session`
        → ถ้าสาเหตุที่ทำให้เกิด 500 คือ session/DB พัง หน้า 500 จะพังตาม
          และ Django จะวน error ซ้ำเป็นลูกโซ่ (ผู้ใช้เห็นหน้าว่าง)
        วิธีที่ถูกคือ `render_to_string()` **โดยไม่ส่ง request** → ไม่มี
        context processor ไหร่ถูกเรียก เหลือแค่อ่านไฟล์เทมเพลต

        เหตุผลที่ยัง log ได้: `logging.getLogger('django.request').exception()`
        ไม่ต้องพึ่ง session/DB เลย

    Args:
        request: HttpRequest

    Returns:
        HttpResponse: status 500 + HTML ของ 500.html (ไม่ผ่าน context processor)
    """
    import logging

    from django.template.loader import render_to_string

    # logger.exception จะดึง traceback ของ exception ที่กำลังจัดการอยู่ให้เอง
    logging.getLogger('django.request').exception(
        'เกิดข้อผิดพลาด 500 ที่ %s %s', request.method, request.path)

    # ไม่ส่ง request → ไม่มี context processor (สำคัญมาก ดูคอมเมนต์ข้างบน)
    return HttpResponse(render_to_string('500.html'), status=500)

