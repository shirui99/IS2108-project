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
from .forms import ProductForm, CustomerForm, OrderForm, ItemBatchForm, CategoryForm, StockAdjustmentForm, OrderCancellationForm
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

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_active and request.user.is_staff):
            return redirect('adminpanel_login')
        return super().dispatch(request, *args, **kwargs)



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
                return HttpResponse('Product not found.', status=404)

        else:

            form = self.form_class()

        rendered_form = form.render('adminpanel/form_template.html')

        # Count each product's items that are still in the warehouse

        products = Product.objects.select_related("Pcategory").annotate(
            stock=Count('product_items', filter=Q(product_items__Istatus='available'))
        )

        context = {
            'product_id': form.instance.pk or '',
            'current_product': Product.objects.filter(pk=form.instance.pk).first() if action == 'update' else None,
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
            except (DatabaseError, OSError):
                form.add_error(None, 'The product could not be saved. Check its details and try again.')
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
            'current_product': Product.objects.filter(pk=form.instance.pk).first() if action == 'update' else None,
            'form': rendered_form,
            'action': action,
            'products': products,
            'status_type': status_type,
            'status_message': status_message,
        }

        return render(request, self.template_name, context)

class CustomerView(View):
    template_name = 'adminpanel/customer_new.html'

    def dispatch(self, request, *args, **kwargs):
        if not _staff_order_access(request):
            return redirect('/adminpanel/login')
        return super().dispatch(request, *args, **kwargs)

    def page(self, request, customer=None, form=None):
        query = request.GET.get('q', '').strip()
        customers = Customer.objects.select_related('Cuser').order_by('Cname', 'Cid')
        if query:
            customers = customers.filter(
                Q(Cid__icontains=query) | Q(Cname__icontains=query)
                | Q(Cuser__username__icontains=query) | Q(Cuser__email__icontains=query)
            )
        context = {'customers': customers, 'query': query, 'customer': customer}
        if customer:
            context.update({
                'form': form if form is not None else CustomerForm(instance=customer),
                'orders': Orders.objects.filter(Ocustomer=customer).order_by('-Odate', '-Oid'),
                'tickets': SupportTicket.objects.filter(Torder__Ocustomer=customer).select_related('Torder').order_by('-Tsubmitted'),
            })
        return render(request, self.template_name, context)

    def get(self, request, pk=None):
        customer = get_object_or_404(Customer.objects.select_related('Cuser'), pk=pk) if pk is not None else None
        return self.page(request, customer)

    def post(self, request, pk=None):
        # The old root URL posted updates by ID; never allow it to create or delete.
        if request.POST.get('action', 'update') != 'update':
            return HttpResponse('Only contact updates are supported.', status=405)
        customer_id = pk if pk is not None else request.POST.get('Cid')
        customer = get_object_or_404(Customer.objects.select_related('Cuser'), pk=customer_id)
        form = CustomerForm(request.POST, instance=customer)
        valid = form.is_valid()
        allowed = {'Cname', 'Caddress', 'email', 'action', 'Cid', 'csrfmiddlewaretoken'}
        if set(request.POST) - allowed or (request.POST.get('Cid') and request.POST['Cid'] != customer.pk):
            form.add_error(None, 'Only the displayed contact fields can be changed.')
            valid = False
        if valid:
            with transaction.atomic():
                customer = form.save(commit=False)
                customer.save(update_fields=['Cname', 'Caddress'])
                customer.Cuser.email = form.cleaned_data['email']
                customer.Cuser.save(update_fields=['email'])
            messages.success(request, 'Contact details updated.')
            return redirect('customer_new', pk=customer.pk)
        return self.page(request, customer, form)


def _staff_order_access(request):
    return request.user.is_authenticated and request.user.is_active and request.user.is_staff


def _order_origin(order):
    group = getattr(order, 'group_purchase', None)
    cycle = getattr(order, 'subscription_cycle', None)
    if group and cycle:
        return 'Multiple origins'
    if group:
        return 'Group'
    if cycle:
        return 'Subscription'
    return 'Other / origin not recorded'


@require_GET
def order_inspection_list(request):
    if not _staff_order_access(request):
        return redirect('adminpanel_login')
    status = request.GET.get('status', '')
    origin = request.GET.get('origin', '')
    errors = []
    if status and status not in dict(Orders.STATUS):
        errors.append('Invalid status filter. Choose a listed status.')
        status = ''
    if origin and origin not in ('group', 'subscription', 'other'):
        errors.append('Invalid origin filter. Choose a listed origin.')
        origin = ''
    orders = Orders.objects.select_related('Ocustomer', 'group_purchase', 'subscription_cycle').order_by('-Odate', '-Oid')
    if status:
        orders = orders.filter(Ostatus=status)
    if origin == 'group':
        orders = orders.filter(group_purchase__isnull=False)
    elif origin == 'subscription':
        orders = orders.filter(subscription_cycle__isnull=False)
    elif origin == 'other':
        orders = orders.filter(group_purchase__isnull=True, subscription_cycle__isnull=True)
    for order in orders:
        order.origin_label = _order_origin(order)
    return render(request, 'adminpanel/order_inspection_list.html', {'orders': orders, 'statuses': Orders.STATUS,
        'selected_status': status, 'selected_origin': origin, 'filter_errors': errors})


