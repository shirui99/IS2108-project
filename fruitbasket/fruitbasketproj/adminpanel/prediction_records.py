import hashlib
import json

from django import forms
from django.contrib import messages
from django.db import DatabaseError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import Customer, Product, RestockCapture
from store.restock import get_customer_purchase_history, load_restock_artifacts, predict_restock


class CaptureSelection(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.order_by('Cname', 'Cid'))
    product = forms.ModelChoiceField(queryset=Product.objects.order_by('Pname', 'Pid'))


class CaptureFilters(CaptureSelection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False


def staff_access(request):
    return request.user.is_authenticated and request.user.is_active and request.user.is_staff


def capture_current(customer, product, employee):
    # Capture a calculation, not customer exposure or purchase eligibility.
    events = get_customer_purchase_history(customer.pk).get(product.pk, [])
    latest = events[-1] if events else None
    previous = events[-2] if len(events) > 1 else None
    inputs = {
        'latest_purchase_at': latest['purchased_at'].isoformat() if latest else None,
        'household_size': customer.Chouseholdsize,
        'category': product.Pcategory_id,
        'purchased_quantity': latest['purchased_quantity'] if latest else None,
        'previous_interval_days': (latest['purchased_at'] - previous['purchased_at']).days if previous else None,
        'history_count': len(events),
    }
    result = predict_restock(**inputs)
    metadata = load_restock_artifacts().get('metadata') or {}
    version = metadata.get('model_version')
    version = version if isinstance(version, str) and version else None
    calculation = {'customer_id': customer.pk, 'product_id': product.pk, 'inputs': inputs,
                   'result': result, 'declared_version': version}
    fingerprint = hashlib.sha256(json.dumps(calculation, sort_keys=True).encode()).hexdigest()
    snapshot = {**calculation, 'customer_name': customer.Cname, 'product_name': product.Pname,
                'category_name': product.Pcategory.Cname}
    # The unique fingerprint also protects two requests that save concurrently.
    return RestockCapture.objects.get_or_create(fingerprint=fingerprint, defaults={
        'customer': customer, 'product': product, 'employee': employee, 'snapshot': snapshot,
    })


def render_list(request, capture_form=None):
    filters = CaptureFilters(request.GET, auto_id='filter_%s')
    records = RestockCapture.objects.all()
    if filters.is_valid():
        for name, value in filters.cleaned_data.items():
            if value:
                records = records.filter(**{name: value})
    else:
        records = records.none()
    return render(request, 'adminpanel/prediction_list.html', {
        'filters': filters, 'capture_form': capture_form if capture_form is not None else CaptureSelection(),
        'records': records,
    })


@require_GET
def prediction_list(request):
    if not staff_access(request):
        return redirect('adminpanel_login')
    return render_list(request)


@require_POST
def prediction_capture(request):
    if not staff_access(request):
        return redirect('adminpanel_login')
    form = CaptureSelection(request.POST)
    if form.is_valid():
        try:
            with transaction.atomic():
                record, created = capture_current(form.cleaned_data['customer'], form.cleaned_data['product'], request.user)
        except DatabaseError:
            form.add_error(None, 'The capture could not be saved. Please try again.')
        else:
            messages.success(request, 'Staff capture saved.' if created else 'This calculation has already been captured.')
            return redirect('prediction_detail', pk=record.pk)
    return render_list(request, form)


@require_GET
def prediction_detail(request, pk):
    if not staff_access(request):
        return redirect('adminpanel_login')
    record = get_object_or_404(RestockCapture.objects.select_related('employee'), pk=pk)
    return render(request, 'adminpanel/prediction_detail.html', {'record': record, 's': record.snapshot})
