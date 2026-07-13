import calendar
import json
import logging
import secrets
from datetime import time
import mimetypes
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.validators import validate_email
from django.core.mail import BadHeaderError, send_mail
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.conf import settings
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.dateparse import parse_datetime, parse_time
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils._os import safe_join
from .forms import ApplicantRegistrationForm
from .models import Applicant, Evaluation, Schedule, StatusHistory, Placement
from .validators import validate_applicant_upload

logger = logging.getLogger(__name__)

ZOOM_UPCOMING_URL = 'https://us05web.zoom.us/signin#/upcoming'


def staff_permission_required(perm):
    def decorator(view_func):
        @login_required
        @user_passes_test(lambda u: u.is_staff)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.has_perm(perm):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def ensure_staff_permissions(user):
    if user.is_staff and not user.is_superuser:
        from django.contrib.auth.models import Group, Permission
        group, created = Group.objects.get_or_create(name='Recruiters')
        if created:
            codenames = [
                'view_applicant', 'change_applicant',
                'add_schedule', 'view_schedule', 'change_schedule',
                'add_evaluation', 'view_evaluation', 'change_evaluation',
                'view_placement', 'add_placement', 'change_placement', 'delete_placement',
                'view_statushistory', 'view_logentry'
            ]
            perms = Permission.objects.filter(codename__in=codenames)
            group.permissions.set(perms)
        if not user.groups.filter(id=group.id).exists():
            user.groups.add(group)


