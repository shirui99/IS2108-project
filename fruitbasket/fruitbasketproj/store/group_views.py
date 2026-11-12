import secrets

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from adminpanel.models import Customer, GroupLine, GroupMember, GroupPurchase, Product

from .forms import GroupForm
from .ordering import OrderNotPlaced, place_order, unit_price


def pooled_lines(group):

    # Add up every member's quantity for each product and price the pooled quantity

    quantities = {}

    for line in group.group_lines.all():

        quantities[line.GLproduct_id] = quantities.get(line.GLproduct_id, 0) + line.GLquantity

    lines = []
    total = 0

    for Pid, quantity in quantities.items():

        product = Product.objects.get(pk=Pid)
        price = unit_price(product, quantity, use_bulk_price=True)
        subtotal = price * quantity
        total += subtotal

        lines.append({'product': product, 'quantity': quantity, 'price': price, 'subtotal': subtotal, 'bulk': price < product.Pprice})

    return quantities, lines, total


def groups(request):

    # SF20: create a shared basket. Also lists the groups the customer belongs to.

    customer = Customer.objects.get(pk=request.session['Cid'])

    if request.method == 'POST':

        form = GroupForm(request.POST)

        if form.is_valid():

            with transaction.atomic():

                group = GroupPurchase.objects.create(
                    Gname=form.cleaned_data['Gname'],
                    Gaddress=form.cleaned_data['Gaddress'],
                    Gcode=secrets.token_urlsafe(12),
                    Gcreated=timezone.localdate(),
                    Gorganiser=customer,
                )

                # The organiser is the first member
                GroupMember.objects.create(GMgroup=group, GMcustomer=customer)

            messages.success(request, 'Group purchase created. Share the invitation link with the people you want to invite.')
            return redirect(f'/store/groups/{group.pk}')

    else:

        form = GroupForm(initial={'Gaddress': customer.Caddress})

    context = {
        'form': form,
        'memberships': GroupMember.objects.filter(GMcustomer=customer).select_related('GMgroup__Gorganiser').order_by('-GMgroup__pk'),
        'customer': customer,
    }

    return render(request, 'store/groups.html', context)


def group_join(request, code):

    # SF21: an invited customer opens the invitation link and joins while the group is open

    customer = Customer.objects.get(pk=request.session['Cid'])
    group = GroupPurchase.objects.filter(Gcode=code).first()

    if group is None:

        messages.error(request, 'This invitation link is not valid.')
        return redirect('/store/groups')

    if GroupMember.objects.filter(GMgroup=group, GMcustomer=customer).exists():

        return redirect(f'/store/groups/{group.pk}')

    if request.method == 'POST':

        if group.Gstatus != 'open':

            messages.error(request, 'This group purchase is no longer open to new members.')
            return redirect('/store/groups')

        GroupMember.objects.get_or_create(GMgroup=group, GMcustomer=customer)

        messages.success(request, f'You joined {group.Gname}.')
        return redirect(f'/store/groups/{group.pk}')

    return render(request, 'store/group_join.html', {'group': group})


