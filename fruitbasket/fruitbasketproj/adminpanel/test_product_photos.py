import io
import tempfile
from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from PIL import Image

from .models import Customer, Item, Orders, Product


def photo(name='photo.png', fmt='PNG', size=None):
    out = io.BytesIO()
    Image.new('RGB', (3, 3), (20, 100, 30)).save(out, format=fmt)
    content = out.getvalue()
    if size:
        content += b'\0' * (size - len(content))
    return SimpleUploadedFile(name, content, content_type='image/png')


class ProductPhotoTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = tempfile.TemporaryDirectory()
        cls.media_override = override_settings(MEDIA_ROOT=cls.media.name)
        cls.media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.media_override.disable()
        cls.media.cleanup()

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('photo_staff', is_staff=True)
        cls.customer_user = User.objects.create_user('photo_customer')
        cls.customer = Customer.objects.create(Cid='PHT01', Cname='Buyer', Caddress='A', Chouseholdsize=1, Cmealsperweek=0, Cuser=cls.customer_user)

    def setUp(self):
        self.client.force_login(self.staff)
        self.data = {'Pid':'PH001', 'Pname':'Photo apple', 'Pcategory':'fruit', 'Psize':'pack', 'Pprice':'4', 'Plowstock':'1', 'Pactive':'on', 'Pexpirydays':'0'}
        self.url = '/adminpanel/product_new/PH001'

    def create(self, image=None):
        return self.client.post('/adminpanel/product_new', {**self.data, 'action':'create', **({'Pimage':image} if image else {})})

    def update(self, **changes):
        return self.client.post(self.url, {**self.data, 'action':'update', **changes})

    def assert_saved_photo_readable(self, product):
        self.assertTrue(product.Pimage.storage.exists(product.Pimage.name))
        with product.Pimage.open("rb") as stored:
            with Image.open(stored) as decoded:
                decoded.load()

    def assert_photo_views(self, name=None):
        product = Product.objects.get(pk='PH001')
        for url in ['/store/', '/store/product/PH001']:
            response = self.client.get(url)
            if name:
                self.assertContains(response, product.Pimage.url)
                self.assertContains(response, 'alt="Photo apple"')
            else:
                self.assertContains(response, 'No product photo')

    def test_create_replace_preserve_remove_and_customer_displays(self):
        self.assertEqual(self.create(photo()).status_code, 302)
        product = Product.objects.get(pk='PH001')
        old = product.Pimage.name
        self.assert_saved_photo_readable(product)
        self.assert_photo_views(old)
        self.assertContains(self.client.get(self.url), 'Current product photo')
        self.assertEqual(self.update().status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.Pimage.name, old)
        self.assertEqual(self.update(Pimage=photo('replacement.jpg', 'JPEG')).status_code, 302)
        product.refresh_from_db()
        self.assertNotEqual(product.Pimage.name, old)
        self.assert_saved_photo_readable(product)
        self.assertTrue(product.Pimage.storage.exists(old))
        self.assert_photo_views(product.Pimage.name)
        self.assertEqual(self.update(**{'Pimage-clear':'on'}).status_code, 302)
        product.refresh_from_db()
        self.assertFalse(product.Pimage)
        self.assert_photo_views()
        self.assertContains(self.client.get(self.url), 'No product photo.')
        self.assertEqual(self.update(**{'Pimage-clear':'on'}).status_code, 302)
        product.refresh_from_db()
        self.assertFalse(product.Pimage)
        self.assertEqual(self.update(Pimage=photo('added.webp', 'WEBP')).status_code, 302)
        product.refresh_from_db()
        self.assertTrue(product.Pimage)
        self.assert_saved_photo_readable(product)

    def test_shared_file_is_not_deleted_after_removal(self):
        self.create(photo())
        first = Product.objects.get(pk='PH001')
        name = first.Pimage.name
        other = Product.objects.create(Pid='PH002', Pname='Other', Pcategory_id='fruit', Psize='pack', Pprice=4, Plowstock=1, Pimage=name)
        self.assertEqual(self.update(**{'Pimage-clear': 'on'}).status_code, 302)
        other.refresh_from_db()
        self.assertEqual(other.Pimage.name, name)
        self.assertTrue(other.Pimage.storage.exists(name))

    def test_image_validation_and_size_boundaries(self):
        for upload in [SimpleUploadedFile('fake.png', b'not an image'), photo('unsupported.gif', 'GIF'), photo('disguised.png', 'GIF'), photo('oversize.png', size=2*1024*1024+1)]:
            with self.subTest(name=upload.name):
                response = self.create(upload)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Photo apple')
                self.assertContains(response, 'select the file again')
                self.assertFalse(Product.objects.exists())
        self.assertEqual(self.create(photo('boundary.png', size=2*1024*1024)).status_code, 302)

    def test_pixel_limit_and_animated_images(self):
        large = io.BytesIO()
        Image.new('RGB', (4001, 4000)).save(large, format='PNG')
        response = self.create(SimpleUploadedFile('large.png', large.getvalue()))
        self.assertContains(response, '16 megapixels')
        animation = io.BytesIO()
        frames = [Image.new('RGB', (2, 2), color) for color in ('red', 'blue')]
        frames[0].save(animation, format='WEBP', save_all=True, append_images=frames[1:], duration=100, loop=0)
        response = self.create(SimpleUploadedFile('animated.webp', animation.getvalue()))
        self.assertContains(response, 'Animated photos are not supported')
        self.assertFalse(Product.objects.exists())

    def test_truncated_jpeg_preserves_existing_photo_and_input(self):
        from django.forms import ImageField
        self.create(photo())
        product = Product.objects.get(pk='PH001')
        old = product.Pimage.name
        data = photo('broken.jpg', 'JPEG').read()[:-2]
        ImageField().clean(SimpleUploadedFile('broken.jpg', data))
        response = self.update(Pname='Retained text', Pimage=SimpleUploadedFile('broken.jpg', data))
        self.assertContains(response, 'corrupt or incomplete')
        self.assertContains(response, 'Retained text')
        product.refresh_from_db()
        self.assertEqual(product.Pimage.name, old)
        self.assert_saved_photo_readable(product)

    def test_invalid_product_conflict_and_failed_save_preserve_photo(self):
        self.create(photo())
        product = Product.objects.get(pk='PH001')
        old = product.Pimage.name
        for extra in [dict(Pprice='bad', Pname='Entered name', Pimage=photo('new.png')), dict(Pprice='bad', **{'Pimage-clear':'on'}), {'Pimage':photo('new.png'), 'Pimage-clear':'on'}]:
            with self.subTest(keys=list(extra)):
                response = self.update(**extra)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'select the file again')
                if 'Pname' in extra:
                    self.assertContains(response, 'Entered name')
                if 'Pimage' in extra and 'Pimage-clear' in extra:
                    self.assertContains(response, 'Please either submit a file or check the clear checkbox')
                product.refresh_from_db()
                self.assertEqual(product.Pimage.name, old)
                self.assertTrue(product.Pimage.storage.exists(old))
        with patch.object(Product, '_do_update', side_effect=DatabaseError('save failure')):
            response = self.update(Pname='Keep this text', Pimage=photo('new.png'))
        self.assertContains(response, 'could not be saved')
        self.assertContains(response, 'Keep this text')
        product.refresh_from_db()
        self.assertEqual(product.Pimage.name, old)
        self.assertTrue(product.Pimage.storage.exists(old))

    def test_photo_changes_preserve_stock_order_history_and_inactive(self):
        self.create(photo())
        product = Product.objects.get(pk='PH001')
        order = Orders.objects.create(Oid='PH0001', Ocustomer=self.customer, Odate=date.today(), Oaddress='Recorded')
        item = Item.objects.create(Iproduct=product, Iorder=order, Ireceived=date.today(), Istatus='delivered', Ipurchasedprice=3)
        warehouse = Item.objects.create(Iproduct=product, Ireceived=date.today(), Istatus='available')
        Product.objects.filter(pk=product.pk).update(Pactive=False)
        product.refresh_from_db()
        before = (product.Pactive, product.Pcategory_id, product.Pprice, warehouse.Istatus, item.Iorder_id, item.Istatus, item.Ipurchasedprice, order.Oaddress)
        self.data.pop('Pactive')
        self.assertEqual(self.update(Pimage=photo('replacement.png')).status_code, 302)
        warehouse.refresh_from_db()
        item.refresh_from_db(); order.refresh_from_db(); product.refresh_from_db()
        self.assertEqual((product.Pactive, product.Pcategory_id, product.Pprice, warehouse.Istatus, item.Iorder_id, item.Istatus, item.Ipurchasedprice, order.Oaddress), before)

    def test_access_missing_repeat_and_csrf(self):
        self.assertEqual(self.client.get('/adminpanel/product_new/MISS').status_code, 404)
        self.assertEqual(self.client.post('/adminpanel/product_new/MISS', {**self.data, 'Pid':'MISS', 'action':'update'}).status_code, 404)
        self.create(photo())
        self.assertEqual(self.create(photo()).status_code, 200)
        self.assertEqual(Product.objects.count(), 1)
        inactive = User.objects.create_user('photo_inactive', is_staff=True, is_active=False)
        for user in [None, self.customer_user, inactive]:
            client = Client()
            if user: client.force_login(user)
            self.assertEqual(client.post(self.url, {**self.data, 'action':'update', 'Pimage':photo()}).status_code, 302)
        self.staff.is_staff = False; self.staff.save(update_fields=['is_staff'])
        self.assertEqual(self.update(Pimage=photo()).status_code, 302)
        self.staff.is_staff = True; self.staff.save(update_fields=['is_staff'])
        client = Client(enforce_csrf_checks=True); client.force_login(self.staff); client.get(self.url)
        for token in ['', 'invalid']:
            self.assertEqual(client.post(self.url, {**self.data, 'action':'update', 'Pimage':photo(), 'csrfmiddlewaretoken':token}).status_code, 403)
        self.assertEqual(client.post(self.url, {**self.data, 'action':'update', 'Pimage':photo(), 'csrfmiddlewaretoken':client.cookies['csrftoken'].value}).status_code, 302)
