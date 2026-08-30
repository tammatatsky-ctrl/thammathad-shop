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