def safe_post_redirect(request, fallback_view, *fallback_args, **fallback_kwargs):
    redirect_to = (request.POST.get('redirect_to') or '').strip()
    if redirect_to and url_has_allowed_host_and_scheme(
        redirect_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(redirect_to)
    return redirect(fallback_view, *fallback_args, **fallback_kwargs)


def can_access_uploaded_applicant_file(request, path):
    if request.user.is_authenticated and request.user.is_staff and request.user.has_perm('ats_new.view_applicant'):
        return True

    applicant_id = request.session.get('applicant_id')
    if not applicant_id:
        return False

    return Applicant.objects.filter(applicant_id=applicant_id).filter(
        Q(resume=path) |
        Q(video=path) |
        Q(video_2=path) |
        Q(tefl_certificate=path)
    ).exists()


def uploaded_media(request, path):
    path_parts = Path(path).parts
    if not path_parts or any(part.startswith('.') for part in path_parts):
        raise Http404('File not found.')

    allowed_upload_dirs = {'resumes', 'videos', 'certificates'}
    public_asset_extensions = {
        '.apng', '.avif', '.gif', '.ico', '.jpeg', '.jpg', '.png', '.svg', '.webp',
        '.mp4', '.webm',
    }

    media_roots = [settings.MEDIA_ROOT]
    if path_parts[0] in allowed_upload_dirs:
        if not can_access_uploaded_applicant_file(request, path):
            raise Http404('File not found.')
        media_roots.append(settings.BASE_DIR)
    if len(path_parts) == 1 and Path(path).suffix.lower() in public_asset_extensions:
        media_roots.append(settings.BASE_DIR.parent / 'frontend')

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

@staff_permission_required('ats_new.change_applicant')
def send_applicant_email(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)

    recipient = (request.POST.get('to') or request.POST.get('recipient') or '').strip()
    subject = (request.POST.get('subject') or '').strip()
    message = (request.POST.get('message') or '').strip()

    if not recipient or not subject or not message:
        return JsonResponse({'ok': False, 'error': 'Recipient, subject, and message are required.'}, status=400)
    try:
        validate_email(recipient)
    except ValidationError:
        return JsonResponse({'ok': False, 'error': 'Recipient email is invalid.'}, status=400)

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
    except Exception:
        logger.exception('Failed to send applicant email to %s', recipient)
        return JsonResponse({'ok': False, 'error': 'Email provider error. Please check the server logs.'}, status=502)

    if not sent_count:
        return JsonResponse({'ok': False, 'error': 'Email provider did not accept the message.'}, status=502)

    applicant = Applicant.objects.filter(email__iexact=recipient).first()
    if applicant:
        StatusHistory.objects.create(
            applicant=applicant,
            status=applicant.status,
            notes=f"Sent email to applicant: \"{subject}\".",
            changed_by=request.user
        )

    return JsonResponse({'ok': True})


GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'


def google_oauth_redirect_uri(request):
    configured_uri = getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', '')
    if configured_uri:
        return configured_uri
    return request.build_absolute_uri('/auth/google/callback/')


def render_google_auth_error(request, message, role='applicant'):
    template = 'login.html' if role == 'admin' else 'applicant_login.html'
    return render(request, template, {'oauth_error': message})


def google_oauth_start(request):
    role = request.GET.get('role') or 'applicant'
    if role not in {'admin', 'applicant'}:
        role = 'applicant'

    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
    if not client_id:
        return render_google_auth_error(request, 'Google sign-in is not configured yet.', role)

    state = secrets.token_urlsafe(32)
    request.session['google_oauth_state'] = state
    request.session['google_oauth_role'] = role

    params = {
        'client_id': client_id,
        'redirect_uri': google_oauth_redirect_uri(request),
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account',
    }
    return redirect(f'{GOOGLE_AUTH_URL}?{urlencode(params)}')


def exchange_google_code(request, code):
    payload = urlencode({
        'code': code,
        'client_id': getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', ''),
        'client_secret': getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', ''),
        'redirect_uri': google_oauth_redirect_uri(request),
        'grant_type': 'authorization_code',
    }).encode('utf-8')
    token_request = Request(
        GOOGLE_TOKEN_URL,
        data=payload,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    with urlopen(token_request, timeout=10) as response:
        return json.loads(response.read().decode('utf-8'))


def fetch_google_userinfo(access_token):
    userinfo_request = Request(
        GOOGLE_USERINFO_URL,
        headers={'Authorization': f'Bearer {access_token}'},
        method='GET',
    )
    with urlopen(userinfo_request, timeout=10) as response:
        return json.loads(response.read().decode('utf-8'))


def google_oauth_callback(request):
    role = request.session.pop('google_oauth_role', 'applicant')
    expected_state = request.session.pop('google_oauth_state', '')
    received_state = request.GET.get('state') or ''
    code = request.GET.get('code') or ''

    if not expected_state or received_state != expected_state:
        return render_google_auth_error(request, 'Google sign-in expired. Please try again.', role)
    if not code:
        return render_google_auth_error(request, 'Google did not return an authorization code.', role)

    try:
        token_data = exchange_google_code(request, code)
        userinfo = fetch_google_userinfo(token_data.get('access_token'))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.exception('Google OAuth failed')
        return render_google_auth_error(request, f'Google sign-in failed: {exc}', role)

    email = (userinfo.get('email') or '').strip().lower()
    if not email or not userinfo.get('email_verified'):
        return render_google_auth_error(request, 'Google account email must be verified.', role)

    if role == 'admin':
        User = get_user_model()
        user = (
            User.objects.filter(email__iexact=email).first()
            or User.objects.filter(username__iexact=email).first()
        )
        if not user and email in settings.GOOGLE_ADMIN_EMAILS:
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=userinfo.get('given_name') or '',
                last_name=userinfo.get('family_name') or '',
            )
            user.set_unusable_password()
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=['password', 'is_staff', 'is_superuser', 'first_name', 'last_name'])
        
        if user:
            # Sync name from Google if blank
            updated_fields = []
            if not user.first_name and userinfo.get('given_name'):
                user.first_name = userinfo.get('given_name')
                updated_fields.append('first_name')
            if not user.last_name and userinfo.get('family_name'):
                user.last_name = userinfo.get('family_name')
                updated_fields.append('last_name')
            if updated_fields:
                user.save(update_fields=updated_fields)

        if not user or not user.is_staff:
            return render_google_auth_error(request, 'This Google account is not registered as staff.', role)
        ensure_staff_permissions(user)
        login(request, user)
        request.session.pop('applicant_id', None)
        return redirect('admin_dashboard')

    applicant = Applicant.objects.filter(email__iexact=email).first()
    if not applicant:
        return render_google_auth_error(request, 'No applicant account is registered with this Google email.', role)
    if applicant.status == 'Pending':
        return render_google_auth_error(request, 'Your application is still pending approval. Please check back later.', role)

    logout(request)
    request.session['applicant_id'] = str(applicant.applicant_id)
    return redirect('applicant_portal')

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


