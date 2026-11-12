from django.core.management.base import BaseCommand

from store.subscriptions import process_due_subscriptions


class Command(BaseCommand):

    help = 'Create orders for active subscriptions that are due today or earlier.'

    def handle(self, *args, **options):

        cycles = process_due_subscriptions()

        for cycle in cycles:

            self.stdout.write(f'Subscription {cycle.SCsubscription_id}: {cycle.get_SCresult_display()} - {cycle.SCnote}')

        self.stdout.write(f'{len(cycles)} due subscription(s) processed.')
