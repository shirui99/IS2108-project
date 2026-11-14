from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser, User
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, RequestFactory, TestCase

from .forms import CategoryForm, ProductForm
from .models import Category, Product
from .views import CategoryView
from store.restock import load_restock_artifacts, predict_restock


class CategoryTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='categories', is_staff=True)
        self.client.force_login(self.staff)
        self.url = '/adminpanel/category_new'

    def test_create_trim_prg_and_repeat(self):
        response = self.client.post(self.url, {'Cname': '  Drinks\u3000'})
        self.assertRedirects(response, self.url)
        category = Category.objects.get(Cname='Drinks')
        self.assertEqual(len(category.pk), 20)
        self.assertContains(self.client.post(self.url, {'Cname': 'drinks'}), 'already exists')
        self.assertEqual(Category.objects.filter(Cname='DRINKS').count(), 1)
        self.assertEqual(category.pk, Category.objects.get(Cname='Drinks').pk)

    def test_invalid_names_and_bound_input(self):
        for name in ['', ' \t\n\u3000', 'x' * 201, 'fruit & vegetables', ' Fruit & Vegetables ']:
            with self.subTest(name=name):
                self.assertFalse(CategoryForm({'Cname': name}).is_valid())
        response = self.client.post(self.url, {'Cname': 'x' * 201})
        self.assertContains(response, 'x' * 201)
        self.assertContains(response, '200')

    def test_database_matches_ascii_case_rule_and_unicode_limits(self):
        Category.objects.create(Cname='Tea')
        for name in ['TEA', '', '  ', ' Tea', 'Tea\u3000', 'x' * 201]:
            with self.subTest(name=name), self.assertRaises(IntegrityError), transaction.atomic():
                # Bypass save and forms: constraints must still enforce the contract.
                Category.objects.bulk_create([Category(Ccode='test', Cname=name)])
        for name in ['\u00c9', '\u00e9', 'Stra\u00dfe', 'STRASSE']:
            self.assertTrue(CategoryForm({'Cname': name}).is_valid())
            Category.objects.create(Cname=name)

    @patch('adminpanel.views.category_code', side_effect=['fruit', 'c1234567890123456789'])
    def test_code_collision_retries_without_overwriting(self, code):
        self.assertRedirects(self.client.post(self.url, {'Cname': 'Drinks'}), self.url)
        self.assertEqual(Category.objects.get(pk='fruit').Cname, 'Fruit & Vegetables')
        self.assertEqual(Category.objects.get(Cname='Drinks').pk, 'c1234567890123456789')

    @patch('adminpanel.views.category_code', return_value='fruit')
    def test_code_collision_exhaustion_retains_input(self, code):
        response = self.client.post(self.url, {'Cname': 'Drinks'})
        self.assertContains(response, 'could not be generated')
        self.assertContains(response, 'Drinks')
        self.assertFalse(Category.objects.filter(Cname='Drinks').exists())

    @patch('adminpanel.views.Category.objects.create', side_effect=IntegrityError)
    def test_database_failure_is_form_error(self, create):
        self.assertContains(self.client.post(self.url, {'Cname': 'Drinks'}), 'could not be saved')

    def test_racing_duplicate_is_form_error(self):
        Category.objects.create(Cname='Drinks')
        with patch.object(CategoryForm, 'is_valid', return_value=True), patch.object(CategoryForm, 'cleaned_data', {'Cname': 'drinks'}, create=True):
            self.assertContains(self.client.post(self.url, {'Cname': 'drinks'}), 'already exists')

    def test_authorization_including_direct_view_and_inactive(self):
        users = [AnonymousUser(), User.objects.create_user(username='customer'), User.objects.create_user(username='inactive', is_staff=True, is_active=False)]
        for user in users:
            for method in ['get', 'post']:
                request = getattr(RequestFactory(), method)(self.url, {'Cname': 'Unauthorised'})
                request.user = user
                self.assertEqual(CategoryView.as_view()(request).status_code, 302)
            client = Client()
            if user.is_authenticated:
                client.force_login(user)
            self.assertEqual(client.post(self.url, {'Cname': 'Unauthorised'}).status_code, 302)
        self.assertFalse(Category.objects.filter(Cname='Unauthorised').exists())

    def test_methods_and_csrf(self):
        before = Category.objects.count()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        for method in ['put', 'patch', 'delete']:
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        self.assertEqual(client.post(self.url, {'Cname': 'Drinks'}).status_code, 403)
        client.get(self.url)
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.post(self.url, {'Cname': 'Drinks', 'csrfmiddlewaretoken': 'bad'}).status_code, 403)
        self.assertEqual(Category.objects.count(), before)
        self.assertRedirects(client.post(self.url, {'Cname': 'Drinks', 'csrfmiddlewaretoken': token}), self.url)

    def test_product_forms_filters_labels_and_protection(self):
        category = Category.objects.create(Cname='Drinks')
        data = dict(Pid='NEW01', Pname='Tea', Pcategory=category.pk, Psize='1 pack', Pprice='3', Plowstock='0', Pactive='on', Pexpirydays='0')
        self.assertContains(self.client.get('/adminpanel/product_new'), 'Drinks')
        self.assertRedirects(self.client.post('/adminpanel/product_new', dict(data, action='create')), '/adminpanel/product_new')
        product = Product.objects.get(pk='NEW01')
        self.assertEqual(product.Pcategory_id, category.pk)
        self.assertContains(self.client.get('/adminpanel/product_new/NEW01'), f'value="{category.pk}" selected')
        self.assertRedirects(self.client.post('/adminpanel/product_new/NEW01', dict(data, action='update', Pcategory='fruit')), '/adminpanel/product_new')
        response = self.client.get('/store/', {'category': 'fruit', 'sort': 'price_desc'})
        self.assertContains(response, 'Fruit &amp; Vegetables')
        self.assertIn('NEW01', [p.pk for p in response.context['products']])
        product.Pcategory = category
        product.save()
        response = self.client.get('/store/', {'category': category.pk, 'sort': 'price_asc'})
        self.assertEqual([p.pk for p in response.context['products']], ['NEW01'])
        self.assertFalse(ProductForm(dict(data, Pcategory='missing')).is_valid())
        with self.assertRaises(ProtectedError):
            category.delete()


