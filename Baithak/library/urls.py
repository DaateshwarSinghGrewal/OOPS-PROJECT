from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('index/', views.index_view, name='index'),
    path('book_seat/', views.book_seat, name='seat'),
    path('notification/', views.notification, name='notification'),
    path('break/', views.break_status, name='break'),
    path('checkin/', views.checkin, name='checkin'),
    path('checkin/scan/', views.scan_checkin, name='scan_checkin'),
    path('location/report/', views.location_report, name='location_report'),
]
