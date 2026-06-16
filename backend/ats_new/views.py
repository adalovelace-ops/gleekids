import calendar
import logging
from datetime import time
import mimetypes
from pathlib import Path

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.core.mail import BadHeaderError, send_mail
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render, redirect
from django.conf import settings
from django.utils.dateparse import parse_time
from django.utils import timezone
from django.utils._os import safe_join
from django.views.decorators.csrf import csrf_exempt
from .forms import ApplicantRegistrationForm
from .models import Applicant, Schedule, StatusHistory

logger = logging.getLogger(__name__)


def uploaded_media(request, path):
    media_roots = [
        settings.MEDIA_ROOT,
        settings.BASE_DIR,
        settings.BASE_DIR.parent / 'frontend',
    ]

    for root in media_roots:
        try:
            candidate = Path(safe_join(root, path))
        except ValueError:
            raise Http404('File not found.')

        if candidate.is_file():
            content_type, _ = mimetypes.guess_type(candidate)
            return FileResponse(
                candidate.open('rb'),
                content_type=content_type or 'application/octet-stream',
            )

    raise Http404('File not found.')


@login_required
@user_passes_test(lambda u: u.is_staff)
def send_applicant_email(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)

    recipient = (request.POST.get('to') or request.POST.get('recipient') or '').strip()
    subject = (request.POST.get('subject') or '').strip()
    message = (request.POST.get('message') or '').strip()

    if not recipient or not subject or not message:
        return JsonResponse({'ok': False, 'error': 'Recipient, subject, and message are required.'}, status=400)

    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        return JsonResponse({'ok': False, 'error': 'Email account is not configured in .env.'}, status=500)

    try:
        sent_count = send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
    except BadHeaderError:
        return JsonResponse({'ok': False, 'error': 'Invalid email subject or message header.'}, status=400)
    except Exception as exc:
        logger.exception('Failed to send applicant email to %s', recipient)
        return JsonResponse({'ok': False, 'error': f'Email provider error: {exc}'}, status=502)

    if not sent_count:
        return JsonResponse({'ok': False, 'error': 'Email provider did not accept the message.'}, status=502)

    return JsonResponse({'ok': True})

def home_page(request):
    return render(request, 'hero.html')


def teacher_stories(request):
    return render(request, 'teacher_stories.html')


def applicant_registration(request):
    if request.method == 'POST':
        form = ApplicantRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return render(request, 'applicant_form.html', {'success': True})
        else:
            return render(request, 'applicant_form.html', {'form_errors': form.errors})
    
    return render(request, 'applicant_form.html')


def sample_intro_videos(request):
    return render(request, 'sample_intro_videos.html')


def applicant_login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        try:
            applicant = Applicant.objects.get(email=email, password=password)
            
            if applicant.status == 'Pending':
                return render(request, 'applicant_login.html', {'error': 'Your application is still pending approval. Please check back later.'})
                
            request.session['applicant_id'] = str(applicant.applicant_id)
            return redirect('applicant_portal')
        except Applicant.DoesNotExist:
            return render(request, 'applicant_login.html', {'error': 'Invalid email or password'})
    
    return render(request, 'applicant_login.html')

