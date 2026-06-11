import calendar
import mimetypes
from pathlib import Path

from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render, redirect
from django.conf import settings
from django.utils import timezone
from django.utils._os import safe_join
from django.views.decorators.csrf import csrf_exempt
from .forms import ApplicantRegistrationForm
from .models import Applicant, Schedule


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

def home_page(request):
    return render(request, 'hero.html')

def applicant_registration(request):
    if request.method == 'POST':
        form = ApplicantRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return render(request, 'applicant_form.html', {'success': True})
        else:
            return render(request, 'applicant_form.html', {'form_errors': form.errors})
    
    return render(request, 'applicant_form.html')

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
    latest_evaluation = applicant.evaluations.order_by('-created_at').first()
    current_percent, current_stage_index = applicant.get_progress()
            
    context = {
        'app': applicant,
        'stages': applicant.get_progress_stages(),
        'current_percent': current_percent,
        'current_stage_index': current_stage_index,
        'next_step_text': applicant.get_next_step_text(),
        'latest_schedule': applicant.schedules.all().order_by('-scheduled_at').first(),
        'history': applicant.history.all().order_by('-created_at'),
        'demoEval': latest_evaluation,
        'demoScore': f"{latest_evaluation.total_score}/25" if latest_evaluation else None,
        'demoUpdated': latest_evaluation.created_at.strftime('%B %d, %Y') if latest_evaluation else None,
        'zoomCloneUrl': zoom_clone_base_url(),
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

    return {
        'pipeline_items': pipeline_items,
        'referral_items': referral_items,
        'referral_total': sum(item['total'] for item in referral_counts.values()),
    }

def applicant_admin_context(status_filter=None):
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

    context = {
        'applicants': applicants,
        'stats': stats,
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
    history = applicant.history.all().order_by('-created_at')
    latest_schedule = applicant.schedules.all().order_by('-scheduled_at').first()
    latest_evaluation = applicant.evaluations.order_by('-created_at').first()
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
        'evaluation_items': evaluation_items,
        'zoomCloneUrl': zoom_clone_base_url(),
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
            applicant.update_status(new_status)
        else:
            applicant.update_profile_from_post(request.POST)
        return redirect('applicant_details', applicant_id=applicant_id)
    return redirect('admin_dashboard')

import json
import uuid

@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_calendar(request):
    schedules = Schedule.objects.all().select_related('applicant')
    events = []
    
    # Colors for different stages
    colors = {
        'initial': '#f59e0b',
        'demo': '#7c3aed',
        'training': '#2563eb',
        'onboarding': '#10b981',
    }
    
    for s in schedules:
        events.append({
            'title': f"{s.applicant.first_name} {s.applicant.last_name} - {s.title}",
            'start': s.scheduled_at.isoformat(),
            'color': colors.get(s.type, '#6b7280'),
            'extendedProps': {
                'name': f"{s.applicant.first_name} {s.applicant.last_name}",
                'email': s.applicant.email,
                'phone': s.applicant.phone,
                'meetingLink': s.meeting_link,
                'stageLabel': s.get_type_display(),
                'stageKey': s.type,
                'applicantUrl': f"/applicant-details/{s.applicant.applicant_id}/",
                'applicantId': str(s.applicant.applicant_id),
                'scheduleId': str(s.schedule_id)
            }
        })
        
    context = {
        'eventsJson': json.dumps(events),
        'stageMetaJson': json.dumps({
            'initial': {'label': 'Screening', 'color': colors['initial']},
            'demo': {'label': 'Demo', 'color': colors['demo']},
            'training': {'label': 'Training', 'color': colors['training']},
            'onboarding': {'label': 'Onboarding', 'color': colors['onboarding']},
        }),
        'stageCountsJson': json.dumps({
            'initial': schedules.filter(type='initial').count(),
            'demo': schedules.filter(type='demo').count(),
        }),
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
        
        applicant = Applicant.objects.get(applicant_id=applicant_id)
        
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
        schedule.sync_applicant_status(title)

        # Auto-generate meeting link if none provided
        if not schedule.meeting_link:
            schedule.meeting_link = request.build_absolute_uri(
                f'/video-call/{schedule.schedule_id}/'
            )
            schedule.save(update_fields=['meeting_link'])
        
        return redirect(request.POST.get('redirect_to', 'admin_dashboard'))
    return redirect('admin_dashboard')

@login_required
@user_passes_test(lambda u: u.is_staff)
def schedule_initial(request):
    applicants = Applicant.objects.filter(status='Initial Screening')
    # Pre-fetch schedules for these applicants
    for app in applicants:
        app.current_schedule = app.schedules.filter(type='initial').first()
    return render(request, 'schedule_initial.html', {'applicants': applicants})

@login_required
@user_passes_test(lambda u: u.is_staff)
def demo_evaluation(request):
    applicants = Applicant.objects.filter(status='Demo Evaluation')
    for app in applicants:
        app.current_schedule = app.schedules.filter(type='demo').first()
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
        applicant.latest_evaluation = applicant.evaluations.order_by('-created_at').first()
        if applicant.latest_evaluation:
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
    return render(request, 'client_endorsement.html', {'applicants': applicants})

@login_required
@user_passes_test(lambda u: u.is_staff)
def evaluate_applicant(request, applicant_id):
    applicant = Applicant.objects.get(applicant_id=applicant_id)
    existing_eval = Evaluation.objects.filter(applicant=applicant).first()
    
    # Criteria for the loop
    criteria = [
        {'key': 'teaching_performance', 'label': 'Teaching Performance', 'desc': 'Clarity, pacing, and subject mastery'},
        {'key': 'communication_skills', 'label': 'Communication Skills', 'desc': 'Verbal and non-verbal delivery'},
        {'key': 'curriculum_understanding', 'label': 'Curriculum Understanding', 'desc': 'Ability to follow lesson materials'},
        {'key': 'engagement_level', 'label': 'Engagement Level', 'desc': 'Ability to keep students interested'},
        {'key': 'technical_proficiency', 'label': 'Technical Proficiency', 'desc': 'Handling of meeting tools/apps'},
    ]
    
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
        
        Evaluation.objects.update_or_create(
            applicant=applicant,
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

    overall_comments = payload.get('overallComments') or '\n'.join(
        f"{label}: {comment}"
        for label, comment in comments.items()
        if comment
    )

    eval_obj, _ = Evaluation.objects.update_or_create(
        applicant=applicant,
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

    applicants = Applicant.objects.filter(status='Approved')
    for app in applicants:
        app.current_schedule = app.schedules.filter(type='onboarding').first()
    
    context = {
        'applicants': applicants,
        'accounts': Applicant.ACCOUNT_CHOICES
    }
    return render(request, 'schedule_onboarding.html', context)

def applicant_logout(request):
    logout(request) # Also logs out django users
    request.session.flush()
    return redirect('home')

def video_call(request, schedule_id):
    schedule = Schedule.objects.filter(schedule_id=schedule_id).first()
    if not schedule:
        return render(request, 'video_call.html', {'error': 'Meeting not found.'})
    context = {
        'schedule': schedule,
        'room_id': str(schedule_id),
        'room_title': schedule.title,
        'room_subtitle': schedule.scheduled_at.strftime('%B %d, %Y @ %I:%M %p'),
        'user_role': 'admin' if request.user.is_authenticated and request.user.is_staff else 'applicant',
    }
    context.update(mini_calendar_context())
    return render(request, 'video_call.html', context)

@login_required
@user_passes_test(lambda u: u.is_staff)
def new_video_room(request):
    return redirect('video_room', room_id=uuid.uuid4())

def video_landing(request):
    room_id = str(uuid.uuid4())
    role = 'admin' if request.user.is_authenticated and request.user.is_staff else 'applicant'
    zoom_clone_url = f'{zoom_clone_base_url().rstrip("/")}/{room_id}?role={role}'
    context = {
        'room_id': room_id,
        'room_title': 'Video Conference',
        'room_subtitle': 'Live Zoom clone room',
        'user_role': role,
        'zoom_clone_url': zoom_clone_url,
    }
    context.update(mini_calendar_context())
    return render(request, 'video_landing.html', context)

def video_room(request, room_id):
    is_admin = request.user.is_authenticated and request.user.is_staff
    context = {
        'room_id': str(room_id),
        'room_title': 'Admin Video Conference',
        'room_subtitle': 'Live Zoom-style room',
        'user_role': 'admin' if is_admin else 'applicant',
    }
    context.update(mini_calendar_context())
    return render(request, 'video_call.html', context)
