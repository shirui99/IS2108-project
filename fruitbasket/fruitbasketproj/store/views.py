from django.db.models import Count, Avg
from django.shortcuts import redirect, render, HttpResponse
from django.utils import timezone

from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.views.decorators.http import require_POST
from django.contrib import messages

from adminpanel.models import Customer, Product, Orders, Item, SupportTicket
from adminpanel.inventory import sellable_stock_filter
from django.db import transaction
from django.db.models import F
from .restock import get_customer_purchase_history, get_restock_suggestions

# Create your views here.

def index(request):

    # Find avg rating and number of ratings from all items
    products = Product.objects.filter(Pactive=True).annotate(
        rating=Avg('product_items__Irating'),
        reviews=Count('product_items__Irating'),
        sellable_stock=Count('product_items', filter=sellable_stock_filter(item_prefix='product_items__', product_prefix=''))
    )

    category = request.GET.get('category', '')
    if category not in dict(Product.CATEGORY):
        category = ''
    if category:
        products = products.filter(Pcategory=category)

    sort = request.GET.get('sort', 'name')
    sort_options = {
        'name': ('Pname', 'Pid'),
        'price_asc': ('Pprice', 'Pname', 'Pid'),
        'price_desc': ('-Pprice', 'Pname', 'Pid'),
    }
    if sort not in sort_options:
        sort = 'name'
    products = products.order_by(*sort_options[sort])

    return render(request, 'store/index.html', {
        'products': products,
        'categories': Product.CATEGORY,
        'selected_category': category,
        'selected_sort': sort,
    })


def restock(request):
    """Render due restock suggestions for the session's customer.

    Args:
        request: Django request containing the project's `Cid` session value.

    Returns:
        A redirect to the existing login route when unauthenticated, otherwise
        the server-rendered restock page with due product suggestions.
    """
    customer_id = request.session.get('Cid')
    if not customer_id:
        return redirect('/store/login')

    has_purchase_history = bool(get_customer_purchase_history(customer_id))
    suggestions = get_restock_suggestions(customer_id)
    today = timezone.localdate()
    for suggestion in suggestions:
        suggestion['due_status'] = (
            'Overdue'
            if suggestion['restock_date'] < today.isoformat()
            else 'Due soon'
        )
        suggestion['estimate_label'] = (
            'ML estimate'
            if suggestion['status'] == 'MODEL'
            else 'Initial estimate'
        )

    empty_message = (
        'No qualifying purchase history is available for personalised suggestions.'
        if not has_purchase_history
        else 'No products are currently due for restocking.'
    )
    return render(
        request,
        'store/restock.html',
        {'suggestions': suggestions, 'empty_message': empty_message},
    )

def generate_customer_id():
    customer_count = Customer.objects.count()
    return str(customer_count + 1).zfill(4)

def generate_order_id():
    order_count = Orders.objects.count()
    return str(order_count + 1).zfill(5)

def signup(request):

    if request.method == 'GET':

        # Display the user creation form
        return render(request, 'store/signup.html')

    elif request.method == 'POST':

        username = request.POST.get('username')
        password = request.POST.get('password')
        email = request.POST.get('email')
        Cname = request.POST.get('Cname')
        Caddress = request.POST.get('Caddress')
        Chouseholdsize = request.POST.get('Chouseholdsize')
        Cmealsperweek = request.POST.get('Cmealsperweek')

        user = User.objects.create_user(username=username, password=password, email=email)

        newCustomer = Customer(
            Cid= "C" + generate_customer_id(),
            Cname=Cname,
            Caddress=Caddress,
            Chouseholdsize=Chouseholdsize,
            Cmealsperweek=Cmealsperweek,
            Cuser=user
        )

        newCustomer.save()

        return render(request, 'store/signup.html', {'message': 'User created successfully!'})