@never_cache
@ensure_csrf_cookie
def applicant_login(request):
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip()
        password = request.POST.get('password') or ''
        applicant = Applicant.objects.filter(email__iexact=email).first()

        if applicant and applicant.check_password(password):
            if not applicant.password_is_hashed():
                applicant.set_password(password)
                applicant.save(update_fields=['password', 'updated_at'])

            if applicant.status == 'Pending':
                return render(request, 'applicant_login.html', {'error': 'Your application is still pending approval. Please check back later.'})

            logout(request)
            request.session['applicant_id'] = str(applicant.applicant_id)
            return redirect('applicant_portal')

        return render(request, 'applicant_login.html', {'error': 'Invalid email or password'})

    return render(request, 'applicant_login.html')

def applicant_portal(request):
    applicant_id = request.session.get('applicant_id')
    if not applicant_id:
        return redirect('applicant_login')
    
    applicant = Applicant.objects.filter(applicant_id=applicant_id).first()
    if not applicant:
        request.session.pop('applicant_id', None)
        return redirect('applicant_login')
    preferred_time_saved = False
    preferred_time_error = ''
    document_upload_saved = ''
    document_upload_error = ''

    if request.method == 'POST' and request.POST.get('action') == 'update_preferred_demo_time':
        selected_time = parse_time(request.POST.get('preferred_demo_time') or '')
        if selected_time and time(13, 0) <= selected_time <= time(17, 0):
            applicant.preferred_demo_time = selected_time
            applicant.save(update_fields=['preferred_demo_time', 'updated_at'])
            preferred_time_saved = True
        else:
            preferred_time_error = 'Please select a time between 1:00 PM and 5:00 PM.'
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
            try:
                validate_applicant_upload(field_name, uploaded_file)
            except ValidationError as exc:
                document_upload_error = ' '.join(exc.messages)
            else:
                setattr(applicant, field_name, uploaded_file)
                applicant.save(update_fields=[field_name, 'updated_at'])
                document_upload_saved = upload_fields[field_name]

    latest_evaluation = applicant.evaluations.filter(evaluation_type='demo').order_by('-created_at').first()
    latest_client_evaluation = applicant.evaluations.filter(evaluation_type='client').order_by('-created_at').first()
    latest_schedule = applicant.schedules.all().order_by('-scheduled_at').first()

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
        'meetingUrl': latest_schedule.meeting_link if latest_schedule and latest_schedule.meeting_link else ZOOM_UPCOMING_URL,
        'preferred_time_saved': preferred_time_saved,
        'preferred_time_error': preferred_time_error,
        'document_upload_saved': document_upload_saved,
        'document_upload_error': document_upload_error,
        'hasCertDoc': 'fa-check-circle' if applicant.tefl_certificate else 'fa-times-circle',
        'hasResumeDoc': 'fa-check-circle' if applicant.resume else 'fa-times-circle',
    }
    return render(request, 'applicant_portal.html', context)

SCHEDULE_COLORS = {
    'initial': '#f59e0b',
    'demo': '#ee5f88',
    'training': '#3b82f6',
    'onboarding': '#10b981',
    'endorsement': '#8b5cf6',
}



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
                'date_iso': day.isoformat(),
                'number': day.day,
                'in_month': day.month == today.month,
                'is_today': day == today,
                'has_events': day in event_dates,
                'calendar_url': f"/admin-calendar/?date={day.isoformat()}",
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
            'calendar_url': f"/admin-calendar/?date={timezone.localtime(schedule.scheduled_at).date().isoformat()}",
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
        {'s': 'Initial Screening', 'card_label': 'Screening', 'total': Applicant.objects.filter(status__in=['Pending', 'Initial Screening']).count(), 'key': 'Initial Screening'},
        {'s': 'Demo Evaluation', 'card_label': 'Demo', 'total': Applicant.objects.filter(status='Demo Evaluation').count(), 'key': 'Demo Evaluation'},
        {'s': 'Client Endorsement', 'card_label': 'Endorsements', 'total': Applicant.objects.filter(status='Endorsement').count(), 'key': 'Endorsement'},
        {'s': 'Training', 'card_label': 'Training', 'total': Applicant.objects.filter(status='Training').count(), 'key': 'Training'},
        {'s': 'Approved', 'card_label': 'Approved', 'total': Applicant.objects.filter(status='Approved').count(), 'key': 'Approved'},
    ]
    applicants = Applicant.objects.all().order_by('-created_at')
    if status_filter:
        if status_filter == 'screening':
            applicants = applicants.filter(status__in=['Pending', 'Initial Screening'])
        else:
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

