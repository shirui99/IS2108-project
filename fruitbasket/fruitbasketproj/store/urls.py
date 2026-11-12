from django.urls import path

from . import views, subscription_views, group_views, account_views

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
    path('pantry/<int:pk>', views.pantry, name='pantry'),
    path('restock/', views.restock, name='restock'),
    path('product/<pk>', views.product, name='product'),
    path('profile', views.profile, name='profile'),
    path('profile/password', account_views.change_password, name='change_password'),
    path('list', account_views.saved_list, name='saved_list'),
    path('list/<pk>', account_views.saved_item, name='saved_item'),
    path('notify/<pk>', account_views.stock_notice, name='stock_notice'),
    path('subscriptions', subscription_views.subscriptions, name='subscriptions'),
    path('subscriptions/new/<pk>', subscription_views.subscription_new, name='subscription_new'),
    path('subscriptions/<int:pk>', subscription_views.subscription_action, name='subscription_action'),
    path('subscriptions/<int:pk>/edit', subscription_views.subscription_edit, name='subscription_edit'),
    path('groups', group_views.groups, name='groups'),
    path('groups/join/<code>', group_views.group_join, name='group_join'),
    path('groups/<int:pk>', group_views.group_detail, name='group_detail'),
]