def applicant_portal(request):
    applicant_id = request.session.get('applicant_id')
    if not applicant_id:
        return redirect('applicant_login')
    
    applicant = Applicant.objects.get(applicant_id=applicant_id)
    preferred_time_saved = False
    preferred_time_error = ''
    document_upload_saved = ''
    document_upload_error = ''

    if request.method == 'POST' and request.POST.get('action') == 'update_preferred_demo_time':
        selected_time = parse_time(request.POST.get('preferred_demo_time') or '')
        if selected_time and time(8, 0) <= selected_time <= time(17, 0):
            applicant.preferred_demo_time = selected_time
            applicant.save(update_fields=['preferred_demo_time', 'updated_at'])
            preferred_time_saved = True
        else:
            preferred_time_error = 'Please select a time between 8:00 AM and 5:00 PM.'
    elif request.method == 'POST' and request.POST.get('action') == 'upload_document':
        upload_fields = {
            'resume': 'Resume/CV',
            'tefl_certificate': 'Certificate / TEFL',
            'video': 'Video Introduction',
            'video_2': 'Second Video',
        }
        field_name = request.POST.get('document_field')
        uploaded_file = request.FILES.get('document_file')

        if field_name not in upload_fields:
            document_upload_error = 'Please choose a valid document type.'
        elif not uploaded_file:
            document_upload_error = 'Please choose a file to upload.'
        else:
            setattr(applicant, field_name, uploaded_file)
            applicant.save(update_fields=[field_name, 'updated_at'])
            document_upload_saved = upload_fields[field_name]

    latest_evaluation = applicant.evaluations.filter(evaluation_type='demo').order_by('-created_at').first()
    latest_client_evaluation = applicant.evaluations.filter(evaluation_type='client').order_by('-created_at').first()
    latest_schedule = applicant.schedules.all().order_by('-scheduled_at').first()
    meeting_room_id = applicant.applicant_id
    applicant_room_url = zoom_clone_room_url(
        meeting_room_id,
        'applicant',
        'client' if applicant.status == 'Endorsement' else 'demo'
    )
    current_percent, current_stage_index = applicant.get_progress()
            
    context = {
        'app': applicant,
        'stages': applicant.get_progress_stages(),
        'current_percent': current_percent,
        'current_stage_index': current_stage_index,
        'next_step_text': applicant.get_next_step_text(),
        'latest_schedule': latest_schedule,
        'history': applicant.history.all().order_by('-created_at'),
        'demoEval': latest_evaluation,
        'demoScore': f"{latest_evaluation.total_score}/25" if latest_evaluation else None,
        'demoUpdated': latest_evaluation.created_at.strftime('%B %d, %Y') if latest_evaluation else None,
        'demoSummary': latest_evaluation.comments if latest_evaluation else None,
        'clientEval': latest_client_evaluation,
        'clientScore': latest_client_evaluation.client_decision if latest_client_evaluation else None,
        'clientUpdated': latest_client_evaluation.created_at.strftime('%B %d, %Y') if latest_client_evaluation else None,
        'clientSummary': latest_client_evaluation.comments if latest_client_evaluation else None,
        'zoomCloneUrl': zoom_clone_base_url(),
        'zoomCloneRoomUrl': applicant_room_url,
        'preferred_time_saved': preferred_time_saved,
        'preferred_time_error': preferred_time_error,
        'document_upload_saved': document_upload_saved,
        'document_upload_error': document_upload_error,
        'hasCertDoc': 'fa-check-circle' if applicant.tefl_certificate else 'fa-times-circle',
        'hasResumeDoc': 'fa-check-circle' if applicant.resume else 'fa-times-circle',
    }
    return render(request, 'applicant_portal.html', context)

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test

SCHEDULE_COLORS = {
    'initial': '#f59e0b',
    'demo': '#ee5f88',
    'training': '#3b82f6',
    'onboarding': '#10b981',
    'endorsement': '#8b5cf6',
}

def zoom_clone_base_url():
    return getattr(settings, 'ZOOM_CLONE_URL', 'http://127.0.0.1:3000/')


def zoom_clone_room_url(room_id, role='applicant', evaluation_type='demo'):
    safe_role = 'admin' if role == 'admin' else 'applicant'
    safe_evaluation_type = 'client' if evaluation_type == 'client' else 'demo'
    return f"{zoom_clone_base_url().rstrip('/')}/{room_id}?role={safe_role}&evaluationType={safe_evaluation_type}"


def assign_applicant_room_urls(applicant):
    applicant.demo_room_url = zoom_clone_room_url(applicant.applicant_id, 'admin', 'demo')
    applicant.client_room_url = zoom_clone_room_url(applicant.applicant_id, 'admin', 'client')
    applicant.applicant_demo_room_url = zoom_clone_room_url(applicant.applicant_id, 'applicant', 'demo')
    applicant.applicant_client_room_url = zoom_clone_room_url(applicant.applicant_id, 'applicant', 'client')
    return applicant


def mini_calendar_context():
    today = timezone.localdate()
    month_start = today.replace(day=1)
    _, days_in_month = calendar.monthrange(today.year, today.month)
    month_end = today.replace(day=days_in_month)

    month_schedules = Schedule.objects.filter(
        scheduled_at__date__gte=month_start,
        scheduled_at__date__lte=month_end,
    ).select_related('applicant')
    event_dates = {timezone.localtime(schedule.scheduled_at).date() for schedule in month_schedules}

    weeks = []
    for week in calendar.Calendar(firstweekday=6).monthdatescalendar(today.year, today.month):
        weeks.append([
            {
                'date': day,
                'number': day.day,
                'in_month': day.month == today.month,
                'is_today': day == today,
                'has_events': day in event_dates,
            }
            for day in week
        ])

    upcoming_schedules = Schedule.objects.filter(
        scheduled_at__gte=timezone.now()
    ).select_related('applicant').order_by('scheduled_at')[:4]
    upcoming_events = [
        {
            'time': timezone.localtime(schedule.scheduled_at).strftime('%I:%M %p').lstrip('0'),
            'title': schedule.title or schedule.get_type_display(),
            'subtitle': schedule.applicant.full_name if schedule.applicant_id else schedule.get_type_display(),
            'color': SCHEDULE_COLORS.get(schedule.type, '#6b7280'),
        }
        for schedule in upcoming_schedules
    ]

    return {
        'mini_calendar': {
            'month_label': today.strftime('%B %Y'),
            'weeks': weeks,
            'upcoming_events': upcoming_events,
            'more_events_count': max(Schedule.objects.filter(scheduled_at__gte=timezone.now()).count() - len(upcoming_events), 0),
        }
    }

