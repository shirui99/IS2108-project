from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from uuid import uuid4
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Count, Q, F
from django.db.models.deletion import RestrictedError
from django.shortcuts import render, HttpResponse, redirect, get_object_or_404
from datetime import timedelta
from django.utils import timezone
from django.views import View

from .models import Product, Customer, Orders, Item, SupportTicket, Category, category_code, InventoryBatch, StockAdjustment
from .forms import ProductForm, CustomerForm, OrderForm, ItemBatchForm, CategoryForm, StockAdjustmentForm
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

        products = Product.objects.select_related("Pcategory").annotate(
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

        if action == 'deactivate':
            pk = kwargs.get('pk') or request.POST.get('Pid')
            if kwargs.get('pk') and request.POST.get('Pid') != pk:
                return HttpResponse('Product ID does not match.', status=400)
            product = get_object_or_404(Product, pk=pk)
            if Product.objects.filter(pk=product.pk, Pactive=True).update(Pactive=False):
                messages.success(request, f'{product.Pname} was deactivated.')
            else:
                messages.info(request, f'{product.Pname} is already inactive.')
            return redirect('product_new')

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
            products = Product.objects.select_related("Pcategory").annotate(
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

        products = Product.objects.select_related("Pcategory").annotate(
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

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_active and request.user.is_staff):
            return redirect('adminpanel_login')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return self.render_page(request, self.form_class(initial={'Ireceived': timezone.localdate()}))

    def post(self, request):
        if request.POST.get('action') not in (None, '', 'create'):
            return HttpResponse('Invalid action.', status=400)
        form = self.form_class(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                with transaction.atomic():
                    # Conditional write serializes the active check with deactivation on SQLite.
                    if not Product.objects.filter(pk=data['Iproduct'].pk, Pactive=True).update(Pactive=F('Pactive')):
                        form.add_error('Iproduct', 'Select an active product.')
                        return self.render_page(request, form)
                    batch = InventoryBatch.objects.create(Breference=data['Breference'], Bproduct=data['Iproduct'],
                        Breceived=data['Ireceived'], Bquantity=data['Iquantity'], Bdatetype=data['Bdatetype'], Bdate=data['Iexpiry'])
                    Item.objects.bulk_create([Item(Ibatch=batch, Iproduct=data['Iproduct'], Ireceived=data['Ireceived'],
                        Iexpiry=data['Iexpiry']) for _ in range(data['Iquantity'])])
            except IntegrityError:
                if InventoryBatch.objects.filter(Breference=data['Breference']).exists():
                    form.add_error('Breference', 'This batch reference has already been received.')
                else:
                    form.add_error(None, 'The batch could not be saved. Please try again.')
            else:
                messages.success(request, f"Received {data['Iquantity']} packs of {data['Iproduct'].Pname}.")
                return redirect('item_new')
        return self.render_page(request, form)

    def render_page(self, request, form):
        today = timezone.localdate()
        receipts = InventoryBatch.objects.select_related('Bproduct').annotate(
            available=Count('items', filter=Q(items__Istatus='available'))).order_by('-Breceived', '-pk')
        for receipt in receipts:
            receipt.group_token = signing.dumps({'batch': receipt.pk}, salt='stock-group')
            if receipt.Bdate is None:
                receipt.concern = 'Undated'
            elif receipt.Bdate < today:
                receipt.concern = 'Past printed date - not sellable'
            elif receipt.Bdate < today + timedelta(days=receipt.Bproduct.Pexpirydays):
                receipt.concern = 'Within product shelf-life cutoff - not sellable'
            elif receipt.Bdate <= today + timedelta(days=7):
                receipt.concern = 'Near printed date - review stock'
            else:
                receipt.concern = 'Meets date cutoff'
        legacy = Item.objects.filter(Ibatch__isnull=True).values(
            'Iproduct', 'Iproduct__Pname', 'Ireceived', 'Iexpiry').annotate(
                count=Count('id', filter=Q(Istatus='available', Iorder__isnull=True))).order_by('Iexpiry', 'Iproduct')
        legacy = list(legacy)
        for group in legacy:
            group['group_token'] = signing.dumps({'product': group['Iproduct'], 'received': group['Ireceived'].isoformat(), 'date': group['Iexpiry'].isoformat() if group['Iexpiry'] else None}, salt='stock-group')
        return render(request, self.template_name, {'history': StockAdjustment.objects.select_related('staff', 'product', 'batch'), 'form': form.render('adminpanel/form_template.html'),
            'receipts': receipts, 'batches': legacy, 'today': today,
            'written_off': Item.objects.filter(Iorder__isnull=True, Istatus='expired').count()})

class StockChanged(Exception):
    pass


def stock_group(token):
    try:
        group = signing.loads(token, salt='stock-group')
        if not isinstance(group, dict):
            raise ValueError
        if set(group) == {'batch'}:
            batch = get_object_or_404(InventoryBatch, pk=group['batch'])
            return batch.Bproduct_id, batch, batch.Breceived, batch.Bdate
        if set(group) != {'product', 'received', 'date'}:
            raise ValueError
        from django.utils.dateparse import parse_date
        received = parse_date(group['received'])
        recorded = parse_date(group['date']) if group['date'] else None
        if not received or (group['date'] and not recorded):
            raise ValueError
        product = get_object_or_404(Product, pk=group['product'])
        if not Item.objects.filter(Ibatch__isnull=True, Iproduct=product, Ireceived=received, Iexpiry=recorded).exists():
            raise ValueError
        return product.pk, None, received, recorded
    except (signing.BadSignature, ValueError, TypeError, KeyError, ValidationError):
        return None


class StockAdjustmentView(View):
    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_active and request.user.is_staff):
            return redirect('adminpanel_login')
        return super().dispatch(request, *args, **kwargs)

    def display(self, request, token, action, form=None):
        group = stock_group(token)
        if not group or action not in ('correction', 'writeoff'):
            return HttpResponse('Stock group or action is invalid.', status=400)
        product_id, batch, received, recorded = group
        items = Item.objects.filter(Iproduct_id=product_id, Ibatch=batch, Ireceived=received, Iexpiry=recorded, Istatus='available', Iorder__isnull=True)
        available = items.count()
        if form is None:
            form = StockAdjustmentForm(action=action, initial={'request_id': uuid4(), 'group': token, 'action': action, 'expected_count': available, 'snapshot': signing.dumps([token, action, available], salt='stock-snapshot')})
        return render(request, 'adminpanel/stock_adjust.html', {'form': form, 'action': action, 'batch': batch,
            'product': Product.objects.get(pk=product_id), 'received': received, 'recorded': recorded, 'available': available})

    def get(self, request):
        return self.display(request, request.GET.get('group', ''), request.GET.get('action', ''))

    def post(self, request):
        token, action = request.POST.get('group', ''), request.POST.get('action', '')
        group = stock_group(token)
        if not group or action not in ('correction', 'writeoff'):
            return HttpResponse('Stock group or action is invalid.', status=400)
        form = StockAdjustmentForm(request.POST, action=action)
        if not form.is_valid():
            return self.display(request, token, action, form)
        product_id, batch, received, recorded = group
        data = form.cleaned_data
        try:
            snapshot = signing.loads(data['snapshot'], salt='stock-snapshot')
            if snapshot != [token, action, data['expected_count']]:
                raise signing.BadSignature
        except signing.BadSignature:
            form.add_error(None, 'The stock count details are invalid. Return to the stock page and open a new form.')
            return self.display(request, token, action, form)
        try:
            with transaction.atomic():
                # Serialize adjustments/receipts by product; on SQLite this takes the write lock before counting.
                Product.objects.filter(pk=product_id).update(Pactive=F('Pactive'))
                if StockAdjustment.objects.filter(request_id=data['request_id']).exists():
                    messages.info(request, 'This adjustment was already submitted.')
                    return redirect('item_new')
                items = Item.objects.select_for_update().filter(Iproduct_id=product_id, Ibatch=batch,
                    Ireceived=received, Iexpiry=recorded, Istatus='available', Iorder__isnull=True)
                ids = list(items.order_by('pk').values_list('pk', flat=True))
                before = len(ids)
                if before != data['expected_count']:
                    form.add_error(None, 'Stock changed since this form was opened. Return to the stock page and open a new form.')
                    return self.display(request, token, action, form)
                after = data['quantity'] if action == 'correction' else before - data['quantity']
                if after < 0:
                    form.add_error('quantity', 'The quantity exceeds available unallocated packs.')
                    return self.display(request, token, action, form)
                difference = after - before
                audit = StockAdjustment.objects.create(request_id=data['request_id'], kind=action,
                    product_id=product_id, batch=batch, received=received, recorded_date=recorded,
                    before_count=before, after_count=after, difference=difference,
                    reason=data['reason'], note=data.get('note', ''), staff=request.user)
                if difference < 0:
                    chosen = ids[:abs(difference)]
                    changed = Item.objects.filter(pk__in=chosen, Istatus='available', Iorder__isnull=True).update(
                        Istatus='adjusted' if action == 'correction' else 'writtenoff')
                    if changed != len(chosen):
                        raise StockChanged
                    audit.items.add(*chosen)
                elif difference > 0:
                    created = Item.objects.bulk_create([Item(Iproduct_id=product_id, Ibatch=batch,
                        Ireceived=received, Iexpiry=recorded) for _ in range(difference)])
                    audit.items.add(*created)
                if Item.objects.filter(Iproduct_id=product_id, Ibatch=batch, Ireceived=received,
                        Iexpiry=recorded, Istatus='available', Iorder__isnull=True).count() != after:
                    raise StockChanged
        except (StockChanged, DatabaseError):
            if StockAdjustment.objects.filter(request_id=data['request_id']).exists():
                messages.info(request, 'This adjustment was already submitted.')
                return redirect('item_new')
            form.add_error(None, 'Stock changed or the adjustment could not be saved. Review the current count and try again.')
            return self.display(request, token, action, form)
        messages.success(request, 'Stock adjustment recorded.')
        return redirect('item_new')


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


class CategoryView(View):
    http_method_names = ['get', 'post', 'head', 'options']

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_active and request.user.is_staff):
            return redirect('adminpanel_login')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return self.render(request, CategoryForm())

    def render(self, request, form):
        return render(request, 'adminpanel/category_new.html', {'form': form})

    def post(self, request):
        form = CategoryForm(request.POST)
        if form.is_valid():
            for attempt in range(5):
                code = category_code()
                try:
                    with transaction.atomic():
                        Category.objects.create(Ccode=code, Cname=form.cleaned_data['Cname'])
                except IntegrityError:
                    # The database decides duplicates, including concurrent submissions.
                    if Category.objects.filter(Cname=form.cleaned_data['Cname']).exists():
                        form.add_error('Cname', 'A category with this name already exists.')
                        break
                    if not Category.objects.filter(pk=code).exists():
                        form.add_error(None, 'The category could not be saved. Please try again.')
                        break
                else:
                    messages.success(request, 'Category created. It is now available on product forms.')
                    return redirect('category_new')
            else:
                form.add_error(None, 'A unique category code could not be generated. Please try again.')
        return self.render(request, form)
