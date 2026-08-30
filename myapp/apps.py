from django.apps import AppConfig


class MyappConfig(AppConfig):
    """AppConfig ของ myapp — ใช้ default ทั้งหมด (ไม่ปรับ verbose_name/app_label)."""

    name = 'myapp'
