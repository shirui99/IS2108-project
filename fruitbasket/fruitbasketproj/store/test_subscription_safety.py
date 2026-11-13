from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from django.contrib.auth.models import User
from django.db import DatabaseError, IntegrityError, close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone
from adminpanel.models import Category, Customer, GroupLine, GroupMember, GroupPurchase, Item, Orders, Product, Subscription, SubscriptionCycle
from store.subscriptions import ScheduledCycleConflict, process_due_subscriptions
from store.forms import SubscriptionEditForm

class SubscriptionSafetyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user=User.objects.create_user('cycle_customer',password='secret')
        cls.other=User.objects.create_user('cycle_member',password='secret')
        cls.outsider=User.objects.create_user('cycle_outsider')
        cls.staff=User.objects.create_user('cycle_staff',is_staff=True)
        cls.customer=Customer.objects.create(Cid='V0001',Cname='Customer',Caddress='Address',Chouseholdsize=1,Cmealsperweek=1,Cuser=cls.user)
        cls.member=Customer.objects.create(Cid='V0002',Cname='Member',Caddress='Address',Chouseholdsize=1,Cmealsperweek=1,Cuser=cls.other)
        cls.nonmember=Customer.objects.create(Cid='V0003',Cname='Outsider',Caddress='Address',Chouseholdsize=1,Cmealsperweek=1,Cuser=cls.outsider)
        cls.product=Product.objects.create(Pid='V0001',Pname='Milk',Pcategory_id='dairy',Psize='pack',Pprice=2,Plowstock=0)
    def setUp(self):
        self.today=timezone.localdate()
        self.plan=Subscription.objects.create(Scustomer=self.customer,Sproduct=self.product,Squantity=1,Sinterval=7,Snextdate=self.today,Sceiling=10,Screated=self.today)
        for i in range(3): Item.objects.create(Iproduct=self.product,Ireceived=self.today)
        self.client.force_login(self.user);session=self.client.session;session['Cid']=self.customer.pk;session.save()
    def test_edit_does_not_restore_due_date_after_processing(self):
        original=SubscriptionEditForm.is_valid
        def interleave(form):
            valid=original(form)
            process_due_subscriptions(self.today)
            return valid
        with patch.object(SubscriptionEditForm,'is_valid',autospec=True,side_effect=interleave):
            response=self.client.post(f'/store/subscriptions/{self.plan.pk}/edit', {'Squantity':2,'Sinterval':14,'Sceiling':20,'consent':'on'})
        self.assertEqual(response.status_code,302)
        self.plan.refresh_from_db()
        self.assertEqual((self.plan.Snextdate,self.plan.Squantity,self.plan.Sinterval),(self.today+timedelta(days=7),2,14))
        self.assertEqual((Orders.objects.count(),SubscriptionCycle.objects.count()),(1,1))
        self.assertEqual(process_due_subscriptions(self.today),[])
    def test_edit_does_not_reactivate_concurrently_cancelled_plan(self):
        original=SubscriptionEditForm.is_valid
        def interleave(form):
            valid=original(form)
            Subscription.objects.filter(pk=self.plan.pk).update(Sstatus='cancelled')
            return valid
        with patch.object(SubscriptionEditForm,'is_valid',autospec=True,side_effect=interleave):
            self.client.post(f'/store/subscriptions/{self.plan.pk}/edit', {'Squantity':2,'Sinterval':14,'Sceiling':20,'consent':'on'})
        self.plan.refresh_from_db()
        self.assertEqual((self.plan.Sstatus,self.plan.Squantity,self.plan.Snextdate),('cancelled',1,self.today))

    def test_same_scheduled_cycle_is_not_reprocessed_even_after_cancel(self):
        cycle=process_due_subscriptions(self.today)[0]
        self.assertEqual(cycle.SCscheduleddate,self.today)
        response=self.client.post(f'/store/orders/{cycle.SCorder_id}',{'action':'cancel'})
        self.assertContains(response,'was cancelled')
        self.assertEqual(process_due_subscriptions(self.today),[])
        Subscription.objects.filter(pk=self.plan.pk).update(Snextdate=self.today)
        with self.assertRaises(ScheduledCycleConflict): process_due_subscriptions(self.today)
        self.plan.refresh_from_db();self.assertEqual(self.plan.Snextdate,self.today)
        self.assertEqual((Orders.objects.count(),SubscriptionCycle.objects.count()),(1,1))
        self.assertEqual(Orders.objects.get().Opayment,'refunded')
        with self.assertRaises(IntegrityError), transaction.atomic():
            SubscriptionCycle.objects.create(SCsubscription=self.plan,SCdate=self.today,SCscheduleddate=self.today,SCresult='failed')
    def test_skip_records_scheduled_date_and_duplicate_skip_rolls_back(self):
        response=self.client.post(f'/store/subscriptions/{self.plan.pk}', {'action':'skip'}, follow=True)
        self.assertContains(response, 'skipped')
        cycle=SubscriptionCycle.objects.get()
        self.assertEqual((cycle.SCresult,cycle.SCscheduleddate),('skipped',self.today))
        Subscription.objects.filter(pk=self.plan.pk).update(Snextdate=self.today)
        response=self.client.post(f'/store/subscriptions/{self.plan.pk}', {'action':'skip'}, follow=True)
        self.assertContains(response, 'could not be skipped')
        self.plan.refresh_from_db();self.assertEqual(self.plan.Snextdate,self.today)
        self.assertEqual(SubscriptionCycle.objects.count(),1)

    def test_ambiguous_legacy_cycle_fails_closed(self):
        SubscriptionCycle.objects.create(SCsubscription=self.plan,SCdate=self.today,SCresult='failed')
        with self.assertRaises(ScheduledCycleConflict): process_due_subscriptions(self.today)
        self.plan.refresh_from_db();self.assertEqual(self.plan.Snextdate,self.today)
        self.assertEqual(Orders.objects.count(),0)
    def test_cancellation_outcomes_visible_only_to_group_members(self):
        order=Orders.objects.create(Oid='V00001',Odate=self.today,Oaddress='Private address',Ocustomer=self.customer,Ostatus='cancelled',Opayment='refunded')
        group=GroupPurchase.objects.create(Gname='Test group',Gcode='safe-group-code',Gaddress='Shared address',Gstatus='ordered',Gcreated=self.today,Gorganiser=self.customer,Gorder=order)
        GroupMember.objects.create(GMgroup=group,GMcustomer=self.customer)
        GroupMember.objects.create(GMgroup=group,GMcustomer=self.member)
        GroupLine.objects.create(GLgroup=group,GLcustomer=self.member,GLproduct=self.product,GLquantity=2)
        SubscriptionCycle.objects.create(SCsubscription=self.plan,SCdate=self.today,SCscheduleddate=self.today,SCresult='ordered',SCorder=order,SCnote='Order V00001 for $4.00')
        page=self.client.get('/store/subscriptions');self.assertContains(page,'Current order status: Cancelled');self.assertContains(page,'Refunded (simulated)')
        session=self.client.session;session['Cid']=self.member.pk;session.save()
        page=self.client.get(f'/store/groups/{group.pk}');self.assertContains(page,'Current order status: Cancelled');self.assertContains(page,'Refunded (simulated)')
        self.assertNotContains(page,'Private address');self.assertNotContains(page,'/store/orders/V00001');self.assertNotContains(page,'$4.00');self.assertNotContains(page,'what you owe')
        self.assertContains(self.client.get('/store/groups'),'Refunded (simulated)')
        session=self.client.session;session['Cid']=self.nonmember.pk;session.save()
        self.assertEqual(self.client.get(f'/store/groups/{group.pk}').status_code,302)
        staff=Client();staff.force_login(self.staff)
        page=staff.get(f'/adminpanel/orders/{order.pk}/');self.assertContains(page,'linked order: Cancelled');self.assertContains(page,'Refunded (simulated)')
    def test_customer_cannot_edit_others_plan_and_csrf(self):
        session=self.client.session;session['Cid']=self.member.pk;session.save()
        self.assertEqual(self.client.post(f'/store/subscriptions/{self.plan.pk}/edit',{'Squantity':2,'Sinterval':7,'Sceiling':20}).status_code,302)
        self.plan.refresh_from_db();self.assertEqual(self.plan.Squantity,1)
        c=Client(enforce_csrf_checks=True);c.force_login(self.user);session=c.session;session['Cid']=self.customer.pk;session.save()
        self.assertEqual(c.post(f'/store/subscriptions/{self.plan.pk}/edit',{'Squantity':2,'Sinterval':7,'Sceiling':20}).status_code,403)

