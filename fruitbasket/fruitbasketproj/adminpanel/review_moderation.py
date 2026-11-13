from django import forms
from django.contrib import messages
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import Review, ReviewModeration


class ModerationForm(forms.Form):
    action = forms.ChoiceField(choices=[('hide', 'Hide'), ('restore', 'Restore')], widget=forms.HiddenInput)
    reason = forms.CharField(max_length=1000, label='Reason', widget=forms.Textarea(attrs={'rows': 3}))


def staff_access(request):
    return request.user.is_authenticated and request.user.is_active and request.user.is_staff


def page(request, selected=None, form=None):
    query = request.GET.get('q', '').strip()
    reviews = Review.objects.select_related('Rcustomer', 'Rproduct').order_by('-Rdate', '-pk')
    if query:
        reviews = reviews.filter(Q(Rproduct__Pname__icontains=query) | Q(Rproduct__Pid__icontains=query) | Q(Rcustomer__Cname__icontains=query) | Q(Rcustomer__Cid__icontains=query))
    if selected is not None and form is None:
        form = ModerationForm(initial={'action': 'hide' if selected.Rvisible else 'restore'})
    return render(request, 'adminpanel/review_moderation.html', {'reviews':reviews, 'review':selected, 'form':form, 'query':query})


@require_GET
def review_list(request):
    if not staff_access(request):
        return redirect('adminpanel_login')
    return page(request)


@require_GET
def review_detail(request, pk):
    if not staff_access(request):
        return redirect('adminpanel_login')
    review = get_object_or_404(Review.objects.select_related('Rcustomer','Rproduct'), pk=pk)
    return page(request, review)


@require_POST
def review_action(request, pk):
    if not staff_access(request):
        return redirect('adminpanel_login')
    review = get_object_or_404(Review.objects.select_related('Rcustomer','Rproduct'), pk=pk)
    form = ModerationForm(request.POST)
    if form.is_valid():
        action = form.cleaned_data['action']
        target = action == 'restore'
        try:
            with transaction.atomic():
                # Claim the expected state so competing requests cannot create duplicate audit entries.
                updated = Review.objects.filter(pk=pk, Rvisible=not target).update(Rvisible=target)
                if updated:
                    ReviewModeration.objects.create(review_id=pk, employee=request.user, action=action, reason=form.cleaned_data['reason'])
        except DatabaseError:
            form.add_error(None, 'The change could not be saved. Please try again.')
        else:
            messages.success(request, 'Review visibility updated.' if updated else 'Review is already in that state.')
            return redirect('review_detail', pk=pk)
    return page(request, review, form)
