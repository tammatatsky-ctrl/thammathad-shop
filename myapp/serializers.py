"""Serializers — แปลง Model ⇄ JSON สำหรับ REST API
ใช้ ModelSerializer (OOP: รับ logic จาก model เดิม เช่น get_status_display ผ่าน source)
"""
from django.templatetags.static import static
from rest_framework import serializers

from .models import Employee, Order, OrderItem, Product


def _absolute(request, path):
    """แปลง static/media path → URL เต็มที่ client เอาไปใช้ได้ทันที"""
    if not path:
        return None
    try:
        return request.build_absolute_uri(static(path))
    except ValueError:
        pass
    url = getattr(path, 'url', None)
    return request.build_absolute_uri(url) if url else None


class ProductSerializer(serializers.ModelSerializer):
    """Serializer สินค้า (read-only API): image_path → image_url เต็มให้ client."""

    image_url = serializers.SerializerMethodField()
    model_3d_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'category', 'description', 'price',
                  'stock', 'image_url', 'model_3d_url', 'is_active', 'created_at']

    def get_image_url(self, obj) -> str | None:
        return _absolute(self.context.get('request'), obj.image)

    def get_model_3d_url(self, obj) -> str | None:
        return _absolute(self.context.get('request'), obj.model_3d)


class EmployeeSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Employee
        fields = ['id', 'emp_code', 'name', 'gender', 'department', 'email',
                  'phone', 'status', 'status_display', 'salary', 'hire_date',
                  'avatar_url', 'created_at']
        read_only_fields = ['emp_code']

    def get_avatar_url(self, obj) -> str | None:
        """avatar เป็น ImageField (media/) — ต้องใช้ .url ไม่ใช่ static()"""
        if not obj.avatar:
            return None
        request = self.context.get('request')
        try:
            return request.build_absolute_uri(obj.avatar.url) if request else obj.avatar.url
        except ValueError:
            return None


class OrderItemSerializer(serializers.ModelSerializer):
    """แถวสินค้าในออเดอร์ (ซ้อนใน OrderSerializer) — แถมชื่อสินค้าให้โชว์ตรง."""

    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['product', 'product_name', 'quantity', 'price']


class OrderSerializer(serializers.ModelSerializer):
    """Serializer ออเดอร์ — พร้อม items ซ้อน + ป้ายสถานะภาษาไทย (get_status_display)."""

    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'customer_name', 'phone', 'total', 'status',
                  'status_display', 'payment_method', 'created_at', 'items']
