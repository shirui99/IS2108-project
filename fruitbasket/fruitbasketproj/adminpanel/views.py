from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from .models import Product, Customer, Orders, Item
from .forms import ProductForm, ItemBatchForm, CustomerForm

from .models import Product, Customer, Orders, Item
from .forms import ProductForm

# Create your views here.

def index(request):

    return render(request, 'adminpanel/index.html')



class ProductView(View):

    form_class = ProductForm
    template_name = 'adminpanel/product_new.html'



    def get(self, request, *args, **kwargs):

        pk = kwargs.get('pk') # returns None if not provided
        form = None
        action = 'create'
        status_type = None
        status_message = None

        if pk is not None:

            try:

                product = Product.objects.get(pk=pk)

                if request.GET.get('action') == 'delete':

                    try:

                        product.delete()

                        form = self.form_class()

                        status_type = 'success'
                        status_message = 'Product deleted successfully.'

                    except Exception as e:

                        status_type = 'error'
                        status_message = f'Error deleting product: {str(e)}'

                else: # update

                    form = self.form_class(instance=product)
                    action = 'update'

            except Product.DoesNotExist:

                form = self.form_class()

                status_type = 'error'
                status_message = 'Product not found.'

        else:

            form = self.form_class()

        rendered_form = form.render('adminpanel/form_template.html')

        # Count each product's items that are still in the warehouse

        products = Product.objects.annotate(
            stock=Count('product_items', filter=Q(product_items__Istatus='available'))
        )

        context = {
            'form': rendered_form,
            'action': action,
            'products': products,
            'status_type': status_type,
            'status_message': status_message,
        }

        return render(request, self.template_name, context)



    def post(self, request, *args, **kwargs):

        action = request.POST.get('action')  # returns None if not provided
        form = self.form_class(request.POST)
        status_type = None
        status_message = None



        if action == 'update':

            product = Product.objects.get(pk=request.POST.get('Pid'))
            form = self.form_class(request.POST, instance=product)

        else:

            form = self.form_class(request.POST)

        if form.is_valid():

            if action == 'create':

                newProduct = Product(
                    Pid=form.cleaned_data['Pid'],
                    Pname=form.cleaned_data['Pname'],
                    Pcategory=form.cleaned_data['Pcategory'],
                    Psize=form.cleaned_data['Psize'],
                    Pprice=form.cleaned_data['Pprice'],
                    Plowstock=form.cleaned_data['Plowstock'],
                    Pactive=form.cleaned_data['Pactive']
                )

                try:

                    newProduct.save()

                    status_type = 'success'
                    status_message = 'Product created successfully.'

                except Exception as e:

                    status_type = 'error'
                    status_message = f'Error creating product: {str(e)}'

            elif action == 'update':

                try:

                    product = Product.objects.get(pk=form.cleaned_data['Pid'])
                    product.Pname = form.cleaned_data['Pname']
                    product.Pcategory = form.cleaned_data['Pcategory']
                    product.Psize = form.cleaned_data['Psize']
                    product.Pprice = form.cleaned_data['Pprice']
                    product.Plowstock = form.cleaned_data['Plowstock']
                    product.Pactive = form.cleaned_data['Pactive']

                    try:

                        product.save()

                        status_type = 'success'
                        status_message = 'Product updated successfully.'

                    except Exception as e:

                        status_type = 'error'
                        status_message = f'Error updating product: {str(e)}'

                except Product.DoesNotExist:

                    status_type = 'error'
                    status_message = 'Product not found.'

        else:

            if action == 'create':

                status_type = 'error'
                status_message = f'Error creating product'

            else:

                status_type = 'error'
                status_message = f'Error updating product'

        form = self.form_class()
        rendered_form = form.render('adminpanel/form_template.html')

        # Count each product's items that are still in the warehouse

        products = Product.objects.annotate(
            stock=Count('product_items', filter=Q(product_items__Istatus='available'))
        )
        action = 'create'

        context = {
            'form': rendered_form,
            'action': action,
            'products': products,
            'status_type': status_type,
            'status_message': status_message,
        }

        return render(request, self.template_name, context)

class CustomerView(View):

    form_class = CustomerForm
    template_name = 'adminpanel/customer_new.html'



    def get(self, request, *args, **kwargs):

        pk = kwargs.get('pk') # returns None if not provided
        form = None
        action = 'create'
        status_type = None
        status_message = None

        if pk is not None:

            try:

                customer = Customer.objects.get(pk=pk)

                if request.GET.get('action') == 'delete':

                    try:

                        customer.delete()

                        form = self.form_class()

                        status_type = 'success'
                        status_message = 'Customer deleted successfully.'

                    except Exception as e:

                        status_type = 'error'
                        status_message = f'Error deleting customer: {str(e)}'

                else: # update

                    form = self.form_class(instance=customer)
                    action = 'update'

            except Customer.DoesNotExist:

                form = self.form_class()

                status_type = 'error'
                status_message = 'Customer not found.'

        else:

            form = self.form_class()

        rendered_form = form.render('adminpanel/form_template.html')

        customers = Customer.objects.all()

        context = {
            'form': rendered_form,
            'action': action,
            'customers': customers,
            'status_type': status_type,
            'status_message': status_message,
        }

        return render(request, self.template_name, context)



    def post(self, request, *args, **kwargs):

        action = request.POST.get('action')  # returns None if not provided
        form = self.form_class(request.POST)
        status_type = None
        status_message = None



        if action == 'update':

            customer = Customer.objects.get(pk=request.POST.get('Cid'))
            form = self.form_class(request.POST, instance=customer)

        else:

            form = self.form_class(request.POST)

        if form.is_valid():

            if action == 'create':

                newCustomer = Customer(
                    Cid=form.cleaned_data['Cid'],
                    Cname=form.cleaned_data['Cname'],
                    Caddress=form.cleaned_data['Caddress'],
                    Chouseholdsize=form.cleaned_data['Chouseholdsize'],
                    Cmealsperweek=form.cleaned_data['Cmealsperweek'],
                    Cuser=form.cleaned_data['Cuser']
                )

                try:

                    newCustomer.save()

                    status_type = 'success'
                    status_message = 'Customer created successfully.'

                except Exception as e:

                    status_type = 'error'
                    status_message = f'Error creating customer: {str(e)}'

            elif action == 'update':

                try:

                    customer = Customer.objects.get(pk=form.cleaned_data['Cid'])
                    customer.Cname = form.cleaned_data['Cname']
                    customer.Caddress = form.cleaned_data['Caddress']
                    customer.Chouseholdsize = form.cleaned_data['Chouseholdsize']
                    customer.Cmealsperweek = form.cleaned_data['Cmealsperweek']
                    customer.Cuser = form.cleaned_data['Cuser']

                    try:

                        customer.save()

                        status_type = 'success'
                        status_message = 'Customer updated successfully.'

                    except Exception as e:

                        status_type = 'error'
                        status_message = f'Error updating customer: {str(e)}'

                except Customer.DoesNotExist:

                    status_type = 'error'
                    status_message = 'Customer not found.'

        else:

            if action == 'create':

                status_type = 'error'
                status_message = f'Error creating customer'

            else:

                status_type = 'error'
                status_message = f'Error updating customer'

        form = self.form_class()
        rendered_form = form.render('adminpanel/form_template.html')

        customers = Customer.objects.all()
        action = 'create'

        context = {
            'form': rendered_form,
            'action': action,
            'customers': customers,
            'status_type': status_type,
            'status_message': status_message,
        }

        return render(request, self.template_name, context)