from django.test import TestCase

from .models import Product


class ProductViewTests(TestCase):
    def test_invalid_update_keeps_bound_values_errors_and_update_mode(self):
        Product.objects.create(
            Pid='P001',
            Pname='Original name',
            Pcategory='fruit',
            Psize='1 pack',
            Pprice=2.5,
            Plowstock=3,
            Pactive=True,
            Pexpirydays=5,
        )
        session = self.client.session
        session['isStaff'] = True
        session.save()

        response = self.client.post(
            '/adminpanel/product_new',
            {
                'action': 'update',
                'Pid': 'P001',
                'Pname': 'Entered name',
                'Pcategory': 'fruit',
                'Psize': '1 pack',
                'Pprice': '',
                'Plowstock': '3',
                'Pactive': 'on',
                'Pexpirydays': '5',
            },
        )

        self.assertContains(response, 'Entered name')
        self.assertContains(response, 'This field is required.')
        self.assertContains(response, 'name="action" value="update"')
        self.assertEqual(Product.objects.get(Pid='P001').Pname, 'Original name')
