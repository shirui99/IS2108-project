from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from adminpanel.models import Subscription


class ProfileForm(forms.Form):

    Cname = forms.CharField(max_length=255, label='Name')
    email = forms.EmailField(required=False, label='Email')
    Caddress = forms.CharField(max_length=255, label='Delivery address')
    Chouseholdsize = forms.IntegerField(min_value=1, max_value=20, label='Household size')
    Cmealsperweek = forms.IntegerField(min_value=0, max_value=100, label='Meals cooked at home per week')


class ReviewForm(forms.Form):

    Rrating = forms.TypedChoiceField(choices=[(n, f'{n} / 5') for n in range(1, 6)], coerce=int, label='Rating')
    Rtext = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 3}), label='Review (optional)')


class SubscriptionForm(forms.Form):

    Squantity = forms.IntegerField(min_value=1, max_value=50, label='Packs per order')
    Sinterval = forms.TypedChoiceField(choices=Subscription.INTERVAL, coerce=int, label='Schedule')
    Snextdate = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label='First order date')
    Sceiling = forms.FloatField(min_value=0.01, label='Most I agree to pay per order ($)')
    consent = forms.BooleanField(
        required=True,
        label='I agree that FruitBasket may place this order for me on the schedule above until I pause or cancel it.',
        error_messages={'required': 'You must tick the box to approve the plan.'},
    )

    def clean_Snextdate(self):

        Snextdate = self.cleaned_data['Snextdate']

        if Snextdate <= timezone.localdate():

            raise forms.ValidationError('Choose a date after today.')

        return Snextdate


class ResumeForm(forms.Form):

    Snextdate = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label='Next order date')

    def clean_Snextdate(self):

        Snextdate = self.cleaned_data['Snextdate']

        # Missed dates are never caught up, so the plan restarts from a future date
        if Snextdate <= timezone.localdate():

            raise forms.ValidationError('Choose a date after today.')

        return Snextdate


class GroupForm(forms.Form):

    Gname = forms.CharField(max_length=100, label='Group name')
    Gaddress = forms.CharField(max_length=255, label='Delivery address for the whole group')


class SubscriptionEditForm(forms.Form):

    Squantity = forms.IntegerField(min_value=1, max_value=50, label='Packs per order')
    Sinterval = forms.TypedChoiceField(choices=Subscription.INTERVAL, coerce=int, label='Schedule')
    Sceiling = forms.FloatField(min_value=0.01, label='Most I agree to pay per order ($)')
    consent = forms.BooleanField(
        required=True,
        label='I agree that FruitBasket may place orders for me with these new settings until I pause or cancel the plan.',
        error_messages={'required': 'You must tick the box to approve the change.'},
    )


class PasswordForm(forms.Form):

    current = forms.CharField(widget=forms.PasswordInput, label='Current password')
    new = forms.CharField(widget=forms.PasswordInput, label='New password')
    confirm = forms.CharField(widget=forms.PasswordInput, label='New password again')

    def __init__(self, user, *args, **kwargs):

        # The form needs the user to check the current password
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_current(self):

        current = self.cleaned_data['current']

        if not self.user.check_password(current):

            raise forms.ValidationError('Your current password is not correct.')

        return current

    def clean(self):

        cleaned_data = super().clean()
        new = cleaned_data.get('new')

        if new and new != cleaned_data.get('confirm'):

            self.add_error('confirm', 'The two new passwords do not match.')

        elif new:

            # Django's own rules: long enough, not too common, not all numbers, not like the username
            try:
                validate_password(new, self.user)
            except forms.ValidationError as error:
                self.add_error('new', error)

        return cleaned_data
