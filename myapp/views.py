"""Views แบบ Class-Based ทั้งหมด — ใช้หลัก OOP:
- Inheritance   : LiveSearchListView เป็น base ให้ตารางค้นหาเรียลไทม์ทุกหน้า
- Polymorphism  : subclass override filter_queryset / get_product / ข้อความ โดย base คุมโฟลว์
- Encapsulation : ตรรกะโดเมนอยู่ที่ models (QuerySet/Manager) และ services (Cart)
- Abstraction   : StaffRequiredMixin ซ่อนรายละเอียดการตรวจสิทธิ์จากทุก view
"""
import csv
import os
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import AccessMixin
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
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

from .forms import EmployeeForm, StaffLoginForm
from .models import CustomerAddress, CustomerProfile, Employee, Order, OrderItem, Payment, Product
from .services import Cart, GeminiAI, OrderStatusService, PaymentService, PromptPay, SlipOK, ThaiCalendar, Validators


# ==================== Permissions: Mixin แทน decorator ====================

class StaffRequiredMixin(AccessMixin):
    """ผสมกับ View คลาสไหนก็ได้เพื่อบังคับสิทธิ์ผู้ดูแล (แทน @staff_required เดิม)"""

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_login_url(self):
        return reverse('staff_login')


# ==================== Auth ====================

class CustomerRegisterView(View):
    """สมัครบัญชีลูกค้า — ใช้ Django User (username = อีเมล)"""
    template_name = 'account_register.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(reverse('account'))
        return render(request, self.template_name, {'next': request.GET.get('next', '')})

    def post(self, request, *args, **kwargs):
        from django.contrib.auth.models import User
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone = Validators.normalize_phone(request.POST.get('phone', ''))
        address = request.POST.get('address', '').strip()
        pw1 = request.POST.get('password1', '')
        pw2 = request.POST.get('password2', '')
        back = lambda err: render(request, self.template_name, {   # noqa: E731
            'error': err, 'next': request.POST.get('next', ''),
            'v_name': name, 'v_email': email, 'v_phone': phone, 'v_address': address,
        })

        if not name or not email or not phone or not address:
            return back('กรุณากรอกข้อมูลให้ครบทุกช่อง')
        if not Validators.valid_phone(phone):
            return back('เบอร์โทรศัพท์ไม่ถูกต้อง (0XXXXXXXXX)')
        if '@' not in email or len(email) < 6:
            return back('อีเมลไม่ถูกต้อง')
        if len(pw1) < 6:
            return back('รหัสผ่านต้องยาวอย่างน้อย 6 ตัวอักษร')
        if pw1 != pw2:
            return back('รหัสผ่านสองช่องไม่ตรงกัน')
        if User.objects.filter(username__iexact=email).exists():
            return back('อีเมลนี้ถูกใช้สมัครแล้ว')

        user = User.objects.create_user(username=email, email=email, password=pw1,
                                        first_name=name.split(' ')[0][:30],
                                        last_name=' '.join(name.split(' ')[1:])[:150])
        CustomerProfile.objects.create(user=user, phone=phone, address=address)
        login(request, user)
        messages.success(request, f'สมัครบัญชีสำเร็จ ยินดีต้อนรับ {name}!')
        nxt = request.POST.get('next', '')
        if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
            return redirect(nxt)
        return redirect(reverse('product'))


class CustomerLoginView(View):
    """เข้าสู่ระบบลูกค้า (staff ก็ log in ได้ — dashboard เข้าผ่าน /staff/login/ ตามเดิม)"""
    template_name = 'account_login.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(reverse('account'))
        return render(request, self.template_name, {'next': request.GET.get('next', '')})

    def post(self, request, *args, **kwargs):
        username = request.POST.get('username', '').strip().lower()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if not user:
            return render(request, self.template_name,
                          {'error': 'อีเมลหรือรหัสผ่านไม่ถูกต้อง',
                           'next': request.POST.get('next', ''),
                           'v_username': username})
        login(request, user)
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


class AccountView(CustomerRequiredMixin, TemplateView):
    """โปรไฟล์ + ออเดอร์ของฉัน (ไม่ต้องจำ order id / เบอร์)"""
    template_name = 'account.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        profile = getattr(self.request.user, 'customer_profile', None)
        orders = (self.request.user.orders
                  .prefetch_related('items__product')
                  .order_by('-created_at'))
        ctx.update({
            'profile': profile,
            'display_name': (self.request.user.get_full_name()
                             or self.request.user.username),
            'orders': orders,
            'addresses': self.request.user.addresses.all(),
        })
        return ctx


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
        form = StaffLoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, 'เข้าสู่ระบบผู้ดูแลเรียบร้อยแล้ว')
            return redirect(next_url or reverse('employee_list'))
        return render(request, self.template_name, {'form': form, 'next': next_url})


