"""Django admin (Django Administration) — CRUD เต็มรูปแบบใช้เป็นเครื่องมือสำรอง.
หน้าเว็บหลักใช้ CBV admin zone (/employees/, /product/manage/ ...) — admin นี้
ไว้ตรวจ/แก้ข้อมูลฉุกเฉินโดยตรงในฐานข้อมูล.
"""
from django.contrib import admin
from .models import Employee, Order, OrderItem, Payment, Product


class ProductAdmin(admin.ModelAdmin):
    """การตั้งค่าหน้าแสดงสินค้าใน Django admin."""
    list_display = ('name', 'price', 'stock', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)

class OrderItemInline(admin.TabularInline):
    """Inline แถวสินค้าใต้ฟอร์มออเดอร์ (ไม่ต้องเข้าไปแก้ทีละใบ)."""
    model = OrderItem
    extra = 0

class OrderAdmin(admin.ModelAdmin):
    """การตั้งค่าหน้าแสดง+สืบค้นออเดอร์ใน Django admin."""
    list_display = ('id', 'customer_name', 'phone', 'total', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('customer_name', 'phone')
    inlines = [OrderItemInline]

class PaymentAdmin(admin.ModelAdmin):
    """การตั้งค่าหน้าแสดงบิลการชำระใน Django admin."""
    list_display = ('id', 'order', 'name', 'amount', 'transfer_date', 'created_at')

class EmployeeAdmin(admin.ModelAdmin):
    """การตั้งค่าหน้าแสดงพนักงานใน Django admin."""
    list_display = ('emp_code', 'name', 'gender', 'department', 'phone', 'email', 'status', 'salary', 'hire_date', 'avatar')
    list_filter = ('gender', 'department', 'status')
    search_fields = ('emp_code', 'name', 'department', 'email', 'phone')

admin.site.register(Product, ProductAdmin)
admin.site.register(Order, OrderAdmin)
admin.site.register(Payment, PaymentAdmin)
admin.site.register(Employee, EmployeeAdmin)
