from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, F, Q, Count
from django.utils import timezone
from django.http import JsonResponse
from .models import Product, Sale, SaleItem, StockTransaction
from .forms import SaleForm, SaleItemFormSet, ProductForm, SaleItemForm

def dashboard(request):
    low_stock_products = Product.objects.filter(current_stock__lte=F('min_stock_level'), is_active=True)
    total_products = Product.objects.filter(is_active=True).count()
    total_low_stock = low_stock_products.count()
    recent_sales = Sale.objects.all().order_by('-date')[:5]
    
    # Calculate today's sales
    today = timezone.now().date()
    today_sales = Sale.objects.filter(date__date=today).aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    # Top selling products
    top_products = Product.objects.annotate(
        total_sold=Sum('sale_items__quantity')
    ).order_by('-total_sold')[:5]
    
    context = {
        'low_stock_products': low_stock_products,
        'total_products': total_products,
        'total_low_stock': total_low_stock,
        'recent_sales': recent_sales,
        'today_sales': today_sales,
        'top_products': top_products,
    }
    return render(request, 'inventory/dashboard.html', context)

class ProductListView(ListView):
    model = Product
    template_name = 'inventory/product_list.html'
    context_object_name = 'products'
    paginate_by = 20
    ordering = ['name']
    
    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True)
        search_query = self.request.GET.get('search')
        category_filter = self.request.GET.get('category')
        low_stock = self.request.GET.get('low_stock')
        
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(sku__icontains=search_query) |
                Q(description__icontains=search_query)
            )
        
        if category_filter:
            queryset = queryset.filter(category=category_filter)
            
        if low_stock:
            queryset = queryset.filter(current_stock__lte=F('min_stock_level'))
            
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Product.objects.values_list('category', flat=True).distinct()
        return context

class ProductDetailView(DetailView):
    model = Product
    template_name = 'inventory/product_detail.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transactions'] = self.object.transactions.all().order_by('-timestamp')[:10]
        context['sales_history'] = self.object.sale_items.select_related('sale').order_by('-sale__date')[:10]
        return context

