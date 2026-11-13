from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
from datetime import timedelta
from django.contrib.auth.models import User
from django.core import signing
from django.db import DatabaseError, OperationalError, close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from . import test_subscription_processing as fixtures
from .models import Category, Customer, Product, Subscription, SubscriptionCycle, Orders, Item, StockAdjustment
from store.subscriptions import process_due_subscriptions


def writeoff_data(plan, today):
    group=signing.dumps({'product':plan.Sproduct_id,'received':today.isoformat(),'date':None},salt='stock-group')
    return {'group':group,'action':'writeoff','quantity':2,'reason':'damaged','request_id':str(uuid4()),'expected_count':2,'snapshot':signing.dumps([group,'writeoff',2],salt='stock-snapshot')}


def buyer_client(customer):
    client=Client();client.force_login(customer.Cuser)
    session=client.session;session['Cid']=customer.pk;session['cart']={customer.customer_subscriptions.first().Sproduct_id:2};session.save()
    return client


class FinalVerificationTests(TestCase):
    setUp=fixtures.DueSubscriptionTests.setUp

    def test_later_database_failure_preserves_earlier_success_and_retry(self):
        later=Subscription.objects.create(Scustomer=self.customer,Sproduct=self.product,Squantity=1,Sinterval=7,Snextdate=self.today,Sceiling=10,Screated=self.today)
        Item.objects.create(Iproduct=self.product,Ireceived=self.today)
        original=SubscriptionCycle.objects.create
        def fail(**values):
            if values['SCsubscription'].pk==later.pk:
                self.assertEqual(Orders.objects.count(),2)
                self.assertEqual(Item.objects.filter(Istatus='allocated').count(),3)
                raise DatabaseError('injected after allocation')
            return original(**values)
        with patch('store.subscriptions.SubscriptionCycle.objects.create',side_effect=fail):
            with self.assertRaises(DatabaseError):process_due_subscriptions(self.today)
        self.plan.refresh_from_db();later.refresh_from_db()
        self.assertEqual((Orders.objects.count(),SubscriptionCycle.objects.count(),Item.objects.filter(Istatus='allocated').count()),(1,1,2))
        self.assertEqual((self.plan.Snextdate,later.Snextdate),(self.today+timedelta(days=7),self.today))
        first=SubscriptionCycle.objects.get().SCorder_id
        self.assertEqual(Item.objects.filter(Istatus='available',Iorder__isnull=True,Ipurchasedprice__isnull=True).count(),1)
        process_due_subscriptions(self.today)
        self.assertEqual(Orders.objects.count(),2)
        self.assertEqual(SubscriptionCycle.objects.get(SCsubscription=self.plan).SCorder_id,first)
        self.assertEqual(Orders.objects.filter(Opayment='paid').count(),2)

    def test_cart_then_actual_writeoff_rejects_checkout(self):
        buyer=buyer_client(self.customer)
        self.assertEqual(self.client.post('/adminpanel/stock_adjust',writeoff_data(self.plan,self.today)).status_code,302)
        response=buyer.post('/store/checkout',{'Oaddress':'A'})
        self.assertContains(response,'Only 0 sellable pack(s)')
        self.assertEqual(buyer.session['cart'],{self.product.pk:2})
        self.assertFalse(Orders.objects.exists())
        self.assertFalse(Item.objects.filter(Iorder__isnull=False).exists())
        self.assertEqual(Item.objects.filter(Istatus='writtenoff').count(),2)
        self.assertEqual(StockAdjustment.objects.get().difference,-2)

    def test_contact_email_failure_rolls_back_with_safe_form_response(self):
        original=User.save
        def fail(user,*args,**kwargs):
            if user.pk==self.user.pk and kwargs.get('update_fields')==['email']:
                self.assertEqual(Customer.objects.get(pk=self.customer.pk).Caddress,'Changed')
                raise DatabaseError('injected-email-failure')
            return original(user,*args,**kwargs)
        client=Client(raise_request_exception=False);client.force_login(self.staff)
        data={'Cname':'Changed name','Caddress':'Changed','email':'new@example.com'}
        for path, payload in [('/adminpanel/customer_new/'+self.customer.pk, data),
                              ('/adminpanel/customer_new', {**data,'action':'update','Cid':self.customer.pk})]:
            with self.subTest(path=path), patch.object(User,'save',autospec=True,side_effect=fail):
                response=client.post(path,payload)
            self.customer.refresh_from_db();self.user.refresh_from_db()
            self.assertEqual((self.customer.Cname,self.customer.Caddress,self.user.email),('Buyer','A',''))
            self.assertEqual(response.status_code,200)
            for value in ['Changed name','Changed','new@example.com','The contact details could not be saved. Please try again.']:
                self.assertContains(response,value)
            self.assertNotContains(response,'injected-email-failure')
        self.assertEqual(client.post('/adminpanel/customer_new/'+self.customer.pk,data).status_code,302)
        self.customer.refresh_from_db();self.user.refresh_from_db()
        self.assertEqual((self.customer.Cname,self.customer.Caddress,self.user.email),('Changed name','Changed','new@example.com'))

    def test_subscription_hold_receipt_retry_delivery_pantries(self):
        Item.objects.all().delete()
        self.client.post(self.path)
        cycle=SubscriptionCycle.objects.get();self.assertTrue(cycle.SCretryable)
        self.plan.refresh_from_db();self.assertEqual(self.plan.Snextdate,self.today)
        self.client.post('/adminpanel/item_new',{'action':'create','Iproduct':self.product.pk,'Breference':'FINAL-RECEIPT','Ireceived':self.today.isoformat(),'Iquantity':2,'Bdatetype':'','Iexpiry':''})
        self.client.post(self.path);cycle.refresh_from_db();self.plan.refresh_from_db()
        self.assertEqual((Orders.objects.count(),cycle.SCresult,cycle.SCorder.Opayment,cycle.SCorder.order_items.count()),(1,'ordered','paid',2))
        self.assertEqual(self.plan.Snextdate,self.today+timedelta(days=7))
        buyer=buyer_client(self.customer)
        self.assertEqual(buyer.get('/store/pantry').context['pantry_items'],[])
        for action in ['prepare','dispatch','deliver']:
            self.client.post(f'/adminpanel/orders/{cycle.SCorder_id}/fulfil/',{'action':action})
        self.assertEqual(len(buyer.get('/store/pantry').context['pantry_items']),2)
        other=Customer.objects.create(Cid='FV002',Cname='Other',Caddress='B',Chouseholdsize=1,Cmealsperweek=1,Cuser=User.objects.create_user('final_other'))
        outsider=Client();session=outsider.session;session['Cid']=other.pk;session.save()
        self.assertEqual(outsider.get('/store/pantry').context['pantry_items'],[])
        self.client.post(self.path);self.assertEqual(Orders.objects.count(),1)


