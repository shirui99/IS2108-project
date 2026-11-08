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
        )) and not request.session.get('Cid', False):
            return redirect('/store/login')

        return get_response(request)

    return middleware