def login(request):

    if request.method == 'GET':

        # Display the login form
        return render(request, 'store/login.html')
    
    elif request.method == 'POST':

        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(username=username, password=password)

        if user is not None:

            customer = Customer.objects.filter(Cuser=user).first()

            # Users made outside signup (e.g. createsuperuser) have no Customer yet, so create one
            if customer is None:

                customer = Customer.objects.create(
                    Cid='C' + generate_customer_id(),
                    Cname=user.username,
                    Caddress='',
                    Chouseholdsize=1,
                    Cmealsperweek=0,
                    Cuser=user
                )

            request.session.flush()
            request.session['Cid'] = customer.Cid

            # Redirect directly to the store shop or restock suggestions
            return redirect('/store/')  # Or redirect('restock') / redirect('/store/restock/')
        else:

            return render(request, 'store/login.html', {'error_message': 'Invalid username or password.'})



@require_POST
def logout(request):

    request.session.flush()

    return HttpResponse('You have logged out.')

def cart(request, pk=None):

    if 'cart' not in request.session:

        request.session['cart'] = {}

    cart = request.session['cart']

    if request.method == 'POST' and pk is not None:
        if request.POST.get('action') == 'remove':

            if pk in cart:

                del cart[pk]
                messages.success(request, 'Product removed from cart.')

        else:
            available = Item.objects.filter(sellable_stock_filter(), Iproduct_id=pk).count()
            if available <= cart.get(pk, 0):
                messages.error(request, f'Only {available} sellable pack(s) available. Your cart was not changed.')
                return redirect('/store/cart')

            if pk in cart:

                cart[pk] += 1

            else:

                cart[pk] = 1

            messages.success(request, 'Product added to cart.')

        request.session['cart'] = cart
        return redirect('/store/cart')

    cart_items = []
    total = 0

    for Pid in cart:

        product = Product.objects.filter(pk=Pid).first()
        if product is None:
            continue
        quantity = cart[Pid] if type(cart[Pid]) is int and cart[Pid] > 0 else 0
        subtotal = product.Pprice * quantity
        total += subtotal

        cart_items.append({'product': product, 'quantity': cart[Pid], 'subtotal': subtotal})

    context = {
        'cart_items': cart_items,
        'total': total,
    }

    return render(request, 'store/cart.html', context)

def checkout(request):

    
    cart = request.session.get('cart', {})

    cart_items = []
    total = 0

    for Pid in cart:

        product = Product.objects.filter(pk=Pid).first()
        if product is None:
            continue
        quantity = cart[Pid] if type(cart[Pid]) is int and cart[Pid] > 0 else 0
        subtotal = product.Pprice * quantity
        total += subtotal

        cart_items.append({'product': product, 'quantity': cart[Pid], 'subtotal': subtotal})

    context = {
        'cart_items': cart_items,
        'total': total,
        'status_type': None,
        'status_message': None,
    }

    if request.method == 'GET':

        # Display the order summary and delivery address
        customer = Customer.objects.filter(pk=request.session.get('Cid')).first()
        context['address'] = customer.Caddress if customer else ''

        return render(request, 'store/checkout.html', context)

    elif request.method == 'POST':

        Oaddress = request.POST.get('Oaddress')
        context['address'] = Oaddress

        if len(cart) == 0:

            context['status_type'] = 'error'
            context['status_message'] = 'Your cart is empty.'

            return render(request, 'store/checkout.html', context)

        class StockShortage(Exception):
            pass

        try:
            with transaction.atomic():
                allocations = []
                for Pid, quantity in cart.items():
                    product = Product.objects.filter(pk=Pid).first()
                    if type(quantity) is not int or quantity <= 0:
                        raise StockShortage('Invalid cart quantity. Please remove the product and add it again.')
                    eligible = Item.objects.filter(sellable_stock_filter(), Iproduct_id=Pid)
                    available = eligible.count()
                    if available < quantity or product is None:
                        name = product.Pname if product else Pid
                        raise StockShortage(f'Only {available} sellable pack(s) of {name} available; you requested {quantity}. No order was placed.')
                    ids = list(eligible.order_by(F('Iexpiry').asc(nulls_last=True), 'pk').values_list('pk', flat=True)[:quantity])
                    allocations.append((product, quantity, ids))

                newOrder = Orders.objects.create(
                    Oid='O' + generate_order_id(), Odate=timezone.localdate(),
                    Oaddress=Oaddress, Ocustomer=Customer.objects.get(pk=request.session['Cid']),
                )
                for product, quantity, ids in allocations:
                    claimed = Item.objects.filter(sellable_stock_filter(), pk__in=ids).update(
                        Iorder=newOrder, Istatus='delivered', Ipurchasedprice=product.Pprice,
                    )
                    if claimed != quantity:
                        raise StockShortage('Sellable stock changed during checkout. No order was placed. Please review your cart.')
        except StockShortage as error:
            context['status_type'] = 'error'
            context['status_message'] = str(error)
            return render(request, 'store/checkout.html', context)

        request.session['cart'] = {}

        context['cart_items'] = []
        context['total'] = 0
        context['status_type'] = 'success'
        context['status_message'] = f'Order {newOrder.Oid} placed successfully!'

        return render(request, 'store/checkout.html', context)

