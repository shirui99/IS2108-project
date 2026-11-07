from django import forms

from .models import Product, Customer, Orders, Item



class ProductForm(forms.ModelForm):

    class Meta:

        model = Product
        fields = ['Pid', 'Pname', 'Pcategory', 'Psize', 'Pprice', 'Plowstock', 'Pactive']