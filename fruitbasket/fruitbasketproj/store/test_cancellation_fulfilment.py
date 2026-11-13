from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier
from unittest.mock import patch
from django.contrib.auth.models import User
from django.db import DatabaseError, OperationalError, close_old_connections
from django.db.models.query import QuerySet
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone
from adminpanel.inventory import sellable_stock_filter
from adminpanel.models import Customer, GroupLine, GroupMember, GroupPurchase, Item, Orders, Product, Subscription, SubscriptionCycle

class CancellationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user=User.objects.create_user('cancel_user')
        cls.staff=User.objects.create_user('cancel_staff',is_staff=True)
        cls.customer=Customer.objects.create(Cid='K0001',Cname='Buyer',Caddress='Address',Chouseholdsize=1,Cmealsperweek=1,Cuser=cls.user)
        cls.product=Product.objects.create(Pid='K0001',Pname='Milk',Pcategory_id='dairy',Psize='pack',Pprice=2,Plowstock=0,Pexpirydays=3)
    def setUp(self):
        self.client.force_login(self.user)
        session=self.client.session;session['Cid']=self.customer.pk;session.save()
        self.order=Orders.objects.create(Oid='K00001',Odate=date.today(),Oaddress='Recorded',Ocustomer=self.customer)
        self.packs=[Item.objects.create(Iproduct=self.product,Ireceived=date.today(),Iexpiry=timezone.localdate()+timedelta(days=days),Iorder=self.order,Istatus='allocated',Ipurchasedprice=2) for days in (1,5)]
    def cancel(self): return self.client.post(f'/store/orders/{self.order.pk}',{'action':'cancel'})
    def test_cancel_releases_stock_but_only_cutoff_eligible_can_sell(self):
        self.assertContains(self.cancel(),'was cancelled')
        self.order.refresh_from_db();self.assertEqual((self.order.Ostatus,self.order.Opayment,self.order.Oaddress),('cancelled','refunded','Recorded'))
        for pack in self.packs:
            pack.refresh_from_db();self.assertEqual((pack.Istatus,pack.Iorder_id,pack.Ipurchasedprice),('available',None,None))
        self.assertEqual(Item.objects.filter(sellable_stock_filter(),pk__in=[p.pk for p in self.packs]).count(),1)
        self.assertContains(self.cancel(),'Only a placed order')
    def test_preparing_and_later_reject_customer_and_staff_editor(self):
        staff=Client();staff.force_login(self.staff)
        for status in ['preparing','dispatched','delivered']:
            with self.subTest(status=status):
                Orders.objects.filter(pk=self.order.pk).update(Ostatus=status)
                self.assertContains(self.cancel(),'Only a placed order')
                data={'action':'update','Oid':self.order.pk,'Ocustomer':self.customer.pk,'Oaddress':'Recorded','Odate':date.today().isoformat(),'Ostatus':'cancelled'}
                self.assertContains(staff.post(f'/adminpanel/order_new/{self.order.pk}',data),'Use the fulfilment actions')
                self.order.refresh_from_db();self.assertEqual((self.order.Ostatus,self.order.Opayment),(status,'paid'))
                self.assertEqual(self.order.order_items.count(),2)
    def test_group_subscription_links_remain_and_payment_refunded(self):
        group=GroupPurchase.objects.create(Gname='Group',Gcode='cancelgroup',Gaddress='Address',Gstatus='ordered',Gcreated=date.today(),Gorganiser=self.customer,Gorder=self.order)
        GroupMember.objects.create(GMgroup=group, GMcustomer=self.customer)
        GroupLine.objects.create(GLgroup=group, GLcustomer=self.customer, GLproduct=self.product, GLquantity=2)
        sub=Subscription.objects.create(Scustomer=self.customer,Sproduct=self.product,Squantity=1,Sinterval=7,Snextdate=date.today(),Sceiling=10,Screated=date.today())
        cycle=SubscriptionCycle.objects.create(SCsubscription=sub,SCdate=date.today(),SCresult='ordered',SCorder=self.order)
        self.assertContains(self.cancel(),'was cancelled')
        group.refresh_from_db();cycle.refresh_from_db();self.order.refresh_from_db()
        self.assertEqual((group.Gstatus,group.Gorder_id,cycle.SCresult,cycle.SCorder_id,self.order.Opayment),('ordered',self.order.pk,'ordered',self.order.pk,'refunded'))
        self.assertEqual((group.group_members.count(), group.group_lines.get().GLquantity), (1,2))
    def test_partial_pack_update_rolls_back_all(self):
        original=QuerySet.update
        def shortfall(queryset,**kwargs):
            if kwargs.get('Istatus')=='available': return 0
            return original(queryset,**kwargs)
        with patch.object(QuerySet,'update',shortfall): self.assertContains(self.cancel(),'Order items changed')
        self.order.refresh_from_db();self.assertEqual((self.order.Ostatus,self.order.Opayment),('placed','paid'))
        self.assertEqual(self.order.order_items.filter(Istatus='allocated').count(),2)
    def test_lost_status_claim_does_not_report_cancellation(self):
        original=QuerySet.update
        def lost(queryset, **kwargs):
            if kwargs.get('Ostatus')=='cancelled': return 0
            return original(queryset, **kwargs)
        with patch.object(QuerySet, 'update', lost):
            response=self.cancel()
        self.assertContains(response, 'Only a placed order')
        self.assertNotContains(response, 'was cancelled')
        self.order.refresh_from_db()
        self.assertEqual((self.order.Ostatus,self.order.Opayment),('placed','paid'))
        self.assertEqual(self.order.order_items.count(),2)

    def test_database_error_rolls_back_and_reports_retry(self):
        original=QuerySet.update
        def fail(queryset, **kwargs):
            if kwargs.get('Istatus')=='available': raise DatabaseError('forced')
            return original(queryset, **kwargs)
        with patch.object(QuerySet, 'update', fail): response=self.cancel()
        self.assertContains(response, 'database is busy')
        self.order.refresh_from_db()
        self.assertEqual((self.order.Ostatus,self.order.Opayment),('placed','paid'))
        self.assertEqual(self.order.order_items.count(),2)

    def test_consumed_or_rated_pack_cannot_release(self):
        Item.objects.filter(pk=self.packs[0].pk).update(Irating=4)
        self.assertContains(self.cancel(),'already used or thrown away')
        self.order.refresh_from_db();self.assertEqual((self.order.Ostatus,self.order.Opayment),('placed','paid'))
        self.assertEqual(self.order.order_items.count(),2)

