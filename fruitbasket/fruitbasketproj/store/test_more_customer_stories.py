from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from adminpanel.models import (
    Customer, GroupLine, GroupMember, GroupPurchase, Item, Orders, Product, SavedItem, StockNotice, Subscription,
    SubscriptionCycle, SupportTicket,
)
from store.subscriptions import process_due_subscriptions


class MoreCustomerStoryTests(TestCase):

    def setUp(self):
        self.today = timezone.localdate()
        self.user = User.objects.create_user(username='more_a', password='OldPassw0rd!x')
        self.customer = Customer.objects.create(
            Cid='CMOA', Cname='More A', Caddress='1 Test Road', Chouseholdsize=2, Cmealsperweek=10, Cuser=self.user
        )
        self.other = Customer.objects.create(
            Cid='CMOB', Cname='More B', Caddress='2 Test Road', Chouseholdsize=1, Cmealsperweek=5,
            Cuser=User.objects.create_user(username='more_b', password='password')
        )
        self.milk = Product.objects.create(
            Pid='TMILK', Pname='Test Milk', Pcategory='dairy', Psize='1L', Pprice=3.0, Plowstock=0, Pbulkquantity=4, Pbulkprice=2.5
        )
        self.rice = Product.objects.create(Pid='TRICE', Pname='Test Rice', Pcategory='rice', Psize='5kg', Pprice=10.0, Plowstock=0)
        for _ in range(6):
            Item.objects.create(Iproduct=self.milk, Ireceived=self.today, Iexpiry=self.today + timedelta(days=30))
        self.login(self.customer)

    def login(self, customer):
        session = self.client.session
        session['Cid'] = customer.Cid
        session['cart'] = {}
        session.save()

    def order_with(self, Oid, product, count, status='delivered', customer=None):
        order = Orders.objects.create(Oid=Oid, Odate=self.today, Oaddress='x', Ostatus=status, Ocustomer=customer or self.customer)
        for item in Item.objects.filter(Iproduct=product, Istatus='available')[:count]:
            item.Iorder = order
            item.Istatus = 'delivered'
            item.save()
        return order

    # SF26
    def test_change_password(self):
        url = '/store/profile/password'
        self.client.post(url, {'current': 'wrong', 'new': 'NewPassw0rd!x', 'confirm': 'NewPassw0rd!x'})
        self.client.post(url, {'current': 'OldPassw0rd!x', 'new': 'NewPassw0rd!x', 'confirm': 'different'})
        self.client.post(url, {'current': 'OldPassw0rd!x', 'new': '12345678', 'confirm': '12345678'})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPassw0rd!x'))
        response = self.client.post(url, {'current': 'OldPassw0rd!x', 'new': 'NewPassw0rd!x', 'confirm': 'NewPassw0rd!x'})
        self.assertRedirects(response, '/store/profile', fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPassw0rd!x'))
        self.assertNotContains(self.client.post(url, {'current': 'zzz', 'new': 'a', 'confirm': 'a'}), 'value="zzz"')

    # SF27
    def test_reorder_adds_what_stock_allows(self):
        order = self.order_with('OREO1', self.milk, 4)
        Item.objects.create(Iproduct=self.rice, Ireceived=self.today, Iorder=order, Istatus='used')
        response = self.client.post(f'/store/orders/{order.Oid}', {'action': 'reorder'})
        self.assertRedirects(response, '/store/cart', fetch_redirect_response=False)
        self.assertEqual(self.client.session['cart'], {'TMILK': 2})
        other_order = self.order_with('OREO2', self.milk, 1, customer=self.other)
        self.client.post(f'/store/orders/{other_order.Oid}', {'action': 'reorder'})
        self.assertEqual(self.client.session['cart'], {'TMILK': 2})

    # SF28
    def test_shopping_list(self):
        self.client.post('/store/list/TMILK')
        self.client.post('/store/list/TMILK')
        self.assertEqual(SavedItem.objects.filter(SVcustomer=self.customer).count(), 1)
        self.assertContains(self.client.get('/store/list'), 'Test Milk')
        self.login(self.other)
        self.assertNotContains(self.client.get('/store/list'), 'Test Milk')
        self.client.post('/store/list/TMILK', {'action': 'remove'})
        self.assertEqual(SavedItem.objects.count(), 1)
        self.login(self.customer)
        self.client.post('/store/list/TMILK', {'action': 'remove'})
        self.assertEqual(SavedItem.objects.count(), 0)
        self.assertEqual(self.client.get('/store/list/TMILK').status_code, 405)

    # SF29
    def test_back_in_stock_notice(self):
        self.assertContains(self.client.get('/store/product/TRICE'), 'Tell me when it is back')
        self.assertNotContains(self.client.get('/store/product/TMILK'), 'Tell me when it is back')
        self.client.post('/store/notify/TRICE')
        self.assertEqual(list(self.client.get('/store/').context['back_in_stock']), [])
        Item.objects.create(Iproduct=self.rice, Ireceived=self.today)
        self.assertEqual(list(self.client.get('/store/').context['back_in_stock']), [self.rice])
        self.login(self.other)
        self.assertEqual(list(self.client.get('/store/').context['back_in_stock']), [])
        self.login(self.customer)
        self.client.post('/store/notify/TRICE', {'action': 'remove'})
        self.assertEqual(StockNotice.objects.count(), 0)

    # SF32 / SF33
    def test_skip_and_change_subscription(self):
        due = self.today + timedelta(days=1)
        self.client.post('/store/subscriptions/new/TMILK', {'Squantity': 1, 'Sinterval': 7, 'Snextdate': due, 'Sceiling': '5', 'consent': 'on'})
        plan = Subscription.objects.get()
        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'skip'})
        plan.refresh_from_db()
        self.assertEqual(plan.Snextdate, due + timedelta(days=7))
        self.assertEqual(process_due_subscriptions(due), [])
        self.assertEqual(list(SubscriptionCycle.objects.values_list('SCresult', flat=True)), ['skipped'])

        edit = f'/store/subscriptions/{plan.pk}/edit'
        self.client.post(edit, {'Squantity': 2, 'Sinterval': 14, 'Sceiling': '5', 'consent': 'on'})
        self.client.post(edit, {'Squantity': 2, 'Sinterval': 14, 'Sceiling': '8'})
        plan.refresh_from_db()
        self.assertEqual((plan.Squantity, plan.Sinterval), (1, 7))
        self.client.post(edit, {'Squantity': 2, 'Sinterval': 14, 'Sceiling': '8', 'consent': 'on'})
        plan.refresh_from_db()
        self.assertEqual((plan.Squantity, plan.Sinterval, plan.Sceiling, plan.Snextdate), (2, 14, 8.0, due + timedelta(days=7)))

        self.login(self.other)
        self.client.post(edit, {'Squantity': 5, 'Sinterval': 30, 'Sceiling': '99', 'consent': 'on'})
        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'skip'})
        plan.refresh_from_db()
        self.assertEqual((plan.Squantity, plan.Snextdate), (2, due + timedelta(days=7)))

        self.login(self.customer)
        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'pause'})
        self.client.post(f'/store/subscriptions/{plan.pk}', {'action': 'skip'})
        plan.refresh_from_db()
        self.assertEqual(plan.Snextdate, due + timedelta(days=7))

    # SF34 / SF35
    def test_group_share_and_leave(self):
        self.client.post('/store/groups', {'Gname': 'Block 5', 'Gaddress': '5 Shared Road'})
        group = GroupPurchase.objects.get()
        url = f'/store/groups/{group.pk}'
        self.client.post(url, {'action': 'line', 'Pid': 'TMILK', 'quantity': 1})
        self.client.post(url, {'action': 'leave'})
        self.assertTrue(GroupMember.objects.filter(GMgroup=group, GMcustomer=self.customer).exists())
        self.assertEqual(self.client.get(url).context['my_share'], 3.0)

        self.login(self.other)
        self.client.post(f'/store/groups/join/{group.Gcode}')
        self.client.post(url, {'action': 'line', 'Pid': 'TMILK', 'quantity': 3})
        context = self.client.get(url).context
        self.assertEqual((context['my_share'], context['total']), (7.5, 10.0))
        self.assertEqual([amount for member, amount in context['shares']], [2.5, 7.5])

        self.client.post(url, {'action': 'leave'})
        self.assertEqual(GroupLine.objects.filter(GLcustomer=self.other).count(), 0)
        self.assertFalse(GroupMember.objects.filter(GMgroup=group, GMcustomer=self.other).exists())
        self.assertEqual(self.client.get(url).status_code, 302)

        self.client.post(f'/store/groups/join/{group.Gcode}')
        self.login(self.customer)
        self.client.post(url, {'action': 'lock'})
        self.login(self.other)
        self.client.post(url, {'action': 'leave'})
        self.assertTrue(GroupMember.objects.filter(GMgroup=group, GMcustomer=self.other).exists())

    # SF36
    def test_report_problem_from_pantry(self):
        order = self.order_with('OPAN2', self.milk, 1)
        item = order.order_items.get()
        self.client.post(f'/store/pantry/{item.pk}', {'action': 'report', 'Tmessage': '  '})
        self.assertEqual(SupportTicket.objects.count(), 0)
        self.login(self.other)
        self.client.post(f'/store/pantry/{item.pk}', {'action': 'report', 'Tmessage': 'not mine'})
        self.assertEqual(SupportTicket.objects.count(), 0)
        self.login(self.customer)
        self.client.post(f'/store/pantry/{item.pk}', {'action': 'report', 'Tmessage': 'Leaking carton'})
        ticket = SupportTicket.objects.get()
        self.assertEqual((ticket.Torder, ticket.Tstatus, ticket.Tmessage), (order, 'open', 'Leaking carton'))
        self.assertContains(self.client.get(f'/store/orders/{order.Oid}'), 'Leaking carton')

    # SF37
    def test_filter_orders_by_status(self):
        self.order_with('OFIL1', self.milk, 1, status='delivered')
        self.order_with('OFIL2', self.milk, 1, status='placed')
        ids = lambda response: sorted(order.Oid for order in response.context['orders'])
        self.assertEqual(ids(self.client.get('/store/orders')), ['OFIL1', 'OFIL2'])
        self.assertEqual(ids(self.client.get('/store/orders', {'status': 'placed'})), ['OFIL2'])
        self.assertEqual(ids(self.client.get('/store/orders', {'status': 'cancelled'})), [])
        self.assertEqual(ids(self.client.get('/store/orders', {'status': 'nonsense'})), ['OFIL1', 'OFIL2'])
        self.assertEqual(self.client.get('/store/orders/OFIL1', {'status': 'placed'}).context['order'].Oid, 'OFIL1')

    def test_new_pages_need_login(self):
        self.client.session.flush()
        for path in ['/store/profile/password', '/store/list', '/store/subscriptions/1/edit']:
            self.assertRedirects(self.client.get(path), '/store/login', fetch_redirect_response=False)
        self.assertRedirects(self.client.post('/store/notify/TMILK'), '/store/login', fetch_redirect_response=False)
