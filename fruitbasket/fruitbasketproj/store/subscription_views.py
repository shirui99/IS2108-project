from datetime import timedelta

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from adminpanel.inventory import sellable_stock_filter
from adminpanel.models import Customer, Item, Product, Subscription, SubscriptionCycle

from .forms import ResumeForm, SubscriptionEditForm, SubscriptionForm
from .subscriptions import suggest_interval


def subscriptions(request):

    # List the logged in customer's plans with the orders each plan has created

    plans = Subscription.objects.filter(Scustomer_id=request.session['Cid']).select_related('Sproduct').prefetch_related(
        'subscription_cycles'
    ).order_by('Sstatus', 'Snextdate')

    context = {
        'plans': plans,
        'tomorrow': timezone.localdate() + timedelta(days=1),
    }

    return render(request, 'store/subscriptions.html', context)


def subscription_new(request, pk):

    # SF16: approve a repeat-purchase plan for one product

    customer = Customer.objects.get(pk=request.session['Cid'])
    product = Product.objects.filter(pk=pk, Pactive=True).first()

    if product is None:

        messages.error(request, 'Product not found.')
        return redirect('/store/')

    # One plan per product keeps a customer from being charged twice for the same thing
    if Subscription.objects.filter(Scustomer=customer, Sproduct=product).exclude(Sstatus='cancelled').exists():

        messages.error(request, f'You already have a subscription for {product.Pname}.')
        return redirect('/store/subscriptions')

    interval, estimate_label = suggest_interval(customer, product)

    if request.method == 'POST':

        form = SubscriptionForm(request.POST)

        if form.is_valid():

            total = product.Pprice * form.cleaned_data['Squantity']

            if total > form.cleaned_data['Sceiling']:

                form.add_error('Sceiling', f'This plan costs ${total:.2f} per order at the current price, which is above your limit.')

            else:

                Subscription.objects.create(
                    Scustomer=customer,
                    Sproduct=product,
                    Squantity=form.cleaned_data['Squantity'],
                    Sinterval=form.cleaned_data['Sinterval'],
                    Snextdate=form.cleaned_data['Snextdate'],
                    Sceiling=form.cleaned_data['Sceiling'],
                    Screated=timezone.localdate(),
                )

                messages.success(request, f'Subscription created. The first order of {product.Pname} is planned for {form.cleaned_data["Snextdate"]:%d %b %Y}.')
                return redirect('/store/subscriptions')

    else:

        form = SubscriptionForm(initial={
            'Squantity': 1,
            'Sinterval': interval or 14,
            'Snextdate': timezone.localdate() + timedelta(days=interval or 14),
            'Sceiling': f'{product.Pprice:.2f}',
        })

    context = {
        'product': product,
        'form': form,
        'estimate_label': estimate_label,
        'suggested_interval': interval,
        'sellable_stock': Item.objects.filter(sellable_stock_filter(), Iproduct=product).count(),
    }

    return render(request, 'store/subscription_new.html', context)


@require_POST
def subscription_action(request, pk):

    # SF17 pause, SF18 resume, SF19 cancel. Only the customer's own plan can be changed.

    plan = Subscription.objects.filter(pk=pk, Scustomer_id=request.session['Cid']).first()
    action = request.POST.get('action')

    if plan is None:

        messages.error(request, 'Subscription not found.')

    elif action == 'pause':

        # The status is checked again in the update, so only an active plan can be paused
        if Subscription.objects.filter(pk=plan.pk, Sstatus='active').update(Sstatus='paused'):

            messages.success(request, f'{plan.Sproduct.Pname} subscription paused. No orders will be created until you resume it.')

        else:

            messages.error(request, 'Only an active subscription can be paused.')

    elif action == 'resume':

        form = ResumeForm(request.POST)

        if not form.is_valid():

            messages.error(request, 'Choose a next order date after today and within the next year to resume.')

        elif Subscription.objects.filter(pk=plan.pk, Sstatus='paused').update(Sstatus='active', Snextdate=form.cleaned_data['Snextdate']):

            messages.success(request, f'{plan.Sproduct.Pname} subscription resumed. The next order is planned for {form.cleaned_data["Snextdate"]:%d %b %Y}.')

        else:

            messages.error(request, 'Only a paused subscription can be resumed.')

    elif action == 'skip':

        # SF32: move the next order one schedule step later. The old date is in the filter,
        # so a double click skips only once.
        new_date = plan.Snextdate + timedelta(days=plan.Sinterval)

        if Subscription.objects.filter(pk=plan.pk, Sstatus='active', Snextdate=plan.Snextdate).update(Snextdate=new_date):

            SubscriptionCycle.objects.create(
                SCsubscription=plan, SCdate=timezone.localdate(), SCresult='skipped',
                SCnote=f'Order planned for {plan.Snextdate:%d %b %Y} skipped'
            )
            messages.success(request, f'Next {plan.Sproduct.Pname} order skipped. The following order is planned for {new_date:%d %b %Y}.')

        else:

            messages.error(request, 'Only an active subscription can skip an order.')

    elif action == 'cancel':

        # Orders and cycle records that already exist are kept
        if Subscription.objects.filter(pk=plan.pk).exclude(Sstatus='cancelled').update(Sstatus='cancelled'):

            messages.success(request, f'{plan.Sproduct.Pname} subscription cancelled. It will not create any more orders.')

        else:

            messages.error(request, 'This subscription was already cancelled.')

    return redirect('/store/subscriptions')


def subscription_edit(request, pk):

    # SF33: change the quantity, schedule or spending limit of my own plan

    plan = Subscription.objects.filter(pk=pk, Scustomer_id=request.session['Cid']).exclude(Sstatus='cancelled').first()

    if plan is None:

        messages.error(request, 'Subscription not found.')
        return redirect('/store/subscriptions')

    if request.method == 'POST':

        form = SubscriptionEditForm(request.POST)

        if form.is_valid():

            total = plan.Sproduct.Pprice * form.cleaned_data['Squantity']

            if total > form.cleaned_data['Sceiling']:

                form.add_error('Sceiling', f'This plan costs ${total:.2f} per order at the current price, which is above your limit.')

            else:

                plan.Squantity = form.cleaned_data['Squantity']
                plan.Sinterval = form.cleaned_data['Sinterval']
                plan.Sceiling = form.cleaned_data['Sceiling']
                plan.save()

                # The next order date is not moved; the new schedule applies after that order
                messages.success(request, f'{plan.Sproduct.Pname} subscription updated.')
                return redirect('/store/subscriptions')

    else:

        form = SubscriptionEditForm(initial={
            'Squantity': plan.Squantity,
            'Sinterval': plan.Sinterval,
            'Sceiling': f'{plan.Sceiling:.2f}',
        })

    return render(request, 'store/subscription_edit.html', {'plan': plan, 'form': form})
