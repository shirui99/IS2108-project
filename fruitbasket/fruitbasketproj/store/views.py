from django.shortcuts import render, HttpResponse

from django.contrib.auth.models import User
from django.contrib.auth import authenticate

from adminpanel.models import Customer

# Create your views here.

def index(request):

    return render(request, 'store/index.html')

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

            request.session['Cid'] = user.customer.Cid

            return render(request, 'store/login.html', {'success_message': 'Authentication successful!'})
        
        else:

            return render(request, 'store/login.html', {'error_message': 'Invalid username or password.'})



def logout(request):

    request.session.flush()

    return HttpResponse('You have logged out.')