class StaffLogoutView(View):
    """ออกจากระบบผู้ดูแล — POST เท่านั้น (GET = 405)."""

    def post(self, request, *args, **kwargs):
        logout(request)
        messages.success(request, 'ออกจากระบบผู้ดูแลเรียบร้อยแล้ว')
        return redirect(reverse('index'))


# ==================== หน้าร้าน (Public) ====================

class IndexView(TemplateView):
    """หน้าแรกของร้าน — โชว์สินค้าแนะนำ 3 ชิ้น (hero/badge/entrance ฝั่ง client)."""
    template_name = 'index.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['featured'] = Product.objects.listed()[:3]
        return ctx


class ProductPublicListView(ListView):
    """หน้าร้าน: ค้นหา + กรองหมวดหมู่ + เรียงลำดับ (GET — แชร์ลิงก์/กดถอยหลังได้)"""
    template_name = 'product.html'
    partial_template_name = 'product_grid.html'
    context_object_name = 'all_products'
    paginate_by = 9

    def get_template_names(self):
        """AJAX live search → คืนเฉพาะ partial grid (ไม่รีทั้งหน้า)"""
        if self.request.GET.get('partial') == '1':
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
            'categories': Product.objects.listed().category_choices(),
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
        ctx = {'items': cart.lines(), 'total': cart.total, 'cart_count': cart.count}
        if request.GET.get('partial') == '1':
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
            if _is_ajax(request):
                return JsonResponse({'ok': False, 'error': f"จำนวนเกินสต็อก (เหลือ {product.stock} ชิ้น)"}, status=409)
            messages.error(request, f"จำนวนเกินสต็อก (เหลือ {product.stock} ชิ้น)")
            return redirect(reverse('product_detail', args=[product.id]))
        if _is_ajax(request):
            return JsonResponse({'ok': True, 'count': cart.count, 'message': f"เพิ่ม {product.name} ลงตะกร้าแล้ว!"})
        messages.success(request, f"เพิ่ม {product.name} ลงตะกร้าแล้ว!")
        return redirect(reverse('cart'))


class CartRemoveView(CartMixin, View):
    """ลบสินค้าออกจากตะกร้า — POST เท่านั้น (GET = 405)."""

    def post(self, request, *args, **kwargs):
        self.get_cart().remove(kwargs['product_id'])
        cart = self.get_cart()
        if _is_ajax(request):
            return JsonResponse({'ok': True, 'count': cart.count})
        messages.success(request, 'ลบสินค้าออกจากตะกร้าแล้ว!')
        return redirect(reverse('cart'))


class CartUpdateView(CartMixin, View):
    """แก้จำนวนสินค้าในตะกร้า — POST เท่านั้น (GET = 405)."""

    def post(self, request, *args, **kwargs):
        self.get_cart().update(kwargs['product_id'], request.POST.get('quantity', 1))
        if _is_ajax(request):
            return JsonResponse({'ok': True, 'count': self.get_cart().count})
        return redirect(reverse('cart'))


def _is_ajax(request):
    """fetch จาก JS (ไม่ใช่ form submit ปกติ) — ใช้ header X-Requested-With"""
    return request.headers.get('X-Requested-With') == 'fetch'


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
        ctx['pp_payload'] = PromptPay.qr_payload(order.total) or ''
        try:
            ctx['qr'] = PromptPay.qr_data_uri(order.total)
        except Exception:
            ctx['qr'] = None
        return ctx


class ProductDescribeAIView(StaffRequiredMixin, View):
    """POST /product/describe-ai/ — Gemini ช่วยเขียนคำอธิบายสินค้า (staff only)"""

    def post(self, request, *args, **kwargs):
        name = request.POST.get('name', '').strip()
        if not name:
            return JsonResponse({'error': 'กรอกชื่อสินค้าก่อน แล้วกดปุ่ม AI'}, status=400)
        if not GeminiAI.enabled():
            return JsonResponse({'error': 'ยังไม่ได้ตั้งค่า GEMINI_API_KEY บนเซิร์ฟเวอร์'}, status=503)
        try:
            text = GeminiAI.describe_product(name, request.POST.get('category', '').strip())
        except Exception as exc:
            detail = f' — {exc}' if settings.DEBUG else ''
            return JsonResponse({'error': f'AI ขัดข้องหรือตอบไม่สำเร็จ{detail}'}, status=502)
        return JsonResponse({'description': text})


