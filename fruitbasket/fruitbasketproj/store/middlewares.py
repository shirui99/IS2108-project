from django.shortcuts import redirect


def login_middleware(get_response):
    
    def middleware(request):
        # If staff deleted this customer while they were logged in, end the session
        # instead of letting the pages that load the customer record fail.
        if request.path.startswith((
            '/store/checkout',
            '/store/profile',
            '/store/subscriptions',
            '/store/groups',
            '/store/list',
            '/store/notify',
        )) and request.session.get('Cid'):
            from adminpanel.models import Customer
            if not Customer.objects.filter(pk=request.session['Cid']).exists():
                request.session.flush()
                return redirect('/store/login')

        # Reject unauthenticated requests before a protected view can run.
        if request.path.startswith((
            '/store/cart',
            '/store/checkout',
            '/store/orders',
            '/store/pantry',
            '/store/restock',
            '/store/recipes',
            '/store/profile',
            '/store/subscriptions',
            '/store/groups',
            '/store/list',
            '/store/notify',
        )) and not request.session.get('Cid', False):
            if (request.method == 'POST' and request.path.startswith('/store/cart/')
                    and request.POST.get('action') != 'remove'):
                return redirect('/store/login?cart_login=1')
            return redirect('/store/login')

        return get_response(request)

    return middleware