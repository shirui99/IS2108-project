from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth.models import User
from django.core import signing
from django.db import IntegrityError
from django.test import Client, TestCase
from django.utils import timezone
from .models import Customer, InventoryBatch, Item, Orders, Product, StockAdjustment


class AdjustmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('adjust_staff', password='secret', is_staff=True)
        cls.buyer = User.objects.create_user('adjust_buyer')
        cls.inactive = User.objects.create_user('inactive_staff', is_staff=True, is_active=False)
        cls.product = Product.objects.create(Pid='A0001', Pname='Apples', Pcategory_id='fruit', Psize='1 pack', Pprice=3, Plowstock=0, Pexpirydays=3)
        cls.customer = Customer.objects.create(Cid='A0001', Cname='Buyer', Caddress='Address', Chouseholdsize=1, Cmealsperweek=1, Cuser=cls.buyer)

    def setUp(self):
        self.client.force_login(self.staff)
        self.today = timezone.localdate()
        self.past = self.today - timedelta(days=2)
        self.batch = InventoryBatch.objects.create(Breference='B1', Bproduct=self.product, Breceived=self.today, Bquantity=3, Bdatetype='expiry', Bdate=self.past)
        self.batch_items = [Item.objects.create(Ibatch=self.batch, Iproduct=self.product, Ireceived=self.today, Iexpiry=self.past) for _ in range(3)]
        self.legacy = [Item.objects.create(Iproduct=self.product, Ireceived=self.today, Iexpiry=None) for _ in range(2)]
        self.order = Orders.objects.create(Oid='A00001', Odate=self.today, Oaddress='Address', Ocustomer=self.customer)
        self.allocated = Item.objects.create(Ibatch=self.batch, Iproduct=self.product, Ireceived=self.today, Iexpiry=self.past, Iorder=self.order, Istatus='delivered', Ipurchasedprice=2)
        self.batch_token = signing.dumps({'batch': self.batch.pk}, salt='stock-group')
        self.legacy_token = signing.dumps({'product': self.product.pk, 'received': self.today.isoformat(), 'date': None}, salt='stock-group')

    def data(self, group=None, action='correction', quantity='1', reason='Counted', key=None):
        token = group or self.batch_token
        count = 2 if group == self.legacy_token else 3
        return {'group': token, 'action': action, 'quantity': quantity, 'reason': reason, 'request_id': str(key or uuid4()), 'expected_count': str(count), 'snapshot': signing.dumps([token, action, count], salt='stock-snapshot')}

    def test_batch_decrease_preserves_allocated_and_replay(self):
        data = self.data(quantity='1')
        self.assertRedirects(self.client.post('/adminpanel/stock_adjust', data), '/adminpanel/item_new')
        audit = StockAdjustment.objects.get()
        self.assertEqual((audit.before_count, audit.after_count, audit.difference, audit.staff), (3, 1, -2, self.staff))
        self.assertEqual(audit.items.filter(Istatus='adjusted', Iorder__isnull=True).count(), 2)
        self.allocated.refresh_from_db()
        self.assertEqual((self.allocated.Istatus, self.allocated.Ipurchasedprice), ('delivered', 2))
        self.assertRedirects(self.client.post('/adminpanel/stock_adjust', data), '/adminpanel/item_new')
        self.assertEqual(StockAdjustment.objects.count(), 1)
        self.assertEqual(Item.objects.filter(Ibatch=self.batch, Istatus='available').count(), 1)

    def test_increase_and_legacy_decrease(self):
        self.assertEqual(self.client.post('/adminpanel/stock_adjust', self.data(quantity='5')).status_code, 302)
        audit = StockAdjustment.objects.get()
        self.assertEqual((audit.before_count, audit.after_count, audit.difference), (3, 5, 2))
        self.assertEqual(audit.items.filter(Ibatch=self.batch, Ireceived=self.today, Iexpiry=self.past).count(), 2)
        self.assertEqual(self.client.post('/adminpanel/stock_adjust', self.data(self.legacy_token, quantity='0')).status_code, 302)
        self.assertEqual(Item.objects.filter(Ibatch__isnull=True, Istatus='adjusted').count(), 2)
        page = self.client.get('/adminpanel/item_new')
        self.assertContains(page, 'Correct count')
        self.assertTrue(any(group['Iproduct'] == self.product.pk and group['count'] == 0 for group in page.context['batches']))
        data = self.data(self.legacy_token, quantity='1')
        data['expected_count'] = 0
        data['snapshot'] = signing.dumps([data['group'], data['action'], 0], salt='stock-snapshot')
        self.assertEqual(self.client.post('/adminpanel/stock_adjust', data).status_code, 302)
        self.assertEqual(Item.objects.filter(Ibatch__isnull=True, Istatus='available').count(), 1)

    def test_legacy_increase_preserves_unknown_date(self):
        self.assertEqual(self.client.post('/adminpanel/stock_adjust', self.data(self.legacy_token, quantity='4')).status_code, 302)
        audit = StockAdjustment.objects.get()
        self.assertEqual(audit.items.filter(Ibatch__isnull=True, Ireceived=self.today, Iexpiry__isnull=True).count(), 2)

    def test_writeoff_past_date_and_legacy(self):
        for token, reason in [(self.batch_token, 'expired'), (self.legacy_token, 'damaged')]:
            data = self.data(token, 'writeoff', '1', reason)
            data['note'] = 'Inspection note'
            self.assertEqual(self.client.post('/adminpanel/stock_adjust', data).status_code, 302)
        self.assertEqual(Item.objects.filter(Istatus='writtenoff').count(), 2)
        self.assertEqual(set(StockAdjustment.objects.values_list('reason', flat=True)), {'expired', 'damaged'})
        self.assertEqual(StockAdjustment.objects.filter(kind='writeoff', difference=-1, note='Inspection note').count(), 2)
        self.allocated.refresh_from_db()
        self.assertEqual(self.allocated.Istatus, 'delivered')

    def test_repeated_writeoff_applies_once(self):
        data = self.data(action='writeoff', quantity='1', reason='expired')
        self.assertEqual(self.client.post('/adminpanel/stock_adjust', data).status_code, 302)
        self.assertEqual(self.client.post('/adminpanel/stock_adjust', data).status_code, 302)
        self.assertEqual(StockAdjustment.objects.count(), 1)
        self.assertEqual(Item.objects.filter(Ibatch=self.batch, Istatus='writtenoff').count(), 1)

    def test_writeoff_summary_counts_packs_not_events(self):
        page=self.client.get('/adminpanel/item_new')
        self.assertEqual((page.context['writeoff_total'],page.context['writeoff_expired'],page.context['legacy_expired']),(0,0,0))
        Item.objects.create(Iproduct=self.product,Ireceived=self.today,Istatus='expired')
        expiry=self.data(action='writeoff',quantity='2',reason='expired')
        self.client.post('/adminpanel/stock_adjust',expiry)
        self.client.post('/adminpanel/stock_adjust',expiry)
        self.client.post('/adminpanel/stock_adjust',self.data(self.legacy_token,action='writeoff',quantity='1',reason='damaged'))
        data=self.data(self.legacy_token,action='correction',quantity='0',reason='Count')
        data['expected_count']='1';data['snapshot']=signing.dumps([data['group'],data['action'],1],salt='stock-snapshot')
        self.client.post('/adminpanel/stock_adjust',data)
        for _ in range(2):
            page=self.client.get('/adminpanel/item_new')
            self.assertEqual((page.context['writeoff_total'],page.context['writeoff_expired'],page.context['legacy_expired']),(3,2,1))
            self.assertContains(page,'reason not recorded')

    def test_invalid_fields(self):
        for action, quantity, reason in [('correction', '-1', 'why'), ('correction', '1.5', 'why'), ('correction', '1', ''), ('writeoff', '0', 'expired'), ('writeoff', '4', 'expired'), ('writeoff', '1', 'other'), ('writeoff', 'x', 'expired')]:
            with self.subTest(action=action, quantity=quantity, reason=reason):
                response = self.client.post('/adminpanel/stock_adjust', self.data(action=action, quantity=quantity, reason=reason))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'errorlist')
                self.assertFalse(StockAdjustment.objects.exists())

    @patch('adminpanel.views.Item.objects.bulk_create', side_effect=IntegrityError('forced'))
    def test_increase_failure_rolls_back_history(self, bulk):
        response = self.client.post('/adminpanel/stock_adjust', self.data(quantity='5'))
        self.assertContains(response, 'could not be saved')
        self.assertFalse(StockAdjustment.objects.exists())
        self.assertEqual(Item.objects.filter(Ibatch=self.batch, Istatus='available').count(), 3)

    def test_permissions_csrf_and_get(self):
        url = '/adminpanel/stock_adjust'
        data = self.data()
        for user in [None, self.buyer, self.inactive]:
            client = Client()
            if user: client.force_login(user)
            self.assertEqual(client.post(url, data).status_code, 302)
        self.assertEqual(self.client.get(url, {'group': self.batch_token, 'action': 'correction'}).status_code, 200)
        self.assertEqual(self.client.put(url).status_code, 405)
        self.assertFalse(StockAdjustment.objects.exists())
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        self.assertEqual(client.post(url, data).status_code, 403)
        client.get(url, {'group': self.batch_token, 'action': 'correction'})
        self.assertEqual(client.post(url, dict(data, csrfmiddlewaretoken=client.cookies['csrftoken'].value)).status_code, 302)

    def test_stale_form_rejected_after_stock_changes(self):
        data = self.data(quantity='1')
        Item.objects.filter(pk=self.batch_items[0].pk).update(Istatus='writtenoff')
        response = self.client.post('/adminpanel/stock_adjust', data)
        self.assertContains(response, 'Stock changed since this form was opened')
        self.assertFalse(StockAdjustment.objects.exists())
        self.assertEqual(Item.objects.filter(Ibatch=self.batch, Istatus='available').count(), 2)

    def test_conditional_claim_shortfall_rolls_back(self):
        from django.db.models.query import QuerySet
        original = QuerySet.update
        def changed(queryset, **kwargs):
            if kwargs.get('Istatus') == 'adjusted':
                return 0
            return original(queryset, **kwargs)
        with patch.object(QuerySet, 'update', autospec=True, side_effect=changed):
            response = self.client.post('/adminpanel/stock_adjust', self.data(quantity='1'))
        self.assertContains(response, 'Stock changed or the adjustment could not be saved')
        self.assertFalse(StockAdjustment.objects.exists())
        self.assertEqual(Item.objects.filter(Ibatch=self.batch, Istatus='available').count(), 3)

    def test_remaining_fixed_reasons(self):
        for reason, expected in [('spoiled', 3), ('recalled', 2)]:
            data = self.data(action='writeoff', quantity='1', reason=reason)
            data['expected_count'] = expected
            data['snapshot'] = signing.dumps([data['group'], data['action'], expected], salt='stock-snapshot')
            self.assertEqual(self.client.post('/adminpanel/stock_adjust', data).status_code, 302)
        self.assertEqual(set(StockAdjustment.objects.values_list('reason', flat=True)), {'spoiled', 'recalled'})

    def test_tampered_snapshot_is_rejected(self):
        data = self.data(quantity='1')
        data['expected_count'] = '2'
        response = self.client.post('/adminpanel/stock_adjust', data)
        self.assertContains(response, 'stock count details are invalid')
        self.assertFalse(StockAdjustment.objects.exists())

    def test_legacy_delete_is_disabled(self):
        response = self.client.post('/adminpanel/item_new', {'action': 'delete', 'product': self.product.pk, 'received': self.today.isoformat(), 'expiry': ''})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Item.objects.filter(Ibatch__isnull=True, Istatus='available').count(), 2)