class SubscriptionProcessingRaceTests(TransactionTestCase):
    def test_two_processors_and_safe_retry(self):
        Category.objects.get_or_create(Ccode='dairy',defaults={'Cname':'Dairy, Chilled & Eggs'})
        user=User.objects.create_user('race_plan')
        customer=Customer.objects.create(Cid='V0004',Cname='Race',Caddress='x',Chouseholdsize=1,Cmealsperweek=1,Cuser=user)
        product=Product.objects.create(Pid='V0004',Pname='Milk',Pcategory_id='dairy',Psize='pack',Pprice=2,Plowstock=0)
        today=timezone.localdate()
        Subscription.objects.create(Scustomer=customer,Sproduct=product,Squantity=1,Sinterval=7,Snextdate=today,Sceiling=10,Screated=today)
        for i in range(2): Item.objects.create(Iproduct=product,Ireceived=today)
        barrier=Barrier(2)
        def run(_):
            close_old_connections();barrier.wait()
            try: return len(process_due_subscriptions(today))
            except DatabaseError: return 'sqlite busy'
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,range(2)))
        process_due_subscriptions(today)
        self.assertEqual((Orders.objects.count(),SubscriptionCycle.objects.count()),(1,1))
        self.assertEqual(Orders.objects.get().Opayment,'paid')
        print(f'Subscription processor race results: {results}; orders=1 cycles=1')
