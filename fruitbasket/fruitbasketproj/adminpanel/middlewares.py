from django.http import HttpResponse



def staff_middleware(get_response):
    
    def middleware(request):

        # Check before the page runs, so that nobody can change data without logging in
        if request.path.startswith('/adminpanel') and request.path != '/adminpanel/login' and not request.session.get('isStaff', False):

            return HttpResponse('You are not login as staff. Please <a href="/adminpanel/login">log in</a> first.', status=403)

        response = get_response(request)

        return response

    return middleware