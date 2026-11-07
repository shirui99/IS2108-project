from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='store_index'),
    path('signup', views.signup, name='signup'),
    path('login', views.login, name='login'),
    path('logout', views.logout, name='logout'),
    path('cart', views.cart, name='cart'),
    path('cart/<pk>', views.cart, name='cart'),
    path('checkout', views.checkout, name='checkout'),
    path('orders', views.orders, name='orders'),
    path('orders/<pk>', views.orders, name='orders'),
    path('pantry', views.pantry, name='pantry'),
    path('pantry/<pk>', views.pantry, name='pantry'),
    path('restock/', views.restock, name='restock'),
]