from django.http import HttpResponse



def login_middleware(get_response):
    
    def middleware(request):
    
        response = get_response(request)

        if request.path.startswith(('/store/cart', '/store/checkout', '/store/orders', '/store/pantry')) and not request.session.get('Cid', False):

            return HttpResponse('You are not login. Please <a href="/store/login">log in</a> first.', status=403)

        return response

    return middleware