from django.db.models import Count, Avg
from django.shortcuts import redirect, render, HttpResponse
from django.utils import timezone

from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.views.decorators.http import require_POST
from django.contrib import messages

from adminpanel.models import Customer, Product, Orders, Item, SupportTicket, Category
from adminpanel.inventory import sellable_stock_filter
from django.db import transaction
from django.db.models import F
from adminpanel.models import Review, Subscription, SavedItem, StockNotice
from .restock import get_customer_purchase_history, get_restock_suggestions
from .ordering import OrderNotPlaced, generate_order_id, place_order
from .forms import ProfileForm, ReviewForm

# Create your views here.

def index(request):

    # Find avg rating and number of ratings from all items
    products = Product.objects.filter(Pactive=True).select_related("Pcategory").annotate(
        rating=Avg('product_items__Irating'),
        reviews=Count('product_items__Irating'),
        sellable_stock=Count('product_items', filter=sellable_stock_filter(item_prefix='product_items__', product_prefix=''))
    )

    # SF05: search by product name
    search = request.GET.get('q', '').strip()
    if search:
        products = products.filter(Pname__icontains=search)

    category = request.GET.get('category', '')
    if category and not Category.objects.filter(pk=category).exists():
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

    # SF29: products this customer asked about that can be bought again
    back_in_stock = []

    if request.session.get('Cid'):

        back_in_stock = Product.objects.filter(
            Pactive=True, product_notices__SNcustomer_id=request.session['Cid']
        ).annotate(
            sellable_stock=Count('product_items', filter=sellable_stock_filter(item_prefix='product_items__', product_prefix=''))
        ).filter(sellable_stock__gt=0)

    return render(request, 'store/index.html', {
        'products': products,
        'categories': Category.objects.values_list('Ccode', 'Cname'),
        'selected_category': category,
        'selected_sort': sort,
        'search': search,
        'back_in_stock': back_in_stock,
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

    # A product on an active subscription will be ordered anyway, so it is not suggested again
    subscribed = set(Subscription.objects.filter(Scustomer_id=customer_id, Sstatus='active').values_list('Sproduct_id', flat=True))
    suggestions = [suggestion for suggestion in suggestions if suggestion['product_id'] not in subscribed]
    for suggestion in suggestions:
        if suggestion['status'] == 'UNAVAILABLE':
            suggestion['due_status'] = 'No estimate available'
            suggestion['estimate_label'] = 'No estimate available'
            continue
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

            # A missing quantity means one pack, which is what the Add to cart buttons send
            try:
                quantity = int(request.POST.get('quantity', 1))
            except (TypeError, ValueError):
                quantity = 0

            if quantity < 1:
                messages.error(request, 'Enter a quantity of at least 1. Your cart was not changed.')
                return redirect('/store/cart')

            if request.POST.get('action') == 'set':

                # SF08: replace the quantity of a product that is already in the cart
                if pk not in cart:
                    messages.error(request, 'That product is not in your cart.')
                    return redirect('/store/cart')

                if quantity > available:
                    messages.error(request, f'Only {available} sellable pack(s) available. Your cart was not changed.')
                    return redirect('/store/cart')

                cart[pk] = quantity
                messages.success(request, 'Quantity updated.')

            else:

                # SF07: add the chosen number of packs on top of what is already in the cart
                if available < cart.get(pk, 0) + quantity:
                    messages.error(request, f'Only {available} sellable pack(s) available. Your cart was not changed.')
                    return redirect('/store/cart')

                cart[pk] = cart.get(pk, 0) + quantity

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

        # place_order creates the whole order or nothing (see store/ordering.py)
        try:
            newOrder, total = place_order(Customer.objects.get(pk=request.session['Cid']), Oaddress, cart)
        except OrderNotPlaced as error:
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

    # SF37: the list can be narrowed to one status. Opening an order still works for any status.
    status_filter = request.GET.get('status', '')

    if status_filter not in dict(Orders.STATUS):

        status_filter = ''

    listed_orders = orders.filter(Ostatus=status_filter) if status_filter else orders

    if pk is not None:

        # Only show an order that belongs to the logged in customer
        order = orders.filter(pk=pk).first()

        if order is not None:


            if request.method == 'POST' and request.POST.get('action') == 'reorder':

                # SF27: put the same products and quantities into the cart, limited by what can be sold now
                cart = request.session.get('cart', {})
                added = 0
                short = []

                for line in order.order_items.values('Iproduct', 'Iproduct__Pname').annotate(count=Count('id')):

                    Pid = line['Iproduct']
                    in_cart = cart.get(Pid, 0) if type(cart.get(Pid, 0)) is int else 0
                    available = Item.objects.filter(sellable_stock_filter(), Iproduct_id=Pid).count()
                    quantity = min(in_cart + line['count'], available)

                    if quantity > in_cart:

                        cart[Pid] = quantity
                        added += quantity - in_cart

                    if quantity < in_cart + line['count']:

                        short.append(line['Iproduct__Pname'])

                request.session['cart'] = cart

                if added:

                    messages.success(request, f'{added} pack(s) from order {order.Oid} added to your cart.')

                else:

                    messages.error(request, f'Nothing from order {order.Oid} could be added to your cart.')

                if short:

                    messages.warning(request, 'Not enough stock to add all of: ' + ', '.join(short) + '.')

                return redirect('/store/cart')

            elif request.method == 'POST' and request.POST.get('action') == 'cancel':

                # SF25: only a placed order whose items are all untouched can be cancelled
                if order.Ostatus != 'placed':

                    status_type = 'error'
                    status_message = 'Only a placed order can be cancelled. Please contact support below.'

                elif order.order_items.exclude(Istatus='delivered').exists():

                    status_type = 'error'
                    status_message = 'Some items in this order were already used or thrown away. Please contact support below.'

                else:

                    with transaction.atomic():

                        # The status check is repeated in the update, so a double click releases the stock once
                        cancelled = Orders.objects.filter(pk=order.pk, Ostatus='placed').update(Ostatus='cancelled', Opayment='refunded')

                        if cancelled:

                            order.order_items.update(Iorder=None, Istatus='available', Ipurchasedprice=None, Irating=None)

                    order = orders.filter(pk=pk).first()

                    status_type = 'success'
                    status_message = f'Order {order.Oid} was cancelled. The items went back into stock and the simulated payment was refunded.'

            elif request.method == 'POST': #handle the post request

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
        'orders': listed_orders,
        'status_filter': status_filter,
        'statuses': Orders.STATUS,
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

        elif request.POST.get('action') == 'report':

            # SF36: the ticket is attached to the order this item came from
            message = request.POST.get('Tmessage', '').strip()

            if message:

                SupportTicket.objects.create(
                    Torder=item.Iorder, Tsubject=f'Problem with {item.Iproduct.Pname} (pantry item {item.pk})'[:200], Tmessage=message
                )
                messages.success(request, f'Your issue was sent to support. The reply will appear under order {item.Iorder_id}.')

            else:

                messages.error(request, 'Please describe the problem before sending.')

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

    # SF12: a group order is shared between households, so it is not added to one customer's pantry
    items = Item.objects.filter(
        Iorder__Ocustomer_id=request.session.get('Cid'), Istatus='delivered', Iorder__group_purchase__isnull=True
    ).order_by('Iexpiry')

    pantry_items = []
    expiring_soon = 0
    past_expiry = 0

    for item in items:

        if item.Iexpiry is None:

            days_left = None

        else:

            days_left = (item.Iexpiry - today).days

            if days_left <= 3:

                expiring_soon += 1

            # SF14: dates that have already passed are also counted on their own
            if days_left < 0:

                past_expiry += 1

        pantry_items.append({'item': item, 'days_left': days_left})

    context = {
        'pantry_items': pantry_items,
        'expiring_soon': expiring_soon,
        'past_expiry': past_expiry,
    }

    return render(request, 'store/pantry.html', context)



def product(request, pk):

    # SF06: product details page. SF24: review a delivered product.

    product = Product.objects.filter(pk=pk, Pactive=True).annotate(
        rating=Avg('product_items__Irating'),
        reviews=Count('product_items__Irating'),
        sellable_stock=Count('product_items', filter=sellable_stock_filter(item_prefix='product_items__', product_prefix=''))
    ).first()

    if product is None:

        messages.error(request, 'Product not found.')
        return redirect('/store/')

    Cid = request.session.get('Cid')
    purchase = None
    my_review = None

    if Cid:

        # The purchase that proves this customer received the product. Group orders do not count.
        purchase = Item.objects.filter(
            Iproduct=product, Iorder__Ocustomer_id=Cid, Iorder__Ostatus='delivered', Iorder__group_purchase__isnull=True
        ).order_by('pk').first()
        my_review = Review.objects.filter(Rcustomer_id=Cid, Rproduct=product).first()

    form = ReviewForm(initial={'Rrating': my_review.Rrating, 'Rtext': my_review.Rtext} if my_review else None)

    if request.method == 'POST':

        form = ReviewForm(request.POST)

        if purchase is None:

            messages.error(request, 'You can review a product after an order containing it has been delivered.')
            return redirect(f'/store/product/{product.Pid}')

        if form.is_valid():

            # One review per customer and product: a second submission replaces the first
            Review.objects.update_or_create(
                Rcustomer_id=Cid, Rproduct=product,
                defaults={
                    'Rrating': form.cleaned_data['Rrating'],
                    'Rtext': form.cleaned_data['Rtext'],
                    'Rdate': timezone.localdate(),
                    'Ritem': purchase,
                }
            )

            # The shop page averages Irating, so the rating is copied onto the purchased item
            purchase.Irating = form.cleaned_data['Rrating']
            purchase.save()

            messages.success(request, 'Thank you. Your review was saved.')
            return redirect(f'/store/product/{product.Pid}')

    # Dates are recorded on each pack, so the page can only say whether packs in stock carry a date
    has_dated_stock = Item.objects.filter(sellable_stock_filter(), Iproduct=product, Iexpiry__isnull=False).exists()

    context = {
        'product': product,
        'has_dated_stock': has_dated_stock,
        'visible_reviews': product.product_reviews.filter(Rvisible=True).select_related('Rcustomer').order_by('-Rdate', '-pk'),
        'can_review': purchase is not None,
        'saved': bool(Cid) and SavedItem.objects.filter(SVcustomer_id=Cid, SVproduct=product).exists(),
        'watching': bool(Cid) and StockNotice.objects.filter(SNcustomer_id=Cid, SNproduct=product).exists(),
        'my_review': my_review,
        'form': form,
    }

    return render(request, 'store/product.html', context)



def profile(request):

    # SF04: update household and contact details

    customer = Customer.objects.get(pk=request.session['Cid'])

    if request.method == 'POST':

        form = ProfileForm(request.POST)

        if form.is_valid():

            customer.Cname = form.cleaned_data['Cname']
            customer.Caddress = form.cleaned_data['Caddress']
            customer.Chouseholdsize = form.cleaned_data['Chouseholdsize']
            customer.Cmealsperweek = form.cleaned_data['Cmealsperweek']
            customer.save()

            customer.Cuser.email = form.cleaned_data['email']
            customer.Cuser.save()

            # Earlier orders keep the address stored in Oaddress when they were placed
            messages.success(request, 'Profile updated. Your new details will be used for future orders.')
            return redirect('/store/profile')

    else:

        form = ProfileForm(initial={
            'Cname': customer.Cname,
            'email': customer.Cuser.email,
            'Caddress': customer.Caddress,
            'Chouseholdsize': customer.Chouseholdsize,
            'Cmealsperweek': customer.Cmealsperweek,
        })

    return render(request, 'store/profile.html', {'form': form, 'customer': customer})
