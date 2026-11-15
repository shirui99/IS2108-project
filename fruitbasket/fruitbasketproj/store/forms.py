from datetime import timedelta

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.utils import timezone

from adminpanel.models import Subscription


class SignupForm(forms.Form):

    # SF01: checks every signup field before anything is saved

    username = forms.CharField(max_length=150, validators=[UnicodeUsernameValidator()], label='Username')
    password = forms.CharField(label='Password')
    email = forms.EmailField(label='Email')
    Cname = forms.CharField(max_length=255, label='Name')
    Caddress = forms.CharField(max_length=255, label='Delivery address')
    Chouseholdsize = forms.IntegerField(min_value=1, max_value=20, label='Household size')
    Cmealsperweek = forms.IntegerField(min_value=0, max_value=100, label='Meals cooked at home per week')

    def clean_username(self):

        username = self.cleaned_data['username']

        # "Alex" and "alex" would be too easy to confuse, so they count as the same name
        if User.objects.filter(username__iexact=username).exists():

            raise forms.ValidationError('That username is already taken.')

        return username

    def clean(self):

        cleaned_data = super().clean()
        password = cleaned_data.get('password')

        if password:

            # Django's own rules, also checking the password is not too close to the username or email
            try:
                validate_password(password, User(username=cleaned_data.get('username', ''), email=cleaned_data.get('email', '')))
            except forms.ValidationError as error:
                self.add_error('password', error)

        return cleaned_data


class ProfileForm(forms.Form):

    Cname = forms.CharField(max_length=255, label='Name')
    email = forms.EmailField(
        required=True,
        label='Email',
        error_messages={'required': 'Enter an email address.', 'invalid': 'Enter a valid email address.'},
    )
    Caddress = forms.CharField(max_length=255, label='Delivery address')
    Chouseholdsize = forms.IntegerField(min_value=1, max_value=20, label='Household size')
    Cmealsperweek = forms.IntegerField(min_value=0, max_value=100, label='Meals cooked at home per week')


class ReviewForm(forms.Form):

    Rrating = forms.TypedChoiceField(choices=[(n, f'{n} / 5') for n in range(1, 6)], coerce=int, label='Rating')
    Rtext = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={'rows': 3}), label='Review (optional)')


# Longest a customer can schedule ahead, and the highest spending limit per order.
# Without these, a date like 31 Dec 9999 crashes the date maths when the next order is worked out.
MAX_DAYS_AHEAD = 365
MAX_CEILING = 10000


def check_future_date(Snextdate):

    today = timezone.localdate()

    if Snextdate <= today:

        raise forms.ValidationError('Choose a date after today.')

    if Snextdate > today + timedelta(days=MAX_DAYS_AHEAD):

        raise forms.ValidationError(f'Choose a date within the next {MAX_DAYS_AHEAD} days.')

    return Snextdate


class SubscriptionForm(forms.Form):

    Squantity = forms.IntegerField(min_value=1, max_value=50, label='Packs per order')
    Sinterval = forms.TypedChoiceField(choices=Subscription.INTERVAL, coerce=int, label='Schedule')
    Snextdate = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label='First order date')
    Sceiling = forms.FloatField(min_value=0.01, max_value=MAX_CEILING, label='Most I agree to pay per order ($)')
    consent = forms.BooleanField(
        required=True,
        label='I agree that FruitBasket may place this order for me on the schedule above until I pause or cancel it.',
        error_messages={'required': 'You must tick the box to approve the plan.'},
    )

    def clean_Snextdate(self):

        return check_future_date(self.cleaned_data['Snextdate'])


class ResumeForm(forms.Form):

    Snextdate = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label='Next order date')

    def clean_Snextdate(self):

        # Missed dates are never caught up, so the plan restarts from a future date
        return check_future_date(self.cleaned_data['Snextdate'])


class GroupForm(forms.Form):

    Gname = forms.CharField(max_length=100, label='Group name')
    Gaddress = forms.CharField(max_length=255, label='Delivery address for the whole group')


class SubscriptionEditForm(forms.Form):

    Squantity = forms.IntegerField(min_value=1, max_value=50, label='Packs per order')
    Sinterval = forms.TypedChoiceField(choices=Subscription.INTERVAL, coerce=int, label='Schedule')
    Sceiling = forms.FloatField(min_value=0.01, max_value=MAX_CEILING, label='Most I agree to pay per order ($)')
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
