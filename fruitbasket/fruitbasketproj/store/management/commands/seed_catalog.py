from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from adminpanel.models import Customer, Item, Orders, Product


# Identifiers are reserved for this catalogue; existing records are never overwritten.
CATALOGUE = (
    ("Apples", "fruit", "1 kg", 4.50, 14),
    ("Blueberries", "fruit", "125 g", 4.90, 7),
    ("Bananas", "fruit", "1 bunch", 3.20, 7),
    ("Whole Milk", "dairy", "1 L", 3.00, 14),
    ("Greek Yogurt", "dairy", "500 g", 5.20, 21),
    ("Free Range Eggs", "dairy", "10 eggs", 5.80, 28),
    ("Chicken Breast", "meat", "500 g", 6.90, 7),
    ("Salmon Fillet", "meat", "250 g", 9.90, 7),
    ("Prawns", "meat", "300 g", 8.50, 7),
    ("Wholemeal Bread", "bakery", "1 loaf", 2.50, 7),
    ("Croissants", "bakery", "4 pieces", 4.80, 7),
    ("Bagels", "bakery", "4 pieces", 4.50, 10),
    ("Jasmine Rice", "rice", "2 kg", 7.90, 365),
    ("Dried Spaghetti", "rice", "500 g", 2.80, 365),
    ("Rolled Oats", "rice", "500 g", 3.90, 180),
    ("Roasted Almonds", "snacks", "200 g", 6.20, 180),
    ("Dark Chocolate", "snacks", "100 g", 3.80, 180),
    ("Potato Chips", "snacks", "150 g", 3.20, 90),
    ("Frozen Peas", "frozen", "500 g", 3.90, 180),
    ("Frozen Mixed Berries", "frozen", "500 g", 7.90, 180),
    ("Frozen Dumplings", "frozen", "400 g", 6.50, 180),
    ("Dishwashing Liquid", "household", "1 pack", 4.00, None),
    ("Paper Towels", "household", "2 rolls", 4.50, None),
    ("Laundry Detergent", "household", "1 L", 7.20, None),
)

LEGACY_NAMES = {
    "DEMO1": ("Demo Apples", "Apples"),
    "DEMO2": ("Demo Milk", "Whole Milk"),
    "DEMO3": ("Inactive Demo Rice", "Basmati Rice"),
    "DEMO4": ("Expired Demo Bread", "Wholemeal Bread"),
    "DEMO5": ("No-history Demo Soap", "Dishwashing Liquid"),
}


class Command(BaseCommand):
    help = "Add a sample grocery catalogue without overwriting existing products."

    @transaction.atomic
    def handle(self, *args, **options):
        for product_id, (old_name, new_name) in LEGACY_NAMES.items():
            Product.objects.filter(pk=product_id, Pname=old_name).update(Pname=new_name)

        customer = Customer.objects.filter(pk="CDEMO").select_related("Cuser").first()
        if customer and customer.Cuser.username == "restock_demo":
            if User.objects.filter(username="alex.tan").exclude(pk=customer.Cuser_id).exists():
                raise CommandError("The username alex.tan is already in use; no data was changed.")
            customer.Cuser.username = "alex.tan"
            customer.Cuser.save(update_fields=["username"])
        Customer.objects.filter(pk="CDEMO", Cname="Restock Demo Customer").update(Cname="Alex Tan")
        Customer.objects.filter(pk="CDEMO", Caddress="Demo Address").update(Caddress="12 Grove Lane")
        Orders.objects.filter(Ocustomer_id="CDEMO", Oaddress="Demo Address").update(Oaddress="12 Grove Lane")

        today = timezone.localdate()
        created_count = 0
        for index, (name, category, size, price, shelf_days) in enumerate(CATALOGUE, start=1):
            product = Product.objects.filter(Pname__iexact=name, Pcategory_id=category, Pactive=True).first()
            if product is None:
                product_id = f"FB{index:03d}"
                if Product.objects.filter(pk=product_id).exists():
                    raise CommandError(f"Product ID {product_id} is already in use; no data was changed.")
                product = Product.objects.create(
                    Pid=product_id,
                    Pname=name,
                    Pcategory_id=category,
                    Psize=size,
                    Pprice=price,
                    Plowstock=2,
                    Pactive=True,
                    Pexpirydays=0,
                )
                expiry = today + timedelta(days=shelf_days) if shelf_days else None
                Item.objects.bulk_create([
                    Item(Iproduct=product, Ireceived=today, Iexpiry=expiry, Istatus="available")
                    for _ in range(6)
                ])
                created_count += 1

            # Reuse reserved products without presenting expired stock as available.
            usable_stock = product.product_items.filter(
                Q(Iexpiry__isnull=True) | Q(Iexpiry__gte=today + timedelta(days=product.Pexpirydays)),
                Istatus="available",
                Iorder__isnull=True,
            )
            if product.pk in LEGACY_NAMES and not usable_stock.exists():
                expiry = today + timedelta(days=shelf_days) if shelf_days else None
                Item.objects.bulk_create([
                    Item(Iproduct=product, Ireceived=today, Iexpiry=expiry, Istatus="available")
                    for _ in range(6)
                ])

        self.stdout.write(self.style.SUCCESS(f"Catalogue ready: {created_count} products added."))
