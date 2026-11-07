from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='adminpanel_index'),
    path('product_new', views.ProductView.as_view(), name='product_new'),
    path('product_new/<pk>', views.ProductView.as_view(), name='product_new'),
    path('item_new', views.ItemView.as_view(), name='item_new'),
    path('customer_new', views.CustomerView.as_view(), name='customer_new'),
    path('customer_new/<pk>', views.CustomerView.as_view(), name='customer_new'),
]