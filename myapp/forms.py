from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import Employee


class EmployeeForm(forms.ModelForm):
    """ฟอร์มสร้าง/แก้ไขพนักงาน — widget/placeholder ไทยครบ, รหัสพนักงานเติมให้อัตโนมัติได้.

    ฟิลด์ emp_code/phone/email ถูกปลด required เพราะ view เป็นคนบริหาร
    (รหัส EMP### รันให้เอง + อัปเดตทีหลังได้) — data-live ไว้ให้ JS อัปเดตคำนำหน้าระบบ
    """

    class Meta:
        model = Employee
        fields = ['emp_code', 'name', 'gender', 'department', 'phone', 'email', 'status', 'salary', 'hire_date', 'address', 'avatar']
        widgets = {
            'emp_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'เว้นว่างเพื่อรันเลขอัตโนมัติ เช่น EMP014',
                'data-live': 'code',
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'กรุณากรอกชื่อ-นามสกุล',
                'data-live': 'name',
            }),
            'gender': forms.Select(attrs={'class': 'form-select', 'data-live': 'gender'}),
            'department': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'เช่น ไอที, บุคคล, การตลาด',
                'list': 'departmentList',
                'data-live': 'department',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'เช่น 062-287-4291',
                'inputmode': 'tel',
                'data-live': 'phone',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'เช่น name@example.com',
                'data-live': 'email',
            }),
            'status': forms.Select(attrs={'class': 'form-select', 'data-live': 'status'}),
            'salary': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'เช่น 25000.00',
                'data-live': 'salary',
                'inputmode': 'decimal',
            }),
            'hire_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'data-live': 'hire_date',
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'บ้านเลขที่ ถนน ตำบล อำเภอ จังหวัด รหัสไปรษณีย์',
            }),
            'avatar': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        """ปลด required ของ emp_code/phone/email — view จะจัดการเติม/ยืนยันให้เอง.

        Args:
            *args, **kwargs: ส่งต่อให้ ModelForm ปกติ (instance/data/...)
        """
        super().__init__(*args, **kwargs)
        # รหัสพนักงาน: เว้นว่างได้ → view จะรันเลขให้เอง (แก้ไข: ต้องกรอกตามเดิม)
        self.fields['emp_code'].required = False
        self.fields['phone'].required = False
        self.fields['email'].required = False


