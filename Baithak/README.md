# Baithak — Smart Library Seat Reservation System

Baithak is a Django application for Thapar students to reserve and manage study seats across five library floors. Its existing design and static assets are retained while reservations, attendance, breaks, notifications, and location alerts are stored and validated by the server.

## Run locally on Windows

Open this `Baithak/` folder in File Explorer and double-click `run_local.bat` (or run `run_local.bat` from PowerShell). It creates a local virtual environment if needed, installs the packages, applies database migrations, seeds the seats, and starts Django. Open `http://127.0.0.1:8000/` in your browser. Press **Ctrl+C** in the launcher window to stop the server.

The setup steps do not need to be repeated manually each time. The script checks dependencies and migrations on each start; both are safe to rerun. On first startup, package installation needs an internet connection.

To create an administrator account for the Django admin and staff QR scanner, open a second terminal in this folder and run:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Students register using a `@thapar.edu` email, a 10-digit roll number, and a password. If a matching student row exists from the prototype, registration links it to the new password account. Django stores the password hash, not the password itself.

## Run locally on macOS or Linux

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_seats
python manage.py runserver
```

Then open `http://127.0.0.1:8000/`.

The SQLite database is `db.sqlite3` and is ignored by Git. Run `python manage.py makemigrations library` after model changes, then `python manage.py migrate`. `seed_seats` is safe to run repeatedly and creates 450 seats: 184 ground, 86 first, 60 second, 54 third, and 66 fourth floor.

## Reservation and attendance behavior

- Students can hold one active reservation, and each seat can have one active reservation. Partial unique database constraints enforce both rules.
- Duration limits, suggested duration, increments, check-in grace period, break length, library coordinates, geofence radius, and return countdown are editable in Django admin under **Reservation policies**.
- Booking holds the seat until the separate check-in deadline. The study timer and full requested duration start when the server records a successful check-in; missed check-ins release the seat without starting a study session.
- The check-in page displays a server-issued, one-use QR code for staff to scan at the entrance. The scan page requires a Django staff account; the server checks the reservation, status, deadline, and one-time token and records the student's attendance. Students can also verify their own reservation from their authenticated account.
- Students can renew before expiry, request breaks up to 30 minutes, return from a break, or permanently check out. Reservation, break, and attendance records remain in history.
- Location sharing is opt-in and uses the browser's geolocation permission. While the dashboard remains open, position reports are checked against the configured radius. Server-side expiry sweeps release seats after a return countdown even if the browser closes. Browser background location is not assumed.
- Expiry and warning decisions use server time. The management command below is intended to run every minute in a scheduler; request-time checks are an additional safeguard.

## Automatic expiry scheduler

The app provides `python manage.py expire_reservations`. The one-click `run_local.bat` launcher starts the local server with an expiry sweep every 15 seconds, so a reservation that is not checked into within its 30-minute window is freed even if the student closes the browser.

When running the server through another process manager, schedule `python manage.py expire_reservations` every minute so reservation, check-in, break, location countdowns, and warning notifications are handled when nobody is browsing.

Windows Task Scheduler action:

- Program: the virtual environment's `python.exe`
- Arguments: `manage.py expire_reservations`
- Start in: this `Baithak` directory
- Trigger: repeat every 1 minute indefinitely

Linux cron example (adjust paths):

```cron
* * * * * cd /path/to/Baithak && /path/to/Baithak/.venv/bin/python manage.py expire_reservations
```

For a deployed service, configure a process supervisor or scheduler to run the same command. SQLite is suitable for local development and coursework; use a database with stronger concurrent-write support for a busy multi-worker deployment.

## Administration and configuration

Sign in at `/admin/` with the superuser created above. Create the singleton reservation policy and configure the exact library coordinates and radius before enabling geofence alerts. Defaults are example coordinates and should be checked against the intended entrance. Admin controls include reservation limits, suggested duration, increments, check-in grace, maximum break duration (capped at 30), return countdown, and library location.

For deployment, set `BAITHAK_SECRET_KEY`, `BAITHAK_DEBUG=0`, and `BAITHAK_ALLOWED_HOSTS`. Configure HTTPS, secure cookies, database backups, and an appropriate production database before exposing the service publicly. The default development key and settings are not production credentials.

## Tests

Run the business-rule suite with:

```sh
python manage.py test library
```

The tests cover seat seeding, reservation uniqueness, account registration and login, QR ownership and replay, check-in and reservation expiry, renewal, breaks, and location return behavior.

## OOPS implementation notes

Python demonstrates object-oriented design through Django models and composed manager/service objects:

- **Classes and objects:** `Seat`, `Student`, `Reservation`, and the service managers represent domain entities and operations.
- **Encapsulation:** business transitions are methods on `ReservationManager`, `AttendanceManager`, `BreakManager`, and `LocationMonitor`; views delegate to these services.
- **Constructors:** Django model initialization and Python service construction (`ReservationManager()`, etc.) create configured objects.
- **Abstraction:** service methods expose operations such as `reserve`, `check_in`, and `start` without exposing transaction details to views.
- **Composition and relationships:** reservations connect a student and seat; attendance and break records belong to a reservation; services compose each other where workflows need shared rules.
- **Polymorphism and inheritance:** Django's model and authentication framework use Python inheritance; the app avoids adding artificial domain inheritance where it does not clarify behavior. The `BaithakError` exception hierarchy provides semantic error categories. Python has no C++-style header declarations, virtual keywords, or overload-by-signature semantics; don't interpret its duck typing as those C++ mechanisms.
- **Exceptions and transactions:** domain errors are handled at the view boundary, and writes use Django transactions with database constraints as the final concurrency guard.

The `cpp_oops_demos/` folder contains separate C++ examples for syllabus-specific language features such as function/operator overloading, multiple inheritance, virtual methods and destructors, templates, `new`/`delete`, exceptions, file handling, and formatted I/O. See its README for build instructions.