@require_GET
def order_inspection_detail(request, pk):
    if not _staff_order_access(request):
        return redirect('adminpanel_login')
    from decimal import Decimal
    order = get_object_or_404(Orders.objects.select_related('Ocustomer', 'group_purchase', 'subscription_cycle__SCsubscription__Sproduct'), pk=pk)
    rows = order.order_items.values('Iproduct_id', 'Iproduct__Pname', 'Iproduct__Psize', 'Ipurchasedprice',
        'Ibatch_id', 'Ibatch__Breference').annotate(quantity=Count('id')).order_by('Iproduct_id', 'Ipurchasedprice', 'Ibatch_id')
    grouped = {}
    for row in rows:
        key = (row['Iproduct_id'], row['Ipurchasedprice'])
        if key not in grouped:
            grouped[key] = {'product_id': row['Iproduct_id'], 'name': row['Iproduct__Pname'], 'size': row['Iproduct__Psize'],
                'price': row['Ipurchasedprice'], 'quantity': 0, 'batches': []}
        line = grouped[key]
        line['quantity'] += row['quantity']
        line['batches'].append({'reference': row['Ibatch__Breference'], 'quantity': row['quantity']})
    for line in grouped.values():
        line['amount'] = Decimal(str(line['price'])) * line['quantity'] if line['price'] is not None else None
    group = getattr(order, 'group_purchase', None)
    cycle = getattr(order, 'subscription_cycle', None)
    members = []
    if group:
        contributions = list(group.group_lines.select_related('GLcustomer', 'GLproduct').order_by('GLcustomer__Cname', 'GLproduct__Pname'))
        for member in group.group_members.select_related('GMcustomer').order_by('GMcustomer__Cname', 'pk'):
            members.append({'customer': member.GMcustomer, 'lines': [line for line in contributions if line.GLcustomer_id == member.GMcustomer_id]})
        member_ids = {member['customer'].pk for member in members}
        unmatched = {}
        for line in contributions:
            if line.GLcustomer_id not in member_ids:
                unmatched.setdefault(line.GLcustomer_id, {'customer': line.GLcustomer, 'lines': [], 'unmatched': True})['lines'].append(line)
        members.extend(unmatched.values())
    return render(request, 'adminpanel/order_inspection_detail.html', {'order': order, 'origin': _order_origin(order),
        'lines': list(grouped.values()), 'group': group, 'members': members, 'cycle': cycle, 'cancel_form': OrderCancellationForm()})


class OrderView(View):

    form_class = OrderForm
    template_name = 'adminpanel/order_new.html'



    def dispatch(self, request, *args, **kwargs):
        if not _staff_order_access(request):
            return redirect('adminpanel_login')
        return super().dispatch(request, *args, **kwargs)

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
            'order_id': form.instance.pk or '', 'form': rendered_form,
            'action': action, 
            'orders': orders,
            'status_type': status_type,
            'status_message': status_message,
        }

        return render(request, self.template_name, context)



    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        order = get_object_or_404(Orders, pk=kwargs.get('pk') or request.POST.get('Oid')) if action in ('update', 'delete') else None
        if action == 'delete':
            # Orders are retained once created; deleting them could erase fulfilment history.
            return HttpResponse('Orders must be retained. Use the supported order workflows.', status=400)
        if action not in ('create', 'update'):
            return HttpResponse('Invalid order action.', status=400)
        original_pk = order.pk if order else None
        form = self.form_class(request.POST, instance=order)
        if form.is_valid():
            try:
                with transaction.atomic():
                    if order:
                        Orders.objects.filter(pk=original_pk).update(Ostatus=F('Ostatus'))
                        current = Orders.objects.get(pk=original_pk)
                        if request.POST.get('Oid') != current.pk:
                            form.add_error('Oid', 'The order ID cannot be changed.')
                        if request.POST.get('Ostatus', current.Ostatus) != current.Ostatus:
                            form.add_error(None, 'Use the fulfilment actions to change status.')
                        owner_changed = form.cleaned_data['Ocustomer'].pk != current.Ocustomer_id
                        if owner_changed and (current.order_items.exists() or getattr(current, 'cancellation', None) or getattr(current, 'group_purchase', None) or getattr(current, 'subscription_cycle', None)):
                            form.add_error('Ocustomer', 'The customer cannot change for an allocated or linked order.')
                        if current.Ostatus == 'cancelled':
                            if form.cleaned_data['Oaddress'] != current.Oaddress:
                                form.add_error('Oaddress', 'The delivery address cannot change after cancellation.')
                            if form.cleaned_data['Odate'] != current.Odate:
                                form.add_error('Odate', 'The order date cannot change after cancellation.')
                        if not form.errors:
                            Orders.objects.filter(pk=current.pk).update(Ocustomer=form.cleaned_data['Ocustomer'], Oaddress=form.cleaned_data['Oaddress'], Odate=form.cleaned_data['Odate'])
                    elif request.POST.get('Ostatus', 'placed') != 'placed':
                        form.add_error(None, 'New manual orders must start as placed.')
                    else:
                        form.save(commit=False).save(force_insert=True)
            except DatabaseError:
                form.add_error(None, 'The order could not be saved. Review its ID and try again.')
            else:
                if not form.errors:
                    return redirect('order_new')
        return render(request, self.template_name, {'order_id': original_pk or '', 'form': form.render('adminpanel/form_template.html'), 'action': action,
            'orders': Orders.objects.annotate(items=Count('order_items')), 'status_type': 'error', 'status_message': 'Please correct the order details.'})


