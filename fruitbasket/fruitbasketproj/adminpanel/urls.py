from django.urls import path

from . import views, prediction_records

urlpatterns = [
    path('predictions/', prediction_records.prediction_list, name='prediction_list'),
    path('predictions/capture/', prediction_records.prediction_capture, name='prediction_capture'),
    path('predictions/<int:pk>/', prediction_records.prediction_detail, name='prediction_detail'),
    path('category_new', views.CategoryView.as_view(), name='category_new'),
    path('', views.index, name='adminpanel_index'),
    path('product_new', views.ProductView.as_view(), name='product_new'),
    path('product_new/<pk>', views.ProductView.as_view(), name='product_new'),
    path('stock_adjust', views.StockAdjustmentView.as_view(), name='stock_adjust'),
    path('item_new', views.ItemView.as_view(), name='item_new'),
    path('stock_advice', views.stock_advice, name='stock_advice'),
    path('customer_new', views.CustomerView.as_view(), name='customer_new'),
    path('customer_new/<pk>', views.CustomerView.as_view(), name='customer_new'),
    path('orders/', views.order_inspection_list, name='staff_order_list'),
    path('orders/<str:pk>/cancel/', views.staff_cancel_order, name='staff_order_cancel'),
    path('orders/<str:pk>/fulfil/', views.fulfil_order, name='staff_order_fulfil'),
    path('orders/<str:pk>/', views.order_inspection_detail, name='staff_order_detail'),
    path('order_new', views.OrderView.as_view(), name='order_new'),
    path('order_new/<pk>', views.OrderView.as_view(), name='order_new'),
    path('login', views.login, name='adminpanel_login'),
    path('logout', views.logout, name='adminpanel_logout'),
    path('support', views.SupportView.as_view(), name='support'),
    path('support/<int:pk>', views.SupportView.as_view(), name='support'),
]
