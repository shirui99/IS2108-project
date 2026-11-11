from django.shortcuts import redirect
from django.utils.cache import add_never_cache_headers


def staff_middleware(get_response):
    def middleware(request):
        if request.path.startswith('/adminpanel') and request.path != '/adminpanel/login':
            if not (request.user.is_authenticated and request.user.is_active and request.user.is_staff):
                return redirect('/adminpanel/login')
        response = get_response(request)
        if request.path.startswith('/adminpanel') and request.path != '/adminpanel/login':
            add_never_cache_headers(response)
        return response
    return middleware