class ProductCreateView(CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'inventory/product_form.html'
    success_url = reverse_lazy('inventory:product-list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Product "{form.instance.name}" created successfully!')
        return super().form_valid(form)

class ProductUpdateView(UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'inventory/product_form.html'
    
    def form_valid(self, form):
        messages.success(self.request, f'Product "{form.instance.name}" updated successfully!')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('inventory:product-detail', kwargs={'pk': self.object.pk})

class ProductDeleteView(DeleteView):
    model = Product
    template_name = 'inventory/product_confirm_delete.html'
    success_url = reverse_lazy('inventory:product-list')
    
    def delete(self, request, *args, **kwargs):
        product = self.get_object()
        
        # Check if product has sales before deletion
        if product.sale_items.exists():
            messages.error(request, f'Cannot delete "{product.name}" because it has sales records. Mark as inactive instead.')
            return redirect('inventory:product-detail', pk=product.pk)
        
        messages.success(request, f'Product "{product.name}" deleted successfully!')
        return super().delete(request, *args, **kwargs)

class SaleListView(ListView):
    model = Sale
    template_name = 'inventory/sale_list.html'
    context_object_name = 'sales'
    paginate_by = 20
    ordering = ['-date']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Get filter parameters
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        payment_method = self.request.GET.get('payment_method')
        search_query = self.request.GET.get('search')
        min_amount = self.request.GET.get('min_amount')
        max_amount = self.request.GET.get('max_amount')
        
        # Apply filters
        if date_from:
            queryset = queryset.filter(date__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__date__lte=date_to)
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)
        if min_amount:
            queryset = queryset.filter(total_amount__gte=min_amount)
        if max_amount:
            queryset = queryset.filter(total_amount__lte=max_amount)
        if search_query:
            queryset = queryset.filter(
                Q(sale_number__icontains=search_query) |
                Q(items__product__name__icontains=search_query) |
                Q(notes__icontains=search_query)
            ).distinct()
            
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Calculate summary statistics
        queryset = self.get_queryset()
        total_sales = queryset.count()
        total_revenue = queryset.aggregate(total=Sum('total_amount'))['total'] or 0
        avg_sale = total_revenue / total_sales if total_sales > 0 else 0
        
        context.update({
            'total_sales': total_sales,
            'total_revenue': total_revenue,
            'avg_sale': avg_sale,
            'payment_methods': Sale.PAYMENT_METHOD_CHOICES,
            'filter_params': self.request.GET,
        })
        return context

class SaleCreateView(CreateView):
    model = Sale
    form_class = SaleForm
    template_name = 'inventory/sale_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = SaleItemFormSet(self.request.POST)
        else:
            # CRITICAL: Use empty queryset to avoid loading orphaned records
            context['formset'] = SaleItemFormSet(queryset=SaleItem.objects.none())
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # Save the sale first
                    self.object = form.save(commit=False)
                    self.object.save()  # This generates the sale number if you have auto generation
                    
                    # Now save the formset with the sale instance
                    instances = formset.save(commit=False)
                    for instance in instances:
                        if not instance.product:
                            form.add_error(None, "Each sale item must have a product selected.")
                            return self.form_invalid(form)
                        
                        # Set the sale relationship
                        instance.sale = self.object
                        instance.save()
                    
                    # Handle deleted items
                    for instance in formset.deleted_objects:
                        instance.delete()
                    
                    # Update the sale total
                    self.object.update_total()
                    
                    messages.success(self.request, f'Sale {self.object.sale_number} created successfully!')
                    return redirect(self.get_success_url())
                    
            except Exception as e:
                messages.error(self.request, f'Error creating sale: {str(e)}')
                return self.form_invalid(form)
        else:
            messages.error(self.request, "Please correct the errors below.")
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        # Log formset errors for debugging
        context = self.get_context_data(form=form)
        formset = context['formset']
        
        if formset.errors:
            for i, error_dict in enumerate(formset.errors):
                if error_dict:
                    for field, errors in error_dict.items():
                        for error in errors:
                            messages.error(self.request, f"Item {i+1} - {field}: {error}")
        
        return self.render_to_response(context)
    
    def get_success_url(self):
        return reverse_lazy('inventory:sale-detail', kwargs={'pk': self.object.pk})
class SaleDetailView(DetailView):
    model = Sale
    template_name = 'inventory/sale_detail.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.select_related('product')
        return context

class SaleUpdateView(UpdateView):
    model = Sale
    form_class = SaleForm
    template_name = 'inventory/sale_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = SaleItemFormSet(self.request.POST, instance=self.object)
        else:
            context['formset'] = SaleItemFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # Store original quantities for stock restoration
                    original_quantities = {}
                    for item in self.object.items.all():
                        original_quantities[item.pk] = item.quantity
                    
                    # Validate stock availability
                    instances = formset.save(commit=False)
                    stock_errors = []
                    
                    for i, instance in enumerate(instances):
                        if not instance.product:
                            stock_errors.append(f"Item {i+1}: Product is required")
                            continue
                            
                        available_stock = instance.product.current_stock
                        
                        # If updating existing item, add back original quantity
                        if instance.pk and instance.pk in original_quantities:
                            available_stock += original_quantities[instance.pk]
                        
                        if instance.quantity > available_stock:
                            stock_errors.append(
                                f"Item {i+1}: {instance.product.name} - "
                                f"Insufficient stock. Available: {available_stock}, Requested: {instance.quantity}"
                            )
                    
                    if stock_errors:
                        for error in stock_errors:
                            messages.error(self.request, error)
                        return self.form_invalid(form)
                    
                    # Save the sale
                    self.object = form.save()
                    
                    # Save items (stock handling is done in SaleItem.save() method)
                    for instance in instances:
                        instance.sale = self.object
                        instance.save()
                    
                    # Handle deleted items
                    for instance in formset.deleted_objects:
                        instance.delete()
                    
                    self.object.update_total()
                    
                    messages.success(self.request, f'Sale {self.object.sale_number} updated successfully!')
                    return redirect(self.get_success_url())
                    
            except Exception as e:
                messages.error(self.request, f'Error updating sale: {str(e)}')
                return self.form_invalid(form)
        else:
            messages.error(self.request, "Please correct the errors below.")
            return self.form_invalid(form)
    
    def get_success_url(self):
        return reverse_lazy('inventory:sale-detail', kwargs={'pk': self.object.pk})

class SaleDeleteView(DeleteView):
    model = Sale
    template_name = 'inventory/sale_confirm_delete.html'
    success_url = reverse_lazy('inventory:sale-list')
    
    def delete(self, request, *args, **kwargs):
        sale = self.get_object()
        
        # Restore stock before deletion
        with transaction.atomic():
            for item in sale.items.all():
                item.product.current_stock += item.quantity
                item.product.save()
            
            messages.success(request, f'Sale {sale.sale_number} deleted successfully! Stock has been restored.')
            return super().delete(request, *args, **kwargs)

def low_stock_report(request):
    products = Product.objects.filter(
        current_stock__lte=F('min_stock_level'), 
        is_active=True
    ).order_by('current_stock')
    return render(request, 'inventory/low_stock_report.html', {'products': products})

def sales_report(request):
    sales = Sale.objects.all().order_by('-date')
    
    # Date filtering
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    payment_method = request.GET.get('payment_method')
    
    if date_from:
        sales = sales.filter(date__date__gte=date_from)
    if date_to:
        sales = sales.filter(date__date__lte=date_to)
    if payment_method:
        sales = sales.filter(payment_method=payment_method)
    
    # Calculate totals
    total_sales = sales.count()
    total_revenue = sales.aggregate(total=Sum('total_amount'))['total'] or 0
    avg_sale = total_revenue / total_sales if total_sales > 0 else 0
    
    # Top products
    top_products = Product.objects.filter(
        sale_items__sale__in=sales
    ).annotate(
        total_sold=Sum('sale_items__quantity'),
        total_revenue=Sum('sale_items__unit_price') * F('sale_items__quantity')
    ).order_by('-total_sold')[:10]
    
    context = {
        'sales': sales,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'avg_sale': avg_sale,
        'top_products': top_products,
        'payment_methods': Sale.PAYMENT_METHOD_CHOICES,
        'date_from': date_from,
        'date_to': date_to,
        'payment_method': payment_method,
    }
    return render(request, 'inventory/sales_report.html', context)

def product_price_api(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
        return JsonResponse({
            'price': float(product.selling_price),
            'stock': product.current_stock
        })
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)

def product_stock_api(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
        return JsonResponse({'stock': product.current_stock})
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)