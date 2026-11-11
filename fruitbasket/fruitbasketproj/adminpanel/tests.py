from django.test import TestCase
from django.contrib.auth.models import User

from .models import Product


class ProductViewTests(TestCase):
    def test_invalid_update_keeps_bound_values_errors_and_update_mode(self):
        Product.objects.create(
            Pid='P001',
            Pname='Original name',
            Pcategory='fruit',
            Psize='1 pack',
            Pprice=2.5,
            Plowstock=3,
            Pactive=True,
            Pexpirydays=5,
        )
        user = User.objects.create_user(username='staff', password='password', is_staff=True)
        self.client.force_login(user)

        response = self.client.post(
            '/adminpanel/product_new',
            {
                'action': 'update',
                'Pid': 'P001',
                'Pname': 'Entered name',
                'Pcategory': 'fruit',
                'Psize': '1 pack',
                'Pprice': '',
                'Plowstock': '3',
                'Pactive': 'on',
                'Pexpirydays': '5',
            },
        )

        self.assertContains(response, 'Entered name')
        self.assertContains(response, 'This field is required.')
        self.assertContains(response, 'name="action" value="update"')
        self.assertEqual(Product.objects.get(Pid='P001').Pname, 'Original name')

class StaffAuthenticationTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='staff', password='secret', is_staff=True)
        self.customer = User.objects.create_user(username='customer', password='secret')
        User.objects.create_user(username='inactive', password='secret', is_staff=True, is_active=False)

    def test_rejected_credentials_are_generic(self):
        for username, password in [('', ''), ('staff', ''), ('', 'secret'), ('staff', 'wrong'), ('missing', 'secret'), ('customer', 'secret'), ('inactive', 'secret')]:
            with self.subTest(username=username, password=password):
                response = self.client.post('/adminpanel/login', {'username': username, 'password': password})
                self.assertContains(response, 'Invalid username or password.')
                self.assertRedirects(self.client.get('/adminpanel/'), '/adminpanel/login')

    def test_direct_requests_reject_flag_alone(self):
        session = self.client.session
        session['isStaff'] = True
        session.save()
        for path in ['/adminpanel/', '/adminpanel/product_new', '/adminpanel/product_new/P001', '/adminpanel/item_new', '/adminpanel/customer_new', '/adminpanel/customer_new/C001', '/adminpanel/order_new', '/adminpanel/order_new/O001', '/adminpanel/support', '/adminpanel/support/1']:
            for method in (self.client.get, self.client.post):
                with self.subTest(path=path, method=method.__name__):
                    self.assertRedirects(method(path), '/adminpanel/login')

    def test_session_rotation_and_revocation(self):
        session = self.client.session
        session['Cid'] = 'old'
        session.save()
        old_key = session.session_key
        self.client.post('/adminpanel/login', {'username': 'staff', 'password': 'secret'})
        self.assertNotEqual(old_key, self.client.session.session_key)
        self.assertNotIn('Cid', self.client.session)
        self.assertEqual(self.client.session['staff_user_id'], self.staff.pk)
        response = self.client.get('/adminpanel/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.staff.is_staff = False
        self.staff.save()
        self.assertRedirects(self.client.get('/adminpanel/'), '/adminpanel/login')
        self.staff.is_staff = True
        self.staff.is_active = False
        self.staff.save()
        self.assertRedirects(self.client.get('/adminpanel/'), '/adminpanel/login')

    def test_csrf_and_logout(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.get('/adminpanel/login')
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.post('/adminpanel/login', {'username': 'staff', 'password': 'secret'}).status_code, 403)
        self.assertEqual(client.post('/adminpanel/login', {'username': 'staff', 'password': 'secret', 'csrfmiddlewaretoken': 'invalid'}).status_code, 403)
        client.post('/adminpanel/login', {'username': 'staff', 'password': 'secret', 'csrfmiddlewaretoken': token})
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.get('/adminpanel/logout').status_code, 405)
        self.assertEqual(client.post('/adminpanel/logout').status_code, 403)
        self.assertEqual(client.post('/adminpanel/product_new', {'csrfmiddlewaretoken': 'invalid'}).status_code, 403)
        self.assertEqual(client.post('/adminpanel/logout', {'csrfmiddlewaretoken': token}).status_code, 200)
        self.assertRedirects(client.get('/adminpanel/'), '/adminpanel/login')
        self.assertRedirects(client.get('/adminpanel/'), '/adminpanel/login')

    def test_customer_login_replaces_staff_session_and_logout(self):
        from .models import Customer
        Customer.objects.create(Cid='C001', Cname='Customer', Caddress='', Chouseholdsize=1, Cmealsperweek=0, Cuser=self.customer)
        self.client.post('/adminpanel/login', {'username': 'staff', 'password': 'secret'})
        old_key = self.client.session.session_key
        self.client.post('/store/login', {'username': 'customer', 'password': 'secret'})
        self.assertNotEqual(old_key, self.client.session.session_key)
        self.assertEqual(self.client.session['Cid'], 'C001')
        self.assertRedirects(self.client.get('/adminpanel/'), '/adminpanel/login')
        self.assertEqual(self.client.get('/store/logout').status_code, 405)
        self.assertEqual(self.client.post('/store/logout').status_code, 200)
        self.assertRedirects(self.client.get('/store/pantry'), '/store/login')