@never_cache
@ensure_csrf_cookie
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
            ensure_staff_permissions(user)
            login(request, user)
            request.session.pop('applicant_id', None)
            return redirect('admin_dashboard')
        else:
            return render(request, 'login.html', {'error': 'Invalid credentials', 'email': email})
    return render(request, 'login.html')

@staff_permission_required('ats_new.view_applicant')
def admin_dashboard(request):
    return render(request, 'dashboard.html', applicant_admin_context())

@staff_permission_required('ats_new.view_applicant')
def applicants_page(request):
    return render(request, 'manage_applicants.html', applicant_admin_context(request.GET.get('status')))

@staff_permission_required('ats_new.view_applicant')
def applicant_details(request, applicant_id):
    applicant = get_object_or_404(Applicant, applicant_id=applicant_id)
    if request.method == 'POST' and request.POST.get('action') == 'upload_second_video':
        uploaded_file = request.FILES.get('video_2')
        if uploaded_file:
            try:
                validate_applicant_upload('video_2', uploaded_file)
            except ValidationError as exc:
                messages.error(request, ' '.join(exc.messages))
            else:
                applicant.video_2 = uploaded_file
                applicant.save(update_fields=['video_2', 'updated_at'])
                messages.success(request, 'Second video uploaded.')
        return redirect('applicant_details', applicant_id=applicant.applicant_id)

    history = applicant.history.all().select_related('changed_by').order_by('-created_at')
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

    })

@staff_permission_required('ats_new.delete_applicant')
def delete_applicant(request, applicant_id):
    if request.method != 'POST':
        return redirect('applicants_page')

    applicant = get_object_or_404(Applicant, applicant_id=applicant_id)
    applicant_name = applicant.full_name or applicant.email
    applicant.delete()
    messages.success(request, f'{applicant_name} was deleted.')
    return redirect('applicants_page')

@staff_permission_required('ats_new.change_applicant')
def update_status(request):
    if request.method == 'POST':
        applicant_id = request.POST.get('applicant_id')
        applicant = get_object_or_404(Applicant, applicant_id=applicant_id)
        
        # Check if we are updating status or general info
        if 'new_status' in request.POST:
            new_status = request.POST.get('new_status')
            applicant.update_status(new_status, notes=request.POST.get('status_note'), changed_by=request.user)
        else:
            applicant.update_profile_from_post(request.POST, changed_by=request.user)
        return safe_post_redirect(request, 'applicant_details', applicant_id=applicant_id)
    return redirect('admin_dashboard')

@staff_permission_required('ats_new.view_schedule')
def admin_calendar(request):
    initial_date = request.GET.get('date') or timezone.localdate().isoformat()
    schedules = Schedule.objects.all().select_related('applicant').order_by('scheduled_at', '-created_at')
    events = []
    
    # Colors for different stages
    colors = {
        'initial': '#f59e0b',
        'demo': '#7c3aed',
        'endorsement': '#8b5cf6',
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
                'meetingLink': s.meeting_link or ZOOM_UPCOMING_URL,
                'stageLabel': s.get_type_display(),
                'stageKey': s.type,
                'applicantUrl': f"/applicant-details/{s.applicant.applicant_id}/",
                'applicantId': str(s.applicant.applicant_id),
                'scheduleId': str(s.schedule_id)
            }
        })

    stage_counts = {key: 0 for key in colors}
    for schedule in schedules:
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
        'initialDateJson': json.dumps(initial_date),
    }
    return render(request, 'admin_calendar.html', context)