class CategoryMLTests(TestCase):
    def predict(self, code, count=2):
        return predict_restock(date(2026, 11, 1), 3, code, 2, 10, history_count=count)

    def test_saved_known_category_result_and_schema(self):
        artifacts = load_restock_artifacts()
        self.assertIsNotNone(artifacts['pipeline'], artifacts['error'])
        self.assertEqual(self.predict('fruit')['status'], 'MODEL')
        self.assertEqual(self.predict('fruit')['interval_days'], 10)
        self.assertEqual(self.predict('fruit', 1)['interval_days'], 9)

    @patch('store.restock.load_restock_artifacts')
    def test_unseen_never_calls_pipeline_and_uses_overall(self, load):
        pipeline = Mock()
        load.return_value = {'pipeline': pipeline, 'metadata': {'training_only_category_medians': {'fruit': 9}, 'training_only_overall_median': 14}, 'error': None}
        result = self.predict('new')
        self.assertEqual((result['status'], result['interval_days']), ('INITIAL', 14))
        pipeline.predict.assert_not_called()
        for invalid in [None, 0, -1, float('nan'), float('inf')]:
            load.return_value['metadata']['training_only_overall_median'] = invalid
            result = self.predict('new')
            self.assertEqual(result['status'], 'UNAVAILABLE')
            self.assertIsNone(result['restock_date'])
            self.assertIn('overall training median', result['reason'])

    @patch('store.restock.predict_restock')
    def test_stored_code_passed_to_ml(self, predict):
        from store.tests import RestockFeatureTests
        from store.restock import get_restock_suggestions
        fixture = RestockFeatureTests()
        fixture.setUp()
        order = fixture._order('ML001', fixture.customer, date(2026, 11, 1))
        fixture._item(fixture.product, order)
        fixture._item(fixture.product, None, status='available', expiry=None)
        predict.return_value = {'status': 'INITIAL', 'interval_days': 1, 'restock_date': '2026-11-02'}
        get_restock_suggestions(fixture.customer.pk, today=date(2026, 11, 3))
        self.assertEqual(predict.call_args.kwargs['category'], 'fruit')

    @patch('store.views.get_customer_purchase_history', return_value={'P': []})
    @patch('store.views.get_restock_suggestions')
    def test_initial_label_and_unavailable_explanation(self, suggestions, history):
        session = self.client.session
        session['Cid'] = 'TEST'
        session.save()
        for status, label, date_value in [('INITIAL', 'Initial estimate', '2026-11-01'), ('UNAVAILABLE', 'No estimate available', None)]:
            suggestions.return_value = [{'product_id': 'P', 'product_name': 'Tea', 'status': status, 'restock_date': date_value}]
            response = self.client.get('/store/restock/')
            self.assertContains(response, label)
            if status == 'UNAVAILABLE':
                self.assertContains(response, 'fallback is unavailable')
