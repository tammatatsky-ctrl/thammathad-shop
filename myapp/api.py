"""REST API views — ใช้หลัก OOP เดียวกับ views.py:
- ReadOnlyModelViewSet : สาธารณะอ่านได้อย่างเดียว (สินค้า/หมวดหมู่)
- ModelViewSet         : CRUD ครบ แต่จำกัดสิทธิ์ staff (พนักงาน)
- IsAdminUser          = request.user.is_staff (ระบบเดิมของโปรเจกต์)
"""
from django.db.models import Count
from rest_framework import generics, serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.reverse import reverse as drf_reverse

from .models import Employee, Order, Product
from .serializers import EmployeeSerializer, OrderSerializer, ProductSerializer


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/products/ + /api/products/{id}/ — ใช้ QuerySet เดิม (search/of_category/sorted_by)"""
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        params = self.request.query_params
        return (
            Product.objects.listed()
            .search(params.get('q', '').strip())
            .of_category(params.get('cat', '').strip())
            .sorted_by(params.get('sort', 'newest'))
        )


class CategorySerializer(serializers.Serializer):
    name = serializers.CharField()
    count = serializers.IntegerField()


class CategoryListAPIView(generics.ListAPIView):
    """GET /api/categories/ — [{name, count}] จากสินค้าที่แสดงบนหน้าร้าน"""
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        return (
            Product.objects.listed()
            .exclude(category='')
            .values('category')
            .annotate(count=Count('id'))
            .order_by('category')
        )

    def list(self, request, *args, **kwargs):
        """Override list — แปลงคีย์ 'category' → 'name' และปิด pagination (คืน list เปล่า)."""
        rows = [{'name': r['category'], 'count': r['count']} for r in self.get_queryset()]
        return Response(rows)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/orders/ — เฉพาะ staff (มีรายการสินค้าย่อยใน items)"""
    queryset = Order.objects.prefetch_related('items').order_by('-created_at')
    serializer_class = OrderSerializer
    permission_classes = [IsAdminUser]


class EmployeeViewSet(viewsets.ModelViewSet):
    """CRUD /api/employees/ — เฉพาะ staff; emp_code สร้างอัตโนมัติเสมอ (read-only)"""
    queryset = Employee.objects.all().order_by('emp_code')
    serializer_class = EmployeeSerializer
    permission_classes = [IsAdminUser]

    def perform_create(self, serializer):
        """สร้างพนักงานผ่าน REST — รหัส EMP### รันอัตโนมัติเสมอ (client ตั้งไม่ต้องส่ง).

        Args:
            serializer: EmployeeSerializer ที่ผ่านการ validate แล้ว
        """
        serializer.save(emp_code=Employee.objects.next_code())


@api_view(['GET'])
@permission_classes([AllowAny])
def api_root(request):
    """GET /api/ — สารบัญ endpoint ทั้งหมด"""
    return Response({
        'products': drf_reverse('api-products-list', request=request),
        'categories': drf_reverse('api-categories', request=request),
        'orders': drf_reverse('api-orders-list', request=request),
        'employees': drf_reverse('api-employees-list', request=request),
        'token': drf_reverse('api-token', request=request),
    })
