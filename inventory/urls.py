from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Products
    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/add/', views.ProductCreateView.as_view(), name='product-create'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('products/<int:pk>/edit/', views.ProductUpdateView.as_view(), name='product-update'),
    path('products/<int:pk>/delete/', views.ProductDeleteView.as_view(), name='product-delete'),
    
    # Sales
    path('sales/', views.SaleListView.as_view(), name='sale-list'),
    path('sales/add/', views.SaleCreateView.as_view(), name='sale-create'),
    path('sales/<int:pk>/', views.SaleDetailView.as_view(), name='sale-detail'),
    path('sales/<int:pk>/edit/', views.SaleUpdateView.as_view(), name='sale-update'),
    path('sales/<int:pk>/delete/', views.SaleDeleteView.as_view(), name='sale-delete'),
    
    # Reports
    path('reports/low-stock/', views.low_stock_report, name='low-stock-report'),
    path('reports/sales/', views.sales_report, name='sales-report'),
    
    # API endpoints
    path('api/product/<int:product_id>/price/', views.product_price_api, name='product-price-api'),
    path('api/product/<int:product_id>/stock/', views.product_stock_api, name='product-stock-api'),
]