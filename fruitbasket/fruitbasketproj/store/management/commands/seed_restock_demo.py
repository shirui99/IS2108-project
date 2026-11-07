from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from adminpanel.models import Customer, Item, Orders, Product


DEMO_CUSTOMER_ID = "CDEMO"
DEMO_USERNAME = "restock_demo"
DEMO_PRODUCT_IDS = ("DEMO1", "DEMO2", "DEMO3", "DEMO4", "DEMO5")
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
        Item.objects.filter(Iorder__Oid__in=DEMO_ORDER_IDS).delete()
        Item.objects.filter(Iproduct_id__in=DEMO_PRODUCT_IDS, Iorder__isnull=True).delete()
        Orders.objects.filter(Oid__in=DEMO_ORDER_IDS).delete()
        Product.objects.filter(Pid__in=DEMO_PRODUCT_IDS).delete()

        user, _ = User.objects.get_or_create(username=DEMO_USERNAME)
        user.set_password("restock-demo-password")
        user.save(update_fields=["password"])
        customer, _ = Customer.objects.update_or_create(
            Cid=DEMO_CUSTOMER_ID,
            defaults={
                "Cname": "Restock Demo Customer",
                "Caddress": "Demo Address",
                "Chouseholdsize": 3,
                "Cmealsperweek": 14,
                "Cuser": user,
            },
        )

        products = {
            "DEMO1": Product.objects.create(
                Pid="DEMO1",
                Pname="Demo Apples",
                Pcategory="fruit",
                Psize="1 kg",
                Pprice=4.50,
                Plowstock=1,
                Pactive=True,
            ),
            "DEMO2": Product.objects.create(
                Pid="DEMO2",
                Pname="Demo Milk",
                Pcategory="dairy",
                Psize="1 L",
                Pprice=3.00,
                Plowstock=1,
                Pactive=True,
            ),
            "DEMO3": Product.objects.create(
                Pid="DEMO3",
                Pname="Inactive Demo Rice",
                Pcategory="rice",
                Psize="1 kg",
                Pprice=5.00,
                Plowstock=1,
                Pactive=False,
            ),
            "DEMO4": Product.objects.create(
                Pid="DEMO4",
                Pname="Expired Demo Bread",
                Pcategory="bakery",
                Psize="1 loaf",
                Pprice=2.50,
                Plowstock=1,
                Pactive=True,
            ),
            "DEMO5": Product.objects.create(
                Pid="DEMO5",
                Pname="No-history Demo Soap",
                Pcategory="household",
                Psize="1 pack",
                Pprice=4.00,
                Plowstock=1,
                Pactive=True,
            ),
        }

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
