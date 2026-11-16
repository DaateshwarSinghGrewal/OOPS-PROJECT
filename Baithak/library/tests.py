from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Attendance, BreakRecord, LocationEvent, Reservation, ReservationPolicy, Seat, Student
from .services import (AttendanceManager, BaithakError, BreakManager,
                       LocationMonitor, ReservationManager, SeatManager,
                       SeatUnavailable)


@override_settings(ALLOWED_HOSTS=["testserver"])
class BaithakBusinessRuleTests(TestCase):
    def setUp(self):
        ReservationPolicy.objects.create(pk=1, minimum_minutes=30, maximum_minutes=240, default_minutes=120, increment_minutes=30, checkin_grace_minutes=30)
        User = get_user_model()
        user = User.objects.create_user(username="student@thapar.edu", email="student@thapar.edu", password="test-password-123")
        self.student = Student.objects.create(user=user, name="Test Student", email=user.email, roll_no="1234567890")
        self.seat = Seat.objects.create(floor=Seat.Floor.GROUND, number=1)

    def reserve(self, student=None, seat=None, minutes=60):
        return ReservationManager().reserve(student or self.student, (seat or self.seat).pk, minutes)

    def test_seed_creates_exactly_450_seats_idempotently(self):
        Seat.objects.all().delete()
        manager = SeatManager()
        self.assertEqual(manager.seed(), 450)
        self.assertEqual(manager.seed(), 0)
        self.assertEqual(Seat.objects.count(), 450)

    def test_student_and_seat_cannot_have_two_active_reservations(self):
        self.reserve()
        second_student_user = get_user_model().objects.create_user(username="other@thapar.edu", password="test-password-123")
        second = Student.objects.create(user=second_student_user, name="Other", email="other@thapar.edu", roll_no="1234567891")
        with self.assertRaises(SeatUnavailable):
            self.reserve(student=second)
        other_seat = Seat.objects.create(floor=Seat.Floor.GROUND, number=2)
        with self.assertRaises(BaithakError):
            self.reserve(seat=other_seat)

    def test_duration_must_follow_policy_increments(self):
        with self.assertRaises(BaithakError):
            self.reserve(minutes=45)

    def test_checkin_is_server_validated_and_qr_cannot_be_replayed(self):
        reservation = self.reserve()
        self.assertIsNone(reservation.study_started_at)
        self.assertIsNone(reservation.ends_at)
        checked = AttendanceManager().check_in(self.student, reservation.qr_token)
        self.assertEqual(checked.status, Reservation.Status.ACTIVE)
        self.assertEqual(checked.study_started_at, checked.checked_in_at)
        self.assertEqual(checked.ends_at, checked.checked_in_at + timedelta(minutes=60))
        self.assertEqual(Attendance.objects.filter(reservation=reservation).count(), 1)
        with self.assertRaises(BaithakError):
            AttendanceManager().check_in(self.student, reservation.qr_token)

    def test_checkin_rejects_another_students_token(self):
        reservation = self.reserve()
        second_user = get_user_model().objects.create_user(username="other@thapar.edu", password="test-password-123")
        second = Student.objects.create(user=second_user, name="Other", email=second_user.email, roll_no="1234567891")
        with self.assertRaises(BaithakError):
            AttendanceManager().check_in(second, reservation.qr_token)

    def test_expiry_uses_server_clock_and_releases_seat(self):
        reservation = self.reserve()
        now = timezone.now()
        Reservation.objects.filter(pk=reservation.pk).update(created_at=now - timedelta(hours=2), ends_at=now - timedelta(seconds=1))
        ReservationManager().expire_due()
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)
        self.assertIsNone(Seat.objects.get(pk=self.seat.pk).active_reservation)

    def test_unchecked_reservation_releases_at_checkin_deadline(self):
        reservation = self.reserve()
        Reservation.objects.filter(pk=reservation.pk).update(checkin_deadline=timezone.now() - timedelta(seconds=1))
        ReservationManager().expire_due()
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)

    def test_renewal_extends_an_active_reservation(self):
        reservation = self.reserve()
        AttendanceManager().check_in(self.student, reservation.qr_token)
        reservation.refresh_from_db()
        old_end = reservation.ends_at
        renewed = ReservationManager().renew(self.student, 30)
        self.assertEqual(renewed.pk, reservation.pk)
        self.assertEqual(renewed.ends_at, old_end + timedelta(minutes=30))

    def test_break_return_restores_occupied_status_and_expiry_releases(self):
        reservation = self.reserve()
        AttendanceManager().check_in(self.student, reservation.qr_token)
        pause = BreakManager().start(self.student, 20)
        self.assertEqual(Reservation.objects.get(pk=reservation.pk).status, Reservation.Status.BREAK)
        BreakManager().return_from_break(self.student)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.ACTIVE)
        self.assertIsNotNone(BreakRecord.objects.get(pk=pause.pk).returned_at)
        pause = BreakRecord.objects.create(reservation=reservation, expires_at=timezone.now() - timedelta(seconds=1))
        reservation.status = Reservation.Status.BREAK
        reservation.save(update_fields=["status"])
        ReservationManager().expire_due()
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.RELEASED)

    def test_location_monitor_uses_configured_radius_and_return(self):
        reservation = self.reserve()
        AttendanceManager().check_in(self.student, reservation.qr_token)
        policy = ReservationPolicy.current()
        near = (policy.library_latitude, policy.library_longitude)
        far = (policy.library_latitude, policy.library_longitude + 0.02)
        outside = LocationMonitor().report(self.student, *far)
        self.assertEqual(outside["status"], Reservation.Status.AWAY)
        back = LocationMonitor().report(self.student, *near)
        self.assertEqual(back["status"], Reservation.Status.ACTIVE)
        LocationMonitor().report(self.student, *far)
        LocationEvent.objects.filter(reservation=reservation, returned_at__isnull=True).update(recorded_at=timezone.now() - timedelta(minutes=6))
        ReservationManager().expire_due()
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.RELEASED)

    def test_registration_and_login_use_django_authentication(self):
        response = self.client.post("/register/", {"name": "New Student", "email": "new@thapar.edu", "rollno": "9876543210", "password": "secure-password-1"})
        self.assertRedirects(response, "/index/")
        self.assertTrue(get_user_model().objects.get(username="new@thapar.edu").check_password("secure-password-1"))
        self.client.post("/logout/")
        response = self.client.post("/login/", {"email": "new@thapar.edu", "password": "secure-password-1"})
        self.assertRedirects(response, "/index/")

    def test_seat_page_and_booking_are_database_backed(self):
        self.client.force_login(self.student.user)
        SeatManager().seed()
        response = self.client.get("/book_seat/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ground Floor")
        self.assertContains(response, "Fourth Floor")
        response = self.client.post("/book_seat/", {"seat_id": self.seat.pk, "duration": 60})
        self.assertRedirects(response, "/index/")
        self.assertTrue(Reservation.objects.filter(student=self.student, seat=self.seat, status=Reservation.Status.RESERVED).exists())

    def test_checkin_page_renders_server_generated_qr(self):
        self.client.force_login(self.student.user)
        self.reserve()
        response = self.client.get("/checkin/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Single-use check-in QR code")

    def test_staff_scans_qr_and_server_records_student_attendance(self):
        reservation = self.reserve()
        staff = get_user_model().objects.create_user(username="librarian", password="staff-password-123", is_staff=True)
        self.client.force_login(staff)
        response = self.client.post("/checkin/scan/", {"token": str(reservation.qr_token)})
        self.assertEqual(response.status_code, 200)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.ACTIVE)
        self.assertTrue(Attendance.objects.filter(reservation=reservation).exists())
