from django.core.management.base import BaseCommand
from faker import Faker
from inventory.models import Product, Sale, SaleItem, StockTransaction
from decimal import Decimal
import random
from django.utils import timezone
from django.db import transaction


class Command(BaseCommand):
    help = 'Populate database with fake data for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--products',
            type=int,
            default=20,
            help='Number of products to create (default: 20)'
        )
        parser.add_argument(
            '--sales',
            type=int,
            default=15,
            help='Number of sales to create (default: 15)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before populating'
        )
        parser.add_argument(
            '--active-only',
            action='store_true',
            help='Create only active products'
        )

    def handle(self, *args, **options):
        fake = Faker()
        products_count = options['products']
        sales_count = options['sales']
        clear_data = options['clear']
        active_only = options['active_only']

        if clear_data:
            self.clear_existing_data()

        self.stdout.write(self.style.SUCCESS('Starting data population...'))
        self.stdout.write(f'Products to create: {products_count}')
        self.stdout.write(f'Sales to create: {sales_count}')

        # Create products
        products = self.create_products(fake, products_count, active_only)
        
        # Create sales with sale items (only if we have products)
        if products:
            sales = self.create_sales(fake, sales_count, products)
            
            # Create stock transactions
            self.create_stock_transactions(fake, products)
        else:
            self.stdout.write(self.style.WARNING('No products created. Skipping sales.'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully populated database with {len(products)} products '
                f'and {sales_count} sales!'
            )
        )

    def clear_existing_data(self):
        """Clear existing data"""
        self.stdout.write(self.style.WARNING('Clearing existing data...'))
        StockTransaction.objects.all().delete()
        SaleItem.objects.all().delete()
        Sale.objects.all().delete()
        Product.objects.all().delete()

    def create_products(self, fake, count, active_only=False):
        """Create fake products"""
        self.stdout.write(f'Creating {count} products...')
        
        categories = [
            'Electronics', 'Computers & Laptops', 'Mobile Phones', 'Tablets', 
            'Accessories', 'Software', 'Books', 'Office Supplies', 
            'Home Appliances', 'Gaming', 'Networking', 'Storage'
        ]
        
        suppliers = [
            'TechCorp Ltd', 'Global Supplies Inc', 'Quality Goods Co', 
            'Best Electronics', 'Premium Suppliers', 'Reliable Tech',
            'Kenya Tech Imports', 'Nairobi Computer Wholesalers',
            'Mombasa Electronics', 'Kisumu Gadget Distributors'
        ]
        
        brands = [
            'Dell', 'HP', 'Lenovo', 'Samsung', 'Apple', 'Toshiba',
            'Acer', 'Asus', 'Microsoft', 'Logitech', 'Canon', 'Epson',
            'Intel', 'AMD', 'NVIDIA', 'Western Digital', 'Seagate'
        ]
        
        products = []
        for i in range(count):
            # Generate realistic pricing
            buying_price = Decimal(random.uniform(500, 50000)).quantize(Decimal('0.01'))
            markup_percentage = Decimal(random.uniform(1.2, 2.0))  # 20% to 100% markup
            selling_price = (buying_price * markup_percentage).quantize(Decimal('0.01'))
            
            product_name = f"{random.choice(brands)} {fake.word().title()} {random.choice(['Pro', 'Elite', 'Max', 'Plus', 'Standard', 'Basic'])}"
            
            product = Product(
                name=product_name,
                description=fake.paragraph(nb_sentences=2),
                category=random.choice(categories),
                buying_price=buying_price,
                selling_price=selling_price,
                current_stock=random.randint(10, 200),  # Start with some stock
                min_stock_level=random.randint(5, 20),
                supplier=random.choice(suppliers),
                supplier_contact=fake.email(),
                is_active=active_only or random.choice([True, True, True, False])  # 75% active unless active-only
            )
            products.append(product)

        # Use bulk_create for better performance
        Product.objects.bulk_create(products)
        
        # Generate SKUs after saving (since SKU generation happens on save)
        for product in products:
            product.save()  # This will generate the SKU
        
        self.stdout.write(self.style.SUCCESS(f'Created {len(products)} products'))
        
        # Display some created products
        self.stdout.write("\nSample products created:")
        for product in random.sample(products, min(5, len(products))):
            self.stdout.write(f"  - {product.name} (Ksh {product.selling_price:,.2f}) - Stock: {product.current_stock}")
        
        return list(Product.objects.all())  # Return with actual IDs

    def create_sales(self, fake, count, products):
        """Create fake sales with sale items"""
        self.stdout.write(f'Creating {count} sales...')
        
        # Filter only active products with stock for sales
        available_products = [p for p in products if p.is_active and p.current_stock > 0]
        
        if not available_products:
            self.stdout.write(self.style.WARNING('No active products with stock available for sales'))
            return []

        payment_methods = [choice[0] for choice in Sale.PAYMENT_METHOD_CHOICES]
        sales_created = 0
        
        for i in range(count):
            try:
                with transaction.atomic():
                    # Create sale
                    sale = Sale(
                        date=fake.date_time_between(
                            start_date='-90d',  # Last 3 months
                            end_date='now',
                            tzinfo=timezone.get_current_timezone()
                        ),
                        payment_method=random.choice(payment_methods),
                        notes=fake.sentence() if random.choice([True, False]) else ''
                    )
                    sale.save()  # This will generate sale_number

                    # Create 1-4 sale items per sale
                    sale_items_count = random.randint(1, min(4, len(available_products)))
                    selected_products = random.sample(available_products, sale_items_count)
                    
                    sale_total = Decimal('0.00')

                    for product in selected_products:
                        # Ensure we don't sell more than available stock
                        max_quantity = min(product.current_stock, random.randint(1, 3))
                        if max_quantity <= 0:
                            continue
                            
                        quantity = random.randint(1, max_quantity)
                        unit_price = product.selling_price

                        sale_item = SaleItem(
                            sale=sale,
                            product=product,
                            quantity=quantity,
                            unit_price=unit_price
                        )
                        sale_item.save()  # This will update stock automatically
                        sale_total += sale_item.subtotal

                    # Update sale total
                    sale.total_amount = sale_total
                    sale.save()

                    sales_created += 1

                    if sales_created % 10 == 0:  # Progress indicator
                        self.stdout.write(f'Created {sales_created} sales...')

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error creating sale {i+1}: {str(e)}'))
                continue

        self.stdout.write(self.style.SUCCESS(f'Created {sales_created} sales with items'))
        return sales_created

    def create_stock_transactions(self, fake, products):
        """Create stock transactions for products"""
        self.stdout.write('Creating stock transactions...')
        
        transactions_created = 0
        for product in products:
            # Create initial stock-in transaction
            if product.current_stock > 0:
                transaction_type = 'in'
                quantity = product.current_stock
                
                stock_transaction = StockTransaction(
                    product=product,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    reference=f"INIT-{product.sku}",
                    notes="Initial stock"
                )
                stock_transaction.save()
                transactions_created += 1

            # Create some additional transactions
            num_additional = random.randint(0, 3)
            for i in range(num_additional):
                transaction_type = random.choice(['in', 'out', 'adjust'])
                
                if transaction_type == 'in':
                    quantity = random.randint(10, 50)
                elif transaction_type == 'out':
                    quantity = -random.randint(1, 20)
                else:  # adjust
                    quantity = random.randint(-5, 5)
                
                stock_transaction = StockTransaction(
                    product=product,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    reference=f"{transaction_type.upper()}-{fake.random_number(digits=4)}",
                    notes=fake.sentence()
                )
                stock_transaction.save()
                transactions_created += 1

        self.stdout.write(self.style.SUCCESS(f'Created {transactions_created} stock transactions'))