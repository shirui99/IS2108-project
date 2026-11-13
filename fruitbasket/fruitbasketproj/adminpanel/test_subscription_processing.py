from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import DatabaseError
from django.test import Client, TestCase
from django.utils import timezone
from adminpanel.models import Customer, Product, Item, Orders, Subscription, SubscriptionCycle
from store.subscriptions import ScheduledCycleConflict, process_due_subscriptions


class DueSubscriptionTests(TestCase):
    def setUp(self):
        self.today=timezone.localdate()
        self.staff=User.objects.create_user('process_staff',is_staff=True)
        self.user=User.objects.create_user('process_buyer')
        self.customer=Customer.objects.create(Cid='DS001',Cname='Buyer',Caddress='A',Chouseholdsize=1,Cmealsperweek=1,Cuser=self.user)
        self.product=Product.objects.create(Pid='DS001',Pname='Apple',Pcategory_id='fruit',Psize='pack',Pprice=3,Plowstock=0)
        self.plan=Subscription.objects.create(Scustomer=self.customer,Sproduct=self.product,Squantity=2,Sinterval=7,Snextdate=self.today,Sceiling=10,Screated=self.today)
        for _ in range(2):Item.objects.create(Iproduct=self.product,Ireceived=self.today)
        self.client.force_login(self.staff)
        self.path=f'/adminpanel/subscriptions/{self.plan.pk}/process/'

    def assert_hold(self, reason):
        cycle=process_due_subscriptions(self.today)[0]
        self.assertEqual((cycle.SCresult,cycle.SCretryable,cycle.SCorder_id),('failed',True,None))
        self.assertIn(reason,cycle.SCnote)
        self.plan.refresh_from_db();self.assertEqual(self.plan.Snextdate,self.today)
        self.assertFalse(Orders.objects.exists())
        self.assertFalse(Item.objects.exclude(Istatus='available').exists())
        self.assertFalse(Item.objects.filter(Iorder__isnull=False).exists())
        self.assertFalse(Item.objects.filter(Ipurchasedprice__isnull=False).exists())
        return cycle

    def assert_retry(self, cycle):
        result=process_due_subscriptions(self.today)[0]
        self.assertEqual(result.pk,cycle.pk)
        self.assertEqual((result.SCresult,result.SCretryable,result.SCorder.Opayment),('ordered',False,'paid'))
        self.assertEqual(result.SCorder.order_items.count(),2)
        self.assertEqual(SubscriptionCycle.objects.count(),1)
        self.plan.refresh_from_db();self.assertEqual(self.plan.Snextdate,self.today+timedelta(days=7))
        self.assertEqual(process_due_subscriptions(self.today),[])
        self.assertEqual(Orders.objects.count(),1)

    def test_stock_hold_retry_same_cycle(self):
        Item.objects.first().delete()
        cycle=self.assert_hold('sellable')
        again=self.assert_hold('sellable');self.assertEqual(again.pk,cycle.pk)
        self.assertContains(self.client.get('/adminpanel/subscriptions/'),'On hold')
        buyer=Client();session=buyer.session;session['Cid']=self.customer.pk;session.save()
        self.assertContains(buyer.get('/store/subscriptions'),'On hold')
        Item.objects.create(Iproduct=self.product,Ireceived=self.today)
        self.assert_retry(cycle)
        self.assertNotContains(buyer.get('/store/subscriptions'),'On hold')
        self.assertContains(buyer.get('/store/subscriptions'),'Order created')

    def test_inactive_product_hold_retry(self):
        self.product.Pactive=False;self.product.save()
        cycle=self.assert_hold('no longer available')
        self.product.Pactive=True;self.product.save()
        self.assert_retry(cycle)

    def test_ceiling_hold_retry_command(self):
        self.plan.Sceiling=5;self.plan.save()
        cycle=self.assert_hold('approved limit')
        self.plan.Sceiling=10;self.plan.save()
        call_command('process_subscriptions',stdout=StringIO())
        cycle.refresh_from_db();self.assertEqual((cycle.SCresult,cycle.SCretryable),('ordered',False))
        self.assertEqual(Orders.objects.count(),1)

    def test_cycle_save_failure_rolls_back_order_stock_and_schedule(self):
        with patch('store.subscriptions.SubscriptionCycle.objects.create',side_effect=DatabaseError('fail')):
            with self.assertRaises(DatabaseError):process_due_subscriptions(self.today)
        self.plan.refresh_from_db();self.assertEqual(self.plan.Snextdate,self.today)
        self.assertFalse(Orders.objects.exists());self.assertFalse(SubscriptionCycle.objects.exists())
        self.assertFalse(Item.objects.filter(Iorder__isnull=False).exists())

    def test_historical_failures_not_retried(self):
        SubscriptionCycle.objects.create(SCsubscription=self.plan,SCdate=self.today,SCscheduleddate=self.today,SCresult='failed',SCnote='Old failure')
        with self.assertRaises(ScheduledCycleConflict):process_due_subscriptions(self.today)
        self.plan.refresh_from_db();self.assertEqual(self.plan.Snextdate,self.today)
        self.assertFalse(Orders.objects.exists())

    def test_excluded_plans_permissions_csrf_and_screen(self):
        for status,due in [('paused',self.today),('cancelled',self.today),('active',self.today+timedelta(days=1))]:
            self.plan.Sstatus=status;self.plan.Snextdate=due;self.plan.save()
            self.assertEqual(process_due_subscriptions(self.today),[])
        self.assertContains(self.client.get('/adminpanel/subscriptions/'),'No active subscriptions')
        self.plan.Sstatus='active';self.plan.Snextdate=self.today;self.plan.save()
        inactive=User.objects.create_user('inactive_process_staff',is_staff=True,is_active=False)
        for user in [None,self.user,inactive]:
            client=Client()
            if user:client.force_login(user)
            self.assertEqual(client.get('/adminpanel/subscriptions/').status_code,302)
            self.assertEqual(client.post(self.path).status_code,302)
        self.staff.is_staff=False;self.staff.save();self.assertEqual(self.client.post(self.path).status_code,302)
        self.staff.is_staff=True;self.staff.save()
        client=Client(enforce_csrf_checks=True);client.force_login(self.staff);client.get('/adminpanel/subscriptions/')
        self.assertEqual(client.get(self.path).status_code,405)
        for token in ['', 'bad']:
            self.assertEqual(client.post(self.path,{'csrfmiddlewaretoken':token}).status_code,403)
        self.assertEqual(client.post('/adminpanel/subscriptions/99999/process/',{'csrfmiddlewaretoken':client.cookies['csrftoken'].value}).status_code,404)
        self.assertEqual(client.post(self.path,{'csrfmiddlewaretoken':client.cookies['csrftoken'].value}).status_code,302)
        self.assertContains(client.get('/adminpanel/subscriptions/'),'created')
        self.assertEqual(client.post(self.path,{'csrfmiddlewaretoken':client.cookies['csrftoken'].value}).status_code,302)
        self.assertEqual(Orders.objects.count(),1)

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase


