from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase

from .models import Customer, Item, Orders, Product
from store.restock import get_customer_purchase_history, get_restock_suggestions


class DeactivateProductTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='staff_ad06', password='password', is_staff=True)
        self.user = User.objects.create_user(username='buyer_ad06', password='password')
        self.customer = Customer.objects.create(Cid='C001', Cname='Buyer', Caddress='Address', Chouseholdsize=2, Cmealsperweek=3, Cuser=self.user)
        self.product = Product.objects.create(Pid='P001', Pname='Apples', Pcategory='fruit', Psize='1 pack', Pprice=2, Plowstock=1)
        self.other = Product.objects.create(Pid='P002', Pname='Bananas', Pcategory='fruit', Psize='1 pack', Pprice=3, Plowstock=1)
        self.order = Orders.objects.create(Oid='O001', Odate=date.today(), Oaddress='Address', Ocustomer=self.customer, Ostatus='delivered')
        self.pantry = Item.objects.create(Iproduct=self.product, Iorder=self.order, Ireceived=date.today(), Istatus='delivered', Ipurchasedprice=2)
        self.warehouse = Item.objects.create(Iproduct=self.product, Ireceived=date.today())
        self.client.force_login(self.staff)

    def deactivate(self, client=None, pk='P001'):
        return (client or self.client).post(f'/adminpanel/product_new/{pk}', {'action': 'deactivate', 'Pid': pk}, follow=True)

    def test_deactivate_preserves_history_and_is_repeatable(self):
        before = get_customer_purchase_history(self.customer.pk)
        self.assertContains(self.deactivate(), 'Apples was deactivated.')
        self.product.refresh_from_db()
        self.assertFalse(self.product.Pactive)
        self.assertTrue(Product.objects.get(pk='P002').Pactive)
        self.assertEqual(get_customer_purchase_history(self.customer.pk), before)
        self.pantry.refresh_from_db()
        self.warehouse.refresh_from_db()
        self.assertEqual((self.pantry.Iorder_id, self.pantry.Istatus, self.pantry.Ipurchasedprice), ('O001', 'delivered', 2))
        self.assertEqual(self.warehouse.Istatus, 'available')
        self.assertContains(self.deactivate(), 'Apples is already inactive.')
        self.assertEqual(self.deactivate(pk='MISSING').status_code, 404)

    def test_get_denial_and_csrf(self):
        self.assertEqual(self.client.get('/adminpanel/product_new/P001?action=deactivate&Pid=P001').status_code, 200)
        self.product.refresh_from_db()
        self.assertTrue(self.product.Pactive)
        for user in (None, self.user):
            client = Client()
            if user:
                client.force_login(user)
            self.assertEqual(client.post('/adminpanel/product_new/P001', {'action': 'deactivate', 'Pid': 'P001'}).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        client.get('/adminpanel/product_new')
        for token in (None, 'invalid'):
            data = {'action': 'deactivate', 'Pid': 'P001'}
            if token:
                data['csrfmiddlewaretoken'] = token
            self.assertEqual(client.post('/adminpanel/product_new/P001', data).status_code, 403)
        data['csrfmiddlewaretoken'] = client.cookies['csrftoken'].value
        self.assertEqual(client.post('/adminpanel/product_new/P001', data).status_code, 302)
        self.product.refresh_from_db()
        self.assertFalse(self.product.Pactive)

    @patch('store.restock.predict_restock', return_value={'status': 'INITIAL', 'interval_days': 1, 'restock_date': '2026-01-01'})
    def test_cart_checkout_catalogue_restock_and_history(self, prediction):
        session = self.client.session
        session['Cid'] = self.customer.pk
        session['cart'] = {'P001': 1}
        session.save()
        self.deactivate()
        self.assertNotContains(self.client.get('/store/'), 'Apples')
        self.assertContains(self.client.get('/store/'), 'Bananas')
        self.assertEqual(get_restock_suggestions(self.customer.pk, today=date.today()), [])
        self.assertContains(self.client.get('/store/cart'), 'No longer available. Remove this product before checkout.')
        self.assertContains(self.client.get('/store/checkout'), 'No longer available.')
        before_orders = Orders.objects.count()
        response = self.client.post('/store/checkout', {'Oaddress': 'Address'})
        self.assertContains(response, 'Apples is no longer available.')
        self.assertEqual(Orders.objects.count(), before_orders)
        self.warehouse.refresh_from_db()
        self.assertEqual(self.warehouse.Istatus, 'available')
        self.assertEqual(self.client.session['cart'], {'P001': 1})
        self.assertContains(self.client.get('/store/orders/O001'), 'Apples')
        self.assertContains(self.client.get('/store/pantry'), 'Apples')
        self.client.post('/store/cart/P001', {'action': 'remove'})
        self.client.post('/store/cart/P001')
        self.assertEqual(self.client.session['cart'], {})
