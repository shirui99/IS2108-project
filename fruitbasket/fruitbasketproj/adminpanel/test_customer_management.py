from datetime import date

from django.contrib.auth.models import AnonymousUser, User
from django.test import Client, RequestFactory, TestCase

from .models import Customer, Orders, SupportTicket
from .views import CustomerView


class CustomerManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('customer_staff', password='secret', is_staff=True)
        cls.user = User.objects.create_user('buyer_a', password='secret', email='old@example.com')
        cls.other_user = User.objects.create_user('buyer_b', password='secret', email='other@example.com')
        cls.customer = Customer.objects.create(Cid='A0001', Cname='Alice', Caddress='Current address', Chouseholdsize=2, Cmealsperweek=3, Cuser=cls.user)
        cls.other = Customer.objects.create(Cid='B0001', Cname='Beatrice', Caddress='Other address', Chouseholdsize=1, Cmealsperweek=0, Cuser=cls.other_user)
        cls.order = Orders.objects.create(Oid='A00001', Ocustomer=cls.customer, Odate=date(2025, 1, 1), Oaddress='Historical address')
        other_order = Orders.objects.create(Oid='B00001', Ocustomer=cls.other, Odate=date(2025, 1, 1), Oaddress='Other historical address')
        SupportTicket.objects.create(Torder=cls.order, Tsubject='Alice ticket', Tmessage='Help')
        SupportTicket.objects.create(Torder=other_order, Tsubject='Private other ticket', Tmessage='Help')

    def setUp(self):
        self.client.force_login(self.staff)
        self.path = '/adminpanel/customer_new/A0001'
        self.data = {'Cname': 'Alice Updated', 'Caddress': 'New address', 'email': 'new@example.com'}

    def test_search_and_empty_results(self):
        for value in ['A0001', 'alice', 'buyer_a', 'old@example.com']:
            with self.subTest(value=value):
                response = self.client.get('/adminpanel/customer_new', {'q': value})
                self.assertEqual([c.pk for c in response.context['customers']], ['A0001'])
        self.assertContains(self.client.get('/adminpanel/customer_new', {'q': 'not found'}), 'No customers found.')

    def test_profile_scopes_orders_and_tickets(self):
        response = self.client.get(self.path)
        self.assertContains(response, 'A00001')
        self.assertContains(response, 'Alice ticket')
        self.assertNotContains(response, 'B00001')
        self.assertNotContains(response, 'Private other ticket')
        self.assertEqual(self.client.get('/adminpanel/customer_new/none').status_code, 404)
        self.assertEqual(self.client.post('/adminpanel/customer_new/none', self.data).status_code, 404)

    def test_update_and_historical_address(self):
        self.assertRedirects(self.client.post(self.path, self.data), self.path)
        self.customer.refresh_from_db()
        self.user.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual((self.customer.Cname, self.customer.Caddress, self.user.email), ('Alice Updated', 'New address', 'new@example.com'))
        self.assertEqual(self.order.Oaddress, 'Historical address')
        self.assertEqual((self.customer.Chouseholdsize, self.customer.Cmealsperweek, self.customer.Cuser_id), (2, 3, self.user.pk))

    def test_invalid_values_remain_visible_and_do_not_save(self):
        for field, value in [('Cname', '   '), ('Caddress', ''), ('email', 'invalid'), ('email', 'x' * 255 + '@example.com')]:
            with self.subTest(field=field):
                data = {**self.data, field: value}
                response = self.client.post(self.path, data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertEqual(response.context['form'].data[field], value)
                self.customer.refresh_from_db()
                self.assertEqual(self.customer.Cname, 'Alice')

    def test_tampering_and_old_routes_cannot_change_protected_fields(self):
        password = self.user.password
        for path, extra in [(self.path, {'Cuser': str(self.other_user.pk)}), (self.path, {'Cid': self.other.pk}),
                            (self.path, {'Chouseholdsize': '5'}), (self.path, {'is_staff': '1'}),
                            (self.path, {'password': 'new'}), ('/adminpanel/customer_new', {'Cid': self.customer.pk, 'Cuser': str(self.other_user.pk)}),
                            (self.path, {'action': 'delete'}), ('/adminpanel/customer_new', {'action': 'create', 'Cid': 'C0003'})]:
            with self.subTest(path=path, extra=extra):
                response = self.client.post(path, {**self.data, **extra})
                self.assertIn(response.status_code, [200, 405])
                self.customer.refresh_from_db()
                self.user.refresh_from_db()
                self.assertEqual((self.customer.Cname, self.customer.Cuser_id, self.customer.Chouseholdsize), ('Alice', self.user.pk, 2))
                self.assertEqual((self.user.password, self.user.is_staff), (password, False))
                self.assertEqual(Customer.objects.count(), 2)
        self.assertRedirects(self.client.post('/adminpanel/customer_new', {**self.data, 'action': 'update', 'Cid': self.customer.pk}), self.path)

    def test_permissions_methods_and_csrf(self):
        inactive = User.objects.create_user('inactive_customer_staff', is_staff=True, is_active=False)
        for user in [None, self.user, inactive]:
            client = Client()
            if user:
                client.force_login(user)
            for path in ['/adminpanel/customer_new', self.path]:
                self.assertEqual(client.get(path).status_code, 302)
                self.assertEqual(client.post(path, self.data).status_code, 302)
            request = RequestFactory().post(self.path, self.data)
            request.user = user or AnonymousUser()
            self.assertEqual(CustomerView.as_view()(request, pk=self.customer.pk).status_code, 302)
        self.assertEqual(self.client.put(self.path).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        csrf_client.get(self.path)
        self.assertEqual(csrf_client.post(self.path, self.data).status_code, 403)
        self.assertEqual(csrf_client.post(self.path, {**self.data, 'csrfmiddlewaretoken': 'bad'}).status_code, 403)
        token = csrf_client.cookies['csrftoken'].value
        self.assertEqual(csrf_client.post(self.path, {**self.data, 'csrfmiddlewaretoken': token}).status_code, 302)