@staff_permission_required('ats_new.change_schedule')
def schedule_action(request):
    if request.method == 'POST':
        applicant_id = request.POST.get('applicant_identifier')
        sched_type = request.POST.get('type')
        scheduled_date = request.POST.get('scheduled_date')
        scheduled_time = request.POST.get('scheduled_time')
        if scheduled_date and scheduled_time:
            scheduled_at = f"{scheduled_date}T{scheduled_time}"
        meeting_link = (request.POST.get('meeting_link') or '').strip()
        title = request.POST.get('title')
        reschedule_reason = (request.POST.get('reschedule_reason') or '').strip()
        was_unavailable = request.POST.get('applicant_unavailable') == '1'
        
        applicant = get_object_or_404(Applicant, applicant_id=applicant_id)
        if sched_type not in dict(Schedule.TYPE_CHOICES):
            messages.error(request, 'Invalid schedule type.')
            return safe_post_redirect(request, 'admin_dashboard')

        parsed_scheduled_at = parse_datetime(scheduled_at or '')
        if not parsed_scheduled_at:
            messages.error(request, 'Invalid schedule date/time.')
            return safe_post_redirect(request, 'admin_dashboard')
        if timezone.is_naive(parsed_scheduled_at):
            parsed_scheduled_at = timezone.make_aware(parsed_scheduled_at, timezone.get_current_timezone())

        if sched_type == 'demo':
            local_scheduled_time = timezone.localtime(parsed_scheduled_at).time()
            if not (time(13, 0) <= local_scheduled_time <= time(17, 0)):
                messages.error(request, 'Demo interviews must be scheduled between 1:00 PM and 5:00 PM.')
                return safe_post_redirect(request, 'admin_dashboard')

        if sched_type == 'endorsement':
            local_scheduled_time = timezone.localtime(parsed_scheduled_at).time()
            if not (time(7, 0) <= local_scheduled_time <= time(23, 0)):
                messages.error(request, 'Client interviews must be scheduled between 7:00 AM and 11:00 PM.')
                return safe_post_redirect(request, 'admin_dashboard')

        if sched_type == 'training':
            local_scheduled_time = timezone.localtime(parsed_scheduled_at).time()
            if not (time(7, 0) <= local_scheduled_time <= time(23, 0)):
                messages.error(request, 'Training sessions must be scheduled between 7:00 AM and 11:00 PM.')
                return safe_post_redirect(request, 'admin_dashboard')

        existing_schedule = applicant.schedules.filter(type=sched_type).first()
        previous_time = existing_schedule.scheduled_at if existing_schedule else None
        if not meeting_link and existing_schedule:
            meeting_link = existing_schedule.meeting_link
        
        # Create or Update schedule
        schedule, _ = Schedule.objects.update_or_create(
            applicant=applicant,
            type=sched_type,
            defaults={
                'title': title,
                'scheduled_at': parsed_scheduled_at,
                'meeting_link': meeting_link
            }
        )
        schedule.refresh_from_db()

        schedule.sync_applicant_status(title, changed_by=request.user)
        
        # Log new schedule creation
        if not existing_schedule:
            note = f"Scheduled {schedule.get_type_display()} for {timezone.localtime(schedule.scheduled_at).strftime('%B %d, %Y @ %I:%M %p')}."
            StatusHistory.objects.create(
                applicant=applicant,
                status=applicant.status,
                notes=note,
                changed_by=request.user
            )

        advance_status = request.POST.get('advance_status')
        if advance_status and advance_status != applicant.status:
            applicant.update_status(
                advance_status,
                notes=f"Moved forward from {applicant.status} to {advance_status} after schedule update.",
                changed_by=request.user,
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
                changed_by=request.user,
            )
        
        return safe_post_redirect(request, 'admin_dashboard')
    return redirect('admin_dashboard')

