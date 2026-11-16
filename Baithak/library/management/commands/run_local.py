import logging
import threading

from django.core.management import call_command
from django.core.management.base import BaseCommand
from library.services import ReservationManager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the local Baithak server with automatic reservation expiry enabled."

    def handle(self, *args, **options):
        stop = threading.Event()

        def expiry_worker():
            while not stop.is_set():
                try:
                    ReservationManager().expire_due()
                except Exception:
                    logger.exception("Baithak expiry sweep failed; it will retry shortly.")
                stop.wait(15)

        worker = threading.Thread(target=expiry_worker, name="baithak-expiry", daemon=True)
        worker.start()
        self.stdout.write(self.style.SUCCESS("Automatic seat expiry is running."))
        try:
            call_command("runserver", "127.0.0.1:8000", use_reloader=False)
        finally:
            stop.set()
            worker.join(timeout=2)
