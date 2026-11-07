from django.contrib import admin

from .models import Product, Customer, Orders, Item



# Register your models here.

admin.site.register(Product)
admin.site.register(Customer)
admin.site.register(Orders)
admin.site.register(Item)