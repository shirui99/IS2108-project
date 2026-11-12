from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from adminpanel.models import Customer, Item, Orders, Product, SupportTicket


DEMO_CUSTOMER_ID = "CDEMO"
DEMO_USERNAME = "alex.tan"
DEMO_PRODUCTS = (
    ("DEMO1", "Apples", "fruit", "1 kg", 4.50, True),
    ("DEMO2", "Whole Milk", "dairy", "1 L", 3.00, True),
    ("DEMO3", "Basmati Rice", "rice", "1 kg", 5.00, False),
    ("DEMO4", "Wholemeal Bread", "bakery", "1 loaf", 2.50, True),
    ("DEMO5", "Dishwashing Liquid", "household", "1 pack", 4.00, True),
)
DEMO_PRODUCT_IDS = tuple(product[0] for product in DEMO_PRODUCTS)
DEMO_ORDER_IDS = ("DMO001", "DMO002")


class Command(BaseCommand):
    help = "Create or refresh reserved demo data for the restock feature."

    @transaction.atomic
    def handle(self, *args, **options):
        """Create a repeatable, isolated restock demonstration dataset.

        The command deletes and recreates only records using the reserved
        DEMO*/CDEMO/DMO* identifiers, then creates valid delivered order
        items and separate available warehouse stock items.
        """
        # Clear everything on the demo customer's orders. Tickets and items must go before the orders
        SupportTicket.objects.filter(Torder__Ocustomer_id=DEMO_CUSTOMER_ID).delete()
        Item.objects.filter(Iorder__Ocustomer_id=DEMO_CUSTOMER_ID).delete()
        Orders.objects.filter(Ocustomer_id=DEMO_CUSTOMER_ID).delete()

        # Clear demo stock that is not on any order
        Item.objects.filter(Iproduct_id__in=DEMO_PRODUCT_IDS, Iorder__isnull=True).delete()

        user, _ = User.objects.get_or_create(username=DEMO_USERNAME)
        user.set_password("restock-demo-password")
        user.save(update_fields=["password"])
        customer, _ = Customer.objects.update_or_create(
            Cid=DEMO_CUSTOMER_ID,
            defaults={
                "Cname": "Alex Tan",
                "Caddress": "12 Grove Lane",
                "Chouseholdsize": 3,
                "Cmealsperweek": 14,
                "Cuser": user,
            },
        )

        products = {}

        for pid, name, category, size, price, active in DEMO_PRODUCTS:

            products[pid], _ = Product.objects.update_or_create(
                Pid=pid,
                defaults={
                    "Pname": name,
                    "Pcategory_id": category,
                    "Psize": size,
                    "Pprice": price,
                    "Plowstock": 1,
                    "Pactive": active,
                },
            )

        today = date.today()
        orders = [
            Orders.objects.create(
                Oid="DMO001",
                Odate=today - timedelta(days=20),
                Oaddress=customer.Caddress,
                Ostatus="delivered",
                Ocustomer=customer,
            ),
            Orders.objects.create(
                Oid="DMO002",
                Odate=today - timedelta(days=10),
                Oaddress=customer.Caddress,
                Ostatus="delivered",
                Ocustomer=customer,
            ),
        ]
        Item.objects.create(
            Ireceived=orders[0].Odate,
            Istatus="delivered",
            Iproduct=products["DEMO1"],
            Iorder=orders[0],
        )
        Item.objects.create(
            Ireceived=orders[1].Odate,
            Istatus="used",
            Iproduct=products["DEMO1"],
            Iorder=orders[1],
        )
        Item.objects.create(
            Ireceived=orders[0].Odate,
            Istatus="delivered",
            Iproduct=products["DEMO2"],
            Iorder=orders[0],
        )

        for product in products.values():
            Item.objects.create(
                Ireceived=today - timedelta(days=1),
                Istatus="available",
                Iexpiry=(today + timedelta(days=10)) if product.Pid != "DEMO4" else today - timedelta(days=1),
                Iproduct=product,
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded reserved restock demo data for "
                f"{customer.Cid}: {len(products)} products, {len(orders)} orders."
            )
        )
