from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from adminpanel.models import (
    Customer, GroupPurchase, Item, Orders, Product, SavedItem, StockNotice, Subscription, SubscriptionCycle, SupportTicket,
)
from store.ordering import generate_order_id
from store.views import generate_customer_id
from store.subscriptions import process_due_subscriptions


class CustomerEdgeCaseTests(TestCase):

    # Input validation and edge cases for the customer pages

    def setUp(self):
        self.today = timezone.localdate()
        self.customer = Customer.objects.create(
            Cid='CEDGE', Cname='Edge', Caddress='1 Edge Road', Chouseholdsize=2, Cmealsperweek=7,
            Cuser=User.objects.create_user(username='edge', password='password')
        )
        self.milk = Product.objects.create(Pid='EMILK', Pname='Edge Milk', Pcategory_id='dairy', Psize='1L', Pprice=3.0, Plowstock=0)
        for _ in range(3):
            Item.objects.create(Iproduct=self.milk, Ireceived=self.today, Iexpiry=self.today + timedelta(days=30))
        self.login()

    def login(self, cart=None):
        session = self.client.session
        session['Cid'] = self.customer.Cid
        session['cart'] = cart or {}
        session.save()

    def delivered_item(self):
        order = Orders.objects.create(Oid='OEDG1', Odate=self.today, Oaddress='x', Ostatus='delivered', Ocustomer=self.customer)
        item = Item.objects.filter(Iproduct=self.milk, Istatus='available').first()
        item.Iorder = order
        item.Istatus = 'delivered'
        item.save()
        return order, item

    # Checkout address

    def test_blank_or_too_long_address_places_no_order(self):
        for address in ['', '    ', 'x' * 256]:
            self.login({'EMILK': 1})
            response = self.client.post('/store/checkout', {'Oaddress': address})
            self.assertEqual(response.context['status_type'], 'error')
        self.assertEqual(Orders.objects.count(), 0)
        self.client.post('/store/checkout', {'Oaddress': '  2 Real Road  '})
        self.assertEqual(Orders.objects.get().Oaddress, '2 Real Road')

    # Inactive products

    def test_deactivated_product_in_cart_cannot_be_bought(self):
        self.login({'EMILK': 1})
        Product.objects.filter(pk='EMILK').update(Pactive=False)
        response = self.client.post('/store/checkout', {'Oaddress': '1 Edge Road'})
        self.assertIn('no longer available', response.context['status_message'])
        self.assertEqual(Orders.objects.count(), 0)
        self.client.post('/store/cart/EMILK')
        self.assertEqual(self.client.session['cart'], {'EMILK': 1})

    def test_subscription_cycle_fails_when_product_deactivated(self):
        Subscription.objects.create(
            Scustomer=self.customer, Sproduct=self.milk, Squantity=1, Sinterval=7,
            Snextdate=self.today, Sceiling=10, Screated=self.today
        )
        Product.objects.filter(pk='EMILK').update(Pactive=False)
        cycle = process_due_subscriptions(self.today)[0]
        self.assertEqual((cycle.SCresult, Orders.objects.count()), ('failed', 0))

    # Cart quantities at the boundary

    def test_cart_quantity_boundaries(self):
        self.client.post('/store/cart/EMILK', {'quantity': 3})
        self.assertEqual(self.client.session['cart'], {'EMILK': 3})
        for bad in ['4', '1.5', '1e3', ' ', '99999999999999999999']:
            self.client.post('/store/cart/EMILK', {'action': 'set', 'quantity': bad})
            self.assertEqual(self.client.session['cart'], {'EMILK': 3})
        self.client.post('/store/cart/NOPE', {'quantity': 1})
        self.assertNotIn('NOPE', self.client.session['cart'])

    # Support tickets

    def test_support_ticket_length_limits(self):
        order, item = self.delivered_item()
        self.client.post(f'/store/orders/{order.Oid}', {'Tsubject': 's' * 201, 'Tmessage': 'm'})
        self.client.post(f'/store/orders/{order.Oid}', {'Tsubject': 's', 'Tmessage': 'm' * 2001})
        self.client.post(f'/store/orders/{order.Oid}', {'Tsubject': '   ', 'Tmessage': 'm'})
        self.client.post(f'/store/pantry/{item.pk}', {'action': 'report', 'Tmessage': 'm' * 2001})
        self.assertEqual(SupportTicket.objects.count(), 0)
        self.client.post(f'/store/orders/{order.Oid}', {'Tsubject': 's' * 200, 'Tmessage': 'm' * 2000})
        self.assertEqual(SupportTicket.objects.count(), 1)

    def test_text_is_escaped(self):
        order, item = self.delivered_item()
        self.client.post(f'/store/orders/{order.Oid}', {'Tsubject': '<script>x</script>', 'Tmessage': '<b>hi</b>'})
        response = self.client.get(f'/store/orders/{order.Oid}')
        self.assertNotContains(response, '<script>x</script>')
        self.assertContains(response, '&lt;script&gt;')

    # Bad IDs in the address

    def test_bad_ids_do_not_crash(self):
        for url in ['/store/pantry/abc', '/store/pantry/999999', '/store/orders/NOPE', '/store/product/NOPE',
                    '/store/subscriptions/new/NOPE', '/store/groups/999999', '/store/groups/join/NOPE']:
            for method in (self.client.get, self.client.post):
                self.assertLess(method(url).status_code, 500, url)

    # Subscription dates and limits

    def test_subscription_date_and_ceiling_limits(self):
        url = '/store/subscriptions/new/EMILK'
        base = {'Squantity': 1, 'Sinterval': 7, 'Sceiling': '5', 'consent': 'on'}
        for date in [self.today, self.today + timedelta(days=366), '9999-12-31', 'not-a-date']:
            self.client.post(url, dict(base, Snextdate=date))
        for ceiling in ['10001', 'inf', 'nan', '-1', '0']:
            self.client.post(url, dict(base, Snextdate=self.today + timedelta(days=1), Sceiling=ceiling))
        self.assertEqual(Subscription.objects.count(), 0)
        self.client.post(url, dict(base, Snextdate=self.today + timedelta(days=365), Sceiling='10000'))
        plan = Subscription.objects.get()

        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'pause'})
        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'resume', 'Snextdate': '9999-12-31'})
        plan.refresh_from_db()
        self.assertEqual(plan.Sstatus, 'paused')
        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'nonsense'})
        plan.refresh_from_db()
        self.assertEqual(plan.Sstatus, 'paused')

    def test_process_command_twice_on_the_same_day_orders_once(self):
        Subscription.objects.create(
            Scustomer=self.customer, Sproduct=self.milk, Squantity=1, Sinterval=7,
            Snextdate=self.today - timedelta(days=20), Sceiling=10, Screated=self.today
        )
        process_due_subscriptions(self.today)
        process_due_subscriptions(self.today)
        self.assertEqual((Orders.objects.count(), SubscriptionCycle.objects.count()), (1, 1))
        self.assertEqual(Subscription.objects.get().Snextdate, self.today + timedelta(days=7))

    # Group purchases

    def test_group_validation_and_reopen_after_failed_checkout(self):
        self.client.post('/store/groups', {'Gname': '   ', 'Gaddress': 'x'})
        self.client.post('/store/groups', {'Gname': 'g' * 101, 'Gaddress': 'x'})
        self.assertEqual(GroupPurchase.objects.count(), 0)
        self.client.post('/store/groups', {'Gname': 'Block', 'Gaddress': '5 Shared Road'})
        group = GroupPurchase.objects.get()
        url = f'/store/groups/{group.pk}'
        for quantity in ['-1', '501', 'abc', '']:
            self.client.post(url, {'action': 'line', 'Pid': 'EMILK', 'quantity': quantity})
        self.assertFalse(group.group_lines.exists())
        self.client.post(url, {'action': 'line', 'Pid': 'EMILK', 'quantity': 2})
        self.client.post(url, {'action': 'lock'})
        Product.objects.filter(pk='EMILK').update(Pactive=False)
        self.client.post(url, {'action': 'checkout'})
        group.refresh_from_db()
        self.assertEqual((group.Gstatus, Orders.objects.count()), ('locked', 0))
        self.client.post(url, {'action': 'unlock'})
        group.refresh_from_db()
        self.assertEqual(group.Gstatus, 'open')
        self.client.post(url, {'action': 'line', 'Pid': 'EMILK', 'quantity': 0})
        self.assertFalse(group.group_lines.exists())

    # Session edge cases

    def test_deleted_customer_is_logged_out(self):
        for url in ['/store/profile', '/store/groups', '/store/subscriptions', '/store/list', '/store/subscriptions/new/EMILK']:
            session = self.client.session
            session['Cid'] = 'CGONE'
            session.save()
            self.assertRedirects(self.client.get(url), '/store/login', fetch_redirect_response=False)
            self.assertNotIn('Cid', self.client.session)

    def test_profile_and_review_boundaries(self):
        base = {'Cname': 'Edge', 'email': '', 'Caddress': '1 Edge Road', 'Chouseholdsize': 2, 'Cmealsperweek': 7}
        for change in [{'Cname': '   '}, {'Caddress': 'a' * 256}, {'Chouseholdsize': 21}, {'Cmealsperweek': -1}, {'email': 'not-an-email'}]:
            self.client.post('/store/profile', dict(base, **change))
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.Cname, self.customer.Chouseholdsize), ('Edge', 2))

        self.delivered_item()
        for rating, text in [('0', ''), ('6', ''), ('abc', ''), ('5', 't' * 1001)]:
            self.client.post('/store/product/EMILK', {'Rrating': rating, 'Rtext': text})
        self.assertFalse(self.milk.product_reviews.exists())

    # SF01 signup

    def signup(self, **changes):
        data = {'username': 'new_user', 'password': 'Str0ngPass!x', 'email': 'new@example.com', 'Cname': 'New User',
                'Caddress': '3 New Road', 'Chouseholdsize': '2', 'Cmealsperweek': '5'}
        data.update(changes)
        return self.client.post('/store/signup', data)

    def test_signup_rejects_bad_input_without_creating_anything(self):
        self.client.session.flush()
        bad = [
            {'username': ''}, {'username': 'EDGE'}, {'username': 'bad name!'}, {'username': 'x' * 151},
            {'password': ''}, {'password': 'short'}, {'password': '12345678'}, {'password': 'new_user1'},
            {'email': ''}, {'email': 'not-an-email'},
            {'Cname': '   '}, {'Caddress': ''}, {'Caddress': 'a' * 256},
            {'Chouseholdsize': 'abc'}, {'Chouseholdsize': '0'}, {'Chouseholdsize': '21'}, {'Cmealsperweek': '-1'}, {'Cmealsperweek': '1.5'},
        ]
        for change in bad:
            response = self.signup(**change)
            self.assertEqual(response.status_code, 200, change)
            self.assertTrue(response.context['errors'], change)
        self.assertEqual(self.client.post('/store/signup', {}).status_code, 200)
        self.assertEqual((User.objects.count(), Customer.objects.count()), (1, 1))

        response = self.signup()
        customer = Customer.objects.get(Cuser__username='new_user')
        self.assertEqual((customer.Chouseholdsize, customer.Cuser.is_staff), (2, False))
        self.assertTrue(customer.Cuser.check_password('Str0ngPass!x'))
        self.assertTrue(self.signup().context['errors'])
        self.assertEqual(User.objects.filter(username='new_user').count(), 1)

    def test_ids_skip_numbers_already_used(self):
        # A deleted record must not make the next new ID clash with an existing one
        Customer.objects.filter(pk='CEDGE').update(Cid='C0002')
        self.assertEqual(generate_customer_id(), '0003')
        Orders.objects.create(Oid='O00001', Odate=self.today, Oaddress='x', Ocustomer_id='C0002')
        Orders.objects.create(Oid='O00003', Odate=self.today, Oaddress='x', Ocustomer_id='C0002')
        Orders.objects.filter(pk='O00001').delete()
        self.assertEqual(generate_order_id(), '00002')
        Orders.objects.create(Oid='O00002', Odate=self.today, Oaddress='x', Ocustomer_id='C0002')
        self.assertEqual(generate_order_id(), '00004')

    # SF28 / SF29

    def test_list_and_notice_only_for_sensible_products(self):
        Product.objects.create(Pid='EOLD', Pname='Old', Pcategory_id='dairy', Psize='1', Pprice=1, Plowstock=0, Pactive=False)
        Product.objects.create(Pid='EOUT', Pname='Out', Pcategory_id='dairy', Psize='1', Pprice=1, Plowstock=0)
        self.client.post('/store/list/EOLD')
        self.client.post('/store/notify/EOLD')
        self.client.post('/store/notify/EMILK')
        self.assertEqual((SavedItem.objects.count(), StockNotice.objects.count()), (0, 0))
        self.client.post('/store/notify/EOUT')
        self.client.post('/store/list/EMILK')
        self.assertEqual((SavedItem.objects.count(), StockNotice.objects.count()), (1, 1))

    # Methods and CSRF

    def test_changes_need_post_with_csrf(self):
        for url in ['/store/list/EMILK', '/store/notify/EMILK', '/store/logout']:
            self.assertEqual(self.client.get(url).status_code, 405, url)
        strict = self.client_class(enforce_csrf_checks=True)
        session = strict.session
        session['Cid'] = 'CEDGE'
        session.save()
        for url in ['/store/cart/EMILK', '/store/checkout', '/store/profile', '/store/groups', '/store/list/EMILK']:
            self.assertEqual(strict.post(url, {'Oaddress': 'x'}).status_code, 403, url)
