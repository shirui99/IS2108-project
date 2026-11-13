from datetime import date
from unittest.mock import patch
from django.contrib.auth.models import User
from django.db import DatabaseError
from django.test import Client, TestCase
from .models import Customer, GroupPurchase, Item, Orders, Product, Subscription, SubscriptionCycle
from store.ordering import place_order

class FulfilmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff=User.objects.create_user('fulfil_staff',is_staff=True)
        cls.buyer=User.objects.create_user('fulfil_buyer')
        cls.other=User.objects.create_user('other_buyer')
        cls.inactive=User.objects.create_user('inactive',is_staff=True,is_active=False)
        cls.other_customer=Customer.objects.create(Cid='F0002',Cname='Other',Caddress='x',Chouseholdsize=1,Cmealsperweek=1,Cuser=cls.other)
        cls.customer=Customer.objects.create(Cid='F0001',Cname='Buyer',Caddress='Address',Chouseholdsize=1,Cmealsperweek=1,Cuser=cls.buyer)
        cls.product=Product.objects.create(Pid='F0001',Pname='Apple',Pcategory_id='fruit',Psize='pack',Pprice=3,Plowstock=0)
    def setUp(self):
        self.client.force_login(self.staff)
        Item.objects.create(Iproduct=self.product,Ireceived=date(2026,1,1))
        self.order,_=place_order(self.customer,'Recorded address',{self.product.pk:1})
        self.item=self.order.order_items.get()
        self.url=f'/adminpanel/orders/{self.order.pk}/fulfil/'
    def step(self,action): return self.client.post(self.url,{'action':action})
    def pantry(self,user=None):
        c=Client(); c.force_login(user or self.buyer)
        session=c.session; session['Cid']=self.customer.pk if user!=self.other else self.other_customer.pk; session.save()
        return c.get('/store/pantry').context['pantry_items']
    def test_sequence_repeat_timestamps_and_pantry(self):
        self.assertEqual(self.item.Istatus,'allocated')
        self.assertEqual(self.pantry(),[])
        for action,status in [('prepare','preparing'),('dispatch','dispatched'),('deliver','delivered')]:
            self.assertEqual(self.step(action).status_code,302)
            self.order.refresh_from_db(); self.assertEqual(self.order.Ostatus,status)
            before=(self.order.Odispatched,self.order.Odelivered)
            self.step(action); self.order.refresh_from_db()
            self.assertEqual((self.order.Odispatched,self.order.Odelivered),before)
            if action!='deliver': self.assertEqual(self.pantry(),[])
        self.assertIsNotNone(self.order.Odispatched); self.assertIsNotNone(self.order.Odelivered)
        self.item.refresh_from_db(); self.assertEqual(self.item.Istatus,'delivered')
        self.assertEqual((self.item.Ipurchasedprice,self.item.Iorder_id),(3,self.order.pk))
        self.assertEqual(len(self.pantry()),1); self.assertEqual(self.pantry(self.other),[])
        self.assertEqual(Item.objects.count(),1)
    def test_invalid_out_of_order_empty_and_unknown(self):
        self.step('dispatch'); self.step('deliver'); self.order.refresh_from_db(); self.assertEqual(self.order.Ostatus,'placed')
        self.assertEqual(self.step('bad').status_code,400)
        self.order.Ostatus='cancelled';self.order.save(update_fields=['Ostatus'])
        for action in ['prepare','dispatch','deliver']: self.step(action)
        self.order.refresh_from_db();self.assertEqual(self.order.Ostatus,'cancelled')
        self.order.Ostatus='placed';self.order.save(update_fields=['Ostatus'])
        self.assertEqual(self.client.post('/adminpanel/orders/MISSING/fulfil/',{'action':'prepare'}).status_code,404)
        self.order.order_items.update(Istatus='used')
        self.step('prepare'); self.order.refresh_from_db(); self.assertEqual(self.order.Ostatus,'placed')
        self.order.order_items.update(Iorder=None,Istatus='available')
        self.step('prepare'); self.order.refresh_from_db(); self.assertEqual(self.order.Ostatus,'placed')
    def test_group_and_subscription(self):
        GroupPurchase.objects.create(Gname='Group',Gcode='fulfil-group',Gaddress='x',Gstatus='ordered',Gcreated=date.today(),Gorganiser=self.customer,Gorder=self.order)
        sub=Subscription.objects.create(Scustomer=self.customer,Sproduct=self.product,Squantity=1,Sinterval=7,Snextdate=date.today(),Sceiling=10,Screated=date.today())
        SubscriptionCycle.objects.create(SCsubscription=sub,SCdate=date.today(),SCresult='ordered',SCorder=self.order)
        for action in ['prepare','dispatch','deliver']: self.step(action)
        self.assertEqual(self.pantry(),[])
        self.assertEqual(GroupPurchase.objects.get().Gorder_id,self.order.pk)
        # A separate subscription delivery enters its subscriber's pantry.
        Item.objects.create(Iproduct=self.product,Ireceived=date.today())
        order,_=place_order(self.customer,'Subscriber address',{self.product.pk:1})
        SubscriptionCycle.objects.create(SCsubscription=sub,SCdate=date.today(),SCresult='ordered',SCorder=order)
        for action in ['prepare','dispatch','deliver']: self.client.post(f'/adminpanel/orders/{order.pk}/fulfil/',{'action':action})
        self.assertEqual(len(self.pantry()),1)
    def test_permissions_csrf_and_get(self):
        for user in [None,self.buyer,self.inactive]:
            c=Client()
            if user:c.force_login(user)
            self.assertEqual(c.post(self.url,{'action':'prepare'}).status_code,302)
        self.assertEqual(self.client.get(self.url).status_code,405)
        c=Client(enforce_csrf_checks=True);c.force_login(self.staff)
        self.assertEqual(c.post(self.url,{'action':'prepare'}).status_code,403)
        self.assertEqual(c.post(self.url,{'action':'prepare','csrfmiddlewaretoken':'bad'}).status_code,403)
        c.get(f'/adminpanel/orders/{self.order.pk}/')
        self.assertEqual(c.post(self.url,{'action':'prepare','csrfmiddlewaretoken':c.cookies['csrftoken'].value}).status_code,302)
    def test_editor_cannot_change_status_owner_or_id(self):
        data={'action':'update','Oid':self.order.pk,'Ocustomer':self.customer.pk,'Odate':'2026-01-01','Oaddress':'Updated','Ostatus':'delivered'}
        r=self.client.post(f'/adminpanel/order_new/{self.order.pk}',data)
        self.assertContains(r,'Use the fulfilment actions')
        self.order.refresh_from_db();self.assertEqual(self.order.Ostatus,'placed')
        data['Ostatus']='placed';data['Oid']='OTHER'
        self.assertContains(self.client.post(f'/adminpanel/order_new/{self.order.pk}',data),'order ID cannot be changed')
        data['Oid']=self.order.pk;data.pop('Ostatus')
        other_customer=self.other_customer
        data['Ocustomer']=other_customer.pk
        self.assertContains(self.client.post(f'/adminpanel/order_new/{self.order.pk}',data),'customer cannot change')
        data['Ocustomer']=self.customer.pk
        self.assertEqual(self.client.post(f'/adminpanel/order_new/{self.order.pk}',data).status_code,302)
        self.order.refresh_from_db();self.assertEqual(self.order.Oaddress,'Updated')
    def test_delivery_failure_rolls_back_parent_and_timestamp(self):
        self.step('prepare');self.step('dispatch')
        from django.db.models.query import QuerySet
        original=QuerySet.update
        def fail(q,**values):
            if values.get('Istatus')=='delivered': raise DatabaseError('forced')
            return original(q,**values)
        with patch.object(QuerySet,'update',autospec=True,side_effect=fail):self.step('deliver')
        self.order.refresh_from_db();self.item.refresh_from_db()
        self.assertEqual(self.order.Ostatus,'dispatched');self.assertIsNone(self.order.Odelivered)
        self.assertEqual(self.item.Istatus,'allocated')


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections, OperationalError
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TransactionTestCase
from .views import fulfil_order

