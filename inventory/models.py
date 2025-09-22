from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

class Product(models.Model):
    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, blank=True)
    buying_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    current_stock = models.PositiveIntegerField(default=0)
    min_stock_level = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        if self.selling_price < self.buying_price:
            raise ValidationError("Selling price cannot be less than buying price.")
        
        if self.current_stock < 0:
            raise ValidationError("Stock cannot be negative.")

    def save(self, *args, **kwargs):
        self.clean()
        if not self.sku:
            self.sku = f"SKU-{self.id or Product.objects.count() + 1}"
        super().save(*args, **kwargs)

    @property
    def is_low_stock(self):
        return self.current_stock <= self.min_stock_level

class Sale(models.Model):
    # Payment method choices
    CASH = 'cash'
    CARD = 'card'
    TRANSFER = 'transfer'
    DIGITAL = 'digital'
    
    PAYMENT_METHOD_CHOICES = [
        (CASH, 'Cash'),
        (CARD, 'Credit/Debit Card'),
        (TRANSFER, 'Bank Transfer'),
        (DIGITAL, 'Digital Wallet'),
    ]
    
    sale_number = models.CharField(max_length=20, unique=True, blank=True)
    date = models.DateTimeField(default=timezone.now)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(
        max_length=20, 
        choices=PAYMENT_METHOD_CHOICES, 
        default=CASH
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Sale {self.sale_number}"

    def save(self, *args, **kwargs):
        if not self.sale_number:
            # Generate sale number
            last_sale = Sale.objects.order_by('-id').first()
            last_number = int(last_sale.sale_number.split('-')[-1]) if last_sale else 0
            self.sale_number = f"SALE-{last_number + 1:06d}"
        super().save(*args, **kwargs)

    def update_total(self):
        """Recalculate total amount from sale items"""
        self.total_amount = self.items.aggregate(
            total=models.Sum(models.F('quantity') * models.F('unit_price'))
        )['total'] or 0
        self.save()

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='sale_items')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ['sale', 'product']

    def __str__(self):
        if self.product_id:  # product is set
            return f"{self.quantity} x {self.product.name}"
        return f"SaleItem (unsaved)"


    def clean(self):
        """Validate stock availability and business rules"""
        if not self.product:
            raise ValidationError("Sale item must have a product.")
        
        if self.quantity < 1:
            raise ValidationError("Quantity must be at least 1.")
        
        if self.unit_price < 0:
            raise ValidationError("Unit price cannot be negative.")
        
        # Stock validation
        if self.product and self.quantity:
            available_stock = self.product.current_stock
            
            # If updating existing item, add back the original quantity
            if self.pk:
                try:
                    original_item = SaleItem.objects.get(pk=self.pk)
                    available_stock += original_item.quantity
                except SaleItem.DoesNotExist:
                    pass
            
            if self.quantity > available_stock:
                raise ValidationError({
                    'quantity': f'Insufficient stock. Available: {available_stock}, Requested: {self.quantity}'
                })

    def save(self, *args, **kwargs):
        self.clean()
        
        # If this is an update, restore original stock first
        if self.pk:
            try:
                original_item = SaleItem.objects.get(pk=self.pk)
                original_item.product.current_stock += original_item.quantity
                original_item.product.save()
            except SaleItem.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # Update product stock
        self.product.current_stock -= self.quantity
        self.product.save()

    @property
    def subtotal(self):
        return self.quantity * self.unit_price

class StockTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
        ('adjust', 'Adjustment'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField()  # Positive for in, negative for out
    reference = models.CharField(max_length=100, blank=True)  # Sale number, PO number, etc.
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} - {self.get_transaction_type_display()} - {self.quantity}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update product stock
        self.product.current_stock += self.quantity
        self.product.save()