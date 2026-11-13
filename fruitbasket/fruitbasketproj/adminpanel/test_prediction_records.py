from datetime import date
from unittest.mock import patch
from django.contrib.auth.models import User
from django.db import DatabaseError
from django.test import Client, TestCase
from adminpanel.models import Customer, Product, Orders, Item, RestockCapture, Subscription, SubscriptionCycle, GroupPurchase
from store.restock import get_customer_purchase_history
from store.subscriptions import suggest_interval


class PredictionCaptureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('capture_staff', is_staff=True)
        cls.user = User.objects.create_user('capture_buyer')
        cls.customer = Customer.objects.create(Cid='PC001', Cname='Snapshot buyer', Caddress='A', Chouseholdsize=2, Cmealsperweek=1, Cuser=cls.user)
        cls.product = Product.objects.create(Pid='PC001', Pname='Snapshot apple', Pcategory_id='fruit', Psize='pack', Pprice=3, Plowstock=0)
        for index, day in enumerate([1, 10]):
            order = Orders.objects.create(Oid=f'PC000{index}', Ocustomer=cls.customer, Odate=date(2026, 1, day), Oaddress='A', Ostatus='delivered')
            Item.objects.create(Iproduct=cls.product, Iorder=order, Ireceived=date(2026,1,1), Istatus='delivered', Ipurchasedprice=2)

    def setUp(self):
        self.client.force_login(self.staff)
        self.data = {'customer':self.customer.pk, 'product':self.product.pk}

    def capture(self):
        return self.client.post('/adminpanel/predictions/capture/', self.data)

    def test_capture_duplicate_changed_inputs_filters_and_snapshot(self):
        self.assertEqual(self.capture().status_code, 302)
        record = RestockCapture.objects.get()
        self.assertEqual(record.snapshot['inputs'], {'latest_purchase_at':'2026-01-10', 'household_size':2, 'category':'fruit', 'purchased_quantity':1, 'previous_interval_days':9, 'history_count':2})
        original = record.snapshot
        self.capture()
        self.assertEqual(RestockCapture.objects.count(), 1)
        Customer.objects.filter(pk=self.customer.pk).update(Cname='Changed buyer', Chouseholdsize=4)
        Product.objects.filter(pk=self.product.pk).update(Pname='Changed product')
        self.capture()
        self.assertEqual(RestockCapture.objects.count(), 2)
        record.refresh_from_db()
        self.assertEqual(record.snapshot, original)
        detail = self.client.get(f'/adminpanel/predictions/{record.pk}/')
        self.assertContains(detail, 'Snapshot buyer')
        self.assertContains(detail, 'Snapshot apple')
        self.assertContains(detail, 'not a verified artifact identity')
        for query in [self.data, {'customer':self.customer.pk}, {'product':self.product.pk}]:
            self.assertEqual(len(self.client.get('/adminpanel/predictions/', query).context['records']), 2)
        other_product=Product.objects.create(Pid='PC002', Pname='No captures', Pcategory_id='fruit', Psize='pack', Pprice=2, Plowstock=0)
        self.assertEqual(len(self.client.get('/adminpanel/predictions/', {'product':other_product.pk}).context['records']), 0)
        before=list(RestockCapture.objects.values())
        self.client.get(f'/adminpanel/predictions/{record.pk}/')
        self.client.get('/adminpanel/predictions/')
        self.assertEqual(list(RestockCapture.objects.values()),before)
        self.assertContains(self.client.get('/adminpanel/predictions/', {'customer':'bad'}), 'Select a valid choice')
        self.assertContains(self.client.get('/adminpanel/predictions/', {'product':'bad'}), 'No prediction records')

    @patch('store.restock.load_restock_artifacts', return_value={'pipeline':None, 'metadata':None, 'error':'Missing artifacts'})
    @patch('adminpanel.prediction_records.load_restock_artifacts', return_value={'metadata':None})
    def test_unavailable_and_unknown_history(self, metadata, artifacts):
        self.capture()
        record = RestockCapture.objects.get()
        self.assertEqual(record.snapshot['result']['status'], 'UNAVAILABLE')
        self.assertIsNone(record.snapshot['result']['interval_days'])
        self.assertIsNone(record.snapshot['declared_version'])
        self.assertContains(self.client.get(f'/adminpanel/predictions/{record.pk}/'), 'No estimate available')
        Item.objects.all().delete()
        self.capture()
        latest = RestockCapture.objects.first()
        self.assertIsNone(latest.snapshot['inputs']['latest_purchase_at'])
        self.assertIsNone(latest.snapshot['inputs']['purchased_quantity'])

    @patch('adminpanel.prediction_records.predict_restock')
    def test_model_initial_and_changed_output(self, predict):
        predict.return_value={'status':'MODEL', 'interval_days':9, 'restock_date':'2026-01-19', 'reason':'Random Forest prediction'}
        self.capture()
        first=RestockCapture.objects.first()
        self.assertEqual(first.snapshot['result'], predict.return_value)
        self.assertContains(self.client.get(f'/adminpanel/predictions/{first.pk}/'), 'ML estimate')
        predict.return_value={'status':'INITIAL', 'interval_days':14, 'restock_date':'2026-01-24', 'reason':'Insufficient purchase history'}
        self.capture()
        self.assertEqual(RestockCapture.objects.count(),2)
        second=RestockCapture.objects.first()
        self.assertContains(self.client.get(f'/adminpanel/predictions/{second.pk}/'), 'Initial estimate')
        self.assertEqual(second.snapshot['result'],predict.return_value)

    def test_permissions_methods_csrf_and_validation(self):
        self.assertEqual(self.client.get('/adminpanel/predictions/capture/').status_code, 405)
        self.assertEqual(self.client.post('/adminpanel/predictions/').status_code, 405)
        self.assertEqual(self.client.get('/adminpanel/predictions/999999/').status_code, 404)
        self.assertContains(self.client.post('/adminpanel/predictions/capture/', {'customer':'bad','product':'bad'}), 'Select a valid choice')
        inactive = User.objects.create_user('capture_inactive', is_staff=True, is_active=False)
        for user in [None, self.user, inactive]:
            client=Client()
            if user: client.force_login(user)
            self.assertEqual(client.get('/adminpanel/predictions/').status_code, 302)
            self.assertEqual(client.post('/adminpanel/predictions/capture/', self.data).status_code, 302)
        self.staff.is_staff=False; self.staff.save()
        self.assertEqual(self.capture().status_code, 302)
        self.staff.is_staff=True; self.staff.save()
        client=Client(enforce_csrf_checks=True); client.force_login(self.staff); client.get('/adminpanel/predictions/')
        for token in ['', 'invalid']:
            self.assertEqual(client.post('/adminpanel/predictions/capture/', {**self.data,'csrfmiddlewaretoken':token}).status_code, 403)
        self.assertEqual(client.post('/adminpanel/predictions/capture/', {**self.data,'csrfmiddlewaretoken':client.cookies['csrftoken'].value}).status_code,302)

    def test_get_and_subscription_do_not_capture_and_failed_save(self):
        session=self.client.session; session['Cid']=self.customer.pk; session.save()
        for path in ['/adminpanel/predictions/', '/store/restock/']:
            self.assertEqual(self.client.get(path).status_code,200)
        suggest_interval(self.customer, self.product)
        self.assertFalse(RestockCapture.objects.exists())
        with patch('adminpanel.prediction_records.capture_current', side_effect=DatabaseError('busy')):
            self.assertContains(self.capture(), 'could not be saved')
        self.assertFalse(RestockCapture.objects.exists())

    def test_group_and_subscription_orders_excluded_from_history(self):
        # Linked origins are excluded from personal prediction history.
        orders=list(Orders.objects.order_by('Odate'))
        GroupPurchase.objects.create(Gname='History group', Gcode='history-group', Gaddress='A', Gstatus='ordered', Gcreated=date(2026,1,1), Gorganiser=self.customer, Gorder=orders[0])
        sub=Subscription.objects.create(Scustomer=self.customer, Sproduct=self.product, Squantity=1, Sinterval=7, Snextdate=date(2026,2,1), Sceiling=10, Screated=date(2026,1,1))
        SubscriptionCycle.objects.create(SCsubscription=sub, SCdate=date(2026,1,10), SCresult='ordered', SCorder=orders[1])
        self.assertNotIn(self.product.pk, get_customer_purchase_history(self.customer.pk))

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PredictionMigrationTests(TransactionTestCase):
    def test_additive_migration_preserves_populated_history(self):
        old=[('adminpanel','0014_cancellation_history')]
        new=[('adminpanel','0015_restock_capture')]
        def restore_schema():
            executor=MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        self.addCleanup(restore_schema)
        executor=MigrationExecutor(connection); executor.migrate(old)
        try:
            apps=executor.loader.project_state(old).apps
            apps.get_model('adminpanel','Category').objects.get_or_create(Ccode='fruit', defaults={'Cname':'Fruit & Vegetables'})
            user=apps.get_model('auth','User').objects.create(username='capture_migration')
            customer=apps.get_model('adminpanel','Customer').objects.create(Cid='PM001', Cname='Existing', Caddress='A', Chouseholdsize=1, Cmealsperweek=0, Cuser_id=user.pk)
            product=apps.get_model('adminpanel','Product').objects.create(Pid='PM001', Pname='Existing', Pcategory_id='fruit', Psize='pack', Pprice=2, Plowstock=0, Pactive=False)
            order=apps.get_model('adminpanel','Orders').objects.create(Oid='PM0001', Ocustomer_id=customer.pk, Odate=date(2025,1,1), Oaddress='Historical', Ostatus='cancelled', Opayment='refunded')
            apps.get_model('adminpanel','Item').objects.create(Iproduct_id=product.pk, Ireceived=date(2025,1,1), Istatus='available')
            def snapshot():
                with connection.cursor() as cursor:
                    return {table:cursor.execute('SELECT * FROM '+table).fetchall() for table in ['adminpanel_customer','adminpanel_product','adminpanel_orders','adminpanel_item']}
            before=snapshot()
            executor=MigrationExecutor(connection); executor.migrate(new)
            self.assertEqual(snapshot(),before)
            self.assertFalse(RestockCapture.objects.exists())
        finally:
            restore_schema()