class DueRetryConcurrencyTests(TransactionTestCase):
    def test_two_requests_retry_one_held_cycle(self):
        from adminpanel.models import Category
        Category.objects.get_or_create(Ccode='fruit',defaults={'Cname':'Fruit & Vegetables'})
        staff=User.objects.create_user('retry_race_staff',is_staff=True)
        user=User.objects.create_user('retry_race_buyer')
        customer=Customer.objects.create(Cid='DR001',Cname='Buyer',Caddress='A',Chouseholdsize=1,Cmealsperweek=1,Cuser=user)
        product=Product.objects.create(Pid='DR001',Pname='Apple',Pcategory_id='fruit',Psize='pack',Pprice=3,Plowstock=0)
        today=timezone.localdate()
        plan=Subscription.objects.create(Scustomer=customer,Sproduct=product,Squantity=1,Sinterval=7,Snextdate=today,Sceiling=10,Screated=today)
        held=process_due_subscriptions(today)[0]
        Item.objects.create(Iproduct=product,Ireceived=today)
        clients=[Client(),Client()]
        for client in clients:client.force_login(staff)
        barrier=Barrier(2)
        def run(index):
            close_old_connections();barrier.wait(timeout=10)
            try:return clients[index].post(f'/adminpanel/subscriptions/{plan.pk}/process/').status_code
            except DatabaseError:return 'sqlite busy'
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
        process_due_subscriptions(today)
        held.refresh_from_db();plan.refresh_from_db()
        self.assertEqual((SubscriptionCycle.objects.count(),Orders.objects.count(),held.SCresult),(1,1,'ordered'))
        self.assertEqual((held.SCorder.Opayment,held.SCorder.order_items.count()),('paid',1))
        self.assertEqual(plan.Snextdate,today+timedelta(days=7))
        print('Held-cycle retry race:',results)

from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class SubscriptionHoldMigrationTests(TransactionTestCase):
    def test_old_failed_cycles_are_not_made_retryable(self):
        def restore():
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
        self.addCleanup(restore)
        target=[('adminpanel','0016_review_moderation')]
        executor=MigrationExecutor(connection);executor.migrate(target)
        apps=executor.loader.project_state(target).apps
        apps.get_model('adminpanel','Category').objects.get_or_create(Ccode='fruit',defaults={'Cname':'Fruit & Vegetables'})
        user=apps.get_model('auth','User').objects.create(username='hold_migration')
        customer=apps.get_model('adminpanel','Customer').objects.create(Cid='HM001',Cname='Buyer',Caddress='A',Chouseholdsize=1,Cmealsperweek=1,Cuser_id=user.pk)
        product=apps.get_model('adminpanel','Product').objects.create(Pid='HM001',Pname='Apple',Pcategory_id='fruit',Psize='pack',Pprice=3,Plowstock=0)
        plan=apps.get_model('adminpanel','Subscription').objects.create(Scustomer_id=customer.pk,Sproduct_id=product.pk,Squantity=1,Sinterval=7,Snextdate=timezone.localdate()+timedelta(days=7),Sceiling=10,Screated=timezone.localdate())
        cycle=apps.get_model('adminpanel','SubscriptionCycle').objects.create(SCsubscription_id=plan.pk,SCdate=timezone.localdate(),SCscheduleddate=timezone.localdate(),SCresult='failed',SCnote='Historical hold')
        due=plan.Snextdate
        restore()
        cycle=SubscriptionCycle.objects.get(pk=cycle.pk);plan=Subscription.objects.get(pk=plan.pk)
        self.assertEqual((cycle.SCretryable,cycle.SCnote,plan.Snextdate),(False,'Historical hold',due))
