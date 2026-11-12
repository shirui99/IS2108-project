from datetime import timedelta

from django.db.models import DateField, DurationField, ExpressionWrapper, F, IntegerField, Q, Value
from django.db.models.functions import Cast
from django.utils import timezone


def stock_cutoff(today, product_prefix='Iproduct__'):
    days = ExpressionWrapper(
        Cast(F(product_prefix + 'Pexpirydays'), IntegerField()) * Value(timedelta(days=1)),
        output_field=DurationField(),
    )
    return ExpressionWrapper(Value(today, output_field=DateField()) + days, output_field=DateField())


def sellable_stock_filter(today=None, item_prefix='', product_prefix='Iproduct__'):
    """ORM predicate for individual packs or a product's reverse item relation."""
    today = today or timezone.localdate()
    return Q(**{product_prefix + 'Pactive': True, item_prefix + 'Istatus': 'available'}) & (
        Q(**{item_prefix + 'Iexpiry__isnull': True})
        | Q(**{item_prefix + 'Iexpiry__gte': stock_cutoff(today, product_prefix)})
    )
