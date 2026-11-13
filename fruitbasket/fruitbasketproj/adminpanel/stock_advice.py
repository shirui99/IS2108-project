from datetime import timedelta

from django.db.models import Count, Q

from .models import Item, Product
from .inventory import sellable_stock_filter, stock_cutoff


def get_stock_advice(today):
    # The agreed recent-sales measure uses order dates and current delivered status.
    period_start = today - timedelta(days=29)
    near_end = today + timedelta(days=7)
    available = Q(product_items__Istatus='available')
    products = Product.objects.annotate(
        available=Count('product_items', filter=available),
        sellable=Count('product_items', filter=sellable_stock_filter(today, 'product_items__', '')),
        cutoff_excluded=Count('product_items', filter=available & Q(product_items__Iexpiry__lt=stock_cutoff(today, ''))),
        near_date=Count('product_items', filter=available & Q(product_items__Iexpiry__range=(today, near_end))),
        past_date=Count('product_items', filter=available & Q(product_items__Iexpiry__lt=today)),
        undated=Count('product_items', filter=available & Q(product_items__Iexpiry__isnull=True)),
        recent_delivered=Count('product_items', filter=Q(
            product_items__Iorder__Ostatus='delivered',
            product_items__Iorder__Odate__range=(period_start, today),
        )),
    ).order_by('Pname', 'Pid')
    for product in products:
        product.low_stock = product.sellable <= product.Plowstock
        product.replenish = (
            None if product.Ptargetstock is None
            else max(product.Ptargetstock - product.sellable, 0)
        )
    dated_batches = Item.objects.filter(
        Istatus='available', Iexpiry__lte=near_end,
    ).values(
        'Iproduct_id', 'Iproduct__Pname', 'Iproduct__Psize',
        'Iproduct__Pactive', 'Ireceived', 'Iexpiry',
    ).annotate(quantity=Count('pk')).order_by('Iexpiry', 'Iproduct_id', 'Ireceived')
    return {
        'products': products,
        'dated_batches': dated_batches,
        'today': today,
        'period_start': period_start,
        'near_end': near_end,
    }
