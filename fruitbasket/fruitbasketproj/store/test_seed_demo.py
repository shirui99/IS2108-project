from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone

from adminpanel.models import (
    Category,
    Customer,
    Item,
    Orders,
    Product,
    RestockCapture,
    SupportTicket,
)
from store.ordering import place_order
from store.restock import get_restock_suggestions


def _seed_base_catalogue():
    for code, name in (
        ("fruit", "Fruit & Vegetables"),
        ("dairy", "Dairy, Chilled & Eggs"),
        ("bakery", "Bakery"),
        ("rice", "Rice, Noodles & Cooking Ingredients"),
        ("household", "Household"),
    ):
        Category.objects.get_or_create(Ccode=code, defaults={"Cname": name})

    today = timezone.localdate()
    for pid, name, cat, size, price in (
        ("FB002", "Blueberries", "fruit", "125 g", 4.90),
        ("FB005", "Greek Yogurt", "dairy", "500 g", 5.20),
        ("FB006", "Free Range Eggs", "dairy", "10 eggs", 5.80),
        ("FB011", "Croissants", "bakery", "4 pieces", 4.80),
        ("FB023", "Paper Towels", "household", "2 rolls", 4.50),
    ):
        prod = Product.objects.create(
            Pid=pid, Pname=name, Pcategory_id=cat, Psize=size, Pprice=price, Plowstock=2, Pactive=True
        )
        Item.objects.bulk_create([Item(Iproduct=prod, Ireceived=today, Istatus="available") for _ in range(4)])

    Product.objects.create(
        Pid="DEMO3", Pname="Basmati Rice", Pcategory_id="rice", Psize="1 kg", Pprice=5.00, Plowstock=1, Pactive=False
    )


