import re
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone

from adminpanel.models import (
    Category,
    Customer,
    GroupMember,
    GroupPurchase,
    Item,
    Orders,
    Product,
    Review,
    SavedItem,
    StockNotice,
    Subscription,
    SupportTicket,
)


def extract_csrf_token(response):
    match = re.search(
        r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)["\']',
        response.content.decode('utf-8'),
    )
    if not match:
        raise AssertionError('CSRF token not found in HTML response.')
    return match.group(1)


class StorefrontAuditGapTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(Ccode='FR', Cname='Fruit')
        self.today = timezone.localdate()

        self.u1 = User.objects.create_user(username='audit_u1', password='Password123!', email='u1@example.com')
        self.c1 = Customer.objects.create(
            Cid='CAUD1',
            Cname='Audit One',
            Caddress='10 Audit Way',
            Chouseholdsize=2,
            Cmealsperweek=7,
            Cuser=self.u1,
        )

        self.u2 = User.objects.create_user(username='audit_u2', password='Password123!', email='u2@example.com')
        self.c2 = Customer.objects.create(
            Cid='CAUD2',
            Cname='Audit Two',
            Caddress='20 Audit Way',
            Chouseholdsize=3,
            Cmealsperweek=10,
            Cuser=self.u2,
        )

        self.p_apple = Product.objects.create(
            Pid='PAUD1',
            Pname='Audit Apple',
            Pcategory=self.cat,
            Psize='4 pcs',
            Pprice=Decimal('4.50'),
            Pbulkquantity=5,
            Pbulkprice=Decimal('3.80'),
            Plowstock=2,
            Pexpirydays=2,
            Pactive=True,
        )
        self.p_inactive = Product.objects.create(
            Pid='PAUD2',
            Pname='Hidden Pear',
            Pcategory=self.cat,
            Psize='2 pcs',
            Pprice=Decimal('3.00'),
            Plowstock=2,
            Pexpirydays=2,
            Pactive=False,
        )

        for _ in range(4):
            Item.objects.create(
                Iproduct=self.p_apple,
                Ireceived=self.today,
                Iexpiry=self.today + timedelta(days=10),
                Istatus='available',
            )

    def test_sf01_valid_signup_and_retained_values_on_error(self):
        # Invalid signup retains entered values and rejects duplicate username
        bad_resp = self.client.post(
            '/store/signup',
            {
                'username': 'audit_u1',
                'password': 'Password123!',
                'email': 'dup@example.com',
                'Cname': 'Duplicate User',
                'Caddress': '99 Repeat Rd',
                'Chouseholdsize': '4',
                'Cmealsperweek': '12',
            },
        )
        self.assertEqual(bad_resp.status_code, 200)
        self.assertContains(bad_resp, 'Duplicate User')
        self.assertContains(bad_resp, '99 Repeat Rd')
        self.assertNotContains(bad_resp, 'Password123!')

        ok_resp = self.client.post(
            '/store/signup',
            {
                'username': 'audit_new',
                'password': 'Password123!',
                'email': 'new@example.com',
                'Cname': 'New Audit',
                'Caddress': '1 Fresh St',
                'Chouseholdsize': '2',
                'Cmealsperweek': '8',
            },
        )
        self.assertEqual(ok_resp.status_code, 200)
        self.assertContains(ok_resp, 'User created successfully!')
        user = User.objects.get(username='audit_new')
        cust = Customer.objects.get(Cuser=user)
        self.assertEqual(cust.Cname, 'New Audit')

    def test_sf02_sf03_login_and_csrf_post_logout(self):
        csrf_client = Client(enforce_csrf_checks=True)
        login_page = csrf_client.get('/store/login')
        token = extract_csrf_token(login_page)

        bad_login = csrf_client.post(
            '/store/login',
            {'username': 'audit_u1', 'password': 'wrong', 'csrfmiddlewaretoken': token},
        )
        self.assertEqual(bad_login.status_code, 200)
        self.assertContains(bad_login, 'Invalid username or password.')
        self.assertNotIn('Cid', csrf_client.session)

        ok_login = csrf_client.post(
            '/store/login',
            {'username': 'audit_u1', 'password': 'Password123!', 'csrfmiddlewaretoken': token},
        )
        self.assertRedirects(ok_login, '/store/')
        self.assertEqual(csrf_client.session['Cid'], self.c1.Cid)

        # GET logout is rejected and preserves session
        get_logout = csrf_client.get('/store/logout')
        self.assertEqual(get_logout.status_code, 405)
        self.assertEqual(csrf_client.session['Cid'], self.c1.Cid)

        # POST logout with CSRF clears session
        shop_page = csrf_client.get('/store/')
        logout_token = extract_csrf_token(shop_page)
        missing_token = csrf_client.post('/store/logout')
        self.assertEqual(missing_token.status_code, 403)
        self.assertEqual(csrf_client.session['Cid'], self.c1.Cid)

        post_logout = csrf_client.post(
            '/store/logout', {'csrfmiddlewaretoken': logout_token}, follow=True
        )
        self.assertRedirects(post_logout, '/store/login', fetch_redirect_response=False)
        self.assertContains(post_logout, 'You have logged out successfully.')
        self.assertNotIn('Cid', csrf_client.session)
        self.assertRedirects(csrf_client.get('/store/pantry'), '/store/login')
        self.assertRedirects(csrf_client.get('/store/profile'), '/store/login')

    def test_sf05_sf06_placeholders_empty_search_inactive_and_hidden_review(self):
        shop = self.client.get('/store/')
        self.assertContains(shop, 'No product photo')
        self.assertContains(shop, 'No reviews yet')

        empty_search = self.client.get('/store/', {'q': 'NonExistentItemXYZ'})
        self.assertContains(empty_search, 'No products found')

        inactive_detail = self.client.get(f'/store/product/{self.p_inactive.Pid}')
        self.assertRedirects(inactive_detail, '/store/')

        # Hidden review (Rvisible=False) must not show on product page or affect public rating
        hidden_order = Orders.objects.create(
            Oid='OAUD_HID',
            Ocustomer=self.c2,
            Oaddress=self.c2.Caddress,
            Odate=self.today,
            Ostatus='delivered',
            Opayment='paid',
        )
        hidden_item = Item.objects.create(
            Iproduct=self.p_apple,
            Iorder=hidden_order,
            Ireceived=self.today,
            Istatus='delivered',
            Irating=1,
            Ipurchasedprice=Decimal('4.50'),
        )
        Review.objects.create(
            Rcustomer=self.c2,
            Rproduct=self.p_apple,
            Ritem=hidden_item,
            Rrating=1,
            Rtext='Hidden offensive text',
            Rdate=self.today,
            Rvisible=False,
        )
        detail = self.client.get(f'/store/product/{self.p_apple.Pid}')
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, 'Hidden offensive text')
        self.assertContains(detail, 'No ratings yet')

    def test_sf09_cart_remove_item(self):
        self.client.login(username='audit_u1', password='Password123!')
        s = self.client.session
        s['Cid'] = self.c1.Cid
        s['cart'] = {self.p_apple.Pid: 2}
        s.save()

        resp = self.client.post(f'/store/cart/{self.p_apple.Pid}', {'action': 'remove'})
        self.assertRedirects(resp, '/store/cart')
        self.assertEqual(self.client.session['cart'], {})
        cart_page = self.client.get('/store/cart')
        self.assertContains(cart_page, 'Your cart is empty')

    def test_sf11_order_ownership_and_legacy_missing_price(self):
        other_order = Orders.objects.create(
            Oid='OAUD_OTHER',
            Ocustomer=self.c2,
            Oaddress='Secret Address 99',
            Odate=self.today,
            Ostatus='placed',
            Opayment='paid',
        )
        legacy_order = Orders.objects.create(
            Oid='OAUD_LEG',
            Ocustomer=self.c1,
            Oaddress=self.c1.Caddress,
            Odate=self.today,
            Ostatus='delivered',
            Opayment='paid',
        )
        Item.objects.create(
            Iproduct=self.p_apple,
            Iorder=legacy_order,
            Ireceived=self.today,
            Istatus='delivered',
            Ipurchasedprice=None,
        )

        s = self.client.session
        s['Cid'] = self.c1.Cid
        s.save()

        blocked = self.client.get(f'/store/orders/{other_order.Oid}')
        self.assertEqual(blocked.status_code, 200)
        self.assertNotContains(blocked, 'Secret Address 99')

        own = self.client.get(f'/store/orders/{legacy_order.Oid}')
        self.assertEqual(own.status_code, 200)
        self.assertContains(own, 'Not recorded')

    def test_sf12_sf13_group_order_excluded_from_pantry_and_mark_expired(self):
        group_order = Orders.objects.create(
            Oid='OAUD_GRP',
            Ocustomer=self.c1,
            Oaddress=self.c1.Caddress,
            Odate=self.today,
            Ostatus='delivered',
            Opayment='paid',
        )
        GroupPurchase.objects.create(
            Gname='Group Pantry Test',
            Gaddress=self.c1.Caddress,
            Gcode='code_pantry_test',
            Gcreated=self.today,
            Gorganiser=self.c1,
            Gstatus='ordered',
            Gorder=group_order,
        )
        Item.objects.create(
            Iproduct=self.p_apple,
            Iorder=group_order,
            Ireceived=self.today,
            Istatus='delivered',
            Iexpiry=self.today + timedelta(days=1),
        )

        personal_order = Orders.objects.create(
            Oid='OAUD_PER',
            Ocustomer=self.c1,
            Oaddress=self.c1.Caddress,
            Odate=self.today,
            Ostatus='delivered',
            Opayment='paid',
        )
        personal_item = Item.objects.create(
            Iproduct=self.p_apple,
            Iorder=personal_order,
            Ireceived=self.today,
            Istatus='delivered',
            Iexpiry=self.today - timedelta(days=1),
        )

        s = self.client.session
        s['Cid'] = self.c1.Cid
        s.save()

        pantry_page = self.client.get('/store/pantry')
        self.assertEqual(pantry_page.context['expiring_soon'], 1)
        self.assertEqual(pantry_page.context['past_expiry'], 1)
        self.assertEqual(len(pantry_page.context['pantry_items']), 1)

        resp = self.client.post(f'/store/pantry/{personal_item.pk}', {'action': 'expired'})
        self.assertRedirects(resp, '/store/pantry')
        personal_item.refresh_from_db()
        self.assertEqual(personal_item.Istatus, 'expired')
        self.assertEqual(personal_item.Ifinished, self.today)

    @patch('store.views.get_restock_suggestions')
    def test_sf15_restock_excludes_active_sub_and_empty_messages(self, mock_suggestions):
        s = self.client.session
        s['Cid'] = self.c1.Cid
        s.save()

        # No purchase history empty message
        mock_suggestions.return_value = []
        resp_no_hist = self.client.get('/store/restock/')
        self.assertContains(resp_no_hist, 'No qualifying purchase history is available for personalised suggestions.')

        # Purchase history exists, but only product is actively subscribed -> filtered out
        hist_order = Orders.objects.create(
            Oid='OAUD_HIS',
            Ocustomer=self.c1,
            Oaddress=self.c1.Caddress,
            Odate=self.today - timedelta(days=10),
            Ostatus='delivered',
            Opayment='paid',
        )
        Item.objects.create(
            Iproduct=self.p_apple,
            Iorder=hist_order,
            Ireceived=self.today - timedelta(days=10),
            Istatus='delivered',
        )
        Subscription.objects.create(
            Scustomer=self.c1,
            Sproduct=self.p_apple,
            Squantity=1,
            Sinterval=7,
            Snextdate=self.today + timedelta(days=3),
            Sceiling=Decimal('10.00'),
            Screated=self.today,
            Sstatus='active',
        )
        mock_suggestions.return_value = [
            {
                'product_id': self.p_apple.Pid,
                'product_name': self.p_apple.Pname,
                'restock_date': (self.today + timedelta(days=1)).isoformat(),
                'status': 'INITIAL',
            }
        ]
        resp_due_empty = self.client.get('/store/restock/')
        self.assertContains(resp_due_empty, 'No products are currently due for restocking.')


class StorefrontIntegratedJourneysTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(Ccode='VG', Cname='Vegetables')
        self.today = timezone.localdate()
        self.p1 = Product.objects.create(
            Pid='PJ1',
            Pname='Journey Kale',
            Pcategory=self.cat,
            Psize='200g',
            Pprice=Decimal('3.50'),
            Pbulkquantity=4,
            Pbulkprice=Decimal('2.80'),
            Plowstock=2,
            Pexpirydays=2,
            Pactive=True,
        )
        self.p2 = Product.objects.create(
            Pid='PJ2',
            Pname='Journey Carrot',
            Pcategory=self.cat,
            Psize='500g',
            Pprice=Decimal('2.00'),
            Plowstock=2,
            Pexpirydays=2,
            Pactive=True,
        )
        for _ in range(6):
            Item.objects.create(
                Iproduct=self.p1,
                Ireceived=self.today,
                Iexpiry=self.today + timedelta(days=8),
                Istatus='available',
            )
        for _ in range(3):
            Item.objects.create(
                Iproduct=self.p2,
                Ireceived=self.today,
                Iexpiry=self.today + timedelta(days=8),
                Istatus='available',
            )

    def _login_csrf(self, client, username, password):
        page = client.get('/store/login')
        token = extract_csrf_token(page)
        return client.post(
            '/store/login',
            {'username': username, 'password': password, 'csrfmiddlewaretoken': token},
        )

    def test_journey_1_account_lifecycle_with_csrf(self):
        c = Client(enforce_csrf_checks=True)
        signup_page = c.get('/store/signup')
        token = extract_csrf_token(signup_page)
        resp = c.post(
            '/store/signup',
            {
                'csrfmiddlewaretoken': token,
                'username': 'j1_user',
                'password': 'OldPassword123!',
                'email': 'j1@example.com',
                'Cname': 'Journey One',
                'Caddress': '1 First Ave',
                'Chouseholdsize': '2',
                'Cmealsperweek': '6',
            },
        )
        self.assertContains(resp, 'User created successfully!')

        self.assertRedirects(self._login_csrf(c, 'j1_user', 'OldPassword123!'), '/store/')

        prof_page = c.get('/store/profile')
        prof_token = extract_csrf_token(prof_page)
        self.assertRedirects(
            c.post(
                '/store/profile',
                {
                    'csrfmiddlewaretoken': prof_token,
                    'Cname': 'Journey Updated',
                    'email': 'j1_new@example.com',
                    'Caddress': '2 Second Ave',
                    'Chouseholdsize': '3',
                    'Cmealsperweek': '10',
                },
            ),
            '/store/profile',
        )
        cust = Customer.objects.get(Cuser__username='j1_user')
        self.assertEqual(cust.Caddress, '2 Second Ave')

        pw_page = c.get('/store/profile/password')
        pw_token = extract_csrf_token(pw_page)
        self.assertRedirects(
            c.post(
                '/store/profile/password',
                {
                    'csrfmiddlewaretoken': pw_token,
                    'current': 'OldPassword123!',
                    'new': 'NewPassword123!',
                    'confirm': 'NewPassword123!',
                },
            ),
            '/store/profile',
        )

        shop_page = c.get('/store/')
        logout_token = extract_csrf_token(shop_page)
        self.assertRedirects(
            c.post('/store/logout', {'csrfmiddlewaretoken': logout_token}),
            '/store/login',
        )
        self.assertRedirects(self._login_csrf(c, 'j1_user', 'NewPassword123!'), '/store/')

    def test_journey_2_browse_cart_checkout_filter_and_cancel(self):
        user = User.objects.create_user(username='j2_user', password='Password123!')
        cust = Customer.objects.create(
            Cid='CJ2', Cname='Journey Two', Caddress='20 Basket St', Chouseholdsize=2, Cmealsperweek=5, Cuser=user
        )
        c = Client(enforce_csrf_checks=True)
        self._login_csrf(c, 'j2_user', 'Password123!')

        shop = c.get('/store/', {'q': 'Kale', 'category': 'VG', 'sort': 'price_asc'})
        self.assertContains(shop, 'Journey Kale')
        self.assertNotContains(shop, 'Journey Carrot')

        detail = c.get(f'/store/product/{self.p1.Pid}')
        token = extract_csrf_token(detail)
        self.assertRedirects(
            c.post(f'/store/cart/{self.p1.Pid}', {'quantity': '1', 'csrfmiddlewaretoken': token}),
            '/store/cart',
        )
        token = extract_csrf_token(c.get(f'/store/product/{self.p2.Pid}'))
        self.assertRedirects(
            c.post(f'/store/cart/{self.p2.Pid}', {'quantity': '1', 'csrfmiddlewaretoken': token}),
            '/store/cart',
        )

        cart_page = c.get('/store/cart')
        cart_token = extract_csrf_token(cart_page)
        self.assertRedirects(
            c.post(
                f'/store/cart/{self.p1.Pid}',
                {'action': 'set', 'quantity': '2', 'csrfmiddlewaretoken': cart_token},
            ),
            '/store/cart',
        )
        cart_token = extract_csrf_token(c.get('/store/cart'))
        self.assertRedirects(
            c.post(
                f'/store/cart/{self.p2.Pid}',
                {'action': 'remove', 'csrfmiddlewaretoken': cart_token},
            ),
            '/store/cart',
        )
        self.assertEqual(c.session['cart'], {self.p1.Pid: 2})

        checkout_page = c.get('/store/checkout')
        chk_token = extract_csrf_token(checkout_page)
        placed = c.post(
            '/store/checkout',
            {'Oaddress': '25 Checkout Ln', 'csrfmiddlewaretoken': chk_token},
        )
        self.assertEqual(placed.status_code, 200)
        self.assertContains(placed, 'placed successfully!')
        order = Orders.objects.get(Ocustomer=cust)
        self.assertEqual(order.Ostatus, 'placed')
        self.assertEqual(Item.objects.filter(Iproduct=self.p1, Istatus='available').count(), 4)

        filtered = c.get('/store/orders', {'status': 'placed'})
        self.assertContains(filtered, order.Oid)

        order_detail = c.get(f'/store/orders/{order.Oid}')
        ord_token = extract_csrf_token(order_detail)
        cancelled = c.post(
            f'/store/orders/{order.Oid}',
            {'action': 'cancel', 'csrfmiddlewaretoken': ord_token},
        )
        self.assertEqual(cancelled.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.Ostatus, 'cancelled')
        self.assertEqual(order.Opayment, 'refunded')
        self.assertEqual(Item.objects.filter(Iproduct=self.p1, Istatus='available').count(), 6)

    def test_journey_3_pantry_support_review_and_reorder(self):
        user = User.objects.create_user(username='j3_user', password='Password123!')
        cust = Customer.objects.create(
            Cid='CJ3', Cname='Journey Three', Caddress='30 Pantry Rd', Chouseholdsize=2, Cmealsperweek=7, Cuser=user
        )
        order = Orders.objects.create(
            Oid='OJ3',
            Ocustomer=cust,
            Oaddress=cust.Caddress,
            Odate=self.today - timedelta(days=3),
            Ostatus='delivered',
            Opayment='paid',
        )
        item = Item.objects.create(
            Iproduct=self.p1,
            Iorder=order,
            Ireceived=self.today - timedelta(days=3),
            Istatus='delivered',
            Iexpiry=self.today + timedelta(days=2),
            Ipurchasedprice=Decimal('3.50'),
        )

        c = Client(enforce_csrf_checks=True)
        self._login_csrf(c, 'j3_user', 'Password123!')

        pantry = c.get('/store/pantry')
        self.assertEqual(pantry.context['expiring_soon'], 1)
        self.assertEqual(pantry.context['past_expiry'], 0)
        token = extract_csrf_token(pantry)

        c.post(f'/store/pantry/{item.pk}', {'action': 'report', 'Tmessage': 'Bruised leaves', 'csrfmiddlewaretoken': token})
        self.assertTrue(SupportTicket.objects.filter(Torder=order, Tmessage='Bruised leaves').exists())

        token = extract_csrf_token(c.get('/store/pantry'))
        c.post(f'/store/pantry/{item.pk}', {'action': 'used', 'csrfmiddlewaretoken': token})
        item.refresh_from_db()
        self.assertEqual(item.Istatus, 'used')

        ord_page = c.get(f'/store/orders/{order.Oid}')
        ord_token = extract_csrf_token(ord_page)
        c.post(
            f'/store/orders/{order.Oid}',
            {'Tsubject': 'Follow up', 'Tmessage': 'Thanks for checking', 'csrfmiddlewaretoken': ord_token},
        )
        self.assertTrue(SupportTicket.objects.filter(Torder=order, Tsubject='Follow up').exists())

        prod_page = c.get(f'/store/product/{self.p1.Pid}')
        rev_token = extract_csrf_token(prod_page)
        c.post(
            f'/store/product/{self.p1.Pid}',
            {'Rrating': '5', 'Rtext': 'Fresh and crisp!', 'csrfmiddlewaretoken': rev_token},
        )
        self.assertTrue(Review.objects.filter(Rcustomer=cust, Rproduct=self.p1, Rrating=5).exists())

        ord_token2 = extract_csrf_token(c.get(f'/store/orders/{order.Oid}'))
        self.assertRedirects(
            c.post(f'/store/orders/{order.Oid}', {'action': 'reorder', 'csrfmiddlewaretoken': ord_token2}),
            '/store/cart',
        )
        self.assertEqual(c.session['cart'], {self.p1.Pid: 1})

    def test_journey_4_restock_and_subscription_lifecycle(self):
        user = User.objects.create_user(username='j4_user', password='Password123!')
        cust = Customer.objects.create(
            Cid='CJ4', Cname='Journey Four', Caddress='40 Sub St', Chouseholdsize=2, Cmealsperweek=7, Cuser=user
        )
        hist = Orders.objects.create(
            Oid='OJ4_H',
            Ocustomer=cust,
            Oaddress=cust.Caddress,
            Odate=self.today - timedelta(days=20),
            Ostatus='delivered',
            Opayment='paid',
        )
        Item.objects.create(Iproduct=self.p1, Iorder=hist, Ireceived=self.today - timedelta(days=20), Istatus='used', Ipurchasedprice=Decimal('3.50'))

        c = Client(enforce_csrf_checks=True)
        self._login_csrf(c, 'j4_user', 'Password123!')

        restock_page = c.get('/store/restock/')
        self.assertEqual(restock_page.status_code, 200)
        self.assertContains(restock_page, 'Journey Kale')

        new_sub_page = c.get(f'/store/subscriptions/new/{self.p1.Pid}')
        sub_token = extract_csrf_token(new_sub_page)
        start_date = self.today + timedelta(days=5)
        self.assertRedirects(
            c.post(
                f'/store/subscriptions/new/{self.p1.Pid}',
                {
                    'csrfmiddlewaretoken': sub_token,
                    'Squantity': '1',
                    'Sinterval': '7',
                    'Snextdate': start_date.isoformat(),
                    'Sceiling': '5.00',
                    'consent': 'on',
                },
            ),
            '/store/subscriptions',
        )
        plan = Subscription.objects.get(Scustomer=cust, Sproduct=self.p1)

        sub_token = extract_csrf_token(c.get('/store/subscriptions'))
        c.post(f'/store/subscriptions/{plan.pk}', {'action': 'skip', 'csrfmiddlewaretoken': sub_token})
        plan.refresh_from_db()
        self.assertEqual(plan.Snextdate, start_date + timedelta(days=7))

        edit_token = extract_csrf_token(c.get(f'/store/subscriptions/{plan.pk}/edit'))
        c.post(
            f'/store/subscriptions/{plan.pk}/edit',
            {'Squantity': '2', 'Sinterval': '14', 'Sceiling': '8.00', 'consent': 'on', 'csrfmiddlewaretoken': edit_token},
        )
        plan.refresh_from_db()
        self.assertEqual(plan.Squantity, 2)
        self.assertEqual(plan.Sinterval, 14)

        sub_token = extract_csrf_token(c.get('/store/subscriptions'))
        c.post(f'/store/subscriptions/{plan.pk}', {'action': 'pause', 'csrfmiddlewaretoken': sub_token})
        plan.refresh_from_db()
        self.assertEqual(plan.Sstatus, 'paused')

        sub_token = extract_csrf_token(c.get('/store/subscriptions'))
        resume_date = self.today + timedelta(days=10)
        c.post(
            f'/store/subscriptions/{plan.pk}',
            {'action': 'resume', 'Snextdate': resume_date.isoformat(), 'csrfmiddlewaretoken': sub_token},
        )
        plan.refresh_from_db()
        self.assertEqual(plan.Sstatus, 'active')
        self.assertEqual(plan.Snextdate, resume_date)

        sub_token = extract_csrf_token(c.get('/store/subscriptions'))
        c.post(f'/store/subscriptions/{plan.pk}', {'action': 'cancel', 'csrfmiddlewaretoken': sub_token})
        plan.refresh_from_db()
        self.assertEqual(plan.Sstatus, 'cancelled')

    def test_journey_5_group_purchase_end_to_end(self):
        u_org = User.objects.create_user(username='j5_org', password='Password123!')
        c_org = Customer.objects.create(
            Cid='CJ5O', Cname='Organiser', Caddress='50 Group Way', Chouseholdsize=2, Cmealsperweek=7, Cuser=u_org
        )
        u_mem = User.objects.create_user(username='j5_mem', password='Password123!')
        c_mem = Customer.objects.create(
            Cid='CJ5M', Cname='Member', Caddress='51 Member Way', Chouseholdsize=2, Cmealsperweek=7, Cuser=u_mem
        )

        org_client = Client(enforce_csrf_checks=True)
        mem_client = Client(enforce_csrf_checks=True)
        self._login_csrf(org_client, 'j5_org', 'Password123!')
        self._login_csrf(mem_client, 'j5_mem', 'Password123!')

        g_token = extract_csrf_token(org_client.get('/store/groups'))
        org_client.post(
            '/store/groups',
            {'Gname': 'Sunday Kale Pool', 'Gaddress': '50 Group Way', 'csrfmiddlewaretoken': g_token},
        )
        group = GroupPurchase.objects.get(Gorganiser=c_org)

        join_token = extract_csrf_token(mem_client.get(f'/store/groups/join/{group.Gcode}'))
        mem_client.post(f'/store/groups/join/{group.Gcode}', {'csrfmiddlewaretoken': join_token})

        det_org = extract_csrf_token(org_client.get(f'/store/groups/{group.pk}'))
        org_client.post(
            f'/store/groups/{group.pk}',
            {'action': 'line', 'Pid': self.p1.Pid, 'quantity': '2', 'csrfmiddlewaretoken': det_org},
        )
        det_mem = extract_csrf_token(mem_client.get(f'/store/groups/{group.pk}'))
        mem_client.post(
            f'/store/groups/{group.pk}',
            {'action': 'line', 'Pid': self.p1.Pid, 'quantity': '2', 'csrfmiddlewaretoken': det_mem},
        )

        share_view = mem_client.get(f'/store/groups/{group.pk}')
        self.assertContains(share_view, '$5.60')
        self.assertContains(share_view, 'FruitBasket does not collect money between members')

        det_mem = extract_csrf_token(share_view)
        mem_client.post(f'/store/groups/{group.pk}', {'action': 'leave', 'csrfmiddlewaretoken': det_mem})
        self.assertFalse(GroupMember.objects.filter(GMgroup=group, GMcustomer=c_mem).exists())

        join_token2 = extract_csrf_token(mem_client.get(f'/store/groups/join/{group.Gcode}'))
        mem_client.post(f'/store/groups/join/{group.Gcode}', {'csrfmiddlewaretoken': join_token2})
        det_mem2 = extract_csrf_token(mem_client.get(f'/store/groups/{group.pk}'))
        mem_client.post(
            f'/store/groups/{group.pk}',
            {'action': 'line', 'Pid': self.p1.Pid, 'quantity': '2', 'csrfmiddlewaretoken': det_mem2},
        )

        det_org = extract_csrf_token(org_client.get(f'/store/groups/{group.pk}'))
        org_client.post(f'/store/groups/{group.pk}', {'action': 'lock', 'csrfmiddlewaretoken': det_org})
        det_org = extract_csrf_token(org_client.get(f'/store/groups/{group.pk}'))
        org_client.post(f'/store/groups/{group.pk}', {'action': 'checkout', 'csrfmiddlewaretoken': det_org})

        group.refresh_from_db()
        self.assertEqual(group.Gstatus, 'ordered')
        self.assertIsNotNone(group.Gorder)
        self.assertEqual(group.Gorder.order_items.count(), 4)

    def test_journey_6_saved_list_and_back_in_stock_notice(self):
        user = User.objects.create_user(username='j6_user', password='Password123!')
        cust = Customer.objects.create(
            Cid='CJ6', Cname='Journey Six', Caddress='60 List Ave', Chouseholdsize=1, Cmealsperweek=3, Cuser=user
        )
        p_out = Product.objects.create(
            Pid='PJ_OUT',
            Pname='Journey Mango',
            Pcategory=self.cat,
            Psize='2 pcs',
            Pprice=Decimal('5.00'),
            Plowstock=2,
            Pexpirydays=2,
            Pactive=True,
        )

        c = Client(enforce_csrf_checks=True)
        self._login_csrf(c, 'j6_user', 'Password123!')

        prod_page = c.get(f'/store/product/{self.p2.Pid}')
        c.post(f'/store/list/{self.p2.Pid}', {'csrfmiddlewaretoken': extract_csrf_token(prod_page)})
        self.assertTrue(SavedItem.objects.filter(SVcustomer=cust, SVproduct=self.p2).exists())

        out_page = c.get(f'/store/product/{p_out.Pid}')
        c.post(f'/store/notify/{p_out.Pid}', {'csrfmiddlewaretoken': extract_csrf_token(out_page)})
        self.assertTrue(StockNotice.objects.filter(SNcustomer=cust, SNproduct=p_out).exists())

        Item.objects.create(
            Iproduct=p_out,
            Ireceived=self.today,
            Iexpiry=self.today + timedelta(days=6),
            Istatus='available',
        )
        shop = c.get('/store/')
        self.assertContains(shop, 'Back in stock:')
        self.assertContains(shop, 'Journey Mango')

        list_page = c.get('/store/list')
        self.assertContains(list_page, 'Journey Carrot')
        self.assertContains(list_page, 'Journey Mango')
        c.post(
            f'/store/list/{self.p2.Pid}',
            {'action': 'remove', 'csrfmiddlewaretoken': extract_csrf_token(list_page)},
        )
        list_page2 = c.get('/store/list')
        c.post(
            f'/store/notify/{p_out.Pid}',
            {'action': 'remove', 'csrfmiddlewaretoken': extract_csrf_token(list_page2)},
        )
        self.assertFalse(SavedItem.objects.filter(SVcustomer=cust, SVproduct=self.p2).exists())
        self.assertFalse(StockNotice.objects.filter(SNcustomer=cust, SNproduct=p_out).exists())
