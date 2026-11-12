from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User, AnonymousUser
from django.db import IntegrityError
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone
from .models import Category, InventoryBatch, Item, Product
from .views import ItemView


class ReceiptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username='receipt_staff', is_staff=True)
        cls.customer = User.objects.create_user(username='receipt_customer')
        cls.inactive_staff = User.objects.create_user(username='receipt_inactive', is_staff=True, is_active=False)
        cls.product = Product.objects.create(Pid='R001', Pname='Apples', Pcategory_id='fruit', Psize='1 pack', Pprice=3, Plowstock=0, Pexpirydays=3)
        cls.inactive = Product.objects.create(Pid='R002', Pname='Inactive', Pcategory_id='fruit', Psize='1 pack', Pprice=3, Plowstock=0, Pactive=False)

    def setUp(self):
        self.client.force_login(self.staff)
        self.today = timezone.localdate()
        self.data = {'action': 'create', 'Iproduct': 'R001', 'Breference': 'BATCH-1', 'Ireceived': self.today.isoformat(), 'Iquantity': '3', 'Bdatetype': 'best_before', 'Iexpiry': (self.today + timedelta(days=1)).isoformat()}

    def test_receipt_atomic_and_repeat(self):
        response = self.client.post('/adminpanel/item_new', self.data)
        self.assertRedirects(response, '/adminpanel/item_new')
        batch = InventoryBatch.objects.get(Breference='BATCH-1')
        self.assertEqual((batch.Bquantity, batch.Bdatetype), (3, 'best_before'))
        self.assertEqual(Item.objects.filter(Ibatch=batch, Iproduct=self.product, Istatus='available', Iexpiry=batch.Bdate).count(), 3)
        self.assertContains(self.client.get('/adminpanel/item_new'), 'not sellable')
        response = self.client.post('/adminpanel/item_new', self.data)
        self.assertContains(response, 'already been received')
        self.assertContains(response, 'BATCH-1')
        self.assertEqual(Item.objects.count(), 3)

    def test_undated_and_existing_items_preserved(self):
        legacy = Item.objects.create(Iproduct=self.product, Ireceived=self.today, Iexpiry=self.today)
        data = dict(self.data, Breference='UNDATED', Bdatetype='', Iexpiry='')
        self.assertRedirects(self.client.post('/adminpanel/item_new', data), '/adminpanel/item_new')
        self.assertIsNone(InventoryBatch.objects.get(Breference='UNDATED').Bdate)
        legacy.refresh_from_db()
        self.assertIsNone(legacy.Ibatch_id)
        self.assertContains(self.client.get('/adminpanel/item_new'), 'type unknown')

    def test_invalid_values(self):
        cases = [('Iproduct', ''), ('Iproduct', 'missing'), ('Iproduct', 'R002'), ('Breference', ''), ('Breference', '  '), ('Breference', 'x' * 101), ('Iquantity', ''), ('Iquantity', '0'), ('Iquantity', '-1'), ('Iquantity', '1.5'), ('Iquantity', '501'), ('Ireceived', ''), ('Ireceived', 'bad'), ('Iexpiry', 'bad'), ('Bdatetype', 'unknown'), ('Bdatetype', ''), ('Iexpiry', '')]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                response = self.client.post('/adminpanel/item_new', dict(self.data, **{field: value}))
                self.assertEqual(response.status_code, 200)
                if field != 'Breference':
                    self.assertContains(response, 'BATCH-1')
                self.assertContains(response, 'errorlist')
                self.assertEqual(InventoryBatch.objects.count(), 0)
                self.assertEqual(Item.objects.count(), 0)

    @patch('adminpanel.views.Item.objects.bulk_create')
    def test_failure_rolls_back_batch(self, bulk):
        def partial_failure(items):
            Item.objects.create(Ibatch=items[0].Ibatch, Iproduct=items[0].Iproduct, Ireceived=items[0].Ireceived, Iexpiry=items[0].Iexpiry)
            raise IntegrityError('failure')
        bulk.side_effect = partial_failure
        response = self.client.post('/adminpanel/item_new', self.data)
        self.assertContains(response, 'could not be saved')
        self.assertFalse(InventoryBatch.objects.exists())
        self.assertFalse(Item.objects.exists())

    def test_staff_permissions_and_methods(self):
        for user in [None, self.customer, self.inactive_staff]:
            c = Client()
            if user: c.force_login(user)
            self.assertEqual(c.get('/adminpanel/item_new').status_code, 302)
            self.assertEqual(c.post('/adminpanel/item_new', self.data).status_code, 302)
            request = RequestFactory().post('/adminpanel/item_new', self.data)
            request.user = user or AnonymousUser()
            self.assertEqual(ItemView.as_view()(request).status_code, 302)
        self.assertEqual(self.client.put('/adminpanel/item_new').status_code, 405)
        self.assertFalse(InventoryBatch.objects.exists())

    def test_csrf(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.staff)
        self.assertEqual(c.post('/adminpanel/item_new', self.data).status_code, 403)
        c.get('/adminpanel/item_new')
        token = c.cookies['csrftoken'].value
        self.assertEqual(c.post('/adminpanel/item_new', dict(self.data, csrfmiddlewaretoken='bad')).status_code, 403)
        self.assertEqual(c.post('/adminpanel/item_new', dict(self.data, csrfmiddlewaretoken=token)).status_code, 302)

    def test_legacy_delete_does_not_delete_new_receipt(self):
        self.client.post('/adminpanel/item_new', self.data)
        response = self.client.post('/adminpanel/item_new', {'action': 'delete', 'product': 'R001', 'received': self.data['Ireceived'], 'expiry': self.data['Iexpiry']})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Item.objects.count(), 3)