class SeedDemoSafetyTests(TestCase):
    def setUp(self):
        _seed_base_catalogue()

    def test_rerun_preserves_interacted_values_relationships_and_passwords(self):
        call_command("seed_demo")

        staff = User.objects.get(username="demo_staff")
        alice_user = User.objects.get(username="demo_alice")
        staff_hash = staff.password
        alice_hash = alice_user.password

        # Interact with demo records after the first seed run
        avocados = Product.objects.get(Pname="Organic Avocados")
        avocados.Pprice = 7.50
        avocados.save(update_fields=["Pprice"])

        alice = Customer.objects.get(Cuser=alice_user)
        extra_order, _ = place_order(alice, "99 Extra Test Road", {avocados.Pid: 1})

        emma_placed = Orders.objects.get(Ocustomer__Cuser__username="demo_emma", Ostatus="placed")
        Orders.objects.filter(pk=emma_placed.pk).update(Ostatus="preparing")

        open_ticket = SupportTicket.objects.get(Tsubject="Delivery window inquiry")
        open_ticket.Tstatus = "answered"
        open_ticket.Tresponse = "Driver will call on arrival."
        open_ticket.Tresponder = staff
        open_ticket.Tresponded = timezone.now()
        open_ticket.save()

        order_count_before = Orders.objects.count()
        ticket_count_before = SupportTicket.objects.count()

        # Run seed_demo a second time
        call_command("seed_demo")

        staff.refresh_from_db()
        alice_user.refresh_from_db()
        avocados.refresh_from_db()
        emma_placed.refresh_from_db()
        open_ticket.refresh_from_db()

        self.assertEqual(staff.password, staff_hash)
        self.assertEqual(alice_user.password, alice_hash)
        self.assertEqual(avocados.Pprice, 7.50)
        self.assertEqual(emma_placed.Ostatus, "preparing")
        self.assertEqual(open_ticket.Tstatus, "answered")
        self.assertEqual(open_ticket.Tresponse, "Driver will call on arrival.")
        self.assertTrue(Orders.objects.filter(pk=extra_order.pk).exists())
        # Emma's order moved to preparing, so seed_demo adds a fresh placed order only if none exists;
        # verify existing orders and tickets were never deleted or overwritten.
        self.assertGreaterEqual(Orders.objects.count(), order_count_before)
        self.assertEqual(SupportTicket.objects.count(), ticket_count_before)

    def test_collisions_with_unrelated_user_customer_and_product_are_safe(self):
        unrelated_staff = User.objects.create_user(
            username="unrelated_staff", password="KeepThisPassword1!", is_staff=True
        )
        unrelated_cust_user = User.objects.create_user(username="demo_alice", password="KeepCustomerPass1!")
        unrelated_cust = Customer.objects.create(
            Cid="DM001",
            Cname="Unrelated Person",
            Caddress="1 Private Way",
            Chouseholdsize=2,
            Cmealsperweek=7,
            Cuser=unrelated_cust_user,
        )
        unrelated_prod = Product.objects.create(
            Pid="FB001",
            Pname="Unrelated Turnips",
            Pcategory_id="fruit",
            Psize="1 kg",
            Pprice=3.30,
            Plowstock=1,
            Pactive=True,
        )

        staff_hash = unrelated_staff.password
        cust_hash = unrelated_cust_user.password

        call_command("seed_demo")

        unrelated_staff.refresh_from_db()
        unrelated_cust_user.refresh_from_db()
        unrelated_cust.refresh_from_db()
        unrelated_prod.refresh_from_db()

        self.assertTrue(unrelated_staff.is_staff)
        self.assertEqual(unrelated_staff.password, staff_hash)
        self.assertEqual(unrelated_cust.Cname, "Unrelated Person")
        self.assertEqual(unrelated_cust_user.password, cust_hash)
        self.assertEqual(unrelated_prod.Pname, "Unrelated Turnips")

        # Demo records were still created under non-colliding IDs/usernames
        self.assertTrue(User.objects.filter(username="demo_staff", is_staff=True).exists())
        self.assertTrue(Customer.objects.filter(Cname="Demo Alice Tan").exclude(pk="DM001").exists())
        self.assertTrue(Product.objects.filter(Pname="Organic Avocados").exclude(pk="FB001").exists())

    def test_demo_staff_repaired_when_inactive_nonstaff_or_stale_password(self):
        stale_staff = User.objects.create_user(
            username="demo_staff",
            password="OldStalePassword999!",
            is_staff=False,
            is_active=False,
        )
        self.assertFalse(stale_staff.is_staff)
        self.assertFalse(stale_staff.is_active)
        self.assertFalse(stale_staff.check_password("DemoStaff123!"))

        call_command("seed_demo")

        stale_staff.refresh_from_db()
        self.assertTrue(stale_staff.is_staff)
        self.assertTrue(stale_staff.is_active)
        self.assertTrue(stale_staff.check_password("DemoStaff123!"))

    def test_staff_login_with_demo_credentials(self):
        call_command("seed_demo")

        client = Client(enforce_csrf_checks=True)
        login_page = client.get("/adminpanel/login")
        self.assertEqual(login_page.status_code, 200)
        csrf_token = client.cookies["csrftoken"].value

        # Valid staff login
        response = client.post(
            "/adminpanel/login",
            {"username": "demo_staff", "password": "DemoStaff123!", "csrfmiddlewaretoken": csrf_token},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Authentication successful!", response.content)
        self.assertIn("staff_user_id", client.session)
        self.assertEqual(client.session["staff_user_id"], User.objects.get(username="demo_staff").pk)

        # Invalid password rejected
        client_bad = Client(enforce_csrf_checks=True)
        client_bad.get("/adminpanel/login")
        csrf_bad = client_bad.cookies["csrftoken"].value
        bad_response = client_bad.post(
            "/adminpanel/login",
            {"username": "demo_staff", "password": "WrongPassword999!", "csrfmiddlewaretoken": csrf_bad},
        )
        self.assertEqual(bad_response.status_code, 200)
        self.assertIn(b"Invalid username or password.", bad_response.content)
        self.assertNotIn("staff_user_id", client_bad.session)

    def test_prediction_captures_and_customer_restock_screening(self):
        call_command("seed_demo")

        alice = Customer.objects.get(Cuser__username="demo_alice")
        david = Customer.objects.get(Cuser__username="demo_david")
        emma = Customer.objects.get(Cuser__username="demo_emma")

        captures = {
            (rc.customer_id, rc.product.Pname): rc.snapshot["result"]["status"]
            for rc in RestockCapture.objects.select_related("product")
        }
        self.assertEqual(captures[(alice.Cid, "Blueberries")], "MODEL")
        self.assertEqual(captures[(david.Cid, "Organic Avocados")], "INITIAL")
        self.assertEqual(captures[(emma.Cid, "Organic Avocados")], "UNAVAILABLE")

        suggestions = get_restock_suggestions(alice.Cid)
        berry_suggestions = [s for s in suggestions if s["product_name"] == "Blueberries"]
        self.assertEqual(len(berry_suggestions), 1)
        self.assertEqual(berry_suggestions[0]["status"], "MODEL")
        self.assertLessEqual(date.fromisoformat(berry_suggestions[0]["restock_date"]), timezone.localdate() + timedelta(days=3))
