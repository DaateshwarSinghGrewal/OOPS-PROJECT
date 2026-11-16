from django.contrib import admin

# Register your models here.
from .models import (Attendance, BreakRecord, LocationEvent, Notification,
                     Reservation, ReservationPolicy, Seat, Student)

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "roll_no")
    search_fields = ("name", "email", "roll_no")

@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ("floor", "number")
    list_filter = ("floor",)

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("student", "seat", "status", "created_at", "checkin_deadline", "ends_at")
    list_filter = ("status", "seat__floor")
    search_fields = ("student__email", "student__roll_no")
    readonly_fields = ("qr_token", "qr_used_at")

for model in (Attendance, BreakRecord, LocationEvent, Notification):
    admin.site.register(model)

@admin.register(ReservationPolicy)
class ReservationPolicyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not ReservationPolicy.objects.exists()
