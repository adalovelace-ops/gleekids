"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, re_path
from ats_new.views import (
    applicant_registration, applicant_login, applicant_portal, 
    home_page, applicant_logout, admin_login, admin_dashboard,
    applicant_details, update_status, schedule_initial,
    demo_evaluation, evaluations, reports, training_schedule, onboarding,
    admin_calendar, schedule_action, client_endorsement,
    evaluate_applicant, save_evaluation, video_call,
    new_video_room, video_room, uploaded_media, save_room_evaluation
)

urlpatterns = [
    path('', home_page, name='home'),
    path('admin/', admin.site.urls),
    path('apply/', applicant_registration, name='applicant_registration'),
    path('login/', applicant_login, name='applicant_login'),
    path('portal/', applicant_portal, name='applicant_portal'),
    path('logout/', applicant_logout, name='applicant_logout'),
    path('admin-login/', admin_login, name='admin_login'),
    path('admin-dashboard/', admin_dashboard, name='admin_dashboard'),
    path('applicant-details/<uuid:applicant_id>/', applicant_details, name='applicant_details'),
    path('update-status/', update_status, name='update_status'),
    path('schedule-initial/', schedule_initial, name='schedule_initial'),
    path('demo-evaluation/', demo_evaluation, name='demo_evaluation'),
    path('evaluations/', evaluations, name='evaluations'),
    path('reports/', reports, name='reports'),
    path('training-schedule/', training_schedule, name='training_schedule'),
    path('onboarding/', onboarding, name='onboarding'),
    path('admin-calendar/', admin_calendar, name='admin_calendar'),
    path('schedule-action/', schedule_action, name='schedule_action'),
    path('client-endorsement/', client_endorsement, name='client_endorsement'),
    path('evaluate/<uuid:applicant_id>/', evaluate_applicant, name='evaluate_applicant'),
    path('save-evaluation/', save_evaluation, name='save_evaluation'),
    path('api/room-evaluation/', save_room_evaluation, name='save_room_evaluation'),
    path('video-call/<uuid:schedule_id>/', video_call, name='video_call'),
    path('video-room/new/', new_video_room, name='new_video_room'),
    path('video-room/<uuid:room_id>/', video_room, name='video_room'),
    re_path(r'^media/(?P<path>.*)$', uploaded_media, name='uploaded_media'),
]
