from django.shortcuts import redirect



def staff_middleware(get_response):
    
    def middleware(request):

        # Check before the page runs, so that nobody can change data without logging in
        if request.path.startswith('/adminpanel') and request.path != '/adminpanel/login' and not request.session.get('isStaff', False):

            return redirect('/adminpanel/login')

        response = get_response(request)

        return response

    return middleware
