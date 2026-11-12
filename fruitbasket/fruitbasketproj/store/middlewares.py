from django.shortcuts import redirect


def login_middleware(get_response):
    
    def middleware(request):
        # Reject unauthenticated requests before a protected view can run.
        if request.path.startswith((
            '/store/cart',
            '/store/checkout',
            '/store/orders',
            '/store/pantry',
            '/store/restock',
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