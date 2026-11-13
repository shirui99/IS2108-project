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


def process_due_subscriptions(today=None, subscription_id=None):

    # Creates one order for every active subscription whose next date has arrived.
    # Paused and cancelled plans are skipped because only active plans are selected.
    # Returns the list of cycle records that were written.

    today = today or timezone.localdate()
    cycles = []

    due = Subscription.objects.filter(Sstatus='active', Snextdate__lte=today).order_by('pk')
    if subscription_id is not None:
        due = due.filter(pk=subscription_id)
    for subscription in due:

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
            cycle = SubscriptionCycle.objects.filter(SCsubscription=subscription,
                SCscheduleddate=subscription.Snextdate).first()
            retryable = cycle and cycle.SCresult == 'failed' and cycle.SCretryable and cycle.SCorder_id is None
            if ambiguous or (cycle and not retryable):
                raise ScheduledCycleConflict(f'Subscription {subscription.pk}: scheduled cycle {subscription.Snextdate} may already be recorded; review before processing.')

            customer = Customer.objects.get(pk=subscription.Scustomer_id)

            try:

                order, total = place_order(
                    customer, customer.Caddress, {subscription.Sproduct_id: subscription.Squantity}, ceiling=subscription.Sceiling
                )

                values = dict(SCdate=today, SCresult='ordered', SCorder=order, SCretryable=False, SCnote=f'Order {order.Oid} for ${total:.2f}')
                if cycle:
                    for name, value in values.items():
                        setattr(cycle, name, value)
                    cycle.save(update_fields=list(values))
                else:
                    cycle = SubscriptionCycle.objects.create(SCsubscription=subscription, SCscheduleddate=subscription.Snextdate, **values)

            except OrderNotPlaced as error:

                # The provisional schedule claim is retained only after a successful order.
                if Subscription.objects.filter(pk=subscription.pk).update(Snextdate=subscription.Snextdate) != 1:
                    raise ScheduledCycleConflict('The held plan changed; review before retrying.')
                values = dict(SCdate=today, SCresult='failed', SCretryable=True, SCnote=str(error)[:255])
                if cycle:
                    for name, value in values.items():
                        setattr(cycle, name, value)
                    cycle.save(update_fields=list(values))
                else:
                    cycle = SubscriptionCycle.objects.create(SCsubscription=subscription, SCscheduleddate=subscription.Snextdate, **values)

            cycles.append(cycle)

    return cycles
