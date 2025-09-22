from django import forms
from django.forms import inlineformset_factory
from .models import Product, Sale, SaleItem

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'sku', 'description', 'category', 'buying_price', 
                 'selling_price', 'current_stock', 'min_stock_level', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'category': forms.TextInput(attrs={'class': 'form-control'}),
            'buying_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'current_stock': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'min_stock_level': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        selling_price = cleaned_data.get('selling_price')
        buying_price = cleaned_data.get('buying_price')
        
        if selling_price and buying_price and selling_price < buying_price:
            raise forms.ValidationError("Selling price cannot be less than buying price.")
        
        return cleaned_data

class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['date', 'payment_method', 'notes']
        widgets = {
            'date': forms.DateTimeInput(attrs={
                'type': 'datetime-local', 
                'class': 'form-control'
            }),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'rows': 2, 
                'class': 'form-control',
                'placeholder': 'Optional notes about this sale...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure payment method field has choices
        self.fields['payment_method'].widget.choices = self.fields['payment_method'].choices

class SaleItemForm(forms.ModelForm):
    class Meta:
        model = SaleItem
        fields = ['product', 'quantity', 'unit_price']
        widgets = {
            'product': forms.Select(attrs={
                'class': 'form-control product-select',
                'onchange': 'updateProductInfo(this)'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control quantity-input',
                'min': '1',
                'onchange': 'calculateLineTotal(this)'
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control price-input',
                'step': '0.01',
                'onchange': 'calculateLineTotal(this)'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active products
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        
        # Add stock information if product is selected
        if self.instance and self.instance.product:
            self.fields['product'].widget.attrs['data-stock'] = self.instance.product.current_stock
            self.fields['quantity'].widget.attrs['max'] = self.instance.product.current_stock

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')
        
        if product and quantity:
            if quantity > product.current_stock:
                raise forms.ValidationError(
                    f"Insufficient stock for {product.name}. Available: {product.current_stock}"
                )
        
        return cleaned_data

# Create the formset
SaleItemFormSet = inlineformset_factory(
    Sale,
    SaleItem,
    form=SaleItemForm,
    fields=('product', 'quantity', 'unit_price'),
    extra=1,
    can_delete=True,
    #min_num=1,
    #validate_min=True
)