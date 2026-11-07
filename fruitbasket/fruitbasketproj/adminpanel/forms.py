from django import forms

from .models import Product, Customer, Orders, Item



class ProductForm(forms.ModelForm):

    class Meta:

        model = Product
        fields = ['Pid', 'Pname', 'Pcategory', 'Psize', 'Pprice', 'Plowstock', 'Pactive']

class ItemBatchForm(forms.Form):

    Iproduct = forms.ModelChoiceField(queryset=Product.objects.filter(Pactive=True), label='Product')
    Iquantity = forms.IntegerField(min_value=1, max_value=500, label='Quantity')
    Ireceived = forms.DateField(label='Received date', widget=forms.DateInput(attrs={'type': 'date'}))
    Iexpiry = forms.DateField(label='Expiry date', required=False, widget=forms.DateInput(attrs={'type': 'date'}))

class CustomerForm(forms.ModelForm):

    class Meta:

        model = Customer
        fields = ['Cid', 'Cname', 'Caddress', 'Chouseholdsize', 'Cmealsperweek', 'Cuser']