class OrderTrackingView(View):
    template_name = 'order_tracking.html'

    def get(self, request, *args, **kwargs):
        """ผู้ใช้ที่ล็อกอิน: แสดงออเดอร์ของตัวเองให้เลือกดูได้ทันที (ไม่ต้องพิมพ์ id/เบอร์)
        มี ?order=&phone= → ค้นให้เลย | ไม่ล็อกอิน → ฟอร์มค้นหาสำหรับ guest"""
        if request.user.is_authenticated:
            base = {
                'my_orders': request.user.orders.order_by('-created_at')[:12],
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
                'my_orders': request.user.orders.order_by('-created_at')[:12],
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
            reported = order.reported_total()
            ctx['payments'] = order.payments.order_by('-created_at')
            ctx['reported'] = reported
            ctx['remaining'] = order.remaining
            ctx['slip_enabled'] = SlipOK.enabled()
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
        )
        if result['just_paid']:
            messages.success(request, f'ออเดอร์ #{order.id} รับยอดโอนครบแล้ว — ชำระเงินเรียบร้อย!')
        else:
            messages.success(request, f'บันทึกการแจ้งชำระออเดอร์ #{order.id} เรียบร้อย!')
        return redirect(back)


class SlipVerifyView(View):
    """POST /payment/slip/ — อัปโหลดสลิป → SlipOK OCR → สร้าง Payment อัตโนมัติ
    คืน JSON สำหรับ fetch (X-Requested-With)"""

    MAX_MB = 5
    ALLOWED_EXT = {'.jpg', '.jpeg', '.png', '.webp'}

    def post(self, request, *args, **kwargs):
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
            }.get(str(e), 'อ่านสลิปไม่สำเร็จ — ลองถ่ายใหม่ให้ชัด หรือกรอกแบบฟอร์มด้านล่าง')
            detail = str(e) if settings.DEBUG else ''
            return JsonResponse({'ok': False, 'error': msg + (f' ({detail})' if detail else '')}, status=502)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'เชื่อมต่อระบบตรวจสลิปไม่ได้ ลองอีกครั้ง'}, status=502)

        if parsed['amount'] <= 0:
            return JsonResponse({'ok': False, 'error': 'อ่านยอดเงินจากสลิปไม่ได้'}, status=422)
        result = PaymentService.record_payment(
            order=order, name=order.customer_name, phone=order.phone,
            amount=parsed['amount'],
            transfer_date=parsed['transfer_date'] or timezone.localtime().date(),
            note=parsed['note'], source='slip',
        )
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
    """หน้าติดต่อ (เนื้อหาสถิต)."""
    template_name = 'contact.html'


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
        if self.partial_template_name and self.request.headers.get('X-Requested-With') == 'fetch':
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
            'revenue': order_stats['revenue'],
            'departments': departments,
            'dept_max': max([d['n'] for d in departments], default=1) or 1,
            'greeting': ThaiCalendar.greeting(),
            'thai_date': ThaiCalendar.full_date(),
            'pending_reports': self._pending_reports(),
        })
        return context

    @staticmethod
    def _pending_reports():
        """คิวตรวจการแจ้งชำระ: รายการล่าสุดของออเดอร์ที่ยัง pending"""
        rows = []
        payments = (Payment.objects
                    .filter(order__status='pending')
                    .select_related('order')
                    .order_by('-created_at')[:10])
        for p in payments:
            rows.append({
                'payment': p,
                'reported': p.order.reported_total(),
                'remaining': p.order.remaining,
            })
        return rows


class PaymentVerifyView(StaffRequiredMixin, View):
    """POST /dashboard/payment/<id>/verify/ — ยืนยันรายการแจ้งชำระ → ออเดอร์เป็น paid"""

    def post(self, request, *args, **kwargs):
        payment = get_object_or_404(Payment.objects.select_related('order'), id=kwargs['payment_id'])
        order = payment.order
        if order.status == 'pending':
            reported = order.reported_total()
            if reported < order.total:
                messages.error(request,
                               f'ยังยืนยันไม่ได้ — ออเดอร์ #{order.id} แจ้งมา {reported} บาท '
                               f'จากยอดรวม {order.total} บาท (ขาดอีก {order.total - reported} บาท)')
            else:
                OrderStatusService.auto_move(order, 'paid', actor='staff:payment_verify')
                messages.success(request, f'ยืนยันการชำระออเดอร์ #{order.id} ({payment.amount} บาท) แล้ว')
        else:
            messages.info(request, f'ออเดอร์ #{order.id} ถูกดำเนินการไปแล้ว ({order.get_status_display()})')
        return redirect(reverse('dashboard') + '#reports')


