from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from adminpanel.inventory import sellable_stock_filter
from adminpanel.models import Customer, Item, Product, SavedItem, StockNotice

from .forms import PasswordForm


def change_password(request):

    # SF26: change my password

    user = Customer.objects.get(pk=request.session['Cid']).Cuser

    if request.method == 'POST':

        form = PasswordForm(user, request.POST)

        if form.is_valid():

            # set_password stores a hash, never the password itself
            user.set_password(form.cleaned_data['new'])
            user.save()

            messages.success(request, 'Your password was changed.')
            return redirect('/store/profile')

    else:

        form = PasswordForm(user)

    return render(request, 'store/password.html', {'form': form})


def with_stock(products):

    # Adds sellable_stock to each product, the same way the shop page does

    return products.annotate(
        sellable_stock=Count('product_items', filter=sellable_stock_filter(item_prefix='product_items__', product_prefix=''))
    )


def saved_list(request):

    # SF28: my shopping list. SF29: the products I asked to be told about.

    Cid = request.session['Cid']

    context = {
        'saved_products': with_stock(Product.objects.filter(product_saved_items__SVcustomer_id=Cid)).order_by('Pname'),
        'notice_products': with_stock(Product.objects.filter(product_notices__SNcustomer_id=Cid)).order_by('Pname'),
    }

    return render(request, 'store/saved_list.html', context)


@require_POST
def saved_item(request, pk):

    # SF28: add a product to my list or take it off

    product = Product.objects.filter(pk=pk).first()

    if product is None:

        messages.error(request, 'Product not found.')

    elif request.POST.get('action') == 'remove':

        SavedItem.objects.filter(SVcustomer_id=request.session['Cid'], SVproduct=product).delete()
        messages.success(request, f'{product.Pname} removed from your list.')

    elif not product.Pactive:

        messages.error(request, f'{product.Pname} is no longer sold, so it cannot be saved.')

    else:

        SavedItem.objects.get_or_create(
            SVcustomer_id=request.session['Cid'], SVproduct=product, defaults={'SVadded': timezone.localdate()}
        )
        messages.success(request, f'{product.Pname} saved to your list.')

    return redirect('/store/list')


@require_POST
def stock_notice(request, pk):

    # SF29: ask to be told when a product is back, or stop being told

    product = Product.objects.filter(pk=pk).first()

    if product is None:

        messages.error(request, 'Product not found.')

    elif request.POST.get('action') == 'remove':

        StockNotice.objects.filter(SNcustomer_id=request.session['Cid'], SNproduct=product).delete()
        messages.success(request, f'You will no longer be told about {product.Pname}.')

    elif not product.Pactive:

        messages.error(request, f'{product.Pname} is no longer sold, so it will not come back into stock.')

    elif Item.objects.filter(sellable_stock_filter(), Iproduct=product).exists():

        messages.error(request, f'{product.Pname} is already in stock. You can add it to your cart now.')

    else:

        StockNotice.objects.get_or_create(
            SNcustomer_id=request.session['Cid'], SNproduct=product, defaults={'SNcreated': timezone.localdate()}
        )
        messages.success(request, f'We will tell you on the shop page when {product.Pname} is back in stock.')

    return redirect('/store/list')
