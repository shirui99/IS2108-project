from datetime import date
from django.contrib.auth.models import AnonymousUser, User
from django.test import Client, RequestFactory, TestCase
from .models import Customer, GroupLine, GroupMember, GroupPurchase, InventoryBatch, Item, Orders, Product, Subscription, SubscriptionCycle
from .views import order_inspection_list, order_inspection_detail

class OrderInspectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('inspect_staff', is_staff=True)
        cls.buyer = User.objects.create_user('inspect_buyer')
        cls.inactive = User.objects.create_user('inspect_inactive', is_staff=True, is_active=False)
        cls.customer = Customer.objects.create(Cid='X0001', Cname='Test Buyer', Caddress='Address', Chouseholdsize=1, Cmealsperweek=1, Cuser=cls.buyer)
        cls.product = Product.objects.create(Pid='X0001', Pname='Apple', Pcategory_id='fruit', Psize='pack', Pprice=99, Plowstock=0)
        cls.orders = [Orders.objects.create(Oid=f'X0000{i}', Odate=date(2026,1,i), Oaddress='Recorded address', Ocustomer=cls.customer, Ostatus='cancelled' if i==4 else 'placed') for i in range(1,5)]
        cls.group = GroupPurchase.objects.create(Gname='Group', Gcode='test-code', Gaddress='Address', Gstatus='ordered', Gcreated=date(2026,1,1), Gorganiser=cls.customer, Gorder=cls.orders[0])
        GroupPurchase.objects.create(Gname='Solo group', Gcode='test-code-2', Gaddress='Address', Gstatus='ordered', Gcreated=date(2026,1,1), Gorganiser=cls.customer, Gorder=cls.orders[2])
        GroupMember.objects.create(GMgroup=cls.group, GMcustomer=cls.customer)
        GroupLine.objects.create(GLgroup=cls.group, GLcustomer=cls.customer, GLproduct=cls.product, GLquantity=2)
        sub = Subscription.objects.create(Scustomer=cls.customer, Sproduct=cls.product, Squantity=2, Sinterval=7, Snextdate=date(2026,2,1), Sceiling=20, Sstatus='active', Screated=date(2026,1,1))
        SubscriptionCycle.objects.create(SCsubscription=sub, SCdate=date(2026,1,1), SCresult='ordered', SCorder=cls.orders[0])
        SubscriptionCycle.objects.create(SCsubscription=sub, SCdate=date(2026,1,2), SCresult='ordered', SCorder=cls.orders[1])
        batch = InventoryBatch.objects.create(Breference='BATCH-A', Bproduct=cls.product, Breceived=date(2026,1,1), Bquantity=2, Bdatetype='', Bdate=None)
        for price, batch_value in [(2.5, batch), (2.5, batch), (3.0, None), (None, None)]:
            Item.objects.create(Iproduct=cls.product, Ibatch=batch_value, Ireceived=date(2026,1,1), Iorder=cls.orders[0], Istatus='delivered', Ipurchasedprice=price)

    def setUp(self): self.client.force_login(self.staff)

    def test_list_filters_and_dual_origin(self):
        r=self.client.get('/adminpanel/orders/')
        self.assertEqual(len(r.context['orders']), 4)
        self.assertContains(r, 'Multiple origins')
        self.assertContains(r, 'Other / origin not recorded')
        self.assertEqual(set(o.pk for o in self.client.get('/adminpanel/orders/', {'origin':'group'}).context['orders']), {'X00001','X00003'})
        self.assertEqual(set(o.pk for o in self.client.get('/adminpanel/orders/', {'origin':'subscription'}).context['orders']), {'X00001','X00002'})
        self.assertEqual(set(o.pk for o in self.client.get('/adminpanel/orders/', {'origin':'other'}).context['orders']), {'X00004'})
        self.assertEqual([o.pk for o in self.client.get('/adminpanel/orders/', {'status':'cancelled'}).context['orders']], ['X00004'])
        self.assertContains(self.client.get('/adminpanel/orders/', {'status':'bad','origin':'bad'}), 'Invalid status filter')
        self.assertContains(self.client.get('/adminpanel/orders/', {'status':'bad','origin':'bad'}), 'Invalid origin filter')
        self.assertContains(self.client.get('/adminpanel/orders/', {'status':'delivered'}), 'No orders match')

    def test_detail_prices_batches_group_subscription_and_cancellation(self):
        r=self.client.get('/adminpanel/orders/X00001/')
        self.assertContains(r, 'Recorded address')
        self.assertContains(r, 'BATCH-A')
        self.assertContains(r, 'Batch not recorded')
        self.assertContains(r, 'Not recorded')
        self.assertContains(r, 'Subscription order')
        self.assertContains(r, 'Recorded contributions')
        lines = {line['price']:line for line in r.context['lines']}
        self.assertEqual((lines[2.5]['quantity'], str(lines[2.5]['amount'])), (2, '5.0'))
        self.assertIsNone(lines[None]['amount'])
        self.assertNotContains(r, '$99.00')
        self.assertContains(self.client.get('/adminpanel/orders/X00004/'), 'Cancelled orders may have had their item links and prices cleared')
        self.assertEqual(self.client.get('/adminpanel/orders/UNKNOWN/').status_code, 404)

    def test_access_methods_and_get_immutability(self):
        before=(list(Orders.objects.order_by('pk').values()), list(Item.objects.order_by('pk').values()), list(GroupLine.objects.order_by('pk').values()), list(SubscriptionCycle.objects.order_by('pk').values()))
        for user in [None,self.buyer,self.inactive]:
            c=Client()
            if user: c.force_login(user)
            for path in ['/adminpanel/orders/', '/adminpanel/orders/X00001/']:
                self.assertEqual(c.get(path).status_code,302)
            req=RequestFactory().get('/adminpanel/orders/')
            req.user=user or AnonymousUser()
            self.assertEqual(order_inspection_list(req).status_code,302)
            self.assertEqual(order_inspection_detail(req, 'X00001').status_code,302)
        for path in ['/adminpanel/orders/', '/adminpanel/orders/X00001/']:
            self.assertEqual(self.client.post(path).status_code,405)
            self.client.get(path)
        self.assertEqual(before,(list(Orders.objects.order_by('pk').values()), list(Item.objects.order_by('pk').values()), list(GroupLine.objects.order_by('pk').values()), list(SubscriptionCycle.objects.order_by('pk').values())))
        self.assertEqual(self.client.get('/adminpanel/order_new/X00001').status_code,200)
