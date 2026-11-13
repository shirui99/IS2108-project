import io
import json
import tempfile
from pathlib import Path
from datetime import timedelta
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image
from adminpanel.models import Category, Customer, Product, Item, Orders, Review, SupportTicket
from store.restock import EXPECTED_FEATURES, load_restock_artifacts, predict_restock


class AuditJourneys(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory();self.addCleanup(self.media.cleanup)
        self.override=override_settings(MEDIA_ROOT=self.media.name);self.override.enable();self.addCleanup(self.override.disable)
        self.staff=User.objects.create_user('audit_staff',is_staff=True)
        self.user=User.objects.create_user('audit_buyer')
        self.other=User.objects.create_user('audit_other')
        self.customer=Customer.objects.create(Cid='AU001',Cname='Buyer',Caddress='Original',Chouseholdsize=2,Cmealsperweek=1,Cuser=self.user)
        self.other_customer=Customer.objects.create(Cid='AU002',Cname='Other',Caddress='Other',Chouseholdsize=1,Cmealsperweek=1,Cuser=self.other)
        self.client.force_login(self.staff)
        self.buyer=Client();self.buyer.force_login(self.user)
        session=self.buyer.session;session['Cid']=self.customer.pk;session.save()
        self.today=timezone.localdate()

    def create_stock(self):
        self.client.post('/adminpanel/category_new',{'Cname':'Audit category'})
        code=Category.objects.get(Cname='Audit category').pk
        image=io.BytesIO();Image.new('RGB',(4,4),'green').save(image,'PNG')
        self.assertEqual(self.client.post('/adminpanel/product_new',{'action':'create','Pid':'AU001','Pname':'Audit apple','Pcategory':code,'Psize':'pack','Pprice':'3','Plowstock':'0','Pactive':'on','Pexpirydays':'0','Pimage':SimpleUploadedFile('audit.png',image.getvalue())}).status_code,302)
        self.assertEqual(self.client.post('/adminpanel/item_new',{'action':'create','Iproduct':'AU001','Breference':'AUDIT-BATCH','Ireceived':self.today.isoformat(),'Iquantity':3,'Bdatetype':'','Iexpiry':''}).status_code,302)
        self.assertContains(self.buyer.get('/store/',{'category':code}),'Audit apple')
        self.buyer.post('/store/cart/AU001',{'quantity':1})
        self.buyer.post('/store/checkout',{'Oaddress':'Recorded address'})
        return Orders.objects.get()

    def test_product_to_delivery_review_support_and_contact(self):
        order=self.create_stock()
        self.assertEqual((order.order_items.count(),order.Opayment),(1,'paid'))
        self.assertEqual(list(self.buyer.get('/store/pantry').context['pantry_items']),[])
        for action in ['prepare','dispatch','deliver']:
            self.assertEqual(self.client.post(f'/adminpanel/orders/{order.pk}/fulfil/',{'action':action}).status_code,302)
        self.assertEqual(len(self.buyer.get('/store/pantry').context['pantry_items']),1)
        outsider=Client();session=outsider.session;session['Cid']=self.other_customer.pk;session.save()
        self.assertEqual(list(outsider.get('/store/pantry').context['pantry_items']),[])
        self.buyer.post('/store/product/AU001',{'Rrating':5,'Rtext':'Original wording'})
        review=Review.objects.get()
        self.client.post(f'/adminpanel/reviews/{review.pk}/action/',{'action':'hide','reason':'Check'})
        item=order.order_items.get();self.buyer.post(f'/store/pantry/{item.pk}',{'action':'rate','rating':2})
        self.client.post(f'/adminpanel/reviews/{review.pk}/action/',{'action':'restore','reason':'Approved'})
        review.refresh_from_db();self.assertEqual(review.Rrating,2)
        self.assertEqual(self.buyer.get('/store/product/AU001').context['product'].rating,2)
        self.client.post('/adminpanel/customer_new/AU001',{'Cname':'Updated','Caddress':'New','email':'a@example.com'})
        order.refresh_from_db();self.assertEqual(order.Oaddress,'Recorded address')
        self.buyer.post(f'/store/orders/{order.pk}',{'Tsubject':'Issue','Tmessage':'Help'})
        ticket=SupportTicket.objects.get()
        self.client.post(f'/adminpanel/support/{ticket.pk}',{'Tresponse':'Resolved'})
        self.assertContains(self.buyer.get(f'/store/orders/{order.pk}'),'Resolved')
        self.assertNotContains(outsider.get(f'/store/orders/{order.pk}'),'Resolved')

    def test_cancellation_history_survives_pack_reuse(self):
        order=self.create_stock();pack=order.order_items.get()
        self.buyer.post(f'/store/orders/{order.pk}',{'action':'cancel'})
        snapshot=list(order.cancellation.allocations.values())
        self.buyer.post('/store/cart/AU001',{'quantity':1});self.buyer.post('/store/checkout',{'Oaddress':'Second address'})
        pack.refresh_from_db();self.assertNotEqual(pack.Iorder_id,order.pk)
        self.assertEqual(list(order.cancellation.allocations.values()),snapshot)
        self.assertContains(self.client.get(f'/adminpanel/orders/{order.pk}/'),'AUDIT-BATCH')


class AuditFailureProbes(TestCase):
    def test_staff_login_rejects_unsupported_method(self):
        self.assertEqual(self.client.put('/adminpanel/login').status_code,405)

    def test_corrupt_pipeline_uses_available_training_fallback(self):
        # Work only with temporary artifacts; never overwrite the approved model.
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'ml_models';target.mkdir()
            (target/'restock_metadata.json').write_text(json.dumps({'feature_names':EXPECTED_FEATURES,'training_only_category_medians':{'fruit':9},'training_only_overall_median':14}))
            (target/'restock_model.joblib').write_bytes(b'not-a-valid-joblib-file')
            load_restock_artifacts.cache_clear()
            try:
                with override_settings(BASE_DIR=Path(folder)):
                    result=predict_restock(timezone.localdate(),2,'fruit',1,7,history_count=2)
                    self.assertEqual((result['status'],result['interval_days']),('INITIAL',9))
            finally:
                load_restock_artifacts.cache_clear()

class AuditMethodTests(TestCase):
    def test_login_unsupported_methods_preserve_existing_session(self):
        from unittest.mock import patch
        staff=User.objects.create_user('method_staff',is_staff=True)
        self.client.force_login(staff)
        session=self.client.session;session['audit_marker']='unchanged';session.save()
        key=session.session_key
        before=list(User.objects.values())
        with patch('adminpanel.views.authenticate') as authenticate:
            for method in ['put','patch','delete']:
                response=getattr(self.client,method)('/adminpanel/login')
                self.assertEqual(response.status_code,405)
                self.assertEqual(response['Allow'],'GET, POST')
                self.assertEqual(self.client.session.session_key,key)
                self.assertEqual(self.client.session['audit_marker'],'unchanged')
            authenticate.assert_not_called()
        self.assertEqual(list(User.objects.values()),before)
