from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.models.deletion import RestrictedError
from django.shortcuts import render, HttpResponse, redirect, get_object_or_404
from datetime import timedelta
from django.utils import timezone
from django.views import View

from .models import Product, Customer, Orders, Item, SupportTicket
from .forms import ProductForm, CustomerForm, OrderForm, ItemBatchForm
from .stock_advice import get_stock_advice


# Create your views here.

def index(request):

    return render(request, 'adminpanel/index.html')


@require_GET
def stock_advice(request):
    return render(request, 'adminpanel/stock_advice.html', get_stock_advice(timezone.localdate()))



def login(request):

    if request.method == 'GET':

        # Display the login form
        return render(request, 'adminpanel/login.html')
    
    elif request.method == 'POST':

        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(username=username, password=password)

        if user is not None and user.is_active and user.is_staff:

            request.session.flush()
            auth_login(request, user)
            request.session['staff_user_id'] = user.pk #for ticket answering

            return render(request, 'adminpanel/login.html', {'success_message': 'Authentication successful!'})
        
        else:

            return render(request, 'adminpanel/login.html', {'error_message': 'Invalid username or password.'})



@require_POST
def logout(request):

    auth_logout(request)

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

                form = self.form_class(instance=product)
                form.fields['Pid'].disabled = True
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
            'product_id': form.instance.pk or '',
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

        if action == 'delete':
            form = self.form_class()
            try:
                Product.objects.get(pk=request.POST.get('Pid')).delete()
                status_type = 'success'
                status_message = 'Product deleted successfully.'
            except Product.DoesNotExist:
                status_type = 'error'
                status_message = 'Product could not be found.'
            except RestrictedError:
                status_type = 'error'
                status_message = 'This product cannot be deleted while related stock records exist.'
            except Exception:
                status_type = 'error'
                status_message = 'The product could not be deleted.'

            rendered_form = form.render('adminpanel/form_template.html')
            products = Product.objects.annotate(
                stock=Count('product_items', filter=Q(product_items__Istatus='available'))
            )
            context = {
                'product_id': form.instance.pk or '',
                'form': rendered_form,
                'action': 'create',
                'products': products,
                'status_type': status_type,
                'status_message': status_message,
            }
            return render(request, self.template_name, context)



        if action not in ('create', 'update'):
            return HttpResponse('Invalid product action.', status=400)
        if action == 'update':
            product = get_object_or_404(Product, pk=kwargs.get('pk') or request.POST.get('Pid'))
            if kwargs.get('pk') and request.POST.get('Pid') != product.Pid:
                return HttpResponse('Product ID cannot be changed.', status=400)
            form = self.form_class(request.POST, request.FILES, instance=product)
            form.fields['Pid'].disabled = True
        else:
            form = self.form_class(request.POST, request.FILES)

        if form.is_valid():
            try:
                with transaction.atomic():
                    if action == 'create':
                        # A concurrent create must never overwrite the same SKU.
                        form.save(commit=False).save(force_insert=True)
                    else:
                        form.save()
            except IntegrityError:
                form.add_error(None, 'The product could not be saved. Check that its SKU is unique and try again.')
            else:
                return redirect('/adminpanel/product_new')
        status_type = 'error'
        status_message = 'Please correct the product details below.'

        rendered_form = form.render('adminpanel/form_template.html')

        # Count each product's items that are still in the warehouse

        products = Product.objects.annotate(
            stock=Count('product_items', filter=Q(product_items__Istatus='available'))
        )
        context = {
            'product_id': form.instance.pk or '',
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
        save_succeeded = False

        if action == 'delete':
            form = self.form_class()
            try:
                Customer.objects.get(pk=request.POST.get('Cid')).delete()
                status_type = 'success'
                status_message = 'Customer deleted successfully.'
            except Customer.DoesNotExist:
                status_type = 'error'
                status_message = 'Customer could not be found.'
            except RestrictedError:
                status_type = 'error'
                status_message = 'This customer cannot be deleted while related orders exist.'
            except Exception:
                status_type = 'error'
                status_message = 'The customer could not be deleted.'

            rendered_form = form.render('adminpanel/form_template.html')
            customers = Customer.objects.all()
            context = {
                'form': rendered_form,
                'action': 'create',
                'customers': customers,
                'status_type': status_type,
                'status_message': status_message,
            }
            return render(request, self.template_name, context)



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

                    save_succeeded = True
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

                        save_succeeded = True
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

        if save_succeeded:
            # Keep invalid bound data visible so staff can correct the submitted form.
            form = self.form_class()
            action = 'create'

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
        save_succeeded = False

        if action == 'delete':
            form = self.form_class()
            try:
                Orders.objects.get(pk=request.POST.get('Oid')).delete()
                status_type = 'success'
                status_message = 'Order deleted successfully.'
            except Orders.DoesNotExist:
                status_type = 'error'
                status_message = 'Order could not be found.'
            except RestrictedError:
                status_type = 'error'
                status_message = 'This order cannot be deleted while related items or tickets exist.'
            except Exception:
                status_type = 'error'
                status_message = 'The order could not be deleted.'

            rendered_form = form.render('adminpanel/form_template.html')
            orders = Orders.objects.annotate(items=Count('order_items'))
            context = {
                'form': rendered_form,
                'action': 'create',
                'orders': orders,
                'status_type': status_type,
                'status_message': status_message,
            }
            return render(request, self.template_name, context)


        
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
                    save_succeeded = True
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

                        save_succeeded = True
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

        if save_succeeded:
            # Keep invalid bound data visible so staff can correct the submitted form.
            form = self.form_class()
            action = 'create'

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

class ItemView(View):

    form_class = ItemBatchForm
    template_name = 'adminpanel/item_new.html'



    def get(self, request, *args, **kwargs):

        form = self.form_class(initial={'Ireceived': timezone.localdate()})
        status_type = None
        status_message = None

        return self.render_page(request, form, status_type, status_message)



    def post(self, request, *args, **kwargs):

        form = self.form_class(request.POST)
        status_type = None
        status_message = None

        if request.POST.get('action') == 'delete':
            try:
                batch = Item.objects.filter(
                    Istatus='available',
                    Iproduct_id=request.POST.get('product'),
                    Ireceived=request.POST.get('received')
                )
                expiry = request.POST.get('expiry')
                if expiry:
                    batch = batch.filter(Iexpiry=expiry)
                else:
                    batch = batch.filter(Iexpiry__isnull=True)

                count, _ = batch.delete()
                status_type = 'success'
                status_message = f'{count} item(s) removed from stock.'
            except RestrictedError:
                status_type = 'error'
                status_message = 'This stock batch cannot be removed because it is related to another record.'
            except Exception:
                status_type = 'error'
                status_message = 'The stock batch could not be removed.'

            return self.render_page(request, self.form_class(initial={'Ireceived': timezone.localdate()}), status_type, status_message)

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

        # Write-offs require an explicit audited workflow (not implemented here).
        removed = 0

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

class SupportView(View):

    template_name = 'adminpanel/support.html' #support page for tickets



    def get(self, request, *args, **kwargs):

        return self.render_page(request, kwargs.get('pk'), None, None)



    def post(self, request, *args, **kwargs):

        pk = kwargs.get('pk')
        response = request.POST.get('Tresponse', '').strip()

        if not response:

            return self.render_page(request, pk, 'error', 'Please enter a response.')

        # Only answer a ticket that is still open, so a repeated submission changes nothing
        updated = SupportTicket.objects.filter(pk=pk, Tstatus='open').update(
            Tresponse=response,
            Tstatus='answered',
            Tresponder_id=request.user.pk,
            Tresponded=timezone.now()
        )

        if updated:

            return self.render_page(request, pk, 'success', 'Response sent.')

        return self.render_page(request, pk, 'error', 'This ticket has already been answered.')



    def render_page(self, request, pk, status_type, status_message):

        # Open tickets first, oldest first
        tickets = SupportTicket.objects.select_related('Torder__Ocustomer').order_by('-Tstatus', 'Tsubmitted')

        ticket = tickets.filter(pk=pk).first() if pk is not None else None

        context = {
            'tickets': tickets,
            'ticket': ticket,
            'status_type': status_type,
            'status_message': status_message,
        }

        return render(request, self.template_name, context)
