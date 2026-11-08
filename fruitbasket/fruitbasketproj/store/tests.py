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
