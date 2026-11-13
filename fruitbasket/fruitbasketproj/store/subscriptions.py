from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from adminpanel.models import Customer, Subscription, SubscriptionCycle

from .ordering import OrderNotPlaced, place_order
from .restock import get_customer_purchase_history, predict_restock


def suggest_interval(customer, product):

    # SF16: use the restock model to suggest how often this customer buys this product,
    # then pick the closest schedule we offer (7, 14 or 30 days).
    # Returns (interval, label). interval is None if no estimate is available.

    events = get_customer_purchase_history(customer.Cid).get(product.Pid, [])
    today = timezone.localdate()

    latest = events[-1] if events else None
    previous = events[-2] if len(events) >= 2 else None

    prediction = predict_restock(
        latest_purchase_at=latest['purchased_at'] if latest else today,
        household_size=customer.Chouseholdsize,
        category=product.Pcategory_id,
        purchased_quantity=latest['purchased_quantity'] if latest else 1,
        previous_interval_days=(latest['purchased_at'] - previous['purchased_at']).days if previous else None,
        history_count=len(events),
    )

    if prediction['interval_days'] is None:

        return None, 'No estimate available'

    interval = min([7, 14, 30], key=lambda days: abs(days - prediction['interval_days']))
    label = 'ML estimate' if prediction['status'] == 'MODEL' else 'Initial estimate'

    return interval, label


class ScheduledCycleConflict(Exception):
    """The due date may already have been processed and requires staff review."""


def process_due_subscriptions(today=None):

    # Creates one order for every active subscription whose next date has arrived.
    # Paused and cancelled plans are skipped because only active plans are selected.
    # Returns the list of cycle records that were written.

    today = today or timezone.localdate()
    cycles = []

    for subscription in Subscription.objects.filter(Sstatus='active', Snextdate__lte=today).order_by('pk'):

        with transaction.atomic():

            # Moving the next date first, and only if it has not moved yet, stops the same
            # cycle being ordered twice when the command is run twice.
            # The next date counts from today, so missed dates never create backdated orders.
            claimed = Subscription.objects.filter(
                pk=subscription.pk, Sstatus='active', Snextdate=subscription.Snextdate,
                Squantity=subscription.Squantity, Sinterval=subscription.Sinterval, Sceiling=subscription.Sceiling
            ).update(Snextdate=today + timedelta(days=subscription.Sinterval))

            if not claimed:

                continue

            # Older records have no scheduled date. If their processing date falls
            # in this due window, do not guess whether they already cover this cycle.
            ambiguous = SubscriptionCycle.objects.filter(SCsubscription=subscription, SCscheduleddate__isnull=True,
                SCdate__gte=subscription.Snextdate, SCdate__lte=today).exists()
            duplicate = SubscriptionCycle.objects.filter(SCsubscription=subscription,
                SCscheduleddate=subscription.Snextdate).exists()
            if ambiguous or duplicate:
                raise ScheduledCycleConflict(f'Subscription {subscription.pk}: scheduled cycle {subscription.Snextdate} may already be recorded; review before processing.')

            customer = Customer.objects.get(pk=subscription.Scustomer_id)

            try:

                order, total = place_order(
                    customer, customer.Caddress, {subscription.Sproduct_id: subscription.Squantity}, ceiling=subscription.Sceiling
                )

                cycle = SubscriptionCycle.objects.create(
                    SCsubscription=subscription, SCdate=today, SCscheduleddate=subscription.Snextdate, SCresult='ordered', SCorder=order,
                    SCnote=f'Order {order.Oid} for ${total:.2f}'
                )

            except OrderNotPlaced as error:

                cycle = SubscriptionCycle.objects.create(
                    SCsubscription=subscription, SCdate=today, SCscheduleddate=subscription.Snextdate, SCresult='failed', SCnote=str(error)[:255]
                )

            cycles.append(cycle)

    return cycles