def dashboard_panel_context(stats):
    total_applicants = Applicant.objects.count()
    pipeline_items = [
        {
            'label': stat['card_label'],
            'total': stat['total'],
            'percent': round((stat['total'] / total_applicants) * 100) if total_applicants else 0,
            'key': stat['key'],
        }
        for stat in stats
    ]

    referral_counts = {}
    for applicant in Applicant.objects.only('referral', 'status'):
        label = (applicant.referral or '').strip() or 'No referral'
        if label not in referral_counts:
            referral_counts[label] = {'label': label, 'total': 0, 'approved': 0}
        referral_counts[label]['total'] += 1
        if applicant.status == 'Approved':
            referral_counts[label]['approved'] += 1

    referral_items = [
        item
        for item in sorted(referral_counts.values(), key=lambda item: (-item['total'], item['label'].lower()))[:3]
    ]
    application_tables = [
        {
            'key': 'WFH',
            'label': 'WFH',
            'subtitle': 'Work from home applicants',
            'icon': 'fa-home',
            'total': Applicant.objects.filter(work_setup='WFH').count(),
            'applicants': Applicant.objects.filter(work_setup='WFH').order_by('-created_at')[:5],
        },
        {
            'key': 'Office Based',
            'label': 'Office Based',
            'subtitle': 'Applicants available for onsite work',
            'icon': 'fa-building',
            'total': Applicant.objects.filter(work_setup='Office Based').count(),
            'applicants': Applicant.objects.filter(work_setup='Office Based').order_by('-created_at')[:5],
        },
    ]

    return {
        'pipeline_items': pipeline_items,
        'referral_items': referral_items,
        'referral_total': sum(item['total'] for item in referral_counts.values()),
        'application_tables': application_tables,
    }

def applicant_admin_context(status_filter=None):
    pipeline_statuses = [
        {'key': 'Pending', 'label': 'Pending'},
        {'key': 'Initial Screening', 'label': 'Screening'},
        {'key': 'Demo Evaluation', 'label': 'Demo'},
        {'key': 'Endorsement', 'label': 'Endorsement'},
        {'key': 'Training', 'label': 'Training'},
        {'key': 'Approved', 'label': 'Approved'},
    ]
    stats = [
        {'s': 'Initial Screening', 'card_label': 'Screening', 'total': Applicant.objects.filter(status='Initial Screening').count(), 'key': 'Initial Screening'},
        {'s': 'Demo Evaluation', 'card_label': 'Demo', 'total': Applicant.objects.filter(status='Demo Evaluation').count(), 'key': 'Demo Evaluation'},
        {'s': 'Client Endorsement', 'card_label': 'Endorsements', 'total': Applicant.objects.filter(status='Endorsement').count(), 'key': 'Endorsement'},
        {'s': 'Training', 'card_label': 'Training', 'total': Applicant.objects.filter(status='Training').count(), 'key': 'Training'},
        {'s': 'Approved', 'card_label': 'Approved', 'total': Applicant.objects.filter(status='Approved').count(), 'key': 'Approved'},
    ]
    applicants = Applicant.objects.all().order_by('-created_at')
    if status_filter:
        applicants = applicants.filter(status=status_filter)

    pipeline_columns = [
        {
            **stage,
            'count': Applicant.objects.filter(status=stage['key']).count(),
            'applicants': Applicant.objects.filter(status=stage['key']).order_by('-updated_at', '-created_at')[:12],
        }
        for stage in pipeline_statuses
    ]

    context = {
        'applicants': applicants,
        'stats': stats,
        'pipeline_columns': pipeline_columns,
        'pending_applicants_count': Applicant.objects.filter(status='Pending').count(),
        'all_applicants_count': Applicant.objects.count(),
        'total_applicants': applicants.count(),
        'selected_status': status_filter or '',
        'pdo': True
    }
    context.update(mini_calendar_context())
    context.update(dashboard_panel_context(stats))
    return context

