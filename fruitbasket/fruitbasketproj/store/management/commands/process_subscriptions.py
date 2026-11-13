from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from store.subscriptions import ScheduledCycleConflict, process_due_subscriptions


class Command(BaseCommand):

    help = 'Create orders for active subscriptions that are due today or earlier.'

    def handle(self, *args, **options):

        try:
            cycles = process_due_subscriptions()
        except ScheduledCycleConflict as error:
            raise CommandError(f'{error} Earlier subscriptions may already have completed; completed cycles are protected against repeats.') from error
        except DatabaseError as error:
            raise CommandError('Subscription processing could not complete because the database is busy or unavailable. Retry after checking the database; completed cycles will not be repeated.') from error

        for cycle in cycles:

            self.stdout.write(f'Subscription {cycle.SCsubscription_id}: {cycle.get_SCresult_display()} - {cycle.SCnote}')

        self.stdout.write(f'{len(cycles)} due subscription(s) processed.')
