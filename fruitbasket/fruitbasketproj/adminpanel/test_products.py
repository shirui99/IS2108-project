from datetime import date

from django.contrib.auth.models import User
from django.test import Client, TestCase

from .forms import ProductForm
from .models import Customer, Item, Orders, Product


class ProductStoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username='product_staff', password='password', is_staff=True)
        cls.buyer = User.objects.create_user(username='buyer', password='password')
        cls.customer = Customer.objects.create(Cid='C001', Cname='Buyer', Caddress='Address', Chouseholdsize=1, Cmealsperweek=1, Cuser=cls.buyer)

    def setUp(self):
        self.client.force_login(self.staff)
        self.data = dict(Pid='P001', Pname='Apples', Pcategory='fruit', Psize='1 kg', Pprice='4.5', Plowstock='2', Ptargetstock='10', Pbulkquantity='3', Pbulkprice='4', Pactive='on', Pexpirydays='5')

    def create(self, **changes):
        return self.client.post('/adminpanel/product_new', dict(self.data, action='create', **changes))

    def test_create_separate_packs_and_duplicate_sku(self):
        self.assertRedirects(self.create(), '/adminpanel/product_new')
        self.assertRedirects(self.create(Pid='P002', Psize='2 kg'), '/adminpanel/product_new')
        response = self.create(Pname='Duplicate')
        self.assertContains(response, 'already exists')
        self.assertContains(response, 'Duplicate')
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(Product.objects.get(pk='P001').Pname, 'Apples')

    def test_invalid_values_have_field_errors(self):
        cases = [('Pid', ''), ('Pname', ''), ('Psize', ''), ('Pcategory', ''), ('Pcategory', 'invalid'), ('Pprice', ''), ('Pprice', '0'), ('Pprice', '-1'), ('Pprice', 'nan'), ('Pprice', 'inf'), ('Plowstock', '-1'), ('Plowstock', '1.5'), ('Ptargetstock', '-1'), ('Ptargetstock', '1'), ('Pbulkquantity', '-1'), ('Pbulkquantity', '1'), ('Pbulkquantity', '2.5'), ('Pbulkprice', '-1'), ('Pbulkprice', '0'), ('Pbulkprice', '8'), ('Pbulkprice', ''), ('Pbulkquantity', '')]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                form = ProductForm(dict(self.data, **{field: value}))
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
        self.assertFalse(Product.objects.exists())

    def test_edit_isolated_preserves_bound_values_and_id(self):
        self.create()
        self.create(Pid='P002')
        data = dict(self.data, action='update', Pprice='6', Psize='900 g', Plowstock='3', Ptargetstock='20', Pbulkquantity='4', Pbulkprice='5')
        self.assertRedirects(self.client.post('/adminpanel/product_new/P001', data), '/adminpanel/product_new')
        self.assertEqual(Product.objects.get(pk='P001').Pprice, 6)
        self.assertEqual(Product.objects.get(pk='P001').Ptargetstock, 20)
        edited = Product.objects.get(pk='P001')
        self.assertEqual((edited.Psize, edited.Plowstock, edited.Pbulkquantity, edited.Pbulkprice), ('900 g', 3, 4, 5))
        self.assertEqual(Product.objects.get(pk='P002').Pprice, 4.5)
        response = self.client.post('/adminpanel/product_new/P001', dict(data, Pprice='bad', Pname='Retained input'))
        self.assertContains(response, 'Retained input')
        self.assertContains(response, 'Enter a number.')
        self.assertContains(response, 'value="update"')
        self.assertEqual(Product.objects.get(pk='P001').Pprice, 6)
        self.assertEqual(self.client.post('/adminpanel/product_new/P001', dict(data, Pid='P002')).status_code, 400)
        self.assertEqual(self.client.post('/adminpanel/product_new/XXXXX', data).status_code, 404)

    def test_unauthorised_and_csrf(self):
        for user in [None, self.buyer]:
            client = Client()
            if user:
                client.force_login(user)
            for path in ['/adminpanel/product_new', '/adminpanel/product_new/P001']:
                self.assertRedirects(client.get(path), '/adminpanel/login')
                self.assertRedirects(client.post(path, dict(self.data, action='create')), '/adminpanel/login')
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        self.assertEqual(client.post('/adminpanel/product_new', dict(self.data, action='create')).status_code, 403)
        self.assertFalse(Product.objects.exists())

    def test_checkout_records_price_and_legacy_price_stays_unknown(self):
        self.create()
        product = Product.objects.get(pk='P001')
        old = Orders.objects.create(Oid='OOLD', Odate=date.today(), Oaddress='Address', Ocustomer=self.customer)
        legacy = Item.objects.create(Iproduct=product, Ireceived=date.today(), Iorder=old, Istatus='delivered')
        stock = Item.objects.create(Iproduct=product, Ireceived=date.today())
        session = self.client.session
        session['Cid'] = self.customer.pk
        session['cart'] = {'P001': 1}
        session.save()
        self.assertContains(self.client.post('/store/checkout', {'Oaddress': 'Address'}), 'placed successfully')
        stock.refresh_from_db()
        self.assertEqual(stock.Ipurchasedprice, 4.5)
        self.client.post('/adminpanel/product_new/P001', dict(self.data, action='update', Pprice='7'))
        stock.refresh_from_db()
        legacy.refresh_from_db()
        self.assertEqual(stock.Ipurchasedprice, 4.5)
        self.assertIsNone(legacy.Ipurchasedprice)
        self.assertContains(self.client.get(f'/store/orders/{stock.Iorder_id}'), '$4.50')
        self.assertContains(self.client.get('/store/orders/OOLD'), 'Not recorded')