class EmployeeExportCsvView(StaffRequiredMixin, View):
    """ส่งออกข้อมูลพนักงานทั้งหมดเป็น CSV (เปิดใน Excel ได้ทันที รองรับภาษาไทย)"""

    HEADERS = ['รหัสพนักงาน', 'ชื่อ-นามสกุล', 'เพศ', 'แผนก', 'เบอร์โทรศัพท์', 'อีเมล',
               'สถานะ', 'เงินเดือน', 'วันที่เริ่มงาน', 'ที่อยู่']
    _FORMULA_CHARS = ('=', '+', '-', '@', '\t')

    @classmethod
    def _safe_cell(cls, value):
        """กัน CSV formula injection: cell ที่ขึ้นต้น =+-@/tab → คำนำ ' (Excel ไม่ประมวลผล)"""
        text = '' if value is None else str(value)
        if text.startswith(cls._FORMULA_CHARS):
            return "'" + text
        return text

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
        emp = form.save(commit=False)
        if not emp.emp_code:
            emp.emp_code = self.resolve_missing_code(emp)
        emp.save()
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
    """ลบพนักงาน (POST เท่านั้น — ปุ่มในหน้าเว็บส่ง form) พร้อมลบไฟล์รูปเดิม"""

    def post(self, request, *args, **kwargs):
        employee = get_object_or_404(Employee, pk=kwargs['pk'])
        name = employee.name
        if employee.avatar:
            employee.avatar.delete(save=False)  # ลบไฟล์รูปออกจากดิสก์ด้วย
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
        context['all_categories'] = Product.objects.category_choices()
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

        product.apply_form_data(request.POST, image_fallback=self.get_image_fallback(product))
        product.save()
        messages.success(request, self.success_message)
        return redirect(reverse('product_manage'))

    def _render_error(self, request, product=None):
        context = {'all_categories': Product.objects.category_choices(),
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
        qs = Order.objects.select_related('user').prefetch_related('items__product').order_by('-created_at')
        q = self.request.GET.get('q', '').strip()
        if q:
            from django.db.models import Q
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
        if self.request.headers.get('X-Requested-With') == 'fetch':
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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        oid = int(self.kwargs['order_id'])
        order = get_object_or_404(Order.objects.select_related('user').prefetch_related('items__product'), id=oid)
        reported = order.reported_total()
        ctx.update({
            'order': order,
            'items': order.items.select_related('product').all(),
            'payments': order.payments.order_by('-created_at'),
            'reported': reported,
            'remaining': order.remaining,
            'allowed_statuses': [(v, dict(Order.STATUS_CHOICES)[v]) for v in OrderStatusService.staff_options(order)],
        })
        return ctx


class OrderStatusView(StaffRequiredMixin, View):
    """POST /orders/<id>/status/ — เปลี่ยนสถานะออเดอร์"""

    def post(self, request, *args, **kwargs):
        order = get_object_or_404(Order, id=int(kwargs['order_id']))
        new_status = request.POST.get('status', '').strip()
        if new_status not in dict(Order.STATUS_CHOICES):
            messages.error(request, 'สถานะไม่ถูกต้อง')
            return redirect(reverse('order_manage'))
        ok, msg = OrderStatusService.move(order, new_status)
        if ok:
            messages.success(request, f'ออเดอร์ #{order.id}: {msg}')
        else:
            messages.error(request, f'ออเดอร์ #{order.id}: {msg}')
        return redirect(reverse('order_detail', args=[order.id]))


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
        if self.request.headers.get('X-Requested-With') == 'fetch':
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
        if self.request.headers.get('X-Requested-With') == 'fetch':
            return ['payment_list_rows.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['query'] = self.request.GET.get('q', '').strip()
        from django.db.models import Sum
        ctx['total_amount'] = self.get_queryset().aggregate(s=Sum('amount'))['s'] or Decimal('0')
        return ctx


class PaymentExportCsvView(StaffRequiredMixin, View):
    """ส่งออกประวัติการชำระเงินเป็น CSV"""

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
                p.order_id, p.name, p.phone, p.amount,
                p.transfer_date or '', p.note, p.created_at.strftime('%d/%m/%Y %H:%M'),
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
        new_stock = max(0, product.stock + delta)
        product.stock = new_stock
        product.save(update_fields=['stock'])
        if request.headers.get('X-Requested-With') == 'fetch':
            return JsonResponse({'ok': True, 'stock': product.stock, 'name': product.name})
        messages.success(request, f'ปรับ stock {product.name} เป็น {product.stock} ชิ้นแล้ว')
        return redirect(reverse('product_manage'))
