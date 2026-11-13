from datetime import date
from unittest.mock import patch
from django.contrib.auth.models import User
from django.db import DatabaseError
from django.test import Client, TestCase
from .models import Customer, Product, Orders, Item, Review, ReviewModeration


class ReviewModerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff=User.objects.create_user('moderator',is_staff=True)
        cls.user=User.objects.create_user('review_buyer')
        cls.customer=Customer.objects.create(Cid='RM001',Cname='Buyer',Caddress='A',Chouseholdsize=1,Cmealsperweek=0,Cuser=cls.user)
        cls.product=Product.objects.create(Pid='RM001',Pname='Apple',Pcategory_id='fruit',Psize='pack',Pprice=2,Plowstock=0)
        cls.order=Orders.objects.create(Oid='RM0001',Ocustomer=cls.customer,Odate=date.today(),Oaddress='Historical',Ostatus='delivered')
        cls.item=Item.objects.create(Iproduct=cls.product,Iorder=cls.order,Ireceived=date.today(),Istatus='delivered',Irating=5)
        cls.review=Review.objects.create(Rcustomer=cls.customer,Rproduct=cls.product,Ritem=cls.item,Rrating=5,Rtext='<script>original</script>',Rdate=date.today())
        Item.objects.create(Iproduct=cls.product,Ireceived=date.today(),Istatus='available',Irating=3)

    def setUp(self):
        self.client.force_login(self.staff)
        self.path=f'/adminpanel/reviews/{self.review.pk}/action/'

    def test_hide_restore_public_averages_and_history(self):
        def check(avg, count, visible):
            for path in ['/store/', '/store/product/RM001']:
                response=self.client.get(path)
                product=response.context['product'] if path.endswith('RM001') else list(response.context['products'])[0]
                self.assertEqual((product.rating,product.reviews),(avg,count))
            page=self.client.get('/store/product/RM001')
            self.assertEqual(list(page.context['visible_reviews']), [self.review] if visible else [])
            self.assertNotContains(page,'<script>original</script>')
        check(4,2,True)
        self.assertEqual(self.client.post(self.path,{'action':'hide','reason':'  Inappropriate  '}).status_code,302)
        self.review.refresh_from_db(); self.item.refresh_from_db(); self.order.refresh_from_db()
        self.assertEqual((self.review.Rvisible,self.review.Rrating,self.review.Rtext,self.item.Irating,self.order.Oaddress),(False,5,'<script>original</script>',5,'Historical'))
        event=ReviewModeration.objects.get()
        self.assertEqual((event.action,event.reason,event.employee_id),('hide','Inappropriate',self.staff.pk))
        self.assertIsNotNone(event.created_at)
        check(3,1,False)
        self.client.post(self.path,{'action':'hide','reason':'again'})
        self.assertEqual(ReviewModeration.objects.count(),1)
        self.client.post(self.path,{'action':'restore','reason':'Reviewed'})
        self.review.refresh_from_db(); self.assertTrue(self.review.Rvisible)
        self.assertEqual(ReviewModeration.objects.count(),2)
        check(4,2,True)

    def test_customer_pantry_ratings_linked_and_separate_through_moderation(self):
        # Both packs belong to the reviewer; only one is the review's Ritem.
        Item.objects.filter(Iproduct=self.product, Iorder__isnull=True).delete()
        separate=Item.objects.create(Iproduct=self.product, Iorder=self.order, Ireceived=date.today(), Istatus='delivered')
        buyer=Client();buyer.force_login(self.user)
        session=buyer.session;session['Cid']=self.customer.pk;session.save()
        buyer.post(f'/store/pantry/{self.item.pk}', {'action':'rate','rating':'4'})
        buyer.post(f'/store/pantry/{separate.pk}', {'action':'rate','rating':'2'})
        self.item.refresh_from_db();separate.refresh_from_db();self.review.refresh_from_db()
        self.assertEqual((self.item.Irating,separate.Irating,self.review.Rrating),(4,2,4))
        def check(average, count):
            for url in ['/store/','/store/product/RM001']:
                response=buyer.get(url)
                product=response.context['product'] if url.endswith('RM001') else list(response.context['products'])[0]
                self.assertEqual((product.rating,product.reviews),(average,count))
        check(3,2)
        self.client.post(self.path,{'action':'hide','reason':'Moderated'})
        check(2,1)
        # Re-rating the linked pantry pack must not make a hidden review's rating public.
        buyer.post(f'/store/pantry/{self.item.pk}', {'action':'rate','rating':'1'})
        self.review.refresh_from_db()
        self.assertEqual((self.review.Rrating, self.review.Rvisible), (1, False))
        check(2,1)
        self.client.post(self.path,{'action':'restore','reason':'Restored'})
        check(1.5,2)
        self.review.refresh_from_db()
        self.assertEqual(self.review.Rrating,1)
        self.assertTrue(self.review.Rvisible)
        self.assertContains(buyer.get('/store/product/RM001'), '1 / 5')

    def test_legacy_mismatch_uses_review_rating_without_rewriting_item(self):
        Item.objects.filter(Iproduct=self.product, Iorder__isnull=True).delete()
        Item.objects.filter(pk=self.item.pk).update(Irating=2)
        for url in ['/store/', '/store/product/RM001']:
            response=self.client.get(url)
            product=response.context['product'] if url.endswith('RM001') else list(response.context['products'])[0]
            self.assertEqual((product.rating,product.reviews),(5,1))
        self.item.refresh_from_db()
        self.assertEqual(self.item.Irating,2)

    def test_hidden_only_rating_has_no_public_average(self):
        Item.objects.filter(Iproduct=self.product, Iorder__isnull=True).delete()
        self.client.post(self.path, {'action':'hide', 'reason':'Review'})
        for path in ['/store/', '/store/product/RM001']:
            response=self.client.get(path)
            product=response.context['product'] if path.endswith('RM001') else list(response.context['products'])[0]
            self.assertEqual((product.rating,product.reviews),(None,0))

    def test_validation_access_csrf_unknown_and_rollback(self):
        for reason in ['', '  ', 'x'*1001]:
            response=self.client.post(self.path,{'action':'hide','reason':reason})
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.context['form'].errors)
            self.review.refresh_from_db();self.assertTrue(self.review.Rvisible)
        with patch('adminpanel.review_moderation.ReviewModeration.objects.create',side_effect=DatabaseError('fail')):
            self.assertContains(self.client.post(self.path,{'action':'hide','reason':'Keep this'}),'Keep this')
        self.review.refresh_from_db();self.assertTrue(self.review.Rvisible)
        self.assertFalse(ReviewModeration.objects.exists())
        self.assertEqual(self.client.get('/adminpanel/reviews/999999/').status_code,404)
        self.assertEqual(self.client.post('/adminpanel/reviews/999999/action/',{'action':'hide','reason':'x'}).status_code,404)
        self.assertEqual(self.client.get(self.path).status_code,405)
        self.assertEqual(self.client.post(self.path,{'action':'bad','reason':'x'}).status_code,200)
        inactive=User.objects.create_user('inactive_moderator',is_staff=True,is_active=False)
        for user in [None,self.user,inactive]:
            client=Client()
            if user: client.force_login(user)
            self.assertEqual(client.get('/adminpanel/reviews/').status_code,302)
            self.assertEqual(client.post(self.path,{'action':'hide','reason':'x'}).status_code,302)
        self.staff.is_staff=False;self.staff.save();self.assertEqual(self.client.post(self.path,{'action':'hide','reason':'x'}).status_code,302)
        self.staff.is_staff=True;self.staff.save()
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.staff);csrf.get(f'/adminpanel/reviews/{self.review.pk}/')
        for token in ['', 'bad']:
            self.assertEqual(csrf.post(self.path,{'action':'hide','reason':'x','csrfmiddlewaretoken':token}).status_code,403)
        self.assertEqual(csrf.post(self.path,{'action':'hide','reason':'x','csrfmiddlewaretoken':csrf.cookies['csrftoken'].value}).status_code,302)

    def test_search_and_hidden_customer_edit_stays_hidden(self):
        self.assertContains(self.client.get('/adminpanel/reviews/',{'q':'Apple'}),'Buyer')
        self.assertContains(self.client.get('/adminpanel/reviews/',{'q':'missing'}),'No reviews found')
        self.client.post(self.path,{'action':'hide','reason':'moderation'})
        customer=Client();customer.force_login(self.user)
        session=customer.session;session['Cid']=self.customer.pk;session.save()
        customer.post('/store/product/RM001',{'Rrating':4,'Rtext':'Changed by owner'})
        self.review.refresh_from_db();self.assertFalse(self.review.Rvisible)
        self.assertEqual(self.review.Rtext,'Changed by owner')
        self.assertEqual(list(customer.get('/store/product/RM001').context['visible_reviews']),[])

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ReviewModerationMigrationTests(TransactionTestCase):
    def test_existing_reviews_are_preserved_without_audit_backfill(self):
        def restore():
            executor=MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        self.addCleanup(restore)
        old=[('adminpanel','0015_restock_capture')]
        executor=MigrationExecutor(connection);executor.migrate(old)
        apps=executor.loader.project_state(old).apps
        apps.get_model('adminpanel','Category').objects.get_or_create(Ccode='fruit',defaults={'Cname':'Fruit & Vegetables'})
        user=apps.get_model('auth','User').objects.create(username='review_migration')
        customer=apps.get_model('adminpanel','Customer').objects.create(Cid='MG019',Cname='Buyer',Caddress='A',Chouseholdsize=1,Cmealsperweek=1,Cuser_id=user.pk)
        product=apps.get_model('adminpanel','Product').objects.create(Pid='MG019',Pname='Product',Pcategory_id='fruit',Psize='pack',Pprice=2,Plowstock=0)
        order=apps.get_model('adminpanel','Orders').objects.create(Oid='MG0019',Ocustomer_id=customer.pk,Odate=date.today(),Oaddress='Old address',Ostatus='delivered')
        item=apps.get_model('adminpanel','Item').objects.create(Iproduct_id=product.pk,Iorder_id=order.pk,Ireceived=date.today(),Istatus='delivered',Irating=4)
        review=apps.get_model('adminpanel','Review').objects.create(Rcustomer_id=customer.pk,Rproduct_id=product.pk,Ritem_id=item.pk,Rrating=4,Rtext='Original',Rvisible=False,Rdate=date.today())
        restore()
        review=Review.objects.get(pk=review.pk);item=Item.objects.get(pk=item.pk);order=Orders.objects.get(pk=order.pk)
        self.assertEqual((review.Rrating,review.Rtext,review.Rvisible,item.Irating,order.Oaddress),(4,'Original',False,4,'Old address'))
        self.assertFalse(ReviewModeration.objects.exists())
