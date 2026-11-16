import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Student(models.Model):
    """Baithak profile linked to Django's password-hashed authentication user."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="student_profile")
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    roll_no = models.CharField(max_length=10, unique=True)

    def __str__(self):
        return f"{self.name} ({self.roll_no})"


class Seat(models.Model):
    class Floor(models.TextChoices):
        GROUND = "ground", "Ground Floor"
        FIRST = "first", "First Floor"
        SECOND = "second", "Second Floor"
        THIRD = "third", "Third Floor"
        FOURTH = "fourth", "Fourth Floor"

    floor = models.CharField(max_length=10, choices=Floor.choices)
    number = models.PositiveSmallIntegerField()
    class Meta:
        ordering = ["floor", "number"]
        constraints = [models.UniqueConstraint(fields=["floor", "number"], name="unique_seat_per_floor")]

    def __str__(self):
        return f"{self.get_floor_display()} · {self.number}"

    @property
    def active_reservation(self):
        return self.reservations.filter(status__in=Reservation.ACTIVE_STATUSES).first()

    @property
    def live_status(self):
        reservation = self.active_reservation
        if not reservation:
            return "available"
        return "occupied" if reservation.checked_in_at and reservation.status == Reservation.Status.ACTIVE else "reserved"


class Reservation(models.Model):
    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        ACTIVE = "active", "Checked in"
        BREAK = "break", "On break"
        AWAY = "away", "Location return pending"
        COMPLETED = "completed", "Completed"
        EXPIRED = "expired", "Expired"
        RELEASED = "released", "Released"

    ACTIVE_STATUSES = (Status.RESERVED, Status.ACTIVE, Status.BREAK, Status.AWAY)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="reservations")
    seat = models.ForeignKey(Seat, on_delete=models.PROTECT, related_name="reservations")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RESERVED)
    created_at = models.DateTimeField(default=timezone.now)
    duration_minutes = models.PositiveSmallIntegerField(default=120)
    checkin_deadline = models.DateTimeField()
    study_started_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    qr_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    qr_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["student"], condition=Q(status__in=["reserved", "active", "break", "away"]), name="one_active_reservation_per_student"),
            models.UniqueConstraint(fields=["seat"], condition=Q(status__in=["reserved", "active", "break", "away"]), name="one_active_reservation_per_seat"),
            models.CheckConstraint(condition=Q(ends_at__isnull=True) | Q(ends_at__gt=models.F("created_at")), name="reservation_end_after_creation"),
        ]

    @property
    def is_active(self):
        return self.status in self.ACTIVE_STATUSES and (self.ends_at is None or self.ends_at > timezone.now())

    def __str__(self):
        return f"{self.student} — {self.seat} ({self.get_status_display()})"


class Attendance(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name="attendance_records")
    checked_in_at = models.DateTimeField(default=timezone.now)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    method = models.CharField(max_length=20, default="qr")


class BreakRecord(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name="breaks")
    started_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    returned_at = models.DateTimeField(null=True, blank=True)


class Notification(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=240)
    kind = models.CharField(max_length=32, default="info")
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ["-created_at"]


class LocationEvent(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name="location_events")
    latitude = models.FloatField()
    longitude = models.FloatField()
    distance_m = models.FloatField()
    recorded_at = models.DateTimeField(default=timezone.now)
    returned_at = models.DateTimeField(null=True, blank=True)


class ReservationPolicy(models.Model):
    minimum_minutes = models.PositiveSmallIntegerField(default=30, validators=[MinValueValidator(1)])
    maximum_minutes = models.PositiveSmallIntegerField(default=480, validators=[MinValueValidator(1)])
    default_minutes = models.PositiveSmallIntegerField(default=120, validators=[MinValueValidator(1)])
    increment_minutes = models.PositiveSmallIntegerField(default=30, validators=[MinValueValidator(1)])
    checkin_grace_minutes = models.PositiveSmallIntegerField(default=30)
    break_max_minutes = models.PositiveSmallIntegerField(default=30, validators=[MaxValueValidator(30)])
    return_countdown_minutes = models.PositiveSmallIntegerField(default=5)
    library_latitude = models.FloatField(default=30.3560)
    library_longitude = models.FloatField(default=76.3647)
    permitted_radius_m = models.PositiveSmallIntegerField(default=150)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.minimum_minutes > self.maximum_minutes:
            raise ValidationError("Minimum duration must not exceed maximum duration.")
        if not self.minimum_minutes <= self.default_minutes <= self.maximum_minutes:
            raise ValidationError("Suggested duration must be within the allowed range.")
        if self.increment_minutes and (self.default_minutes - self.minimum_minutes) % self.increment_minutes:
            raise ValidationError("Suggested duration must follow the configured duration increments.")

    def accepts_duration(self, minutes):
        return (self.minimum_minutes <= minutes <= self.maximum_minutes and
                (minutes - self.minimum_minutes) % self.increment_minutes == 0)

    @classmethod
    def current(cls):
        policy, _ = cls.objects.get_or_create(pk=1)
        return policy

    def __str__(self):
        return "Library reservation policy"
