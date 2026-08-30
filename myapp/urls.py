"""URL config — รวมเส้นทางของระบบทั้งหมด (หน้าร้าน + บัญชีลูกค้า + admin zone + REST API).

แนวคิด:
- ทุก route ชี้เข้า Class-Based View ผ่าน .as_view() (จุด entry point ของคลาส)
- สิทธิ์ถูกบังคับที่ฝั่ง view (StaffRequiredMixin/CustomerRequiredMixin) — URL ไม่มีพลังในตัว
- REST API จาก DRF DefaultRouter (/api/products/, /api/orders/, /api/employees/)
"""
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import api, views

# REST API router: /api/products/, /api/orders/, /api/employees/ (+ detail, list)
router = DefaultRouter()
router.register('products', api.ProductViewSet, basename='api-products')
router.register('orders', api.OrderViewSet, basename='api-orders')
router.register('employees', api.EmployeeViewSet, basename='api-employees')

# OOP: ทุก route ชี้เข้า Class-Based View — as_view() คืนฟังก์ชัน entry point ของคลาส
urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('dashboard/payment/<int:payment_id>/verify/', views.PaymentVerifyView.as_view(), name='payment_verify'),
    path('product/', views.ProductPublicListView.as_view(), name='product'),
    path('product/manage/', views.ProductManageView.as_view(), name='product_manage'),
    path('product/<int:product_id>/', views.ProductDetailView.as_view(), name='product_detail'),
    path('product/add/', views.ProductCreateView.as_view(), name='product_add'),
    path('product/describe-ai/', views.ProductDescribeAIView.as_view(), name='product_describe_ai'),
    path('product/edit/<int:product_id>/', views.ProductUpdateView.as_view(), name='product_edit'),
    path('product/delete/<int:product_id>/', views.ProductDeleteView.as_view(), name='product_delete'),
    path('cart/', views.CartView.as_view(), name='cart'),
    path('cart/add/<int:product_id>/', views.CartAddView.as_view(), name='cart_add'),
    path('cart/remove/<int:product_id>/', views.CartRemoveView.as_view(), name='cart_remove'),
    path('cart/update/<int:product_id>/', views.CartUpdateView.as_view(), name='cart_update'),
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('order/success/<int:order_id>/', views.OrderSuccessView.as_view(), name='order_success'),
    path('order/tracking/', views.OrderTrackingView.as_view(), name='order_tracking'),
    path('payment/', views.PaymentRedirectView.as_view(), name='payment'),
    path('payment/quick/', views.QuickPayView.as_view(), name='payment_quick'),
    path('payment/slip/', views.SlipVerifyView.as_view(), name='payment_slip'),

    # ==================== บัญชีลูกค้า ====================
    path('account/register/', views.CustomerRegisterView.as_view(), name='account_register'),
    path('account/login/', views.CustomerLoginView.as_view(), name='account_login'),
    path('account/logout/', views.CustomerLogoutView.as_view(), name='account_logout'),
    path('account/', views.AccountView.as_view(), name='account'),
    path('account/addresses/add/', views.AddressCreateView.as_view(), name='address_add'),
    path('account/addresses/<int:addr_id>/edit/', views.AddressUpdateView.as_view(), name='address_edit'),
    path('account/addresses/<int:addr_id>/delete/', views.AddressDeleteView.as_view(), name='address_delete'),
    path('account/addresses/<int:addr_id>/default/', views.AddressSetDefaultView.as_view(), name='address_default'),
    path('contact/', views.ContactView.as_view(), name='contact'),
    path('staff/login/', views.StaffLoginView.as_view(), name='staff_login'),
    path('staff/logout/', views.StaffLogoutView.as_view(), name='staff_logout'),
    path('employees/', views.EmployeeListView.as_view(), name='employee_list'),
    path('employees/export/', views.EmployeeExportCsvView.as_view(), name='employee_export'),
    path('employees/create/', views.EmployeeCreateView.as_view(), name='employee_create'),
    path('employees/<int:pk>/update/', views.EmployeeUpdateView.as_view(), name='employee_update'),
    path('employees/<int:pk>/delete/', views.EmployeeDeleteView.as_view(), name='employee_delete'),

    # ==================== Admin: Order / Customer / Reports / Payments ====================
    path('orders/', views.OrderManageView.as_view(), name='order_manage'),
    path('orders/<int:order_id>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('orders/<int:order_id>/status/', views.OrderStatusView.as_view(), name='order_status'),
    path('customers/', views.CustomerListView.as_view(), name='customer_list'),
    path('customers/<int:user_id>/', views.CustomerDetailView.as_view(), name='customer_detail'),
    path('reports/', views.SalesReportView.as_view(), name='reports'),
    path('payments/', views.PaymentListView.as_view(), name='payment_list'),
    path('payments/export/', views.PaymentExportCsvView.as_view(), name='payment_export'),
    path('product/<int:product_id>/stock-adjust/', views.ProductStockAdjustView.as_view(), name='stock_adjust'),

    # ==================== REST API ====================
    path('api/', api.api_root, name='api-root'),
    path('api/categories/', api.CategoryListAPIView.as_view(), name='api-categories'),
    path('api/', include(router.urls)),
    path('api/token/', obtain_auth_token, name='api-token'),
]
