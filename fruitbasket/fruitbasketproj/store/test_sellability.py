from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db.models.query import QuerySet
from django.test import TestCase

from adminpanel.inventory import sellable_stock_filter
from adminpanel.models import Customer, Item, Orders, Product
from adminpanel.stock_advice import get_stock_advice
from store.restock import get_restock_suggestions


class SellabilityTests(TestCase):
    today = date(2026, 11, 12)

    def setUp(self):
        user = User.objects.create_user(username='policy', password='password', is_staff=True)
        self.customer = Customer.objects.create(Cid='C001', Cname='Policy', Caddress='Address', Chouseholdsize=2, Cmealsperweek=1, Cuser=user)
        self.client.force_login(user)
        session = self.client.session
        session['Cid'] = self.customer.pk
        session.save()
        self.product = Product.objects.create(Pid='P001', Pname='Milk', Pcategory='dairy', Psize='1 litre', Pprice=3, Plowstock=2, Ptargetstock=5, Pexpirydays=3)
        self.clock = patch('django.utils.timezone.localdate', return_value=self.today)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def item(self, offset=None, product=None, **kwargs):
        return Item.objects.create(Iproduct=product or self.product, Ireceived=self.today, Iexpiry=None if offset is None else self.today + timedelta(days=offset), **kwargs)

    def cart(self, contents):
        session = self.client.session
        session['cart'] = contents
        session.save()

    def test_boundaries_undated_inactive_and_status(self):
        before = self.item(2)
        exact, after, undated = self.item(3), self.item(4), self.item()
        self.item(4, Istatus='expired')
        self.assertEqual(set(Item.objects.filter(sellable_stock_filter()).values_list('pk', flat=True)), {exact.pk, after.pk, undated.pk})
        self.product.Pexpirydays = 0
        self.product.save()
        yesterday, today = self.item(-1), self.item(0)
        self.assertFalse(Item.objects.filter(sellable_stock_filter(), pk=yesterday.pk).exists())
        self.assertTrue(Item.objects.filter(sellable_stock_filter(), pk=today.pk).exists())
        self.product.Pactive = False
        self.product.save()
        self.assertFalse(Item.objects.filter(sellable_stock_filter()).exists())
        before.refresh_from_db()
        self.assertEqual(before.Istatus, 'available')

    def test_advice_uses_sellable_and_unset_target(self):
        self.item(2)
        self.item(3)
        self.item()
        self.item(4, Istatus='expired')
        row = list(get_stock_advice(self.today)['products'])[0]
        self.assertEqual((row.available, row.sellable, row.cutoff_excluded, row.replenish), (3, 2, 1, 3))
        for _ in range(4):
            self.item()
        self.assertEqual(list(get_stock_advice(self.today)['products'])[0].replenish, 0)
        self.product.Ptargetstock = None
        self.product.save()
        self.assertIsNone(list(get_stock_advice(self.today)['products'])[0].replenish)

    def test_cart_rejects_ineligible_and_excess(self):
        self.item(2)
        self.client.post('/store/cart/P001')
        self.assertEqual(self.client.session.get('cart'), {})
        self.item(3)
        self.client.post('/store/cart/P001')
        self.client.post('/store/cart/P001')
        self.assertEqual(self.client.session['cart'], {'P001': 1})

    def test_checkout_stale_stock_and_gets_never_write_off(self):
        self.item(3)
        self.cart({'P001': 1})
        self.product.Pexpirydays = 4
        self.product.save()
        before = list(Item.objects.values())
        for path in ['/store/', '/store/cart', '/store/checkout', '/adminpanel/stock_advice', '/adminpanel/item_new']:
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertEqual(self.client.get(path).status_code, 200)
        response = self.client.post('/store/checkout', {'Oaddress': 'Address'})
        self.assertContains(response, 'Only 0 sellable pack(s)')
        self.assertEqual(list(Item.objects.values()), before)
        self.assertFalse(Orders.objects.exists())
        self.assertEqual(self.client.session['cart'], {'P001': 1})

    def test_checkout_rejects_inactive_or_missing_products_and_invalid_quantity(self):
        self.item()
        self.product.Pactive = False
        self.product.save()
        before = list(Item.objects.values())
        for contents in [{'P001': 1}, {'GONE': 1}, {'P001': -1}, {'P001': 'bad'}]:
            self.cart(contents)
            response = self.client.post('/store/checkout', {'Oaddress': 'Address'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['status_type'], 'error')
            self.assertFalse(Orders.objects.exists())
            self.assertEqual(list(Item.objects.values()), before)

    def test_allocation_only_sellable_and_claim_shortfall_rolls_back(self):
        excluded = self.item(2)
        eligible = self.item(3)
        second = Product.objects.create(Pid='P002', Pname='Rice', Pcategory='rice', Psize='1 kg', Pprice=2, Plowstock=0)
        self.item(product=second)
        self.cart({'P001': 1, 'P002': 1})
        original = QuerySet.update
        calls = []
        def shortfall(queryset, **kwargs):
            if kwargs.get('Istatus') == 'delivered':
                calls.append(True)
                if len(calls) == 2:
                    return 0
            return original(queryset, **kwargs)
        before = list(Item.objects.values())
        with patch.object(QuerySet, 'update', shortfall):
            self.assertContains(self.client.post('/store/checkout', {'Oaddress': 'Address'}), 'No order was placed')
        self.assertEqual(list(Item.objects.values()), before)
        self.assertFalse(Orders.objects.exists())
        self.assertContains(self.client.post('/store/checkout', {'Oaddress': 'Address'}), 'placed successfully')
        eligible.refresh_from_db()
        excluded.refresh_from_db()
        self.assertEqual(eligible.Istatus, 'delivered')
        self.assertEqual(excluded.Istatus, 'available')

    @patch('store.restock.predict_restock', return_value={'status': 'INITIAL', 'interval_days': 1, 'restock_date': '2026-11-12'})
    def test_restock_same_screening_preserves_predictions(self, prediction):
        order = Orders.objects.create(Oid='OLD', Odate=self.today - timedelta(days=1), Oaddress='Address', Ocustomer=self.customer, Ostatus='delivered')
        self.item(Iorder=order, Istatus='used')
        self.item(2)
        self.assertEqual(get_restock_suggestions(self.customer.pk, today=self.today), [])
        self.item(3)
        result = get_restock_suggestions(self.customer.pk, today=self.today)
        self.assertEqual((result[0]['available_stock'], result[0]['restock_date']), (1, '2026-11-12'))
