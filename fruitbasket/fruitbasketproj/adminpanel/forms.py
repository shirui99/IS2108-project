from django import forms

from .models import Product, Customer, Orders, Item



class ProductForm(forms.ModelForm):

    class Meta:

        model = Product
        fields = ['Pid', 'Pname', 'Pcategory', 'Psize', 'Pprice', 'Plowstock', 'Ptargetstock', 'Pbulkquantity', 'Pbulkprice', 'Pactive', 'Pimage', 'Pexpirydays']

    def clean(self):
        data = super().clean()
        price, low, target = data.get('Pprice'), data.get('Plowstock'), data.get('Ptargetstock')
        quantity, bulk = data.get('Pbulkquantity'), data.get('Pbulkprice')
        if price is not None and price <= 0:
            self.add_error('Pprice', 'Enter a price greater than zero.')
        if target is not None and low is not None and target < low:
            self.add_error('Ptargetstock', 'Target stock must be at least the low-stock level.')
        if quantity is not None and bulk is None:
            self.add_error('Pbulkprice', 'Enter a bulk unit price with the threshold.')
        if bulk is not None and quantity is None:
            self.add_error('Pbulkquantity', 'Enter a bulk quantity threshold with the price.')
        if bulk is not None and (bulk <= 0 or (price is not None and bulk > price)):
            self.add_error('Pbulkprice', 'Bulk unit price must be positive and no higher than the regular price.')
        return data

class ItemBatchForm(forms.Form):

    Iproduct = forms.ModelChoiceField(queryset=Product.objects.filter(Pactive=True), label='Product')
    Iquantity = forms.IntegerField(min_value=1, max_value=500, label='Quantity')
    Ireceived = forms.DateField(label='Received date', widget=forms.DateInput(attrs={'type': 'date'}))
    Iexpiry = forms.DateField(label='Expiry date', required=False, widget=forms.DateInput(attrs={'type': 'date'}))

class CustomerForm(forms.ModelForm):

    class Meta:

        model = Customer
        fields = ['Cid', 'Cname', 'Caddress', 'Chouseholdsize', 'Cmealsperweek', 'Cuser']

class OrderForm(forms.ModelForm):

    class Meta:

        model = Orders
        fields = ['Oid', 'Ocustomer', 'Oaddress', 'Odate', 'Ostatus']

        widgets = {
            'Odate': forms.DateInput(attrs={'type': 'date'})
        }

