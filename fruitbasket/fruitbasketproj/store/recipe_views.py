from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils import timezone

from .recipes import DAILY_LIMIT, RecipesUnavailable, expiring_items, suggest_recipes


def recipes(request):

    # Recipe ideas (story SF36 in the report): from generative AI for pantry items that expire soon.
    # GET only shows the page. The AI service is called only when the customer presses the button (POST).

    Cid = request.session['Cid']
    today = timezone.localdate()
    items = expiring_items(Cid, today)

    if request.method == 'POST':

        # Each customer gets a small number of requests per day, because every request costs money
        count_key = f'recipes:{Cid}:{today}'
        used = cache.get(count_key, 0)

        if not items:

            messages.error(request, 'You have no pantry items expiring in the next 3 days.')

        elif used >= DAILY_LIMIT:

            messages.error(request, f'You have reached the limit of {DAILY_LIMIT} recipe requests for today.')

        else:

            cache.set(count_key, used + 1, 60 * 60 * 24)

            try:

                found = suggest_recipes(items)

                # Saved in the session so reloading the page does not call the AI service again
                request.session['recipes'] = {
                    'date': str(today),
                    'items': [item['name'] for item in items],
                    'recipes': found,
                }

                if found:

                    messages.success(request, 'Here are some ideas for your expiring items.')

                else:

                    messages.error(request, 'No recipe ideas were found for these items.')

            except RecipesUnavailable as error:

                messages.error(request, str(error))

        return redirect('/store/recipes')

    saved = request.session.get('recipes')

    # Ideas from an earlier day are out of date, so they are not shown
    if type(saved) is not dict or saved.get('date') != str(today):

        saved = None

    context = {
        'items': items,
        'saved': saved,
        'daily_limit': DAILY_LIMIT,
    }

    return render(request, 'store/recipes.html', context)
