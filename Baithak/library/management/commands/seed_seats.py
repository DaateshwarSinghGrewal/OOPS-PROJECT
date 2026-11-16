from django.core.management.base import BaseCommand
from library.services import SeatManager


class Command(BaseCommand):
    help = "Create the 450 Baithak seats. Safe to run more than once."

    def handle(self, *args, **options):
        count = SeatManager().seed()
        total = sum(number for _, number in SeatManager.FLOOR_COUNTS)
        self.stdout.write(self.style.SUCCESS(f"Seat seed complete: {count} added; {total} seats configured."))
