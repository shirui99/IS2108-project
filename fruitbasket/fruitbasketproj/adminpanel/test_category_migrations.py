from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class CategoryMigrationTests(TransactionTestCase):
    old = [('adminpanel', '0007_item_ipurchasedprice_product_pbulkprice_and_more')]
    new = [('adminpanel', '0008_categories')]

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def setUp(self):
        self.apps = self.migrate(self.old)

    def tearDown(self):
        # Restore the schema for Django's test cleanup even after a rejected migration.
        Product = self.apps.get_model('adminpanel', 'Product')
        Product.objects.filter(Pcategory='unexpected').update(Pcategory='fruit')
        self.migrate(self.new)
        super().tearDown()

    def product(self, code='fruit'):
        return self.apps.get_model('adminpanel', 'Product').objects.create(
            Pid='M0001', Pname='Historical fruit', Pcategory=code, Psize='1 pack',
            Pprice=9, Plowstock=0, Pactive=False, Pexpirydays=0)

    def test_populated_migration_and_guarded_rollback(self):
        product = self.product()
        user = self.apps.get_model('auth', 'User').objects.create(username='migration')
        customer = self.apps.get_model('adminpanel', 'Customer').objects.create(
            Cid='M0001', Cname='Fixture', Caddress='Fixture', Chouseholdsize=1,
            Cmealsperweek=1, Cuser=user)
        order = self.apps.get_model('adminpanel', 'Orders').objects.create(
            Oid='M00001', Odate=date(2026, 1, 1), Oaddress='Fixture',
            Ocustomer=customer, Ostatus='delivered')
        self.apps.get_model('adminpanel', 'Item').objects.create(
            Ireceived=date(2026, 1, 1), Iproduct=product, Iorder=order,
            Istatus='delivered', Ipurchasedprice=12.34)
        with connection.cursor() as cursor:
            def snapshot():
                rows = {}
                for table in ['adminpanel_product', 'adminpanel_item', 'adminpanel_orders', 'adminpanel_customer']:
                    columns = sorted(row[1] for row in cursor.execute('PRAGMA table_info('+table+')').fetchall())
                    rows[table] = cursor.execute('SELECT '+','.join(columns)+' FROM '+table).fetchall()
                return rows
            before = snapshot()
            apps = self.migrate(self.new)
            self.assertEqual(before, snapshot())
            Category = apps.get_model('adminpanel', 'Category')
            self.assertEqual(Category.objects.count(), 8)
            self.assertEqual(Category.objects.get(pk='fruit').Cname, 'Fruit & Vegetables')
            self.migrate(self.old)
            self.assertEqual(before, snapshot())
            apps = self.migrate(self.new)
            apps.get_model('adminpanel', 'Category').objects.create(Ccode='new', Cname='New category')
            with self.assertRaisesMessage(RuntimeError, 'rollback blocked'):
                self.migrate(self.old)
            self.assertEqual(before, snapshot())

    def test_unexpected_code_aborts_without_reclassification(self):
        product = self.product('unexpected')
        with self.assertRaisesMessage(RuntimeError, 'unexpected category codes'):
            self.migrate(self.new)
        product.refresh_from_db()
        self.assertEqual(product.Pcategory, 'unexpected')
