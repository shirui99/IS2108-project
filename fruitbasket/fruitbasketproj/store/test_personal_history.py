from datetime import date
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from adminpanel.models import Customer, Product, Orders, Item, GroupPurchase, Subscription, SubscriptionCycle
from store.restock import get_customer_purchase_history, get_restock_suggestions
from store.subscriptions import suggest_interval


class PersonalHistoryTests(TestCase):
    def test_linked_orders_do_not_change_inputs_or_prediction(self):
        user = User.objects.create_user('origin_history')
        customer = Customer.objects.create(Cid='OH001', Cname='Buyer', Caddress='A', Chouseholdsize=2, Cmealsperweek=1, Cuser=user)
        product = Product.objects.create(Pid='OH001', Pname='Apple', Pcategory_id='fruit', Psize='pack', Pprice=2, Plowstock=0)
        def order(oid, day, quantity):
            obj = Orders.objects.create(Oid=oid, Ocustomer=customer, Oaddress='A', Odate=date(2026, 1, day), Ostatus='delivered')
            for _ in range(quantity):
                Item.objects.create(Iorder=obj, Iproduct=product, Ireceived=date(2026,1,1), Istatus='delivered')
            return obj
        order('OH0001', 1, 1)
        order('OH0002', 10, 2)
        Item.objects.create(Iproduct=product, Ireceived=date(2026,1,1), Istatus='available')
        # A deterministic pipeline makes the resulting date depend on the interval.
        class Pipeline:
            def predict(self, row):
                return [row.iloc[0]['previous_interval_days']]
        artifacts={'pipeline':Pipeline(), 'metadata':{'training_only_category_medians':{'fruit':9}, 'training_only_overall_median':14}, 'error':None}
        with patch('store.restock.load_restock_artifacts', return_value=artifacts):
            before_history=get_customer_purchase_history(customer.pk)
            before=get_restock_suggestions(customer.pk, today=date(2026,1,20))
            group=order('OH0003',10,4)
            suborder=order('OH0004',15,3)
            GroupPurchase.objects.create(Gname='Group', Gcode='origin-test', Gaddress='A', Gstatus='ordered', Gcreated=date(2026,1,1), Gorganiser=customer, Gorder=group)
            subscription=Subscription.objects.create(Scustomer=customer, Sproduct=product, Squantity=1, Sinterval=7, Snextdate=date(2026,2,1), Sceiling=10, Screated=date(2026,1,1))
            SubscriptionCycle.objects.create(SCsubscription=subscription, SCdate=date(2026,1,15), SCresult='ordered', SCorder=suborder)
            self.assertEqual(get_customer_purchase_history(customer.pk), before_history)
            after=get_restock_suggestions(customer.pk, today=date(2026,1,20))
            self.assertEqual(after,before)
            self.assertEqual(before_history[product.pk], [{'purchased_at':date(2026,1,1),'purchased_quantity':1}, {'purchased_at':date(2026,1,10),'purchased_quantity':2}])
            self.assertEqual((after[0]['interval_days'], after[0]['restock_date'], after[0]['status']), (9,'2026-01-19','MODEL'))

    def test_same_day_origins_and_subscription_interval(self):
        user = User.objects.create_user('same_day_buyer')
        customer = Customer.objects.create(Cid='SH001', Cname='Buyer', Caddress='A', Chouseholdsize=2, Cmealsperweek=1, Cuser=user)
        product = Product.objects.create(Pid='SH001', Pname='Apple', Pcategory_id='fruit', Psize='pack', Pprice=2, Plowstock=0)

        def purchase(oid, day, quantity):
            order = Orders.objects.create(Oid=oid, Ocustomer=customer, Oaddress='A', Odate=date(2026, 1, day), Ostatus='delivered')
            for _ in range(quantity):
                Item.objects.create(Iorder=order, Iproduct=product, Ireceived=date(2026, 1, 1), Istatus='delivered')
            return order

        purchase('SH0001', 1, 1)
        purchase('SH0002', 10, 2)
        group_order = purchase('SH0003', 10, 4)
        subscription_order = purchase('SH0004', 10, 3)
        GroupPurchase.objects.create(Gname='Group', Gcode='same-day-origin', Gaddress='A', Gstatus='ordered', Gcreated=date(2026, 1, 1), Gorganiser=customer, Gorder=group_order)
        subscription = Subscription.objects.create(Scustomer=customer, Sproduct=product, Squantity=1, Sinterval=7, Snextdate=date(2026, 2, 1), Sceiling=10, Screated=date(2026, 1, 1))
        SubscriptionCycle.objects.create(SCsubscription=subscription, SCdate=date(2026, 1, 10), SCresult='ordered', SCorder=subscription_order)

        later_group = purchase('SH0006', 12, 1)
        later_subscription = purchase('SH0007', 28, 1)
        GroupPurchase.objects.create(Gname='Later group', Gcode='later-origin', Gaddress='A', Gstatus='ordered', Gcreated=date(2026, 1, 1), Gorganiser=customer, Gorder=later_group)
        SubscriptionCycle.objects.create(SCsubscription=subscription, SCdate=date(2026, 1, 28), SCresult='ordered', SCorder=later_subscription)

        # The deterministic pipeline ties the selected subscription schedule to personal purchase spacing.
        class Pipeline:
            def predict(self, row):
                return [row.iloc[0]['previous_interval_days']]
        artifacts = {'pipeline': Pipeline(), 'metadata': {'training_only_category_medians': {'fruit': 9}, 'training_only_overall_median': 14}, 'error': None}
        with patch('store.restock.load_restock_artifacts', return_value=artifacts):
            self.assertEqual(get_customer_purchase_history(customer.pk)[product.pk], [
                {'purchased_at': date(2026, 1, 1), 'purchased_quantity': 1},
                {'purchased_at': date(2026, 1, 10), 'purchased_quantity': 2},
            ])
            self.assertEqual(suggest_interval(customer, product), (7, 'ML estimate'))
            purchase('SH0005', 24, 1)
            self.assertEqual(suggest_interval(customer, product), (14, 'ML estimate'))
