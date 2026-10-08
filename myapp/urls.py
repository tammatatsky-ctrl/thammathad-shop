"""URL config — รวมเส้นทางของระบบทั้งหมด (หน้าร้าน + บัญชีลูกค้า + admin zone + REST API).

แนวคิด:
- ทุก route ชี้เข้า Class-Based View ผ่าน .as_view() (จุด entry point ของคลาส)
- สิทธิ์ถูกบังคับที่ฝั่ง view (StaffRequiredMixin/CustomerRequiredMixin) — URL ไม่มีพลังในตัว
- REST API จาก DRF DefaultRouter (/api/products/, /api/orders/, /api/employees/)
"""
from django.urls import include, path
from django.contrib.auth import views as auth_views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import IsAdminUser
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
    path('product/translate/', views.ProductTranslateView.as_view(), name='product_translate'),
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
    path('account/profile/edit/', views.ProfileEditView.as_view(), name='profile_edit'),
    path('account/password/', views.CustomerPasswordChangeView.as_view(), name='account_password_change'),
    path('account/addresses/add/', views.AddressCreateView.as_view(), name='address_add'),
    path('account/addresses/<int:addr_id>/edit/', views.AddressUpdateView.as_view(), name='address_edit'),
    path('account/addresses/<int:addr_id>/delete/', views.AddressDeleteView.as_view(), name='address_delete'),
    path('account/addresses/<int:addr_id>/default/', views.AddressSetDefaultView.as_view(), name='address_default'),

    # ==================== ลืม/เปลี่ยนรหัสผ่าน (django built-in + template ไทย) ====================
    path('account/password-reset/',
         views.CustomerPasswordResetView.as_view(),
         name='password_reset'),
    path('account/password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(
             template_name='registration/password_reset_done.html'),
         name='password_reset_done'),
    path('account/reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='registration/password_reset_confirm.html',
             success_url='/account/reset/complete/'),
         name='password_reset_confirm'),
    path('account/reset/complete/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='registration/password_reset_complete.html'),
         name='password_reset_complete'),
    path('account/password-change/',
         auth_views.PasswordChangeView.as_view(
             template_name='registration/password_change_form.html',
             success_url='/account/password-change/done/'),
         name='password_change'),
    path('account/password-change/done/',
         auth_views.PasswordChangeDoneView.as_view(
             template_name='registration/password_change_done.html'),
         name='password_change_done'),

    path('contact/', views.ContactView.as_view(), name='contact'),
    path('staff/login/', views.StaffLoginView.as_view(), name='staff_login'),
    path('staff/logout/', views.StaffLogoutView.as_view(), name='staff_logout'),
    path('employees/', views.EmployeeListView.as_view(), name='employee_list'),
    path('employees/export/', views.EmployeeExportCsvView.as_view(), name='employee_export'),
    path('employees/create/', views.EmployeeCreateView.as_view(), name='employee_create'),
    path('employees/<int:pk>/update/', views.EmployeeUpdateView.as_view(), name='employee_update'),
    path('employees/<int:pk>/delete/', views.EmployeeDeleteView.as_view(), name='employee_delete'),

    path('orders/', views.OrderManageView.as_view(), name='order_manage'),
    path('orders/export/', views.OrderExportCsvView.as_view(), name='order_export'),
    path('orders/<int:order_id>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('orders/<int:order_id>/status/', views.OrderStatusView.as_view(), name='order_status'),
    path('orders/<int:order_id>/invoice/', views.OrderInvoiceView.as_view(), name='order_invoice'),
    path('customers/', views.CustomerListView.as_view(), name='customer_list'),
    path('customers/<int:user_id>/', views.CustomerDetailView.as_view(), name='customer_detail'),
    path('staff/users/', views.StaffUserManageView.as_view(), name='staff_users'),
    path('staff/users/<int:user_id>/role/', views.StaffUserRoleUpdateView.as_view(), name='staff_user_role_update'),
    path('reports/', views.SalesReportView.as_view(), name='reports'),
    path('payments/', views.PaymentListView.as_view(), name='payment_list'),
    path('payments/export/', views.PaymentExportCsvView.as_view(), name='payment_export'),
    path('product/<int:product_id>/stock-adjust/', views.ProductStockAdjustView.as_view(), name='stock_adjust'),

    # ==================== REST API ====================
    path('api/', api.api_root, name='api-root'),
    path('api/categories/', api.CategoryListAPIView.as_view(), name='api-categories'),
    path('api/', include(router.urls)),
    path('api/token/', api.TokenObtainThrottledView.as_view(), name='api-token'),

    # API docs (OpenAPI 3) — จำกัดเฉพาะ staff (เคยเป็น AllowAny ทุกคนเข้าดูได้
    # = เปิดโครงสร้าง endpoint/พารามิเตอร์ทั้งระบบให้คนนอกทั่วไปแบบไม่ต้องล็อกอิน)
    # เจ้าหน้าที่ (teacher) ยังดูได้ตามปกติสำหรับตรวจงาน/ส่งอาจารย์
    path('api/schema/', SpectacularAPIView.as_view(
        permission_classes=[IsAdminUser]), name='api-schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(
        url_name='api-schema', permission_classes=[IsAdminUser]), name='api-docs'),
]