class FulfilmentConcurrencyTests(TransactionTestCase):
    def test_two_prepare_requests_change_status_once(self):
        from .models import Category
        Category.objects.get_or_create(Ccode='fruit', defaults={'Cname': 'Fruit & Vegetables'})
        staff=User.objects.create_user('race_staff',is_staff=True)
        user=User.objects.create_user('race_customer')
        customer=Customer.objects.create(Cid='RACE1',Cname='Race',Caddress='x',Chouseholdsize=1,Cmealsperweek=1,Cuser=user)
        product=Product.objects.create(Pid='RACE1',Pname='Apple',Pcategory_id='fruit',Psize='pack',Pprice=3,Plowstock=0)
        order=Orders.objects.create(Oid='RACE01',Odate=date.today(),Oaddress='x',Ocustomer=customer)
        Item.objects.create(Iproduct=product,Ireceived=date.today(),Iorder=order,Istatus='allocated',Ipurchasedprice=3)
        for action,source,target in [('prepare','placed','preparing'),('dispatch','preparing','dispatched'),('deliver','dispatched','delivered')]:
            barrier=Barrier(2)
            def request():
                req=RequestFactory().post('/fulfil/',{'action':action})
                req.user=staff;req.session={};req._messages=FallbackStorage(req)
                return req
            def run():
                close_old_connections()
                barrier.wait()
                try:
                    return fulfil_order(request(),order.pk).status_code
                except OperationalError:
                    return 'sqlite busy'
                finally: close_old_connections()
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:run(),range(2)))
            order.refresh_from_db()
            if order.Ostatus==source:
                fulfil_order(request(),order.pk);order.refresh_from_db()
            self.assertEqual(order.Ostatus,target)
            self.assertEqual(order.order_items.count(),1)
            self.assertEqual(order.order_items.get().Istatus,'delivered' if target=='delivered' else 'allocated')
            self.assertTrue(all(result in [302,'sqlite busy'] for result in results))
        self.assertIsNotNone(order.Odispatched);self.assertIsNotNone(order.Odelivered)
