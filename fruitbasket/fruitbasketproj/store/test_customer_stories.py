from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from adminpanel.models import (
    Customer, GroupLine, GroupMember, GroupPurchase, Item, Orders, Product, Review, Subscription, SubscriptionCycle,
)
from store.subscriptions import process_due_subscriptions


class CustomerStoryTests(TestCase):

    def setUp(self):
        self.today = timezone.localdate()
        self.user = User.objects.create_user(username='story_a', password='password')
        self.customer = Customer.objects.create(
            Cid='CSTA', Cname='Story A', Caddress='1 Test Road', Chouseholdsize=2, Cmealsperweek=10, Cuser=self.user
        )
        self.other_user = User.objects.create_user(username='story_b', password='password')
        self.other = Customer.objects.create(
            Cid='CSTB', Cname='Story B', Caddress='2 Test Road', Chouseholdsize=1, Cmealsperweek=5, Cuser=self.other_user
        )
        self.milk = Product.objects.create(
            Pid='TMILK', Pname='Test Milk', Pcategory_id='dairy', Psize='1L', Pprice=3.0, Plowstock=0,
            Pbulkquantity=4, Pbulkprice=2.5,
        )
        self.rice = Product.objects.create(Pid='TRICE', Pname='Test Rice', Pcategory_id='rice', Psize='5kg', Pprice=10.0, Plowstock=0)
        for _ in range(6):
            Item.objects.create(Iproduct=self.milk, Ireceived=self.today, Iexpiry=self.today + timedelta(days=30))
        for _ in range(2):
            Item.objects.create(Iproduct=self.rice, Ireceived=self.today)
        self.login(self.customer)

    def login(self, customer):
        session = self.client.session
        session['Cid'] = customer.Cid
        session['cart'] = {}
        session.save()

    def messages(self, response):
        return [str(message) for message in response.context['messages']]

    # SF04
    def test_profile_update_validates_and_keeps_old_order_address(self):
        self.user.email = 'original@example.com'
        self.user.save(update_fields=['email'])
        order = Orders.objects.create(Oid='OOLD1', Odate=self.today, Oaddress='1 Test Road', Ocustomer=self.customer)
        bad = self.client.post('/store/profile', {'Cname': 'A', 'Caddress': 'x', 'Chouseholdsize': 0, 'Cmealsperweek': 3, 'email': ''})
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, 'Enter an email address.')
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.Chouseholdsize, 2)
        self.assertEqual(self.customer.Cuser.email, 'original@example.com')
        invalid_email = self.client.post('/store/profile', {'Cname': 'A', 'Caddress': 'x', 'Chouseholdsize': 2, 'Cmealsperweek': 3, 'email': 'bad-email'})
        self.assertContains(invalid_email, 'Enter a valid email address.')
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.Cuser.email, 'original@example.com')
        self.client.post('/store/profile', {'Cname': 'New Name', 'Caddress': '9 New Road', 'Chouseholdsize': 4, 'Cmealsperweek': 3, 'email': 'a@example.com'})
        self.customer.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual((self.customer.Caddress, self.customer.Chouseholdsize), ('9 New Road', 4))
        self.assertEqual(self.customer.Cuser.email, 'a@example.com')
        self.assertEqual(order.Oaddress, '1 Test Road')

    # SF05
    def test_search_by_name(self):
        response = self.client.get('/store/', {'q': 'milk'})
        self.assertContains(response, 'Test Milk')
        self.assertNotContains(response, 'Test Rice')
        self.assertContains(self.client.get('/store/', {'q': 'zzzz'}), 'No products match your search')

    # SF06
    def test_product_page(self):
        response = self.client.get('/store/product/TMILK')
        self.assertContains(response, '6 packs available')
        self.assertContains(response, 'Expiry date on the pack')
        self.assertEqual(self.client.get('/store/product/NOPE').status_code, 302)

    # SF07 / SF08
    def test_cart_quantities(self):
        self.client.post('/store/cart/TMILK', {'quantity': 3})
        self.assertEqual(self.client.session['cart'], {'TMILK': 3})
        self.client.post('/store/cart/TMILK', {'quantity': 4})
        self.assertEqual(self.client.session['cart'], {'TMILK': 3})
        self.client.post('/store/cart/TMILK', {'action': 'set', 'quantity': 5})
        self.assertEqual(self.client.session['cart'], {'TMILK': 5})
        for bad in ['0', '-2', 'abc', '7']:
            self.client.post('/store/cart/TMILK', {'action': 'set', 'quantity': bad})
            self.assertEqual(self.client.session['cart'], {'TMILK': 5})
        self.client.post('/store/cart/TMILK')
        self.assertEqual(self.client.session['cart'], {'TMILK': 6})

    # SF10 / SF25
    def test_checkout_then_cancel_releases_stock_once(self):
        self.client.post('/store/cart/TMILK', {'quantity': 2})
        self.client.post('/store/checkout', {'Oaddress': '1 Test Road'})
        order = Orders.objects.get(Ocustomer=self.customer)
        self.assertEqual((order.Ostatus, order.Opayment, order.order_items.count()), ('placed', 'paid', 2))
        self.assertEqual(self.client.post('/store/checkout', {'Oaddress': '1 Test Road'}).context['status_message'], 'Your cart is empty.')
        self.assertEqual(Orders.objects.count(), 1)

        self.login(self.other)
        self.client.post(f'/store/orders/{order.Oid}', {'action': 'cancel'})
        order.refresh_from_db()
        self.assertEqual(order.Ostatus, 'placed')

        self.login(self.customer)
        self.client.post(f'/store/orders/{order.Oid}', {'action': 'cancel'})
        self.client.post(f'/store/orders/{order.Oid}', {'action': 'cancel'})
        order.refresh_from_db()
        self.assertEqual((order.Ostatus, order.Opayment, order.order_items.count()), ('cancelled', 'refunded', 0))
        self.assertEqual(Item.objects.filter(Iproduct=self.milk, Istatus='available').count(), 6)

    def test_cannot_cancel_delivered_or_partly_used_order(self):
        order = Orders.objects.create(Oid='ODEL1', Odate=self.today, Oaddress='x', Ostatus='delivered', Ocustomer=self.customer)
        response = self.client.post(f'/store/orders/{order.Oid}', {'action': 'cancel'})
        self.assertContains(response, 'Only a placed order can be cancelled')
        placed = Orders.objects.create(Oid='OPLA1', Odate=self.today, Oaddress='x', Ocustomer=self.customer)
        Item.objects.filter(Iproduct=self.rice).update(Iorder=placed, Istatus='used')
        response = self.client.post(f'/store/orders/{placed.Oid}', {'action': 'cancel'})
        self.assertContains(response, 'already used or thrown away')
        placed.refresh_from_db()
        self.assertEqual(placed.Ostatus, 'placed')

    # SF14
    def test_pantry_counts_passed_dates_separately(self):
        order = Orders.objects.create(Oid='OPAN1', Odate=self.today, Oaddress='x', Ocustomer=self.customer, Ostatus='delivered')
        items = list(Item.objects.filter(Iproduct=self.milk)[:3])
        for item, days in zip(items, [-2, 1, 20]):
            item.Iexpiry = self.today + timedelta(days=days)
            item.Iorder = order
            item.Istatus = 'delivered'
            item.save()
        response = self.client.get('/store/pantry')
        self.assertEqual((response.context['expiring_soon'], response.context['past_expiry']), (2, 1))

    # SF24
    def test_review_needs_delivered_purchase_and_is_one_per_product(self):
        self.client.post('/store/product/TMILK', {'Rrating': 5, 'Rtext': 'Great'})
        self.assertEqual(Review.objects.count(), 0)
        order = Orders.objects.create(Oid='OREV1', Odate=self.today, Oaddress='x', Ostatus='delivered', Ocustomer=self.customer)
        item = Item.objects.filter(Iproduct=self.milk).first()
        item.Iorder = order
        item.Istatus = 'delivered'
        item.save()
        self.client.post('/store/product/TMILK', {'Rrating': 9, 'Rtext': 'bad rating'})
        self.assertEqual(Review.objects.count(), 0)
        self.client.post('/store/product/TMILK', {'Rrating': 5, 'Rtext': 'Great'})
        self.client.post('/store/product/TMILK', {'Rrating': 3, 'Rtext': '<b>Changed</b>'})
        review = Review.objects.get()
        self.assertEqual((review.Rrating, review.Ritem_id, review.Rcustomer_id), (3, item.pk, 'CSTA'))
        response = self.client.get('/store/product/TMILK')
        self.assertContains(response, '&lt;b&gt;Changed&lt;/b&gt;')
        review.Rvisible = False
        review.save()
        self.assertEqual(list(self.client.get('/store/product/TMILK').context['visible_reviews']), [])

    # SF16 - SF19, SF15
    def subscribe(self, **changes):
        data = {'Squantity': 2, 'Sinterval': 7, 'Snextdate': self.today + timedelta(days=1), 'Sceiling': '6.00', 'consent': 'on'}
        data.update(changes)
        return self.client.post('/store/subscriptions/new/TMILK', data)

    def test_subscription_needs_consent_future_date_and_ceiling(self):
        data = {'Squantity': 2, 'Sinterval': 7, 'Snextdate': self.today + timedelta(days=1), 'Sceiling': '6.00'}
        self.client.post('/store/subscriptions/new/TMILK', data)
        self.subscribe(Snextdate=self.today)
        self.subscribe(Sceiling='5.00')
        self.subscribe(Sinterval=10)
        self.assertEqual(Subscription.objects.count(), 0)
        self.assertContains(self.client.get('/store/subscriptions/new/TMILK'), 'Initial estimate')
        self.subscribe()
        self.subscribe()
        self.assertEqual(Subscription.objects.count(), 1)

    def test_subscription_cycle_pause_resume_cancel(self):
        self.subscribe()
        plan = Subscription.objects.get()
        self.assertEqual(process_due_subscriptions(self.today), [])

        due = self.today + timedelta(days=1)
        cycles = process_due_subscriptions(due)
        self.assertEqual(process_due_subscriptions(due), [])
        self.assertEqual((len(cycles), cycles[0].SCresult), (1, 'ordered'))
        order = cycles[0].SCorder
        self.assertEqual((order.Ocustomer_id, order.order_items.count(), order.Oaddress), ('CSTA', 2, '1 Test Road'))
        plan.refresh_from_db()
        self.assertEqual(plan.Snextdate, due + timedelta(days=7))

        # Another customer cannot pause it
        self.login(self.other)
        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'pause'})
        plan.refresh_from_db()
        self.assertEqual(plan.Sstatus, 'active')

        self.login(self.customer)
        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'pause'})
        self.assertEqual(process_due_subscriptions(due + timedelta(days=30)), [])
        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'resume', 'Snextdate': self.today})
        plan.refresh_from_db()
        self.assertEqual(plan.Sstatus, 'paused')
        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'resume', 'Snextdate': self.today + timedelta(days=3)})
        plan.refresh_from_db()
        self.assertEqual((plan.Sstatus, plan.Snextdate), ('active', self.today + timedelta(days=3)))

        # Cancelling one subscription order does not cancel the plan
        self.client.post(f'/store/orders/{order.Oid}', {'action': 'cancel'})
        plan.refresh_from_db()
        self.assertEqual(plan.Sstatus, 'active')

        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'cancel'})
        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'resume', 'Snextdate': self.today + timedelta(days=3)})
        plan.refresh_from_db()
        self.assertEqual(plan.Sstatus, 'cancelled')
        self.assertEqual(process_due_subscriptions(self.today + timedelta(days=90)), [])
        self.assertEqual(SubscriptionCycle.objects.count(), 1)

    def test_subscription_cycle_fails_without_order_when_price_or_stock_changes(self):
        self.subscribe()
        self.milk.Pprice = 4.0
        self.milk.Pbulkprice = None
        self.milk.Pbulkquantity = None
        self.milk.save()
        cycles = process_due_subscriptions(self.today + timedelta(days=1))
        self.assertEqual((cycles[0].SCresult, cycles[0].SCorder, Orders.objects.count()), ('failed', None, 0))
        self.assertIn('above the approved limit', cycles[0].SCnote)

    # SF20 - SF22, SF12
    def test_group_purchase_flow(self):
        self.client.post('/store/groups', {'Gname': 'Block 5', 'Gaddress': '5 Shared Road'})
        group = GroupPurchase.objects.get()
        self.assertTrue(GroupMember.objects.filter(GMgroup=group, GMcustomer=self.customer).exists())
        self.client.post(f'/store/groups/{group.pk}', {'action': 'line', 'Pid': 'TMILK', 'quantity': 2})

        # Not a member yet: cannot open or contribute
        self.login(self.other)
        self.assertEqual(self.client.get(f'/store/groups/{group.pk}').status_code, 302)
        self.client.post(f'/store/groups/{group.pk}', {'action': 'line', 'Pid': 'TMILK', 'quantity': 9})
        self.assertEqual(GroupLine.objects.count(), 1)
        self.assertEqual(self.client.get('/store/groups/join/wrong-code').status_code, 302)
        self.client.post(f'/store/groups/join/{group.Gcode}')
        self.client.post(f'/store/groups/{group.pk}', {'action': 'line', 'Pid': 'TMILK', 'quantity': 3})
        self.client.post(f'/store/groups/{group.pk}', {'action': 'line', 'Pid': 'TRICE', 'quantity': 1})
        self.client.post(f'/store/groups/{group.pk}', {'action': 'line', 'Pid': 'TRICE', 'quantity': 0})
        self.assertEqual(GroupLine.objects.filter(GLcustomer=self.other).count(), 1)
        self.assertEqual(Item.objects.filter(Istatus='available').count(), 8)

        # Only the organiser can lock or check out
        self.client.post(f'/store/groups/{group.pk}', {'action': 'lock'})
        self.client.post(f'/store/groups/{group.pk}', {'action': 'checkout'})
        group.refresh_from_db()
        self.assertEqual(group.Gstatus, 'open')

        self.login(self.customer)
        self.client.post(f'/store/groups/{group.pk}', {'action': 'checkout'})
        self.assertEqual(Orders.objects.count(), 0)
        self.client.post(f'/store/groups/{group.pk}', {'action': 'lock'})
        self.client.post(f'/store/groups/{group.pk}', {'action': 'line', 'Pid': 'TMILK', 'quantity': 1})
        self.assertEqual(GroupLine.objects.get(GLcustomer=self.customer).GLquantity, 2)
        response = self.client.get(f'/store/groups/{group.pk}')
        self.assertEqual(response.context['total'], 12.5)

        self.client.post(f'/store/groups/{group.pk}', {'action': 'checkout'})
        self.client.post(f'/store/groups/{group.pk}', {'action': 'checkout'})
        group.refresh_from_db()
        order = Orders.objects.get()
        self.assertEqual((group.Gstatus, group.Gorder, order.Ocustomer_id, order.Oaddress), ('ordered', order, 'CSTA', '5 Shared Road'))
        self.assertEqual(list(order.order_items.values_list('Ipurchasedprice', flat=True)), [2.5] * 5)

        # Group deliveries are not added to the organiser's pantry
        self.assertEqual(self.client.get('/store/pantry').context['pantry_items'], [])

    def test_group_checkout_shortage_allows_retry(self):
        self.client.post('/store/groups', {'Gname': 'Short', 'Gaddress': '5 Shared Road'})
        group = GroupPurchase.objects.get()
        self.client.post(f'/store/groups/{group.pk}', {'action': 'line', 'Pid': 'TRICE', 'quantity': 3})
        self.client.post(f'/store/groups/{group.pk}', {'action': 'lock'})
        self.client.post(f'/store/groups/{group.pk}', {'action': 'checkout'})
        group.refresh_from_db()
        self.assertEqual((group.Gstatus, Orders.objects.count()), ('locked', 0))
        Item.objects.create(Iproduct=self.rice, Ireceived=self.today)
        self.client.post(f'/store/groups/{group.pk}', {'action': 'checkout'})
        group.refresh_from_db()
        self.assertEqual((group.Gstatus, Orders.objects.count()), ('ordered', 1))

    def test_new_pages_need_login(self):
        self.client.session.flush()
        for path in ['/store/profile', '/store/subscriptions', '/store/subscriptions/new/TMILK', '/store/groups', '/store/groups/join/abc']:
            self.assertRedirects(self.client.get(path), '/store/login', fetch_redirect_response=False)
