from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import RequestFactory, TestCase

from adminpanel.models import Customer, Item, Orders, Product

from .restock import (
    get_customer_purchase_history,
    get_restock_suggestions,
    predict_restock,
)
from .middlewares import login_middleware


class CustomerAuthenticationMiddlewareTests(TestCase):
    def test_blocked_checkout_does_not_execute_protected_view(self):
        request = RequestFactory().post('/store/checkout')
        request.session = {}
        view_executed = False

        def protected_view(_request):
            nonlocal view_executed
            view_executed = True

        response = login_middleware(protected_view)(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/store/login')
        self.assertFalse(view_executed)


class CatalogueAndCartLoginTests(TestCase):
    def setUp(self):
        for product_id, name, category, price, active in [
            ('P001', 'Apple', 'fruit', 3, True),
            ('P002', 'Banana', 'fruit', 1, True),
            ('P003', 'Milk', 'dairy', 2, True),
            ('P004', 'Hidden', 'fruit', 4, False),
        ]:
            Product.objects.create(Pid=product_id, Pname=name, Pcategory=category,
                                   Psize='1 pack', Pprice=price, Plowstock=1,
                                   Pactive=active)

    def test_category_and_price_sort_apply_together(self):
        response = self.client.get('/store/', {'category': 'fruit', 'sort': 'price_asc'})
        self.assertEqual([p.Pname for p in response.context['products']], ['Banana', 'Apple'])
        self.assertContains(response, 'value="fruit" selected')
        self.assertContains(response, 'value="price_asc" selected')

    def test_invalid_filters_fall_back_to_all_categories_and_name(self):
        response = self.client.get('/store/', {'category': 'unknown', 'sort': 'unknown'})
        self.assertEqual([p.Pname for p in response.context['products']], ['Apple', 'Banana', 'Milk'])

    def test_guest_add_prompts_for_login_without_adding(self):
        response = self.client.post('/store/cart/P001', follow=True)
        self.assertRedirects(response, '/store/login?cart_login=1')
        self.assertContains(response, 'Please log in to add products to your cart.')
        self.assertNotIn('cart', self.client.session)
        response = self.client.post('/store/login?cart_login=1', {'username': 'bad', 'password': 'bad'})
        self.assertContains(response, 'Please log in to add products to your cart.')
        self.assertContains(response, 'Invalid username or password.')


class StoreMutationTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="store_test", password="password")
        self.customer = Customer.objects.create(
            Cid="CSTORE",
            Cname="Store Customer",
            Caddress="Store Address",
            Chouseholdsize=2,
            Cmealsperweek=5,
            Cuser=user,
        )
        self.product = Product.objects.create(
            Pid="S001",
            Pname="Store Apples",
            Pcategory="fruit",
            Psize="1 pack",
            Pprice=2.0,
            Plowstock=1,
            Pactive=True,
        )
        Item.objects.create(Iproduct=self.product, Ireceived=date.today())
        session = self.client.session
        session["Cid"] = self.customer.Cid
        session.save()

    def test_add_to_cart_uses_post_redirect_get(self):
        response = self.client.post(f"/store/cart/{self.product.Pid}")

        self.assertRedirects(response, "/store/cart")
        self.assertEqual(self.client.session["cart"], {self.product.Pid: 1})

    def test_get_cart_does_not_add_product(self):
        response = self.client.get(f"/store/cart/{self.product.Pid}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get("cart"), {})

    def test_valid_pantry_post_marks_item_used(self):
        order = Orders.objects.create(
            Oid="SORD02",
            Odate=date(2026, 11, 8),
            Oaddress=self.customer.Caddress,
            Ostatus="delivered",
            Ocustomer=self.customer,
        )
        item = Item.objects.create(
            Ireceived=order.Odate,
            Istatus="delivered",
            Iproduct=self.product,
            Iorder=order,
        )

        response = self.client.post(
            f"/store/pantry/{item.pk}",
            {"action": "used"},
        )

        self.assertRedirects(response, "/store/pantry")
        item.refresh_from_db()
        self.assertEqual(item.Istatus, "used")

    def test_get_pantry_does_not_change_item(self):
        order = Orders.objects.create(
            Oid="SORD03",
            Odate=date(2026, 11, 8),
            Oaddress=self.customer.Caddress,
            Ostatus="delivered",
            Ocustomer=self.customer,
        )
        item = Item.objects.create(
            Ireceived=order.Odate,
            Istatus="delivered",
            Iproduct=self.product,
            Iorder=order,
        )

        response = self.client.get(
            f"/store/pantry/{item.pk}?action=used",
        )

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.Istatus, "delivered")

    def test_pantry_post_rejects_another_customers_item(self):
        other_user = User.objects.create_user(
            username="other_store_test",
            password="password",
        )
        other_customer = Customer.objects.create(
            Cid="COTHER",
            Cname="Other Customer",
            Caddress="Other Address",
            Chouseholdsize=2,
            Cmealsperweek=5,
            Cuser=other_user,
        )
        order = Orders.objects.create(
            Oid="SORD04",
            Odate=date(2026, 11, 8),
            Oaddress=other_customer.Caddress,
            Ostatus="delivered",
            Ocustomer=other_customer,
        )
        item = Item.objects.create(
            Ireceived=order.Odate,
            Istatus="delivered",
            Iproduct=self.product,
            Iorder=order,
        )

        response = self.client.post(
            f"/store/pantry/{item.pk}",
            {"action": "used"},
        )

        self.assertRedirects(response, "/store/pantry")
        item.refresh_from_db()
        self.assertEqual(item.Istatus, "delivered")

    def test_invalid_pantry_rating_is_not_saved(self):
        order = Orders.objects.create(
            Oid="SORD01",
            Odate=date(2026, 11, 8),
            Oaddress=self.customer.Caddress,
            Ostatus="delivered",
            Ocustomer=self.customer,
        )
        item = Item.objects.create(
            Ireceived=order.Odate,
            Istatus="delivered",
            Iproduct=self.product,
            Iorder=order,
        )

        response = self.client.post(
            f"/store/pantry/{item.pk}",
            {"action": "rate", "rating": "6"},
        )

        self.assertRedirects(response, "/store/pantry")
        item.refresh_from_db()
        self.assertIsNone(item.Irating)
        messages = list(response.wsgi_request._messages)
        self.assertEqual(str(messages[0]), "Please choose a rating from 1 to 5.")


class RestockFeatureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="restock_test")
        self.customer = Customer.objects.create(
            Cid="CTEST",
            Cname="Test Customer",
            Caddress="Test Address",
            Chouseholdsize=3,
            Cmealsperweek=10,
            Cuser=self.user,
        )
        self.other_user = User.objects.create_user(username="restock_other")
        self.other_customer = Customer.objects.create(
            Cid="COTH",
            Cname="Other Customer",
            Caddress="Other Address",
            Chouseholdsize=2,
            Cmealsperweek=7,
            Cuser=self.other_user,
        )
        self.product = self._product("T001", "Test Apples", "fruit")
        self.other_product = self._product("T002", "Other Milk", "dairy")

    def _product(self, pid, name, category, active=True):
        return Product.objects.create(
            Pid=pid,
            Pname=name,
            Pcategory=category,
            Psize="1 pack",
            Pprice=2.0,
            Plowstock=1,
            Pactive=active,
        )

    def _order(self, oid, customer, order_date, status="delivered"):
        return Orders.objects.create(
            Oid=oid,
            Odate=order_date,
            Oaddress=customer.Caddress,
            Ostatus=status,
            Ocustomer=customer,
        )

    def _item(self, product, order, status="delivered", expiry=None):
        return Item.objects.create(
            Ireceived=order.Odate if order else date(2026, 11, 8),
            Iexpiry=expiry,
            Istatus=status,
            Iproduct=product,
            Iorder=order,
        )

    def test_history_combines_same_day_excludes_cancelled_and_keeps_used_items(self):
        first = self._order("TST001", self.customer, date(2026, 10, 1))
        same_day = self._order("TST002", self.customer, date(2026, 10, 1))
        cancelled = self._order(
            "TST003", self.customer, date(2026, 10, 5), status="cancelled"
        )
        latest = self._order("TST004", self.customer, date(2026, 10, 8))
        self._item(self.product, first)
        self._item(self.product, same_day, status="used")
        self._item(self.product, cancelled, status="used")
        self._item(self.product, latest, status="used")

        history = get_customer_purchase_history(self.customer.Cid)

        self.assertEqual(
            history[self.product.Pid],
            [
                {"purchased_at": date(2026, 10, 1), "purchased_quantity": 2},
                {"purchased_at": date(2026, 10, 8), "purchased_quantity": 1},
            ],
        )

    def test_customer_history_is_isolated(self):
        order = self._order("TST005", self.other_customer, date(2026, 10, 1))
        self._item(self.other_product, order)

        self.assertEqual(get_customer_purchase_history(self.customer.Cid), {})
        self.assertEqual(
            list(get_customer_purchase_history(self.other_customer.Cid)),
            [self.other_product.Pid],
        )

    @patch("store.restock.predict_restock")
    def test_model_and_initial_results_are_returned(self, predict):
        first = self._order("TST006", self.customer, date(2026, 10, 1))
        latest = self._order("TST007", self.customer, date(2026, 10, 8))
        single = self._order("TST008", self.customer, date(2026, 10, 5))
        self._item(self.product, first)
        self._item(self.product, latest)
        self._item(self.other_product, single)
        self._item(self.product, None, status="available", expiry=date(2026, 12, 1))
        self._item(
            self.other_product, None, status="available", expiry=date(2026, 12, 1)
        )
        predict.side_effect = [
            {"status": "MODEL", "interval_days": 2, "restock_date": "2026-10-10"},
            {"status": "INITIAL", "interval_days": 3, "restock_date": "2026-10-08"},
        ]

        suggestions = get_restock_suggestions(
            self.customer.Cid, today=date(2026, 10, 7)
        )

        self.assertEqual([item["status"] for item in suggestions], ["INITIAL", "MODEL"])
        self.assertEqual(predict.call_count, 2)

    @patch("store.restock.predict_restock")
    def test_due_filter_and_product_stock_rules(self, predict):
        products = [
            self.product,
            self._product("T003", "Inactive", "fruit", active=False),
            self._product("T004", "Expired", "fruit"),
            self._product("T005", "Too Late", "fruit"),
        ]
        for index, product in enumerate(products):
            order = self._order(
                f"T{index + 10:05d}", self.customer, date(2026, 10, 1)
            )
            self._item(product, order)
        self._item(self.product, None, status="available", expiry=None)
        self._item(products[1], None, status="available", expiry=None)
        self._item(products[2], None, status="available", expiry=date(2026, 10, 6))
        self._item(products[3], None, status="available", expiry=None)
        predict.side_effect = [
            {
                "status": "INITIAL",
                "interval_days": 1,
                "restock_date": "2026-10-07",
            },
            {
                "status": "INITIAL",
                "interval_days": 20,
                "restock_date": "2026-10-21",
            },
            {
                "status": "INITIAL",
                "interval_days": 20,
                "restock_date": "2026-10-21",
            },
        ]

        suggestions = get_restock_suggestions(
            self.customer.Cid, today=date(2026, 10, 7)
        )

        self.assertEqual([item["product_id"] for item in suggestions], [self.product.Pid])
        self.assertEqual(predict.call_count, 3)

    @patch("store.restock.load_restock_artifacts")
    def test_missing_model_still_uses_initial_fallback(self, load_artifacts):
        load_artifacts.return_value = {
            "pipeline": None,
            "metadata": {
                "training_only_category_medians": {"fruit": 4.0},
                "training_only_overall_median": 9.0,
            },
            "error": "missing model",
        }
        result = predict_restock(
            date(2026, 10, 1),
            household_size=3,
            category="fruit",
            purchased_quantity=2,
            previous_interval_days=None,
            history_count=1,
        )
        self.assertEqual(result["status"], "INITIAL")
        self.assertEqual(result["interval_days"], 4)

    def test_seed_command_is_idempotent_and_reserved(self):
        call_command("seed_restock_demo")
        first_counts = (
            Customer.objects.filter(pk="CDEMO").count(),
            Product.objects.filter(Pid__startswith="DEMO").count(),
            Orders.objects.filter(Oid__startswith="DMO").count(),
        )
        call_command("seed_restock_demo")
        second_counts = (
            Customer.objects.filter(pk="CDEMO").count(),
            Product.objects.filter(Pid__startswith="DEMO").count(),
            Orders.objects.filter(Oid__startswith="DMO").count(),
        )
        self.assertEqual(first_counts, (1, 5, 2))
        self.assertEqual(second_counts, first_counts)
