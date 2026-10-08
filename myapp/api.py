"""REST API views — ใช้หลัก OOP เดียวกับ views.py:
- ReadOnlyModelViewSet : สาธารณะอ่านได้อย่างเดียว (สินค้า/หมวดหมู่)
- ModelViewSet         : CRUD ครบ แต่จำกัดสิทธิ์ staff (พนักงาน)
- IsAdminUser          = request.user.is_staff (ระบบเดิมของโปรเจกต์)
"""
from django.db.models import Count
from rest_framework import generics, serializers, viewsets
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.reverse import reverse as drf_reverse
from rest_framework.throttling import ScopedRateThrottle

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from .models import Employee, Order, Product
from .serializers import EmployeeSerializer, OrderSerializer, ProductSerializer


class TokenObtainThrottledView(ObtainAuthToken):
    """POST /api/token/ — ขอ token ด้วย username/password พร้อมจำกัดอัตรา 10 ครั้ง/นาที ต่อ IP.

    ใช้ ScopedRateThrottle + `throttle_scope='token'` (REST_FRAMEWORK.DEFAULT_THROTTLE_RATES)
    เพื่อกันเดารหัสผ่านผ่าน API แบบ brute force — ผู้ใช้ปกติที่ขอ token ครั้งเดียวไม่ได้รับผลกระทบ.
    หมายเหตุ: ต้องเป็น ScopedRateThrottle (ไม่ใช่ AnonRateThrottle ที่ scope ตายตัว = 'anon').
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'token'


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
    """GET /api/orders/ — เฉพาะ staff (มีรายการสินค้าย่อยใน items).

    prefetch_related('items__product'): OrderItemSerializer อ่าน product.name
    ผ่าน product_name (source='product.name') — ต้อง prefetch ต่อถึง product
    ไม่งั้นเกิด N+1 (1 query ต่อ item ตอน serialize).
    """
    queryset = Order.objects.prefetch_related('items__product').order_by('-created_at')
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


@extend_schema(
    summary='สารบัญ endpoint ของ API',
    description='คืน URL ของทุก endpoint หลัก (รวม schema/docs)',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def api_root(request):
    """GET /api/ — สารบัญ endpoint ทั้งหมด (รวม schema/docs)"""
    return Response({
        'products': drf_reverse('api-products-list', request=request),
        'categories': drf_reverse('api-categories', request=request),
        'orders': drf_reverse('api-orders-list', request=request),
        'employees': drf_reverse('api-employees-list', request=request),
        'token': drf_reverse('api-token', request=request),
        'schema': drf_reverse('api-schema', request=request),
        'docs': drf_reverse('api-docs', request=request),
    })