class StaffLoginForm(AuthenticationForm):
    """อนุญาตให้เฉพาะผู้ใช้ที่เป็น staff เข้าจัดการข้อมูลผ่านหน้าเว็บ"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'ชื่อผู้ใช้แอดมิน',
            'autocomplete': 'username',
        })
        self.fields['password'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'รหัสผ่าน',
            'autocomplete': 'current-password',
        })

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise forms.ValidationError(
                'บัญชีนี้ไม่มีสิทธิ์จัดการข้อมูลผ่านหน้าเว็บ',
                code='not_staff',
            )


class ProfileEditForm(forms.Form):
    """ฟอร์มแก้ไขข้อมูลโปรไฟล์ผู้ใช้ — ชื่อ-นามสกุล, อีเมล, เบอร์โทร, ที่อยู่จัดส่งหลัก"""

    first_name = forms.CharField(
        max_length=30,
        label='ชื่อ',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ชื่อ'}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        label='นามสกุล',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'นามสกุล'}),
    )
    email = forms.EmailField(
        label='อีเมล',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com'}),
    )
    phone = forms.CharField(
        max_length=20,
        label='เบอร์โทรศัพท์',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น 0812345678', 'inputmode': 'tel'}),
    )
    address = forms.CharField(
        required=False,
        label='ที่อยู่จัดส่งหลัก',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'บ้านเลขที่ ถนน ตำบล อำเภอ จังหวัด'}),
    )
    avatar = forms.ImageField(
        required=False,
        label='รูปโปรไฟล์ (รองรับ GIF/PNG/JPG)',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/png, image/jpeg, image/gif, image/webp',
            'id': 'id_avatar',
        }),
    )
    cover = forms.ImageField(
        required=False,
        label='ภาพพื้นหลังหน้าปก (รองรับ GIF/PNG/JPG)',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/png, image/jpeg, image/gif, image/webp',
            'id': 'id_cover',
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_email(self):
        from django.contrib.auth.models import User
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email or '@' not in email:
            raise forms.ValidationError('กรุณากรอกอีเมลให้ถูกต้อง')
        qs = User.objects.filter(username__iexact=email)
        if self.user:
            qs = qs.exclude(pk=self.user.pk)
        if qs.exists():
            raise forms.ValidationError('อีเมลนี้ถูกใช้งานโดยบัญชีอื่นแล้ว')
        return email

    def clean_phone(self):
        from .services import Validators
        phone_raw = self.cleaned_data.get('phone', '')
        phone = Validators.normalize_phone(phone_raw)
        if not Validators.valid_phone(phone):
            raise forms.ValidationError('เบอร์โทรศัพท์ไม่ถูกต้อง (รูปแบบ 0XXXXXXXXX 9-10 หลัก)')
        return phone

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and hasattr(avatar, 'size') and avatar.size > 5 * 1024 * 1024:
            raise forms.ValidationError('ขนาดไฟล์รูปโปรไฟล์ต้องไม่เกิน 5 MB')
        return avatar

    def clean_cover(self):
        cover = self.cleaned_data.get('cover')
        if cover and hasattr(cover, 'size') and cover.size > 8 * 1024 * 1024:
            raise forms.ValidationError('ขนาดไฟล์ภาพพื้นหลังต้องไม่เกิน 8 MB')
        return cover


class CustomerRegistrationForm(forms.Form):
    """ฟอร์มสมัครสมาชิกลูกค้า — ตรวจสอบข้อมูลครบถ้วน รหัสผ่าน เบอร์โทร และอีเมลไม่ซ้ำ"""
    name = forms.CharField(
        max_length=60,
        label='ชื่อ-นามสกุล',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ชื่อ นามสกุล'}),
    )
    email = forms.EmailField(
        label='อีเมล (ใช้เข้าสู่ระบบ)',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}),
    )
    phone = forms.CharField(
        max_length=20,
        label='เบอร์โทรศัพท์',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น 0812345678', 'inputmode': 'tel'}),
    )
    address = forms.CharField(
        label='ที่อยู่จัดส่ง',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'บ้านเลขที่ ถนน ตำบล อำเภอ จังหวัด'}),
    )
    password1 = forms.CharField(
        label='รหัสผ่าน',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'อย่างน้อย 6 ตัวอักษร', 'id': 'id_password1'}),
    )
    password2 = forms.CharField(
        label='ยืนยันรหัสผ่าน',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'กรอกรหัสผ่านอีกครั้ง', 'id': 'id_password2'}),
    )
    agree_terms = forms.BooleanField(
        required=False,
        label='ฉันยอมรับข้อกำหนดการใช้งานและนโยบายความเป็นส่วนตัว',
        initial=True,
    )

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError('กรุณากรอกชื่อ-นามสกุล')
        return name

    def clean_email(self):
        from django.contrib.auth.models import User
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email or '@' not in email or len(email) < 6:
            raise forms.ValidationError('อีเมลไม่ถูกต้อง')
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError('อีเมลนี้ถูกใช้สมัครแล้ว')
        return email

    def clean_phone(self):
        from .services import Validators
        phone_raw = self.cleaned_data.get('phone', '')
        phone = Validators.normalize_phone(phone_raw)
        if not Validators.valid_phone(phone):
            raise forms.ValidationError('เบอร์โทรศัพท์ไม่ถูกต้อง (0XXXXXXXXX)')
        return phone

    def clean_password1(self):
        p1 = self.cleaned_data.get('password1', '')
        if len(p1) < 6:
            raise forms.ValidationError('รหัสผ่านต้องยาวอย่างน้อย 6 ตัวอักษร')
        return p1

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1', '')
        p2 = self.cleaned_data.get('password2', '')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('รหัสผ่านสองช่องไม่ตรงกัน')
        return p2


class CustomerLoginForm(forms.Form):
    """ฟอร์มเข้าสู่ระบบลูกค้า พร้อมตัวเลือก Remember Me"""
    username = forms.EmailField(
        label='อีเมล',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com', 'autocomplete': 'username'}),
    )
    password = forms.CharField(
        label='รหัสผ่าน',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'รหัสผ่าน', 'autocomplete': 'current-password'}),
    )
    remember_me = forms.BooleanField(
        required=False,
        label='จดจำฉันไว้ในระบบ (14 วัน)',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )


class UserRoleChangeForm(forms.Form):
    """ฟอร์มเปลี่ยนบทบาทผู้ใช้สำหรับผู้จัดการ / แอดมิน"""
    ROLE_CHOICES = [
        ('Member', '👤 สมาชิกร้านค้า (Member)'),
        ('Staff', '🛠️ เจ้าหน้าที่ร้าน (Staff)'),
        ('Manager', '👑 ผู้จัดการร้าน (Manager)'),
    ]
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        label='บทบาทที่ต้องการกำหนด',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )



