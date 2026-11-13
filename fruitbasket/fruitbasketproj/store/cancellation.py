from django.db import transaction
from django.db.models import Count
from adminpanel.models import CancelledAllocation, Item, OrderCancellation, Orders


def cancel_order(order_id, *, customer_id=None, employee=None, reason=''):
    """Snapshot the allocation and release it under the same claim as preparation."""
    if employee is not None:
        if not (employee.is_authenticated and employee.is_active and employee.is_staff):
            raise ValueError('Active staff access is required.')
        reason = reason.strip()
        if not reason or len(reason) > 1000:
            raise ValueError('Enter a cancellation reason of at most 1000 characters.')
    elif customer_id is None:
        raise ValueError('Customer ownership is required.')
    with transaction.atomic():
        orders = Orders.objects.filter(pk=order_id, Ostatus='placed')
        if employee is None:
            orders = orders.filter(Ocustomer_id=customer_id)
        if not orders.update(Ostatus='cancelled'):
            return False
        order = Orders.objects.get(pk=order_id)
        if order.Opayment not in ('paid', 'refunded'):
            raise ValueError('The recorded simulated payment state is invalid. Review the order before cancelling.')
        packs = Item.objects.filter(Iorder_id=order_id)
        total = packs.count()
        eligible = packs.filter(Istatus__in=['allocated', 'delivered'], Ifinished__isnull=True, Irating__isnull=True)
        if eligible.count() != total:
            raise ValueError('Some items in this order were already used or thrown away. Please contact support below.')
        record = OrderCancellation.objects.create(order=order, source='staff' if employee else 'customer',
            employee=employee, reason=reason if employee else '', payment_before=order.Opayment, payment_after='refunded')
        rows = eligible.values('Iproduct_id', 'Iproduct__Pname', 'Iproduct__Psize', 'Ipurchasedprice',
            'Ibatch_id', 'Ibatch__Breference', 'Ireceived', 'Iexpiry').annotate(quantity=Count('id'))
        CancelledAllocation.objects.bulk_create([CancelledAllocation(cancellation=record,
            product_id=row['Iproduct_id'], product_name=row['Iproduct__Pname'], pack_size=row['Iproduct__Psize'],
            quantity=row['quantity'], unit_price=row['Ipurchasedprice'], batch_id=row['Ibatch_id'],
            batch_reference=row['Ibatch__Breference'], received=row['Ireceived'], recorded_date=row['Iexpiry']) for row in rows])
        if eligible.update(Iorder=None, Istatus='available', Ipurchasedprice=None, Irating=None) != total:
            raise ValueError('Order items changed during cancellation. Please review the order and try again.')
        if order.Opayment == 'paid':
            refunded = Orders.objects.filter(pk=order_id, Ostatus='cancelled', Opayment='paid').update(Opayment='refunded')
            if refunded != 1:
                raise ValueError('The simulated refund could not be recorded. The cancellation was not completed.')
    return True