def orders(request, pk=None):

    status_type = None
    status_message = None
    tickets = [] # status type, message and tickets is tied directly to order 
    order = None
    order_items = []

    orders = Orders.objects.filter(Ocustomer_id=request.session.get('Cid')).annotate(items=Count('order_items'))

    if pk is not None:

        # Only show an order that belongs to the logged in customer
        order = orders.filter(pk=pk).first()

        if order is not None:


            if request.method == 'POST': #handle the post request

                subject = request.POST.get('Tsubject', '').strip()
                message = request.POST.get('Tmessage', '').strip()

                if subject and message:

                    SupportTicket.objects.create(Torder=order, Tsubject=subject, Tmessage=message) #create the support ticket

                    status_type = 'success'
                    status_message = 'Your issue has been sent to our support team.'

                else: #either subject or message missing

                    status_type = 'error'
                    status_message = 'Please enter a subject and a message.'

            order_items = order.order_items.all()
            tickets = order.order_tickets.order_by('-Tsubmitted')

    context = {
        'orders': orders,
        'order': order,
        'order_items': order_items,
        'tickets': tickets,
        'status_type': status_type,
        'status_message': status_message,
    }

    return render(request, 'store/orders.html', context)



def pantry(request, pk=None):

    today = timezone.localdate()

    if request.method == 'POST' and pk is not None:

        # Only change an item that is in the logged in customer's pantry
        item = Item.objects.filter(pk=pk, Iorder__Ocustomer_id=request.session.get('Cid'), Istatus='delivered').first()

        if item is None:

            messages.error(request, 'Item not found.')

        elif request.POST.get('action') == 'used':

            item.Istatus = 'used'
            item.Ifinished = today
            item.save()

            messages.success(request, f'{item.Iproduct.Pname} marked as used up.')

        elif request.POST.get('action') == 'expired':

            item.Istatus = 'expired'
            item.Ifinished = today
            item.save()

            messages.success(request, f'{item.Iproduct.Pname} marked as thrown away.')

        elif request.POST.get('action') == 'rate':

            try:
                rating = int(request.POST.get('rating'))
            except (TypeError, ValueError):
                rating = None

            if rating not in range(1, 6):
                messages.error(request, 'Please choose a rating from 1 to 5.')
            else:
                item.Irating = rating
                item.save()
                messages.success(request, f'Thank you for rating {item.Iproduct.Pname}.')

        return redirect('/store/pantry')

    items = Item.objects.filter(Iorder__Ocustomer_id=request.session.get('Cid'), Istatus='delivered').order_by('Iexpiry')

    pantry_items = []
    expiring_soon = 0

    for item in items:

        if item.Iexpiry is None:

            days_left = None

        else:

            days_left = (item.Iexpiry - today).days

            if days_left <= 3:

                expiring_soon += 1

        pantry_items.append({'item': item, 'days_left': days_left})

    context = {
        'pantry_items': pantry_items,
        'expiring_soon': expiring_soon,
    }

    return render(request, 'store/pantry.html', context)