def group_detail(request, pk):

    customer = Customer.objects.get(pk=request.session['Cid'])

    # Only members can see or change a group
    group = GroupPurchase.objects.filter(pk=pk, group_members__GMcustomer=customer).first()

    if group is None:

        messages.error(request, 'Group purchase not found.')
        return redirect('/store/groups')

    is_organiser = group.Gorganiser_id == customer.Cid

    if request.method == 'POST':

        action = request.POST.get('action')

        if action == 'line':

            # SF21: a member sets their own quantity of one product. Zero removes the line.
            product = Product.objects.filter(pk=request.POST.get('Pid'), Pactive=True).first()

            try:
                quantity = int(request.POST.get('quantity'))
            except (TypeError, ValueError):
                quantity = -1

            if group.Gstatus != 'open':

                messages.error(request, 'This group purchase is locked. Quantities can no longer be changed.')

            elif product is None or quantity < 0 or quantity > 500:

                messages.error(request, 'Choose a product and enter a quantity of 0 or more.')

            elif quantity == 0:

                GroupLine.objects.filter(GLgroup=group, GLcustomer=customer, GLproduct=product).delete()
                messages.success(request, f'{product.Pname} removed from your contribution.')

            else:

                # The line always belongs to the logged in customer, never to an ID sent by the browser
                GroupLine.objects.update_or_create(
                    GLgroup=group, GLcustomer=customer, GLproduct=product, defaults={'GLquantity': quantity}
                )
                messages.success(request, f'Your quantity of {product.Pname} is now {quantity}.')

        elif action == 'leave':

            # SF34: a member takes their quantities out and leaves while the group is open
            if is_organiser:

                messages.error(request, 'The organiser cannot leave the group purchase.')

            elif group.Gstatus != 'open':

                messages.error(request, 'This group purchase is locked. You can no longer leave it.')

            else:

                with transaction.atomic():

                    GroupLine.objects.filter(GLgroup=group, GLcustomer=customer).delete()
                    GroupMember.objects.filter(GMgroup=group, GMcustomer=customer).delete()

                messages.success(request, f'You left {group.Gname}. Your quantities were removed.')
                return redirect('/store/groups')

        elif action == 'lock':

            # SF22: the organiser freezes contributions before paying
            if not is_organiser:

                messages.error(request, 'Only the organiser can lock this group purchase.')

            elif not group.group_lines.exists():

                messages.error(request, 'Add at least one product before locking the group purchase.')

            elif GroupPurchase.objects.filter(pk=group.pk, Gstatus='open').update(Gstatus='locked'):

                messages.success(request, 'Group purchase locked. Check the pooled total, then confirm the order.')

            else:

                messages.error(request, 'This group purchase is not open.')

        elif action == 'checkout':

            # SF22: the organiser pays for one order that covers every contribution
            if not is_organiser:

                messages.error(request, 'Only the organiser can check out this group purchase.')

            elif group.Gstatus != 'locked':

                messages.error(request, 'Lock the group purchase before checking out.')

            else:

                quantities, lines, total = pooled_lines(group)

                try:

                    with transaction.atomic():

                        order, total = place_order(customer, group.Gaddress, quantities, use_bulk_price=True)

                        # If the group was already ordered by another click, undo this second order
                        if not GroupPurchase.objects.filter(pk=group.pk, Gstatus='locked').update(Gstatus='ordered', Gorder=order):

                            raise OrderNotPlaced('This group purchase was already ordered.')

                    messages.success(request, f'Group order {order.Oid} placed for ${total:.2f}.')

                except OrderNotPlaced as error:

                    # The group stays locked so the organiser can try again
                    messages.error(request, str(error))

        return redirect(f'/store/groups/{group.pk}')

    quantities, lines, total = pooled_lines(group)

    # SF35: each member's share is their own packs at the pooled unit price
    prices = {line['product'].Pid: line['price'] for line in lines}
    shares = {}

    for line in group.group_lines.select_related('GLcustomer'):

        shares.setdefault(line.GLcustomer, 0)
        shares[line.GLcustomer] += line.GLquantity * prices[line.GLproduct_id]

    context = {
        'my_share': shares.get(customer, 0),
        'shares': sorted(shares.items(), key=lambda share: share[0].Cname),
        'group': group,
        'is_organiser': is_organiser,
        'members': group.group_members.select_related('GMcustomer'),
        'my_lines': group.group_lines.filter(GLcustomer=customer).select_related('GLproduct'),
        'all_lines': group.group_lines.select_related('GLcustomer', 'GLproduct').order_by('GLproduct__Pname', 'GLcustomer__Cname'),
        'pooled': lines,
        'total': total,
        'products': Product.objects.filter(Pactive=True).order_by('Pname'),
        'invite_link': request.build_absolute_uri(f'/store/groups/join/{group.Gcode}'),
    }

    return render(request, 'store/group_detail.html', context)
