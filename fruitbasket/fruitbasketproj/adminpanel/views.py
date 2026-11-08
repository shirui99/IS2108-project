from django.contrib.auth import authenticate
from django.db.models import Count, Q
from django.shortcuts import render, HttpResponse
from datetime import timedelta
from django.utils import timezone
from django.views import View

from .models import Product, Customer, Orders, Item
from .forms import ProductForm, CustomerForm, OrderForm, ItemBatchForm


# Create your views here.

def index(request):

    return render(request, 'adminpanel/index.html')



def login(request):

    if request.method == 'GET':

        # Display the login form
        return render(request, 'adminpanel/login.html')
    
    elif request.method == 'POST':

        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(username=username, password=password)

        if user is not None and user.is_staff:

            request.session['isStaff'] = True
            request.session['staff_user_id'] = user.pk #for ticket answering

            return render(request, 'adminpanel/login.html', {'success_message': 'Authentication successful!'})
        
        else:

            return render(request, 'adminpanel/login.html', {'error_message': 'Invalid username or password.'})



def logout(request):

    request.session.flush()

    return HttpResponse('You have logged out.')



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
        form = self.form_class(request.POST, request.FILES)
        status_type = None
        status_message = None



        if action == 'update':

            product = Product.objects.get(pk=request.POST.get('Pid'))
            form = self.form_class(request.POST, request.FILES, instance=product)

        else:

            form = self.form_class(request.POST, request.FILES)

        if form.is_valid():

            if action == 'create':

                newProduct = Product(
                    Pid=form.cleaned_data['Pid'],
                    Pname=form.cleaned_data['Pname'],
                    Pcategory=form.cleaned_data['Pcategory'],
                    Psize=form.cleaned_data['Psize'],
                    Pprice=form.cleaned_data['Pprice'],
                    Plowstock=form.cleaned_data['Plowstock'],
                    Pactive=form.cleaned_data['Pactive'],
                    Pimage=form.cleaned_data['Pimage'] or None,
                    Pexpirydays=form.cleaned_data['Pexpirydays']
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
                    product.Pimage=form.cleaned_data['Pimage'] or None
                    product.Pexpirydays=form.cleaned_data['Pexpirydays']

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

class OrderView(View):

    form_class = OrderForm
    template_name = 'adminpanel/order_new.html'



    def get(self, request, *args, **kwargs):

        pk = kwargs.get('pk') # returns None if not provided
        form = None
        action = 'create'
        status_type = None
        status_message = None

        if pk is not None:            

            try:
            
                order = Orders.objects.get(pk=pk)

                if request.GET.get('action') == 'delete':                
                
                    try:
                    
                        order.delete()
                                        
                        form = self.form_class()
    
                        status_type = 'success'
                        status_message = 'Order deleted successfully.'                            
    
                    except Exception as e:
    
                        status_type = 'error'
                        status_message = f'Error deleting order: {str(e)}'
    
                else: # update
                    
                    form = self.form_class(instance=order)
                    action = 'update'
            
            except Orders.DoesNotExist:

                form = self.form_class()

                status_type = 'error'
                status_message = 'Order not found.'            

        else:
            
            form = self.form_class()
        
        rendered_form = form.render('adminpanel/form_template.html')

        # Count the items in each order

        orders = Orders.objects.annotate(items=Count('order_items'))

        context = {
            'form': rendered_form, 
            'action': action, 
            'orders': orders,
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

            order = Orders.objects.get(pk=request.POST.get('Oid'))
            form = self.form_class(request.POST, instance=order)

        else:
            
            form = self.form_class(request.POST)
        
        if form.is_valid():

            if action == 'create':

                newOrder = Orders(
                    Oid=form.cleaned_data['Oid'],
                    Ocustomer=form.cleaned_data['Ocustomer'],
                    Oaddress=form.cleaned_data['Oaddress'],
                    Odate=form.cleaned_data['Odate'],
                    Ostatus=form.cleaned_data['Ostatus']
                )

                try:                    
                    
                    newOrder.save()
                    status_type = 'success'
                    status_message = 'Order created successfully.'
    
                except Exception as e:
    
                    status_type = 'error'
                    status_message = f'Error creating order: {str(e)}'

            elif action == 'update':
                
                try:

                    order = Orders.objects.get(pk=form.cleaned_data['Oid'])
                    order.Ocustomer = form.cleaned_data['Ocustomer']
                    order.Oaddress = form.cleaned_data['Oaddress']
                    order.Odate = form.cleaned_data['Odate']
                    order.Ostatus = form.cleaned_data['Ostatus']
                    
                    try:

                        order.save()

                        status_type = 'success'
                        status_message = 'Order updated successfully.'

                    except Exception as e:
                                        
                        status_type = 'error'
                        status_message = f'Error updating order: {str(e)}'

                except Orders.DoesNotExist:

                    status_type = 'error'
                    status_message = 'Order not found.'           

        else:

            if action == 'create':
            
                status_type = 'error'
                status_message = f'Error creating order'

            else:
                
                status_type = 'error'
                status_message = f'Error updating order'

        form = self.form_class()
        rendered_form = form.render('adminpanel/form_template.html')

        # Count the items in each order

        orders = Orders.objects.annotate(items=Count('order_items'))
        action = 'create'

        context = {
            'form': rendered_form, 
            'action': action, 
            'orders': orders,
            'status_type': status_type,
            'status_message': status_message,
        }

        return render(request, self.template_name, context)

def remove_expiring_stock():

    # For each product, warehouse items with fewer than Pexpirydays days left are written off as expired

    today = timezone.localdate()
    removed = 0

    for product in Product.objects.all():

        cutoff = today + timedelta(days=product.Pexpirydays)

        removed += Item.objects.filter(Iproduct=product, Istatus='available', Iexpiry__lt=cutoff).update(
            Istatus='expired',
            Ifinished=today
        )

    return removed

class ItemView(View):

    form_class = ItemBatchForm
    template_name = 'adminpanel/item_new.html'



    def get(self, request, *args, **kwargs):

        form = self.form_class(initial={'Ireceived': timezone.localdate()})
        status_type = None
        status_message = None

        if request.GET.get('action') == 'delete':

            try:

                batch = Item.objects.filter(
                    Istatus='available',
                    Iproduct_id=request.GET.get('product'),
                    Ireceived=request.GET.get('received')
                )

                expiry = request.GET.get('expiry')

                if expiry:

                    batch = batch.filter(Iexpiry=expiry)

                else:

                    batch = batch.filter(Iexpiry__isnull=True)

                count, _ = batch.delete()

                status_type = 'success'
                status_message = f'{count} item(s) removed from stock.'

            except Exception as e:

                status_type = 'error'
                status_message = f'Error removing items: {str(e)}'

        return self.render_page(request, form, status_type, status_message)



    def post(self, request, *args, **kwargs):

        form = self.form_class(request.POST)
        status_type = None
        status_message = None

        if form.is_valid():

            product = form.cleaned_data['Iproduct']
            quantity = form.cleaned_data['Iquantity']

            # Build one Item per physical unit, then save them all in one go

            new_items = []

            for i in range(quantity):

                new_items.append(Item(
                    Iproduct=product,
                    Ireceived=form.cleaned_data['Ireceived'],
                    Iexpiry=form.cleaned_data['Iexpiry']
                ))

            try:

                Item.objects.bulk_create(new_items)

                status_type = 'success'
                status_message = f'{quantity} x {product.Pname} added to stock.'

                form = self.form_class(initial={'Ireceived': timezone.localdate()})

            except Exception as e:

                status_type = 'error'
                status_message = f'Error adding items: {str(e)}'

        else:

            status_type = 'error'
            status_message = 'Please correct the errors below.'

        return self.render_page(request, form, status_type, status_message)



    def render_page(self, request, form, status_type, status_message):

        rendered_form = form.render('adminpanel/form_template.html')

        # Write off anything inside each products expiry window before showing the stock

        removed = remove_expiring_stock()

        written_off = Item.objects.filter(Iorder__isnull=True, Istatus='expired').count()

        # Group warehouse items into batches: same product, received date and expiry date

        batches = Item.objects.filter(Istatus='available').values(
            'Iproduct', 'Iproduct__Pname', 'Ireceived', 'Iexpiry'
        ).annotate(count=Count('id')).order_by('Iexpiry', 'Iproduct')

        context = {
            'form': rendered_form,
            'batches': batches,
            'removed': removed,
            'written_off': written_off,
            'today': timezone.localdate(),
            'status_type': status_type,
            'status_message': status_message,
        }

        return render(request, self.template_name, context)