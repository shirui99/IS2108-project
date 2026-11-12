from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from .models import Customer, Item, Orders, Product
from .stock_advice import get_stock_advice


class StockAdviceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = date(2026, 11, 12)
        cls.staff = User.objects.create_user(username='advice_staff', password='password', is_staff=True)
        cls.buyer = User.objects.create_user(username='advice_customer', password='password')
        cls.customer = Customer.objects.create(Cid='C001', Cname='Buyer', Caddress='Address', Chouseholdsize=1, Cmealsperweek=1, Cuser=cls.buyer)

    def setUp(self):
        self.client.force_login(self.staff)

    def product(self, pk='A001', **kwargs):
        return Product.objects.create(Pid=pk, Pname=pk, Pcategory_id='fruit', Psize='1 pack', Pprice=2, Plowstock=2, Ptargetstock=5, **kwargs)

    def item(self, product, expiry=None, status='available', order=None):
        return Item.objects.create(Iproduct=product, Ireceived=self.today, Iexpiry=expiry, Istatus=status, Iorder=order)

    def test_zero_threshold_target_unset_and_inactive(self):
        zero = self.product('ZERO')
        threshold = self.product('LOW')
        at_target = self.product('AT')
        above = self.product('ABOVE')
        unset = self.product('UNSET')
        unset.Ptargetstock = None
        unset.save()
        inactive = self.product('OFF', Pactive=False)
        for product, count in [(threshold, 2), (at_target, 5), (above, 6), (inactive, 1)]:
            for _ in range(count):
                self.item(product)
        rows = {p.pk: p for p in get_stock_advice(self.today)['products']}
        self.assertEqual((rows['ZERO'].available, rows['ZERO'].replenish, rows['ZERO'].low_stock), (0, 5, True))
        self.assertEqual((rows['LOW'].available, rows['LOW'].replenish, rows['LOW'].low_stock), (2, 3, True))
        self.assertEqual(rows['AT'].replenish, 0)
        self.assertEqual(rows['ABOVE'].replenish, 0)
        self.assertIsNone(rows['UNSET'].replenish)
        self.assertEqual(rows['OFF'].replenish, 5)
        self.assertFalse(rows['OFF'].Pactive)
        self.assertTrue(all(p.recent_delivered == 0 for p in rows.values()))

    def test_date_boundaries_batches_and_statuses(self):
        product = self.product()
        for offset in [-1, 0, 7, 7, 8]:
            self.item(product, self.today + timedelta(days=offset))
        self.item(product)
        self.item(product, self.today - timedelta(days=1), status='expired')
        context = get_stock_advice(self.today)
        row = list(context['products'])[0]
        self.assertEqual((row.available, row.near_date, row.past_date, row.undated), (6, 3, 1, 1))
        batches = list(context['dated_batches'])
        self.assertEqual([b['quantity'] for b in batches], [1, 1, 2])

    def test_recent_order_counts_use_order_status_and_date_not_item_status(self):
        product = self.product()
        for index, (offset, status, item_status) in enumerate([
            (-29, 'delivered', 'used'), (0, 'delivered', 'delivered'),
            (-2, 'delivered', 'expired'), (-30, 'delivered', 'delivered'),
            (1, 'delivered', 'delivered'), (0, 'placed', 'delivered'),
            (0, 'cancelled', 'delivered'),
        ]):
            order = Orders.objects.create(Oid=f'O{index}', Odate=self.today + timedelta(days=offset), Oaddress='Address', Ocustomer=self.customer, Ostatus=status)
            self.item(product, status=item_status, order=order)
        self.assertEqual(list(get_stock_advice(self.today)['products'])[0].recent_delivered, 3)

    def test_permissions_and_no_mutations_on_get_or_refresh(self):
        product = self.product(Pexpirydays=20)
        self.item(product, self.today - timedelta(days=2))
        before = list(Item.objects.values())
        for user in [None, self.buyer]:
            client = Client()
            if user:
                client.force_login(user)
            self.assertRedirects(client.get('/adminpanel/stock_advice'), '/adminpanel/login')
            self.assertRedirects(client.post('/adminpanel/stock_advice'), '/adminpanel/login')
        session = self.client.session
        session['Cid'] = self.customer.pk
        session.save()
        with patch('django.utils.timezone.localdate', return_value=self.today):
            for path in ['/adminpanel/stock_advice', '/adminpanel/stock_advice', '/adminpanel/item_new', '/store/', '/store/checkout']:
                self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(list(Item.objects.values()), before)
        self.assertEqual(self.client.post('/adminpanel/stock_advice').status_code, 405)
        self.staff.is_staff = False
        self.staff.save()
        self.assertRedirects(self.client.get('/adminpanel/stock_advice'), '/adminpanel/login')

    def test_empty_states_and_bounded_queries(self):
        response = self.client.get('/adminpanel/stock_advice')
        self.assertContains(response, 'No products configured.')
        self.assertContains(response, 'No available stock has a recorded date')
        for i in range(10):
            self.product(str(i))
        with CaptureQueriesContext(connection) as queries:
            context = get_stock_advice(self.today)
            list(context['products'])
            list(context['dated_batches'])
        self.assertEqual(len(queries), 2)