class WriteoffCheckoutRaceTests(TransactionTestCase):
    def test_competing_requests_have_one_stock_outcome(self):
        Category.objects.get_or_create(Ccode='fruit',defaults={'Cname':'Fruit & Vegetables'})
        fixtures.DueSubscriptionTests.setUp(self)
        buyer=buyer_client(self.customer);data=writeoff_data(self.plan,self.today)
        barrier=Barrier(2)
        def run(index):
            close_old_connections();barrier.wait(timeout=10)
            try:
                response=self.client.post('/adminpanel/stock_adjust',data) if index==0 else buyer.post('/store/checkout',{'Oaddress':'A'})
                return response.status_code
            except OperationalError as error:
                if not any(word in str(error).lower() for word in ['locked','busy']):
                    raise
                return 'sqlite busy'
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(run,[0,1]))
        # Busy outcomes alone prove nothing: drive one bounded serial attempt if neither committed.
        if not Orders.objects.exists() and not StockAdjustment.objects.exists():
            self.client.post('/adminpanel/stock_adjust',data)
            buyer.post('/store/checkout',{'Oaddress':'A'})
        allocated=Item.objects.filter(Istatus='allocated').count();written=Item.objects.filter(Istatus='writtenoff').count()
        self.assertIn((allocated,written),[(2,0),(0,2)])
        self.assertFalse(Item.objects.filter(Istatus='writtenoff',Iorder__isnull=False).exists())
        self.assertEqual(Orders.objects.count(),1 if allocated else 0)
        self.assertEqual(StockAdjustment.objects.count(),1 if written else 0)
        if written:self.assertEqual((StockAdjustment.objects.get().difference,StockAdjustment.objects.get().items.count()),(-2,2))
        if allocated:self.assertEqual((Orders.objects.get().Opayment,Orders.objects.get().order_items.count()),('paid',2))
        print('Writeoff/checkout race:',outcomes,'final:',allocated,written)