@staff_permission_required('ats_new.view_schedule')
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
            'next_status': 'Onboarding',
            'action_label': 'Move to Onboarding',
        },
        'onboarding': {
            'label': 'Onboarding',
            'status': 'Onboarding',
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
        {'label': 'Onboarding', 'status': 'Onboarding'},
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

@staff_permission_required('ats_new.view_schedule')
def screening_schedule(request):
    applicants = Applicant.objects.filter(status__in=['Pending', 'Initial Screening']).order_by('-created_at')
    for applicant in applicants:
        applicant.current_schedule = applicant.schedules.filter(type='initial').first()
    return render(request, 'screening_schedule.html', {'applicants': applicants})

@staff_permission_required('ats_new.view_evaluation')
def demo_evaluation(request):
    applicants = Applicant.objects.filter(status='Demo Evaluation')
    for app in applicants:
        app.current_schedule = app.schedules.filter(type='demo').first()
        app.current_evaluation = app.evaluations.filter(evaluation_type='demo').order_by('-created_at').first()
    return render(request, 'demo_evaluation.html', {'applicants': applicants})

@staff_permission_required('ats_new.view_evaluation')
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

@staff_permission_required('ats_new.view_applicant')
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

@staff_permission_required('ats_new.view_schedule')
def training_schedule(request):
    applicants = Applicant.objects.filter(status='Training')
    for app in applicants:
        app.current_schedule = app.schedules.filter(type='training').first()
    return render(request, 'training_schedule.html', {'applicants': applicants})

@staff_permission_required('ats_new.view_evaluation')
def client_endorsement(request):
    applicants = Applicant.objects.filter(status='Endorsement')
    for app in applicants:
        app.current_schedule = app.schedules.filter(type='endorsement').first()
        app.current_evaluation = app.evaluations.filter(evaluation_type='client').order_by('-created_at').first()
        app.demo_evaluation = app.evaluations.filter(evaluation_type='demo').order_by('-created_at').first()
    return render(request, 'client_endorsement.html', {'applicants': applicants})

@staff_permission_required('ats_new.add_evaluation')
def evaluate_applicant(request, applicant_id):
    applicant = get_object_or_404(Applicant, applicant_id=applicant_id)
    evaluation_type = request.GET.get('type')
    schedule_type = 'endorsement' if evaluation_type == 'client' or applicant.status == 'Endorsement' else 'demo'
    applicant.current_schedule = applicant.schedules.filter(type=schedule_type).first()
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

@staff_permission_required('ats_new.add_evaluation')
def floating_evaluation(request, applicant_id):
    applicant = get_object_or_404(Applicant, applicant_id=applicant_id)
    evaluation_type = request.GET.get('type')
    if evaluation_type not in {'client', 'demo'}:
        evaluation_type = 'client' if applicant.status == 'Endorsement' else 'demo'

    existing_eval = Evaluation.objects.filter(
        applicant=applicant,
        evaluation_type=evaluation_type,
    ).order_by('-created_at').first()

    criteria = [
        {'key': 'teaching_performance', 'label': 'Teaching Performance'},
        {'key': 'communication_skills', 'label': 'Communication Skills'},
        {'key': 'curriculum_understanding', 'label': 'Curriculum Understanding'},
        {'key': 'engagement_level', 'label': 'Engagement Level'},
        {'key': 'technical_proficiency', 'label': 'Technical Proficiency'},
    ]
    for item in criteria:
        item['value'] = str(getattr(existing_eval, item['key'], '')) if existing_eval else ''

    return render(request, 'floating_evaluation.html', {
        'app': applicant,
        'eval': existing_eval,
        'criteria': criteria,
        'evaluation_type': evaluation_type,
        'saved': request.GET.get('saved') == '1',
    })

@staff_permission_required('ats_new.add_evaluation')
def save_evaluation(request):
    if request.method == 'POST':
        applicant_id = request.POST.get('applicant_identifier')
        applicant = get_object_or_404(Applicant, applicant_id=applicant_id)

        if request.POST.get('evaluation_type') == 'client':
            decision = request.POST.get('client_decision')
            if decision not in {'Pass', 'Fail'}:
                return redirect(f"/floating-evaluation/{applicant.applicant_id}/?type=client")

            defaults = Evaluation.client_defaults(decision, request.POST.get('overall_comments'))
            defaults['evaluator'] = request.user
            evaluation, _ = Evaluation.objects.update_or_create(
                applicant=applicant,
                evaluation_type='client',
                defaults=defaults,
            )
            next_status = 'Training' if decision == 'Pass' else 'Withdrawn'
            if applicant.status != next_status:
                applicant.update_status(
                    next_status,
                    notes=f"Client endorsement marked {decision}.",
                    changed_by=request.user,
                )
            else:
                StatusHistory.objects.create(
                    applicant=applicant,
                    status=applicant.status,
                    notes=f"Saved client endorsement evaluation (Decision: {decision}).",
                    changed_by=request.user
                )
            return redirect(f"/floating-evaluation/{applicant.applicant_id}/?type=client&saved=1")

        defaults = Evaluation.rating_defaults_from_request(request.POST)
        defaults['evaluator'] = request.user
        Evaluation.objects.update_or_create(
            applicant=applicant,
            evaluation_type='demo',
            defaults=defaults,
        )
        
        StatusHistory.objects.create(
            applicant=applicant,
            status=applicant.status,
            notes="Submitted/updated demo evaluation rating and comments.",
            changed_by=request.user
        )
        
        return redirect(f"/floating-evaluation/{applicant.applicant_id}/?type=demo&saved=1")
    return redirect('admin_dashboard')

def find_applicant_for_room(room_id, applicant_name=''):
    try:
        schedule = Schedule.objects.filter(schedule_id=room_id).select_related('applicant').first()
        applicant = schedule.applicant if schedule else Applicant.objects.filter(applicant_id=room_id).first()
    except (ValidationError, ValueError, TypeError):
        schedule = None
        applicant = None
    if applicant:
        return applicant, schedule

    applicant_name = (applicant_name or '').strip()
    if applicant_name:
        name_parts = applicant_name.split()
        matches = Applicant.objects.all()
        for part in name_parts:
            matches = matches.filter(Q(first_name__icontains=part) | Q(last_name__icontains=part))
        applicant = matches.first()
    return applicant, schedule


@staff_permission_required('ats_new.view_evaluation')
def room_evaluation_prefill(request):
    room_id = request.GET.get('roomId') or request.GET.get('room_id')
    if not room_id:
        return JsonResponse({'ok': False, 'error': 'Missing room id'}, status=400)

    applicant, schedule = find_applicant_for_room(room_id)
    if not applicant:
        return JsonResponse({'ok': False, 'error': 'Applicant not found for this room'}, status=404)

    evaluation_type = request.GET.get('evaluationType') or request.GET.get('evaluation_type')
    if evaluation_type not in {'client', 'demo'}:
        evaluation_type = 'client' if schedule and schedule.type == 'endorsement' else 'demo'

    evaluation = applicant.evaluations.filter(evaluation_type=evaluation_type).order_by('-created_at').first()
    data = {
        'ok': True,
        'roomId': str(room_id),
        'evaluationType': evaluation_type,
        'applicant': {
            'id': str(applicant.applicant_id),
            'name': applicant.full_name,
            'email': applicant.email,
            'phone': applicant.phone or '',
            'status': applicant.status,
            'workSetup': applicant.work_setup,
            'teachingAccount': applicant.teaching_account or '',
        },
        'evaluation': None,
    }

    if evaluation:
        data['evaluation'] = {
            'id': str(evaluation.evaluation_id),
            'type': evaluation.evaluation_type,
            'ratings': {
                'teaching_performance': evaluation.teaching_performance,
                'communication_skills': evaluation.communication_skills,
                'curriculum_understanding': evaluation.curriculum_understanding,
                'engagement_level': evaluation.engagement_level,
                'technical_proficiency': evaluation.technical_proficiency,
            },
            'totalScore': evaluation.total_score,
            'clientDecision': evaluation.client_decision or '',
            'comments': evaluation.comments or '',
            'createdAt': evaluation.created_at.isoformat(),
        }

    return JsonResponse(data)
@staff_permission_required('ats_new.add_evaluation')
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

    applicant, schedule = find_applicant_for_room(room_id, payload.get('applicantName'))
    if not applicant:
        return JsonResponse({'ok': False, 'error': 'Applicant not found for this room'}, status=404)

    ratings = payload.get('ratings') or {}
    comments = payload.get('comments') or {}
    if not isinstance(ratings, dict):
        return JsonResponse({'ok': False, 'error': 'Ratings must be an object.'}, status=400)
    if not isinstance(comments, dict):
        return JsonResponse({'ok': False, 'error': 'Comments must be an object.'}, status=400)
    evaluation_type = payload.get('evaluationType') or payload.get('evaluation_type')

    if evaluation_type == 'client':
        decision = payload.get('clientDecision') or payload.get('client_decision') or payload.get('decision')
        if decision not in {'Pass', 'Fail'}:
            return JsonResponse({'ok': False, 'error': 'Client decision must be Pass or Fail'}, status=400)

        overall_comments = payload.get('overallComments') or payload.get('commentsText') or ''
        defaults = Evaluation.client_defaults(decision, overall_comments)
        defaults['evaluator'] = request.user
        eval_obj, _ = Evaluation.objects.update_or_create(
            applicant=applicant,
            evaluation_type='client',
            defaults=defaults,
        )
        next_status = 'Training' if decision == 'Pass' else 'Withdrawn'
        if applicant.status != next_status:
            applicant.update_status(
                next_status,
                notes=f"Client endorsement marked {decision} from video conference.",
                changed_by=request.user,
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

    defaults = Evaluation.rating_defaults_from_room_payload(ratings, overall_comments)
    defaults['evaluator'] = request.user
    eval_obj, _ = Evaluation.objects.update_or_create(
        applicant=applicant,
        evaluation_type='demo',
        defaults=defaults,
    )

    StatusHistory.objects.create(
        applicant=applicant,
        status=applicant.status,
        notes=f"Submitted demo evaluation via video conference (Score: {eval_obj.total_score}/25).",
        changed_by=request.user
    )

    return JsonResponse({
        'ok': True,
        'applicantId': str(applicant.applicant_id),
        'evaluationId': str(eval_obj.evaluation_id),
        'totalScore': eval_obj.total_score,
    })

@staff_permission_required('ats_new.view_schedule')
def onboarding(request):
    if request.method == 'POST':
        if not request.user.has_perm('ats_new.change_applicant'):
            raise PermissionDenied
        action = request.POST.get('action')
        applicant_id = request.POST.get('applicant_identifier')
        applicant = get_object_or_404(Applicant, applicant_id=applicant_id)
        
        if action == 'assign_account':
            placement = get_object_or_404(Placement, slug=request.POST.get('account_slug'))
            applicant.assign_teaching_account(
                placement,
                request.POST.get('notes'),
                changed_by=request.user
            )
            return redirect('onboarding')
        if action == 'clear_account':
            applicant.clear_teaching_account(request.POST.get('notes'), changed_by=request.user)
            return redirect('onboarding')

    applicants = Applicant.objects.filter(status__in=['Onboarding', 'Approved'])
    for app in applicants:
        app.current_schedule = app.schedules.filter(type='onboarding').first()

    placement_groups = [
        {
            'slug': placement.slug,
            'label': placement.name,
            'applicants': applicants.filter(teaching_account=placement),
        }
        for placement in Placement.objects.all()
    ]
    
    context = {
        'applicants': applicants,
        'accounts': Placement.objects.all(),
        'placement_groups': placement_groups,
        'unassigned_count': applicants.filter(teaching_account__isnull=True).count(),
    }
    return render(request, 'schedule_onboarding.html', context)

def applicant_logout(request):
    logout(request) # Also logs out django users
    request.session.flush()
    return redirect('home')

def video_call(request, schedule_id):
    schedule = Schedule.objects.filter(schedule_id=schedule_id).first()
    if schedule and schedule.meeting_link:
        return redirect(schedule.meeting_link)
    return redirect(ZOOM_UPCOMING_URL)


@staff_permission_required('ats_new.view_applicant')
def placements_list(request):
    from django.utils.text import slugify
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create':
            if not request.user.has_perm('ats_new.add_placement'):
                raise PermissionDenied
            name = (request.POST.get('name') or '').strip()
            description = (request.POST.get('description') or '').strip()
            
            if not name:
                messages.error(request, 'Placement name is required.')
            else:
                slug = slugify(name)
                if Placement.objects.filter(slug=slug).exists():
                    messages.error(request, f'A placement with name "{name}" already exists.')
                else:
                    Placement.objects.create(name=name, slug=slug, description=description)
                    messages.success(request, f'Placement "{name}" created successfully.')
            return redirect('placements_list')
            
        elif action == 'update':
            if not request.user.has_perm('ats_new.change_placement'):
                raise PermissionDenied
            placement_id = request.POST.get('placement_id')
            placement = get_object_or_404(Placement, id=placement_id)
            name = (request.POST.get('name') or '').strip()
            description = (request.POST.get('description') or '').strip()
            
            if not name:
                messages.error(request, 'Placement name is required.')
            else:
                slug = slugify(name)
                if Placement.objects.filter(slug=slug).exclude(id=placement.id).exists():
                    messages.error(request, f'A placement with name "{name}" already exists.')
                else:
                    placement.name = name
                    placement.slug = slug
                    placement.description = description
                    placement.save()
                    messages.success(request, f'Placement "{name}" updated successfully.')
            return redirect('placements_list')
            
        elif action == 'delete':
            if not request.user.has_perm('ats_new.delete_placement'):
                raise PermissionDenied
            placement_id = request.POST.get('placement_id')
            placement = get_object_or_404(Placement, id=placement_id)
            
            if placement.applicants.exists():
                messages.error(request, f'Cannot delete "{placement.name}" because applicants are currently assigned to it.')
            else:
                placement.delete()
                messages.success(request, f'Placement deleted successfully.')
            return redirect('placements_list')

    placements = Placement.objects.all().order_by('name')
    placements_data = []
    for placement in placements:
        approved_applicants = placement.applicants.filter(status='Approved')
        placements_data.append({
            'placement': placement,
            'approved_applicants': approved_applicants,
            'approved_count': approved_applicants.count(),
        })
        
    context = {
        'placements_data': placements_data,
        'active': 'placements',
        'all_applicants_count': Applicant.objects.count(),
    }
    return render(request, 'placements.html', context)

















