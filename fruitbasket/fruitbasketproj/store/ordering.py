from django.db import transaction
from django.db.models import F
from django.utils import timezone

from adminpanel.inventory import sellable_stock_filter
from adminpanel.models import Item, Orders, Product


class OrderNotPlaced(Exception):

    # Raised when an order cannot be created. The message is shown to the customer.

    pass


def generate_order_id():

    # Start from the count, then move past any number already used.
    # Counting alone repeats an ID once staff have deleted an order.
    number = Orders.objects.count() + 1

    while Orders.objects.filter(Oid='O' + str(number).zfill(5)).exists():

        number += 1

    return str(number).zfill(5)


def unit_price(product, quantity, use_bulk_price=False):

    # Shared group purchases pay the bulk unit price once the pooled quantity reaches the bulk threshold

    if use_bulk_price and product.Pbulkquantity and product.Pbulkprice and quantity >= product.Pbulkquantity:

        return product.Pbulkprice

    return product.Pprice


def order_total(quantities, use_bulk_price=False):

    total = 0

    for Pid, quantity in quantities.items():

        product = Product.objects.filter(pk=Pid).first()

        if product is not None and type(quantity) is int and quantity > 0:

            total += unit_price(product, quantity, use_bulk_price) * quantity

    return total


def place_order(customer, address, quantities, use_bulk_price=False, ceiling=None):

    # Used by checkout, subscriptions and group purchases so they all follow the same stock rules.
    # quantities is a dictionary of Pid -> number of packs.
    # Either the whole order is created, or nothing is changed.

    address = (address or '').strip()

    if not address:

        raise OrderNotPlaced('A delivery address is required. No order was placed.')

    # Orders.Oaddress holds at most 255 characters, and SQLite would not stop a longer one
    if len(address) > 255:

        raise OrderNotPlaced('The delivery address must be 255 characters or fewer. No order was placed.')

    if len(quantities) == 0:

        raise OrderNotPlaced('There is nothing to order.')

    with transaction.atomic():

        allocations = []
        total = 0

        for Pid, quantity in quantities.items():

            product = Product.objects.filter(pk=Pid).first()

            if type(quantity) is not int or quantity <= 0:

                raise OrderNotPlaced('Invalid cart quantity. Please remove the product and add it again.')

            # A product staff have deactivated can no longer be bought, even if it is still in a cart
            if product is not None and not product.Pactive:

                raise OrderNotPlaced(f'{product.Pname} is no longer available. Please remove it from your cart. No order was placed.')

            eligible = Item.objects.filter(sellable_stock_filter(), Iproduct_id=Pid)
            available = eligible.count()

            if available < quantity or product is None:

                name = product.Pname if product else Pid

                raise OrderNotPlaced(f'Only {available} sellable pack(s) of {name} available; you requested {quantity}. No order was placed.')

            # Earliest expiry goes out first; items without a date go last
            ids = list(eligible.order_by(F('Iexpiry').asc(nulls_last=True), 'pk').values_list('pk', flat=True)[:quantity])
            price = unit_price(product, quantity, use_bulk_price)
            total += price * quantity

            allocations.append((quantity, ids, price))

        if ceiling is not None and total > ceiling:

            raise OrderNotPlaced(f'The total of ${total:.2f} is above the approved limit of ${ceiling:.2f}. No order was placed.')

        newOrder = Orders.objects.create(
            Oid='O' + generate_order_id(),
            Odate=timezone.localdate(),
            Oaddress=address,
            Ocustomer=customer,
        )

        for quantity, ids, price in allocations:

            claimed = Item.objects.filter(sellable_stock_filter(), pk__in=ids).update(
                Iorder=newOrder, Istatus='allocated', Ipurchasedprice=price,
            )

            # Another customer took one of these items between the check and the claim
            if claimed != quantity:

                raise OrderNotPlaced('Sellable stock changed during checkout. No order was placed. Please review your cart.')

    return newOrder, total
