import time

from django.core.management.base import BaseCommand
from library.services import ReservationManager


class Command(BaseCommand):
    help = "Apply server-side reservation, check-in, break and location expiries and warnings."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep running expiry sweeps in the background.")
        parser.add_argument("--interval", type=int, default=15, help="Seconds between sweeps when --loop is used.")

    def handle(self, *args, **options):
        interval = max(1, options["interval"])
        while True:
            ReservationManager().expire_due()
            self.stdout.write(self.style.SUCCESS("Expiry and warning sweep completed."))
            if not options["loop"]:
                break
            time.sleep(interval)