def admin_login(request):
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip()
        password = request.POST.get('password') or ''
        User = get_user_model()
        matched_user = (
            User.objects.filter(username__iexact=email).first()
            or User.objects.filter(email__iexact=email).first()
        )
        username = matched_user.get_username() if matched_user else email
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('admin_dashboard')
        else:
            return render(request, 'login.html', {'error': 'Invalid credentials', 'email': email})
    return render(request, 'login.html')

@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_dashboard(request):
    return render(request, 'dashboard.html', applicant_admin_context())

@login_required
@user_passes_test(lambda u: u.is_staff)
def applicants_page(request):
    return render(request, 'manage_applicants.html', applicant_admin_context(request.GET.get('status')))

from .models import Applicant, Schedule, Evaluation

@login_required
@user_passes_test(lambda u: u.is_staff)
def applicant_details(request, applicant_id):
    applicant = Applicant.objects.get(applicant_id=applicant_id)
    assign_applicant_room_urls(applicant)
    history = applicant.history.all().order_by('-created_at')
    latest_schedule = applicant.schedules.all().order_by('-scheduled_at').first()
    latest_evaluation = applicant.evaluations.filter(evaluation_type='demo').order_by('-created_at').first()
    latest_client_evaluation = applicant.evaluations.filter(evaluation_type='client').order_by('-created_at').first()
    evaluation_items = []
    if latest_evaluation:
        evaluation_items = [
            ('Teaching Performance', latest_evaluation.teaching_performance),
            ('Communication Skills', latest_evaluation.communication_skills),
            ('Curriculum Understanding', latest_evaluation.curriculum_understanding),
            ('Engagement Level', latest_evaluation.engagement_level),
            ('Technical Proficiency', latest_evaluation.technical_proficiency),
        ]
    return render(request, 'applicant.html', {
        'app': applicant,
        'history': history,
        'latest_schedule': latest_schedule,
        'latest_evaluation': latest_evaluation,
        'latest_client_evaluation': latest_client_evaluation,
        'evaluation_items': evaluation_items,
        'zoomCloneUrl': zoom_clone_base_url(),
        'zoomCloneRoomUrl': zoom_clone_room_url(
            applicant.applicant_id,
            'admin',
            'client' if applicant.status == 'Endorsement' else 'demo'
        ),
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def update_status(request):
    if request.method == 'POST':
        applicant_id = request.POST.get('applicant_id')
        applicant = Applicant.objects.get(applicant_id=applicant_id)
        
        # Check if we are updating status or general info
        if 'new_status' in request.POST:
            new_status = request.POST.get('new_status')
            applicant.update_status(new_status, notes=request.POST.get('status_note'))
        else:
            applicant.update_profile_from_post(request.POST)
        redirect_to = request.POST.get('redirect_to')
        if redirect_to:
            return redirect(redirect_to)
        return redirect('applicant_details', applicant_id=applicant_id)
    return redirect('admin_dashboard')

import json
import uuid

@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_calendar(request):
    schedules = Schedule.objects.all().select_related('applicant').order_by('applicant_id', '-scheduled_at', '-created_at')
    events = []
    
    # Colors for different stages
    colors = {
        'initial': '#f59e0b',
        'demo': '#7c3aed',
        'endorsement': '#8b5cf6',
        'training': '#2563eb',
        'onboarding': '#10b981',
    }
    
    visible_schedules = []
    seen_applicants = set()
    for s in schedules:
        if s.applicant_id in seen_applicants:
            continue
        seen_applicants.add(s.applicant_id)
        visible_schedules.append(s)
        events.append({
            'title': f"{s.applicant.first_name} {s.applicant.last_name} - {s.title}",
            'start': s.scheduled_at.isoformat(),
            'color': colors.get(s.type, '#6b7280'),
            'extendedProps': {
                'name': f"{s.applicant.first_name} {s.applicant.last_name}",
                'email': s.applicant.email,
                'phone': s.applicant.phone,
                'meetingLink': s.meeting_link,
                'zoomRoomUrl': zoom_clone_room_url(
                    s.applicant.applicant_id,
                    'admin',
                    'client' if s.type == 'endorsement' else 'demo'
                ),
                'applicantRoomUrl': zoom_clone_room_url(
                    s.applicant.applicant_id,
                    'applicant',
                    'client' if s.type == 'endorsement' else 'demo'
                ),
                'stageLabel': s.get_type_display(),
                'stageKey': s.type,
                'applicantUrl': f"/applicant-details/{s.applicant.applicant_id}/",
                'applicantId': str(s.applicant.applicant_id),
                'scheduleId': str(s.schedule_id)
            }
        })

    stage_counts = {key: 0 for key in colors}
    for schedule in visible_schedules:
        if schedule.type in stage_counts:
            stage_counts[schedule.type] += 1
        
    context = {
        'eventsJson': json.dumps(events),
        'stageMetaJson': json.dumps({
            'initial': {'label': 'Screening', 'color': colors['initial']},
            'demo': {'label': 'Demo', 'color': colors['demo']},
            'endorsement': {'label': 'Endorsement', 'color': colors['endorsement']},
            'training': {'label': 'Training', 'color': colors['training']},
            'onboarding': {'label': 'Onboarding', 'color': colors['onboarding']},
        }),
        'stageCountsJson': json.dumps(stage_counts),
        'zoomCloneUrl': zoom_clone_base_url(),
    }
    return render(request, 'admin_calendar.html', context)

@login_required
@user_passes_test(lambda u: u.is_staff)
def schedule_action(request):
    if request.method == 'POST':
        applicant_id = request.POST.get('applicant_identifier')
        sched_type = request.POST.get('type')
        scheduled_at = request.POST.get('scheduled_at')
        meeting_link = request.POST.get('meeting_link')
        title = request.POST.get('title')
        reschedule_reason = (request.POST.get('reschedule_reason') or '').strip()
        was_unavailable = request.POST.get('applicant_unavailable') == '1'
        
        applicant = Applicant.objects.get(applicant_id=applicant_id)
        existing_schedule = applicant.schedules.filter(type=sched_type).first()
        previous_time = existing_schedule.scheduled_at if existing_schedule else None
        
        # Create or Update schedule
        schedule, _ = Schedule.objects.update_or_create(
            applicant=applicant,
            type=sched_type,
            defaults={
                'title': title,
                'scheduled_at': scheduled_at,
                'meeting_link': meeting_link
            }
        )
        schedule.refresh_from_db()
        old_schedules = applicant.schedules.exclude(schedule_id=schedule.schedule_id)
        removed_schedule_labels = [
            f"{old_schedule.get_type_display()} on {timezone.localtime(old_schedule.scheduled_at).strftime('%B %d, %Y @ %I:%M %p')}"
            for old_schedule in old_schedules
        ]
        if removed_schedule_labels:
            old_schedules.delete()
            StatusHistory.objects.create(
                applicant=applicant,
                status=applicant.status,
                notes=f"Calendar moved to {schedule.get_type_display()}; removed previous schedule(s): {', '.join(removed_schedule_labels)}.",
            )

        schedule.sync_applicant_status(title)
        advance_status = request.POST.get('advance_status')
        if advance_status and advance_status != applicant.status:
            applicant.update_status(
                advance_status,
                notes=f"Moved forward from {applicant.status} to {advance_status} after schedule update.",
            )

        if existing_schedule and previous_time and previous_time != schedule.scheduled_at:
            previous_display = timezone.localtime(previous_time).strftime('%B %d, %Y @ %I:%M %p')
            new_display = timezone.localtime(schedule.scheduled_at).strftime('%B %d, %Y @ %I:%M %p')
            note = f"Rescheduled {schedule.get_type_display()} from {previous_display} to {new_display}."
            if was_unavailable:
                note += " Applicant was not available at the previous time."
            if reschedule_reason:
                note += f" Note: {reschedule_reason}"

            StatusHistory.objects.create(
                applicant=applicant,
                status=applicant.status,
                notes=note,
            )

        # Auto-generate meeting link if none provided
        evaluation_type = 'client' if sched_type == 'endorsement' else 'demo'
        schedule.meeting_link = zoom_clone_room_url(applicant.applicant_id, 'applicant', evaluation_type)
        schedule.save(update_fields=['meeting_link'])
        
        return redirect(request.POST.get('redirect_to', 'admin_dashboard'))
    return redirect('admin_dashboard')

@login_required
@user_passes_test(lambda u: u.is_staff)
def schedule_initial(request):
    stage = request.GET.get('stage', 'initial')
    stage_map = {
        'initial': {
            'label': 'Initial Screening',
            'status': 'Initial Screening',
            'next_status': 'Demo Evaluation',
            'action_label': 'Approve for Demo',
        },
        'demo': {
            'label': 'Demo',
            'status': 'Demo Evaluation',
            'next_status': 'Endorsement',
            'action_label': 'Move to Client',
        },
        'client': {
            'label': 'Client',
            'status': 'Endorsement',
            'next_status': 'Training',
            'action_label': 'Move to Training',
        },
        'training': {
            'label': 'Training',
            'status': 'Training',
            'next_status': 'Approved',
            'action_label': 'Mark Hired',
        },
        'hired': {
            'label': 'Hired',
            'status': 'Approved',
            'next_status': '',
            'action_label': '',
        },
        'resign': {
            'label': 'Resign',
            'status': 'Resign',
            'next_status': '',
            'action_label': '',
        },
        'withdrawn': {
            'label': 'Withdrawn',
            'status': 'Withdrawn',
            'next_status': '',
            'action_label': '',
        },
    }
    current_stage = stage_map.get(stage, stage_map['initial'])
    applicants = Applicant.objects.filter(status=current_stage['status']).order_by('-created_at')
    stage_tabs = [
        {'key': key, **value}
        for key, value in stage_map.items()
    ]
    action_status_options = [
        {'label': 'Initial Screening', 'status': 'Initial Screening'},
        {'label': 'Demo', 'status': 'Demo Evaluation'},
        {'label': 'Client', 'status': 'Endorsement'},
        {'label': 'Training', 'status': 'Training'},
        {'label': 'Hired', 'status': 'Approved'},
        {'label': 'Resign', 'status': 'Resign'},
        {'label': 'Withdrawn', 'status': 'Withdrawn'},
    ]
    return render(request, 'schedule_initial.html', {
        'applicants': applicants,
        'active_stage': stage,
        'current_stage': current_stage,
        'stage_tabs': stage_tabs,
        'action_status_options': action_status_options,
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def demo_evaluation(request):
    applicants = Applicant.objects.filter(status='Demo Evaluation')
    for app in applicants:
        app.current_schedule = app.schedules.filter(type='demo').first()
        assign_applicant_room_urls(app)
    return render(request, 'demo_evaluation.html', {'applicants': applicants})

@login_required
@user_passes_test(lambda u: u.is_staff)
def evaluations(request):
    query = (request.GET.get('q') or '').strip()

    applicants = Applicant.objects.filter(status__in=['Demo Evaluation', 'Endorsement']).order_by('-updated_at')
    if query:
        applicants = applicants.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )

    demo_applicants = []
    client_applicants = []
    total_evaluated = 0

    for applicant in applicants:
        applicant.demo_evaluation = applicant.evaluations.filter(evaluation_type='demo').order_by('-created_at').first()
        applicant.client_evaluation = applicant.evaluations.filter(evaluation_type='client').order_by('-created_at').first()
        if applicant.demo_evaluation or applicant.client_evaluation:
            total_evaluated += 1
        if applicant.status == 'Endorsement':
            client_applicants.append(applicant)
        else:
            demo_applicants.append(applicant)

    context = {
        'demo_applicants': demo_applicants,
        'client_applicants': client_applicants,
        'query': query,
        'total_evaluations': total_evaluated,
        'total_demo': len(demo_applicants),
        'total_client': len(client_applicants),
    }
    return render(request, 'evaluations.html', context)

@login_required
@user_passes_test(lambda u: u.is_staff)
def reports(request):
    applicants = Applicant.objects.prefetch_related('history').order_by('-created_at')
    journey_rows = []
    hired_durations = []
    referral_counts = {}

    for applicant in applicants:
        history = list(applicant.history.all().order_by('created_at'))
        approved_event = next((event for event in history if event.status == 'Approved'), None)
        hired_at = approved_event.created_at if approved_event else None
        time_to_hire_days = None

        if hired_at:
            time_to_hire_days = max((hired_at - applicant.created_at).days, 0)
            hired_durations.append(time_to_hire_days)

        journey_rows.append({
            'applicant': applicant,
            'current_status': applicant.status,
            'journey_events': history,
            'steps_count': len(history) + 1,
            'time_to_hire_days': time_to_hire_days,
            'hired_at': hired_at,
        })

        referral = (applicant.referral or '').strip() or 'No referral'
        if referral not in referral_counts:
            referral_counts[referral] = {'label': referral, 'total': 0, 'hired': 0}
        referral_counts[referral]['total'] += 1
        if applicant.status == 'Approved':
            referral_counts[referral]['hired'] += 1

    referral_rows = sorted(
        referral_counts.values(),
        key=lambda row: (-row['total'], row['label'].lower())
    )
    average_time_to_hire = round(sum(hired_durations) / len(hired_durations), 1) if hired_durations else None

    return render(request, 'reports.html', {
        'journey_rows': journey_rows,
        'referral_rows': referral_rows,
        'total_applicants': applicants.count(),
        'hired_count': len(hired_durations),
        'average_time_to_hire': average_time_to_hire,
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def training_schedule(request):
    applicants = Applicant.objects.filter(status='Training')
    for app in applicants:
        app.current_schedule = app.schedules.filter(type='training').first()
    return render(request, 'training_schedule.html', {'applicants': applicants})

from .models import Applicant, Schedule, Evaluation

@login_required
@user_passes_test(lambda u: u.is_staff)
def client_endorsement(request):
    applicants = Applicant.objects.filter(status='Endorsement')
    for app in applicants:
        app.current_schedule = app.schedules.filter(type='endorsement').first()
        assign_applicant_room_urls(app)
    return render(request, 'client_endorsement.html', {'applicants': applicants})

@login_required
@user_passes_test(lambda u: u.is_staff)
def evaluate_applicant(request, applicant_id):
    applicant = Applicant.objects.get(applicant_id=applicant_id)
    assign_applicant_room_urls(applicant)
    evaluation_type = request.GET.get('type')
    if evaluation_type == 'client' or applicant.status == 'Endorsement':
        existing_eval = Evaluation.objects.filter(applicant=applicant, evaluation_type='client').first()
        return render(request, 'evaluate_client.html', {
            'app': applicant,
            'eval': existing_eval,
        })

    existing_eval = Evaluation.objects.filter(applicant=applicant, evaluation_type='demo').first()
    
    # Criteria for the loop
    criteria = [
        {'key': 'teaching_performance', 'label': 'Teaching Performance', 'desc': 'Clarity, pacing, and subject mastery'},
        {'key': 'communication_skills', 'label': 'Communication Skills', 'desc': 'Verbal and non-verbal delivery'},
        {'key': 'curriculum_understanding', 'label': 'Curriculum Understanding', 'desc': 'Ability to follow lesson materials'},
        {'key': 'engagement_level', 'label': 'Engagement Level', 'desc': 'Ability to keep students interested'},
        {'key': 'technical_proficiency', 'label': 'Technical Proficiency', 'desc': 'Handling of meeting tools/apps'},
    ]
    for item in criteria:
        item['value'] = str(getattr(existing_eval, item['key'], '')) if existing_eval else ''
    
    context = {
        'app': applicant,
        'eval': existing_eval,
        'criteria': criteria,
    }
    return render(request, 'evaluate_applicant.html', context)

@login_required
@user_passes_test(lambda u: u.is_staff)
def save_evaluation(request):
    if request.method == 'POST':
        applicant_id = request.POST.get('applicant_identifier')
        applicant = Applicant.objects.get(applicant_id=applicant_id)

        if request.POST.get('evaluation_type') == 'client':
            decision = request.POST.get('client_decision')
            if decision not in {'Pass', 'Fail'}:
                return redirect('evaluate_applicant', applicant_id=applicant.applicant_id)

            evaluation, _ = Evaluation.objects.update_or_create(
                applicant=applicant,
                evaluation_type='client',
                defaults=Evaluation.client_defaults(decision, request.POST.get('overall_comments'))
            )
            next_status = 'Training' if decision == 'Pass' else 'Withdrawn'
            if applicant.status != next_status:
                applicant.update_status(
                    next_status,
                    notes=f"Client endorsement marked {decision}.",
                )
            return redirect('evaluations')

        Evaluation.objects.update_or_create(
            applicant=applicant,
            evaluation_type='demo',
            defaults=Evaluation.rating_defaults_from_request(request.POST)
        )
        
        return redirect('demo_evaluation')
    return redirect('admin_dashboard')

@csrf_exempt
def save_room_evaluation(request):
    if request.method == 'OPTIONS':
        return JsonResponse({'ok': True})

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    room_id = payload.get('roomId')
    if not room_id:
        return JsonResponse({'ok': False, 'error': 'Missing room id'}, status=400)

    schedule = Schedule.objects.filter(schedule_id=room_id).select_related('applicant').first()
    applicant = schedule.applicant if schedule else Applicant.objects.filter(applicant_id=room_id).first()
    if not applicant:
        applicant_name = (payload.get('applicantName') or '').strip()
        if applicant_name:
            name_parts = applicant_name.split()
            matches = Applicant.objects.all()
            for part in name_parts:
                matches = matches.filter(Q(first_name__icontains=part) | Q(last_name__icontains=part))
            applicant = matches.first()
    if not applicant:
        return JsonResponse({'ok': False, 'error': 'Applicant not found for this room'}, status=404)

    ratings = payload.get('ratings') or {}
    comments = payload.get('comments') or {}
    evaluation_type = payload.get('evaluationType') or payload.get('evaluation_type')

    if evaluation_type == 'client':
        decision = payload.get('clientDecision') or payload.get('client_decision') or payload.get('decision')
        if decision not in {'Pass', 'Fail'}:
            return JsonResponse({'ok': False, 'error': 'Client decision must be Pass or Fail'}, status=400)

        overall_comments = payload.get('overallComments') or payload.get('commentsText') or ''
        eval_obj, _ = Evaluation.objects.update_or_create(
            applicant=applicant,
            evaluation_type='client',
            defaults=Evaluation.client_defaults(decision, overall_comments)
        )
        next_status = 'Training' if decision == 'Pass' else 'Withdrawn'
        if applicant.status != next_status:
            applicant.update_status(
                next_status,
                notes=f"Client endorsement marked {decision} from video conference.",
            )

        return JsonResponse({
            'ok': True,
            'applicantId': str(applicant.applicant_id),
            'evaluationId': str(eval_obj.evaluation_id),
            'clientDecision': eval_obj.client_decision,
            'nextStatus': next_status,
        })

    overall_comments = payload.get('overallComments') or '\n'.join(
        f"{label}: {comment}"
        for label, comment in comments.items()
        if comment
    )

    eval_obj, _ = Evaluation.objects.update_or_create(
        applicant=applicant,
        evaluation_type='demo',
        defaults=Evaluation.rating_defaults_from_room_payload(ratings, overall_comments)
    )

    return JsonResponse({
        'ok': True,
        'applicantId': str(applicant.applicant_id),
        'evaluationId': str(eval_obj.evaluation_id),
        'totalScore': eval_obj.total_score,
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def onboarding(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        applicant_id = request.POST.get('applicant_identifier')
        applicant = Applicant.objects.get(applicant_id=applicant_id)
        
        if action == 'assign_account':
            applicant.assign_teaching_account(
                request.POST.get('account_slug'),
                request.POST.get('notes')
            )
            return redirect('onboarding')
        if action == 'clear_account':
            applicant.clear_teaching_account(request.POST.get('notes'))
            return redirect('onboarding')

    applicants = Applicant.objects.filter(status='Approved')
    for app in applicants:
        app.current_schedule = app.schedules.filter(type='onboarding').first()

    placement_groups = [
        {
            'slug': slug,
            'label': label,
            'applicants': applicants.filter(teaching_account=slug),
        }
        for slug, label in Applicant.ACCOUNT_CHOICES
    ]
    
    context = {
        'applicants': applicants,
        'accounts': Applicant.ACCOUNT_CHOICES,
        'placement_groups': placement_groups,
        'unassigned_count': applicants.filter(teaching_account__isnull=True).count() + applicants.filter(teaching_account='').count(),
    }
    return render(request, 'schedule_onboarding.html', context)

def applicant_logout(request):
    logout(request) # Also logs out django users
    request.session.flush()
    return redirect('home')

def video_call(request, schedule_id):
    schedule = Schedule.objects.filter(schedule_id=schedule_id).first()
    if not schedule:
        return redirect(zoom_clone_room_url(schedule_id, 'applicant'))
    role = 'admin' if request.user.is_authenticated and request.user.is_staff else 'applicant'
    evaluation_type = 'client' if schedule.type == 'endorsement' else 'demo'
    return redirect(zoom_clone_room_url(schedule.applicant.applicant_id, role, evaluation_type))

@login_required
@user_passes_test(lambda u: u.is_staff)
def new_video_room(request):
    return redirect(zoom_clone_room_url(uuid.uuid4(), 'admin'))

def video_landing(request):
    room_id = str(uuid.uuid4())
    role = 'admin' if request.user.is_authenticated and request.user.is_staff else 'applicant'
    zoom_clone_url = zoom_clone_room_url(room_id, role)
    demo_room_applicants = list(Applicant.objects.filter(status='Demo Evaluation').order_by('-updated_at', '-created_at'))
    client_room_applicants = list(Applicant.objects.filter(status='Endorsement').order_by('-updated_at', '-created_at'))
    for applicant in [*demo_room_applicants, *client_room_applicants]:
        assign_applicant_room_urls(applicant)
    context = {
        'room_id': room_id,
        'room_title': 'Video Conference',
        'room_subtitle': 'Live Zoom clone room',
        'user_role': role,
        'zoom_clone_url': zoom_clone_url,
        'demo_room_applicants': demo_room_applicants,
        'client_room_applicants': client_room_applicants,
    }
    context.update(mini_calendar_context())
    return render(request, 'video_landing.html', context)

def video_room(request, room_id):
    is_admin = request.user.is_authenticated and request.user.is_staff
    evaluation_type = request.GET.get('evaluationType') or request.GET.get('type') or 'demo'
    return redirect(zoom_clone_room_url(room_id, 'admin' if is_admin else 'applicant', evaluation_type))
