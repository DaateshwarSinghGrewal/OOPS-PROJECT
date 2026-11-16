import base64
import io
import json

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth import password_validation
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Reservation, ReservationPolicy, Seat, Student
from .services import (AttendanceManager, BaithakError, BreakManager,
                       LocationMonitor, NotificationManager, ReservationManager,
                       SeatManager)

User = get_user_model()


def home(request):
    return render(request, "library/home.html")


def register(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        roll_no = request.POST.get("rollno", "").strip()
        password = request.POST.get("password", "")
        if not email.endswith("@thapar.edu"):
            messages.error(request, "Please register with your @thapar.edu email address.")
        elif len(roll_no) != 10 or not roll_no.isdigit():
            messages.error(request, "Roll number must contain exactly 10 digits.")
        elif not name or len(password) < 8:
            messages.error(request, "Enter your name and a password of at least 8 characters.")
        elif User.objects.filter(username=email).exists() or Student.objects.filter(roll_no=roll_no).exclude(email=email).exists():
            messages.error(request, "That email or roll number is already registered.")
        else:
            user_candidate = User(username=email, email=email, first_name=name)
            try:
                password_validation.validate_password(password, user_candidate)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                try:
                    with transaction.atomic():
                        user = User.objects.create_user(username=email, email=email, password=password, first_name=name)
                        student = Student.objects.filter(email=email, roll_no=roll_no, user__isnull=True).first()
                        if student:
                            student.user = user
                            student.name = name
                            student.save(update_fields=["user", "name"])
                        else:
                            student = Student.objects.create(user=user, name=name, email=email, roll_no=roll_no)
                    login(request, user)
                    messages.success(request, f"Welcome to Baithak, {student.name}.")
                    return redirect("index")
                except IntegrityError:
                    messages.error(request, "That email or roll number is already registered.")
    return render(request, "library/register.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("index")
    error = None
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        user = authenticate(request, username=email, password=password)
        if user:
            login(request, user)
            return redirect("index")
        error = "Email or password is incorrect. New here? Register first."
    return render(request, "library/login.html", {"error": error})


def logout_view(request):
    if request.method == "POST":
        logout(request)
    return redirect("home")


def current_student(request):
    try:
        return request.user.student_profile
    except (AttributeError, Student.DoesNotExist):
        return None


def student_required(view_func):
    @login_required
    def wrapped(request, *args, **kwargs):
        if current_student(request) is None:
            messages.error(request, "Register a student profile to use Baithak.")
            return redirect("register")
        return view_func(request, *args, **kwargs)
    return wrapped


@student_required
def index_view(request):
    ReservationManager().expire_due()
    student = current_student(request)
    if request.method == "POST" and request.POST.get("action") == "renew":
        try:
            ReservationManager().renew(student, int(request.POST.get("duration", "")))
            messages.success(request, "Your reservation was renewed successfully.")
            return redirect("index")
        except (ValueError, BaithakError) as exc:
            messages.error(request, str(exc) or "Choose a valid renewal duration.")
    reservation = Reservation.objects.filter(student=student, status__in=Reservation.ACTIVE_STATUSES).select_related("seat").first()
    policy = ReservationPolicy.current()
    seats = Seat.objects.count()
    active = Reservation.objects.filter(status__in=Reservation.ACTIVE_STATUSES)
    context = {
        "student": student, "reservation": reservation,
        "available_count": max(0, seats - active.count()),
        "reserved_count": active.filter(status=Reservation.Status.RESERVED).count(),
        "occupied_count": active.exclude(status=Reservation.Status.RESERVED).count(),
        "recent_notifications": student.notifications.all()[:5],
        "duration_options": range(policy.minimum_minutes, policy.maximum_minutes + 1, policy.increment_minutes),
        "policy": policy,
    }
    return render(request, "library/index.html", context)


@student_required
def book_seat(request):
    manager = SeatManager()
    manager.seed()
    ReservationManager().expire_due()
    error = None
    if request.method == "POST":
        try:
            ReservationManager().reserve(current_student(request), int(request.POST.get("seat_id", "")), int(request.POST.get("duration", "")))
            messages.success(request, "Seat reserved. Your study time starts when your library check-in is verified.")
            return redirect("index")
        except (ValueError, BaithakError) as exc:
            error = str(exc) or "Select a valid seat and duration."
    policy = ReservationPolicy.current()
    status_map = {r.seat_id: r for r in Reservation.objects.filter(status__in=Reservation.ACTIVE_STATUSES).select_related("student")}
    floors = []
    for key, label, count in [(Seat.Floor.GROUND,"Ground Floor",184),(Seat.Floor.FIRST,"First Floor",86),(Seat.Floor.SECOND,"Second Floor",60),(Seat.Floor.THIRD,"Third Floor",54),(Seat.Floor.FOURTH,"Fourth Floor",66)]:
        seats = list(Seat.objects.filter(floor=key).order_by("number"))
        floor_seats = [(seat, status_map.get(seat.pk)) for seat in seats]
        floors.append({"label": label, "capacity": count, "available": sum(1 for _, reservation in floor_seats if reservation is None), "seats": floor_seats})
    duration_options = range(policy.minimum_minutes, policy.maximum_minutes + 1, policy.increment_minutes)
    return render(request, "library/seat.html", {"floors": floors, "policy": policy, "duration_options": duration_options, "error": error, "has_reservation": Reservation.objects.filter(student=current_student(request), status__in=Reservation.ACTIVE_STATUSES).exists()})


@student_required
def checkin(request):
    ReservationManager().expire_due()
    student = current_student(request)
    reservation = Reservation.objects.filter(student=student, status=Reservation.Status.RESERVED).select_related("seat").first()
    error = None
    if request.method == "POST":
        try:
            AttendanceManager().check_in(student, request.POST.get("token", ""))
            messages.success(request, "Check-in successful. Enjoy your study session.")
            return redirect("index")
        except BaithakError as exc:
            error = str(exc)
    qr_data = None
    if reservation:
        checkin_url = request.build_absolute_uri(f"/checkin/scan/?token={reservation.qr_token}")
        try:
            import qrcode
            from qrcode.image.svg import SvgPathImage
            image = qrcode.make(checkin_url, image_factory=SvgPathImage)
            buffer = io.BytesIO()
            image.save(buffer)
            qr_data = "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        except ImportError:
            pass
    return render(request, "library/checkin.html", {"reservation": reservation, "token": reservation.qr_token if reservation else "", "qr_data": qr_data, "error": error, "prefill_token": request.GET.get("token", "")})


@user_passes_test(lambda user: user.is_staff, login_url="/admin/login/")
def scan_checkin(request):
    token = request.POST.get("token", "") if request.method == "POST" else request.GET.get("token", "")
    error = None
    checked_in = None
    if request.method == "POST":
        try:
            checked_in = AttendanceManager().check_in_from_qr(token)
            messages.success(request, f"Verified {checked_in.student.name}; seat {checked_in.seat.number} checked in.")
        except BaithakError as exc:
            error = str(exc)
    return render(request, "library/scan_checkin.html", {"token": token, "error": error, "checked_in": checked_in})


@student_required
def break_status(request):
    ReservationManager().expire_due()
    student = current_student(request)
    manager = BreakManager()
    error = None
    if request.method == "POST":
        try:
            action = request.POST.get("action")
            if action == "start":
                manager.start(student, int(request.POST.get("minutes", "30")))
                messages.success(request, "Break started. Return before it expires to keep your seat.")
            elif action == "return":
                manager.return_from_break(student)
                messages.success(request, "Welcome back. Your seat is active again.")
            elif action == "checkout":
                AttendanceManager().checkout(student)
                messages.success(request, "You checked out and released your seat.")
            return redirect("break")
        except (ValueError, BaithakError) as exc:
            error = str(exc) or "Enter a valid break duration."
    reservation = Reservation.objects.filter(student=student, status__in=Reservation.ACTIVE_STATUSES).select_related("seat").first()
    return render(request, "library/break.html", {"reservation": reservation, "policy": ReservationPolicy.current(), "error": error, "break_record": reservation.breaks.filter(returned_at__isnull=True).first() if reservation else None})


@student_required
def notification(request):
    student = current_student(request)
    if request.method == "POST":
        student.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
        return redirect("notification")
    return render(request, "library/notification.html", {"notifications": student.notifications.all()})


@student_required
@require_POST
def location_report(request):
    try:
        payload = json.loads(request.body or "{}")
        latitude, longitude = float(payload["latitude"]), float(payload["longitude"])
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError
        result = LocationMonitor().report(current_student(request), latitude, longitude)
        return JsonResponse({"ok": True, **result})
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid location coordinates."}, status=400)
    except BaithakError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