class CancelPrepareRaceTests(TransactionTestCase):
    def test_two_clients_cancel_and_prepare(self):
        self.run_race()

    def test_staff_cancel_races_preparation(self):
        self.run_race(staff_cancel=True)

    def run_race(self, staff_cancel=False):
        from adminpanel.models import Category
        Category.objects.get_or_create(Ccode='dairy', defaults={'Cname':'Dairy, Chilled & Eggs'})
        user=User.objects.create_user('race_customer');staff=User.objects.create_user('race_staff',is_staff=True)
        customer=Customer.objects.create(Cid='K0002',Cname='Buyer',Caddress='x',Chouseholdsize=1,Cmealsperweek=1,Cuser=user)
        product=Product.objects.create(Pid='K0002',Pname='Milk',Pcategory_id='dairy',Psize='pack',Pprice=2,Plowstock=0)
        order=Orders.objects.create(Oid='K00002',Odate=date.today(),Oaddress='x',Ocustomer=customer)
        pack=Item.objects.create(Iproduct=product,Ireceived=date.today(),Iorder=order,Istatus='allocated',Ipurchasedprice=2)
        customer_client=Client();customer_client.force_login(user);session=customer_client.session;session['Cid']=customer.pk;session.save()
        staff_client=Client();staff_client.force_login(staff)
        cancel_client=Client();cancel_client.force_login(staff)
        barrier=Barrier(2)
        def run(kind):
            close_old_connections();barrier.wait()
            try:
                return ((cancel_client.post(f'/adminpanel/orders/{order.pk}/cancel/',{'reason':'Race cancellation'}).status_code if staff_cancel else customer_client.post(f'/store/orders/{order.pk}',{'action':'cancel'}).status_code) if kind=='cancel' else staff_client.post(f'/adminpanel/orders/{order.pk}/fulfil/',{'action':'prepare'}).status_code)
            except OperationalError: return 'sqlite busy'
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,['cancel','prepare']))
        order.refresh_from_db();pack.refresh_from_db()
        self.assertTrue(all(result in (200,302,'sqlite busy') for result in results))
        self.assertIn(order.Ostatus,['placed','preparing','cancelled'])
        print(f'Cancel/prepare race: responses={results}; final_status={order.Ostatus}')
        if order.Ostatus=='cancelled':
            self.assertEqual((order.Opayment,pack.Iorder_id,pack.Istatus,pack.Ipurchasedprice),('refunded',None,'available',None))
            self.assertEqual(order.cancellation.allocations.get().quantity,1)
            self.assertEqual(order.cancellation.source,'staff' if staff_cancel else 'customer')
        else: self.assertEqual((order.Opayment,pack.Iorder_id,pack.Istatus,pack.Ipurchasedprice),('paid',order.pk,'allocated',2))
        if order.Ostatus=='placed':
            if staff_cancel:
                cancel_client.post(f'/adminpanel/orders/{order.pk}/cancel/',{'reason':'Race cancellation retry'})
            else:
                customer_client.post(f'/store/orders/{order.pk}',{'action':'cancel'})
            order.refresh_from_db();pack.refresh_from_db()
            self.assertEqual((order.Ostatus,pack.Iorder_id),('cancelled',None))
