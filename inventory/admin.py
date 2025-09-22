from django.contrib import admin
from .models import Product, StockTransaction, Sale, SaleItem

class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 1
    readonly_fields = ('subtotal',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'category', 'current_stock', 'min_stock_level')
    list_filter = ('category',)
    search_fields = ('sku', 'name')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('sale_number', 'date', 'total_amount', 'payment_method')
    list_filter = ('date', 'payment_method')
    inlines = [SaleItemInline]
    readonly_fields = ('sale_number', 'total_amount')

admin.site.register(StockTransaction)