from datetime import date
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class CancellationMigrationTests(TransactionTestCase):
    old = [('adminpanel', '0013_subscription_cycle_identity')]
    new = [('adminpanel', '0014_cancellation_history')]

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def setUp(self):
        self.apps = self.migrate(self.old)

    def tearDown(self):
        self.migrate(self.new)
        super().tearDown()

    def test_existing_cancelled_order_and_links_survive_without_backfill(self):
        apps=self.apps
        Category=apps.get_model('adminpanel','Category')
        Category.objects.get_or_create(Ccode='fruit',defaults={'Cname':'Fruit & Vegetables'})
        User=apps.get_model('auth','User')
        Customer=apps.get_model('adminpanel','Customer')
        Product=apps.get_model('adminpanel','Product')
        Orders=apps.get_model('adminpanel','Orders')
        Item=apps.get_model('adminpanel','Item')
        Group=apps.get_model('adminpanel','GroupPurchase')
        Subscription=apps.get_model('adminpanel','Subscription')
        Cycle=apps.get_model('adminpanel','SubscriptionCycle')
        user=User.objects.create(username='migration_ad20')
        customer=Customer.objects.create(Cid='M0020',Cname='Fixture',Caddress='Old address',Chouseholdsize=1,Cmealsperweek=1,Cuser_id=user.pk)
        product=Product.objects.create(Pid='M0020',Pname='Fixture product',Pcategory_id='fruit',Psize='pack',Pprice=5,Plowstock=0)
        order=Orders.objects.create(Oid='M00020',Ocustomer_id=customer.pk,Odate=date(2024,1,1),Oaddress='Historical address',Ostatus='cancelled',Opayment='refunded')
        Item.objects.create(Iproduct_id=product.pk,Ireceived=date(2024,1,1),Istatus='available',Ipurchasedprice=None)
        group=Group.objects.create(Gname='Legacy group',Gcode='legacy-ad20',Gaddress='Group address',Gstatus='ordered',Gcreated=date(2024,1,1),Gorganiser_id=customer.pk,Gorder_id=order.pk)
        subscription=Subscription.objects.create(Scustomer_id=customer.pk,Sproduct_id=product.pk,Squantity=1,Sinterval=7,Snextdate=date(2024,2,1),Sceiling=10,Sstatus='active',Screated=date(2024,1,1))
        cycle=Cycle.objects.create(SCsubscription_id=subscription.pk,SCdate=date(2024,1,1),SCresult='ordered',SCorder_id=order.pk)
        def snapshot():
            with connection.cursor() as cursor:
                names=['adminpanel_orders','adminpanel_item','adminpanel_grouppurchase','adminpanel_subscription','adminpanel_subscriptioncycle']
                return {name:sorted(cursor.execute('SELECT * FROM '+name).fetchall(),key=repr) for name in names}
        before=snapshot()
        current=self.migrate(self.new)
        self.assertEqual(before,snapshot())
        self.assertFalse(current.get_model('adminpanel','OrderCancellation').objects.exists())
        self.assertFalse(current.get_model('adminpanel','CancelledAllocation').objects.exists())
        self.assertEqual(current.get_model('adminpanel','GroupPurchase').objects.get(pk=group.pk).Gorder_id,order.pk)
        self.assertEqual(current.get_model('adminpanel','SubscriptionCycle').objects.get(pk=cycle.pk).SCorder_id,order.pk)
