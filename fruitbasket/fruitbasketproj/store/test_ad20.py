from unittest.mock import patch
from django.test import Client
from django.db import DatabaseError
from adminpanel.models import CancelledAllocation, Customer, InventoryBatch, Item, OrderCancellation
from store.test_cancellation_fulfilment import CancellationTests
from store.cancellation import cancel_order

class AD20Tests(CancellationTests):
    def test_staff_reason_snapshots_mixed_values_and_repeat(self):
        batch=InventoryBatch.objects.create(Breference='CANCEL-BATCH',Bproduct=self.product,Breceived=self.today if hasattr(self,'today') else self.order.Odate,Bquantity=2)
        Item.objects.filter(pk=self.packs[0].pk).update(Ibatch=batch)
        Item.objects.create(Iproduct=self.product,Ireceived=self.order.Odate,Iorder=self.order,Istatus='allocated',Ipurchasedprice=None)
        Item.objects.create(Iproduct=self.product,Ireceived=self.order.Odate,Iorder=self.order,Istatus='allocated',Ipurchasedprice=3)
        staff=Client();staff.force_login(self.staff)
        path=f'/adminpanel/orders/{self.order.pk}/cancel/'
        self.assertContains(staff.post(path,{'reason':' '}),'This field is required')
        self.assertEqual(staff.post(path,{'reason':'Requested by customer'}).status_code,302)
        record=OrderCancellation.objects.get()
        self.assertEqual((record.source,record.employee,record.reason),('staff',self.staff,'Requested by customer'))
        self.assertEqual(sum(record.allocations.values_list('quantity',flat=True)),4)
        self.assertEqual(set(record.allocations.values_list('unit_price',flat=True)),{None,2,3})
        self.assertEqual(record.allocations.filter(batch_reference='CANCEL-BATCH').count(),1)
        self.assertTrue(record.allocations.filter(batch_reference__isnull=True).exists())
        self.assertEqual(staff.post(path,{'reason':'Repeat'}).status_code,302)
        self.assertEqual(OrderCancellation.objects.count(),1)
        self.assertEqual(Item.objects.filter(Iorder=self.order).count(),0)
        self.assertContains(self.client.get(f'/store/orders/{self.order.pk}'),'Allocation retained at cancellation')
        self.assertContains(staff.get(f'/adminpanel/orders/{self.order.pk}/'),'Requested by customer')
    def test_customer_snapshot_and_original_description_retained(self):
        self.cancel()
        record=OrderCancellation.objects.get()
        self.assertEqual(record.source,'customer');self.assertIsNone(record.employee)
        self.product.Pname='Renamed';self.product.save()
        self.assertEqual(set(record.allocations.values_list('product_name',flat=True)),{'Milk'})
        self.assertEqual(sum(record.allocations.values_list('quantity',flat=True)),2)
    def test_cancelled_order_owner_cannot_be_reassigned(self):
        from django.contrib.auth.models import User
        self.cancel()
        other=User.objects.create_user('snapshot_other')
        customer=Customer.objects.create(Cid='OTHER',Cname='Other',Caddress='x',Chouseholdsize=1,Cmealsperweek=1,Cuser=other)
        staff=Client();staff.force_login(self.staff)
        data={'action':'update','Oid':self.order.pk,'Ocustomer':customer.pk,'Odate':self.order.Odate.isoformat(),'Oaddress':'Recorded'}
        self.assertContains(staff.post(f'/adminpanel/order_new/{self.order.pk}',data),'customer cannot change')
        self.order.refresh_from_db();self.assertEqual(self.order.Ocustomer_id,self.customer.pk)

    def test_snapshot_failure_rolls_back_everything(self):
        with patch('store.cancellation.CancelledAllocation.objects.bulk_create',side_effect=DatabaseError('forced')):
            self.assertContains(self.cancel(),'database is busy')
        self.order.refresh_from_db()
        self.assertEqual((self.order.Ostatus,self.order.Opayment),('placed','paid'))
        self.assertEqual(self.order.order_items.count(),2)
        self.assertFalse(OrderCancellation.objects.exists())
    def test_staff_access_csrf_and_later_status(self):
        path=f'/adminpanel/orders/{self.order.pk}/cancel/'
        c=Client();self.assertEqual(c.post(path,{'reason':'x'}).status_code,302)
        c.force_login(self.user);self.assertEqual(c.post(path,{'reason':'x'}).status_code,302)
        c=Client(enforce_csrf_checks=True);c.force_login(self.staff)
        self.assertEqual(c.post(path,{'reason':'x'}).status_code,403)
        c.get(f'/adminpanel/orders/{self.order.pk}/')
        self.assertEqual(c.get(path).status_code,405)
        self.assertEqual(c.post(path,{'reason':'x','csrfmiddlewaretoken':c.cookies['csrftoken'].value}).status_code,302)
        self.assertEqual(c.post('/adminpanel/orders/MISSING/cancel/',{'reason':'x','csrfmiddlewaretoken':c.cookies['csrftoken'].value}).status_code,404)

    def test_cancelled_address_and_date_are_immutable(self):
        from datetime import timedelta
        self.cancel()
        staff=Client();staff.force_login(self.staff)
        path=f'/adminpanel/order_new/{self.order.pk}'
        data={'action':'update','Oid':self.order.pk,'Ocustomer':self.customer.pk,'Odate':self.order.Odate.isoformat(),'Oaddress':self.order.Oaddress}
        self.assertContains(staff.post(path,dict(data,Oaddress='Changed')), 'delivery address cannot change')
        self.assertContains(staff.post(path,dict(data,Odate=(self.order.Odate+timedelta(days=1)).isoformat())), 'order date cannot change')
        self.order.refresh_from_db()
        self.assertEqual((self.order.Oaddress,self.order.Odate),('Recorded',self.packs[0].Ireceived))
        self.assertEqual(staff.post(path,data).status_code,302)

    def test_refund_shortfall_and_database_error_roll_back(self):
        from django.db.models.query import QuerySet
        original=QuerySet.update
        for fail_with_exception in [False, True]:
            def refund_failure(queryset,**kwargs):
                if kwargs.get('Opayment') == 'refunded':
                    if fail_with_exception: raise DatabaseError('forced')
                    return 0
                return original(queryset,**kwargs)
            with self.subTest(exception=fail_with_exception), patch.object(QuerySet,'update',refund_failure):
                response=self.cancel()
                self.assertContains(response, 'database is busy' if fail_with_exception else 'simulated refund could not be recorded')
                self.order.refresh_from_db()
                self.assertEqual((self.order.Ostatus,self.order.Opayment),('placed','paid'))
                self.assertEqual(self.order.order_items.count(),2)
                self.assertEqual(set(self.order.order_items.values_list('Istatus','Ipurchasedprice')), {('allocated', 2)})
                self.assertFalse(OrderCancellation.objects.exists())
                self.assertFalse(CancelledAllocation.objects.exists())

    def test_already_refunded_and_unknown_payment_states(self):
        from adminpanel.models import Orders
        Orders.objects.filter(pk=self.order.pk).update(Opayment='unknown')
        self.assertContains(self.cancel(),'payment state is invalid')
        self.order.refresh_from_db();self.assertEqual((self.order.Ostatus,self.order.Opayment),('placed','unknown'))
        self.assertFalse(OrderCancellation.objects.exists())
        Orders.objects.filter(pk=self.order.pk).update(Opayment='refunded')
        self.assertContains(self.cancel(),'was cancelled')
        record=OrderCancellation.objects.get()
        self.assertEqual((record.payment_before,record.payment_after),('refunded','refunded'))

    def test_staff_direct_later_status_inactive_invalid_csrf_and_legacy_cancelled(self):
        from django.contrib.auth.models import User
        from adminpanel.models import Orders
        path=f'/adminpanel/orders/{self.order.pk}/cancel/'
        c=Client(enforce_csrf_checks=True);c.force_login(self.staff)
        c.get(f'/adminpanel/orders/{self.order.pk}/')
        self.assertEqual(c.post(path,{'reason':'x','csrfmiddlewaretoken':'invalid'}).status_code,403)
        token=c.cookies['csrftoken'].value
        for status in ['preparing','dispatched','delivered','cancelled']:
            Orders.objects.filter(pk=self.order.pk).update(Ostatus=status)
            self.assertEqual(c.post(path,{'reason':'x','csrfmiddlewaretoken':token}).status_code,302)
            self.order.refresh_from_db();self.assertEqual(self.order.Ostatus,status)
            self.assertFalse(OrderCancellation.objects.exists())
            self.assertEqual(self.order.order_items.count(),2)
        inactive=User.objects.create_user('inactive_ad20',is_staff=True,is_active=False)
        c=Client();c.force_login(inactive)
        self.assertEqual(c.post(path,{'reason':'x'}).status_code,302)
        self.assertFalse(OrderCancellation.objects.exists())