@require_POST
def staff_cancel_order(request, pk):
    if not _staff_order_access(request):
        return redirect('adminpanel_login')
    from store.cancellation import cancel_order
    order = get_object_or_404(Orders, pk=pk)
    form = OrderCancellationForm(request.POST)
    if form.is_valid():
        try:
            cancelled = cancel_order(pk, employee=request.user, reason=form.cleaned_data['reason'])
        except (ValueError, DatabaseError) as error:
            form.add_error(None, str(error) if isinstance(error, ValueError) else 'The order could not be cancelled. Please review it and try again.')
        else:
            if cancelled:
                messages.success(request, 'Order cancelled; allocation history retained and simulated payment refunded.')
            else:
                messages.info(request, 'Only a placed order can be cancelled. This order was not changed.')
            return redirect('staff_order_detail', pk=pk)
    return render(request, 'adminpanel/order_cancel.html', {'order': order, 'form': form})


@require_POST
def fulfil_order(request, pk):
    if not _staff_order_access(request):
        return redirect('adminpanel_login')
    transitions = {'prepare': ('placed', 'preparing'), 'dispatch': ('preparing', 'dispatched'), 'deliver': ('dispatched', 'delivered')}
    step = transitions.get(request.POST.get('action'))
    if not step:
        return HttpResponse('Invalid fulfilment action.', status=400)
    source, target = step
    try:
        get_object_or_404(Orders, pk=pk)
        with transaction.atomic():
            changes = {'Ostatus': target}
            if target == 'dispatched': changes['Odispatched'] = timezone.now()
            if target == 'delivered': changes['Odelivered'] = timezone.now()
            if not Orders.objects.filter(pk=pk, Ostatus=source).update(**changes):
                messages.info(request, 'The order has already moved on or this action is out of sequence.')
                return redirect('staff_order_detail', pk=pk)
            packs = Item.objects.filter(Iorder_id=pk)
            total = packs.count()
            if not total or packs.exclude(Istatus__in=['allocated', 'delivered'], Ifinished__isnull=True, Irating__isnull=True).exists():
                raise ValueError('The order has no untouched allocation. Review its packs before fulfilment.')
            if target == 'delivered':
                changed = packs.filter(Istatus__in=['allocated', 'delivered'], Ifinished__isnull=True, Irating__isnull=True).update(Istatus='delivered')
                if changed != total:
                    raise ValueError('Allocated packs changed. No delivery was recorded.')
    except (ValueError, DatabaseError) as error:
        messages.error(request, str(error) if isinstance(error, ValueError) else 'The order could not be updated. Please try again.')
    else:
        messages.success(request, f'Order marked {target}.')
    return redirect('staff_order_detail', pk=pk)


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
    template_name = 'adminpanel/support.html'
    response_max_length = 2000

    def dispatch(self, request, *args, **kwargs):
        if not _staff_order_access(request):
            return redirect('adminpanel_login')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, pk=None):
        return self.render_page(request, pk)

    def post(self, request, pk=None):
        if pk is None:
            return HttpResponse('Select a ticket before responding.', status=405)
        get_object_or_404(SupportTicket, pk=pk)
        response = request.POST.get('Tresponse', '').strip()
        if not response:
            return self.render_page(request, pk, 'Please enter a response.')
        if len(response) > self.response_max_length:
            return self.render_page(request, pk, 'The response can be at most 2000 characters.')
        try:
            # A single conditional update ensures the first response wins.
            updated = SupportTicket.objects.filter(pk=pk, Tstatus='open').update(
                Tresponse=response, Tstatus='answered', Tresponder_id=request.user.pk,
                Tresponded=timezone.now(),
            )
        except DatabaseError:
            return self.render_page(request, pk, 'The response could not be saved. Please try again.')
        if updated:
            messages.success(request, 'Response sent.')
            return redirect('support', pk=pk)
        return self.render_page(request, pk, 'This ticket has already been answered.')

    def render_page(self, request, pk=None, error=None):
        tickets = SupportTicket.objects.select_related('Torder__Ocustomer', 'Tresponder').order_by('-Tstatus', 'Tsubmitted', 'pk')
        ticket = get_object_or_404(tickets, pk=pk) if pk is not None else None
        return render(request, self.template_name, {
            'tickets': tickets, 'ticket': ticket, 'status_type': 'error' if error else None,
            'status_message': error, 'response_max_length': self.response_max_length,
        })


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
