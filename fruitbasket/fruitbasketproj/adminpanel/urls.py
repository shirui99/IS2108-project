from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='adminpanel_index'),
    path('product_new', views.ProductView.as_view(), name='product_new'),
    path('product_new/<pk>', views.ProductView.as_view(), name='product_new'),
    path('item_new', views.ItemView.as_view(), name='item_new'),
    path('customer_new', views.CustomerView.as_view(), name='customer_new'),
    path('customer_new/<pk>', views.CustomerView.as_view(), name='customer_new'),
    path('order_new', views.OrderView.as_view(), name='order_new'),
    path('order_new/<pk>', views.OrderView.as_view(), name='order_new'),
    path('login', views.login, name='adminpanel_login'),
    path('logout', views.logout, name='adminpanel_logout'),
    path('support', views.SupportView.as_view(), name='support'),
    path('support/<int:pk>', views.SupportView.as_view(), name='support'),
]