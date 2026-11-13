from django.contrib import messages
from django.db import DatabaseError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from .models import Subscription
from store.subscriptions import ScheduledCycleConflict, process_due_subscriptions


def staff_access(request):
    return request.user.is_authenticated and request.user.is_active and request.user.is_staff


@require_GET
def subscription_processing(request):
    if not staff_access(request):
        return redirect('adminpanel_login')
    plans = Subscription.objects.filter(Sstatus='active', Snextdate__lte=timezone.localdate()).select_related('Scustomer','Sproduct').prefetch_related('subscription_cycles').order_by('Snextdate','pk')
    for plan in plans:
        plan.current_cycle = next((cycle for cycle in plan.subscription_cycles.all() if cycle.SCscheduleddate == plan.Snextdate), None)
    return render(request, 'adminpanel/subscription_processing.html', {'plans':plans})


@require_POST
def process_subscriptions(request, pk=None):
    if not staff_access(request):
        return redirect('adminpanel_login')
    if pk is not None:
        get_object_or_404(Subscription, pk=pk)
    try:
        cycles = process_due_subscriptions(subscription_id=pk)
    except (DatabaseError, ScheduledCycleConflict) as error:
        messages.error(request, str(error) if isinstance(error, ScheduledCycleConflict) else 'The database is busy or unavailable. Please try again. Earlier completed plans will not be repeated.')
    else:
        if not cycles:
            messages.info(request, 'No active due plans were processed. The plan may have changed or already completed.')
        for cycle in cycles:
            if cycle.SCresult == 'ordered':
                messages.success(request, f'Subscription {cycle.SCsubscription_id}: order {cycle.SCorder_id} created.')
            else:
                messages.warning(request, f'Subscription {cycle.SCsubscription_id} on hold: {cycle.SCnote}')
    return redirect('subscription_processing')
