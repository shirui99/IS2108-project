from django import forms
from PIL import Image, UnidentifiedImageError

from .models import Product, Customer, Orders, Item, Category, CATEGORY_WHITESPACE, InventoryBatch



class ProductForm(forms.ModelForm):

    class Meta:

        model = Product
        fields = ['Pid', 'Pname', 'Pcategory', 'Psize', 'Pprice', 'Plowstock', 'Ptargetstock', 'Pbulkquantity', 'Pbulkprice', 'Pactive', 'Pimage', 'Pexpirydays']

    def clean_Pimage(self):
        image = self.cleaned_data.get('Pimage')
        upload = self.files.get('Pimage')
        if upload:
            if upload.size > 2 * 1024 * 1024:
                raise forms.ValidationError('The photo must be no larger than 2 MiB.')
            if getattr(getattr(upload, 'image', None), 'format', None) not in {'JPEG', 'PNG', 'WEBP'}:
                raise forms.ValidationError('Choose a JPEG, PNG or WebP image.')
            try:
                upload.seek(0)
                with Image.open(upload) as decoded:
                    if decoded.width * decoded.height > 16_000_000:
                        raise forms.ValidationError('The photo must not exceed 16 megapixels.')
                    if getattr(decoded, 'n_frames', 1) != 1:
                        raise forms.ValidationError('Animated photos are not supported.')
                    decoded.load()
            except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, UnidentifiedImageError):
                raise forms.ValidationError('The photo is corrupt or incomplete. Choose another image.')
            finally:
                upload.seek(0)
        return image

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
    Breference = forms.CharField(max_length=100, label='Batch reference')
    Iquantity = forms.IntegerField(min_value=1, max_value=500, label='Pack quantity')
    Ireceived = forms.DateField(label='Received date', widget=forms.DateInput(attrs={'type': 'date'}))
    Bdatetype = forms.ChoiceField(choices=[('', 'Undated')] + InventoryBatch.DATE_TYPES, required=False, label='Printed date type')
    Iexpiry = forms.DateField(label='Printed date', required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def clean_Breference(self):
        reference = self.cleaned_data['Breference'].strip()
        if InventoryBatch.objects.filter(Breference=reference).exists():
            raise forms.ValidationError('This batch reference has already been received.')
        return reference

    def clean(self):
        data = super().clean()
        if data.get('Bdatetype') and not data.get('Iexpiry') and 'Iexpiry' not in self.errors:
            self.add_error('Iexpiry', 'Enter the printed date for the selected type.')
        if data.get('Iexpiry') and not data.get('Bdatetype') and 'Bdatetype' not in self.errors:
            self.add_error('Bdatetype', 'Select the printed date type, or leave the date blank for undated goods.')
        return data

class CustomerForm(forms.ModelForm):
    email = forms.EmailField(required=False, max_length=254, label='Email')

    class Meta:
        model = Customer
        fields = ['Cname', 'Caddress']
        labels = {'Cname': 'Name', 'Caddress': 'Current delivery address'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['email'].initial = self.instance.Cuser.email


class OrderForm(forms.ModelForm):

    class Meta:

        model = Orders
        fields = ['Oid', 'Ocustomer', 'Oaddress', 'Odate']

        widgets = {
            'Odate': forms.DateInput(attrs={'type': 'date'})
        }



class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['Cname']
        error_messages = {'Cname': {'unique': 'A category with this name already exists.'}}

    def clean_Cname(self):
        return self.cleaned_data['Cname'].strip(CATEGORY_WHITESPACE)


class StockAdjustmentForm(forms.Form):
    request_id = forms.UUIDField(widget=forms.HiddenInput)
    expected_count = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    snapshot = forms.CharField(widget=forms.HiddenInput)
    group = forms.CharField(widget=forms.HiddenInput)
    action = forms.ChoiceField(choices=[('correction', 'Correct stock count'), ('writeoff', 'Write off stock')], widget=forms.HiddenInput)
    quantity = forms.IntegerField(min_value=0, max_value=10000, label='Physical available count')
    reason = forms.CharField(max_length=500, label='Reason')
    note = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}), label='Additional note (optional)')

    def __init__(self, *args, action, **kwargs):
        super().__init__(*args, **kwargs)
        self.expected_action = action
        if action == 'writeoff':
            self.fields['quantity'] = forms.IntegerField(min_value=1, max_value=10000, label='Packs to write off')
            self.fields['reason'] = forms.ChoiceField(choices=[('', 'Select a reason'), ('expired', 'Expired'), ('damaged', 'Damaged'), ('spoiled', 'Spoiled'), ('recalled', 'Recalled')], label='Reason')
        else:
            self.fields.pop('note')

    def clean_action(self):
        action = self.cleaned_data['action']
        if action != self.expected_action:
            raise forms.ValidationError('Invalid adjustment action.')
        return action


class OrderCancellationForm(forms.Form):
    reason = forms.CharField(max_length=1000, label='Cancellation reason', widget=forms.Textarea(attrs={'rows': 3}))
