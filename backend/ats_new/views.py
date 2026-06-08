import mimetypes
from pathlib import Path

from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render, redirect
from django.conf import settings
from django.utils._os import safe_join
from django.views.decorators.csrf import csrf_exempt
from .forms import ApplicantRegistrationForm
from .models import Applicant


def uploaded_media(request, path):
    media_roots = [
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
    
    # Next Steps Content
    next_steps_map = {
        'Pending': 'Our team is currently reviewing your application. Please wait for an approval email to proceed.',
        'Initial Screening': 'Your initial interview is being scheduled. Please check your email for the meeting invite.',
        'Demo Evaluation': 'Prepare your teaching materials! Your demo evaluation session has been scheduled.',
        'Endorsement': 'You have passed the demo! We are now presenting your profile to our clients for final review.',
        'Training': 'Congratulations! You are now in the training phase. Please follow the instructions provided by your trainer.',
        'Approved': 'Welcome to the team! We are finalizing your onboarding documents.',
    }
    
    # Progress Calculation
    stages = [
        {'label': 'Pending', 'status': 'Pending', 'percent': 10},
        {'label': 'Screening', 'status': 'Initial Screening', 'percent': 25},
        {'label': 'Demo', 'status': 'Demo Evaluation', 'percent': 45},
        {'label': 'Endorsement', 'status': 'Endorsement', 'percent': 65},
        {'label': 'Training', 'status': 'Training', 'percent': 85},
        {'label': 'Onboarding', 'status': 'Approved', 'percent': 100},
    ]
    
    current_percent = 0
    current_stage_index = 0
    for i, stage in enumerate(stages):
        if applicant.status == stage['status']:
            current_percent = stage['percent']
            current_stage_index = i
            break
            
    context = {
        'app': applicant,
        'stages': stages,
        'current_percent': current_percent,
        'current_stage_index': current_stage_index,
        'next_step_text': next_steps_map.get(applicant.status, 'Check back later for updates.'),
        'latest_schedule': applicant.schedules.all().order_by('-scheduled_at').first(),
        'history': applicant.history.all().order_by('-created_at'),
        'demoEval': latest_evaluation,
        'demoScore': f"{latest_evaluation.total_score}/25" if latest_evaluation else None,
        'demoUpdated': latest_evaluation.created_at.strftime('%B %d, %Y') if latest_evaluation else None,
        'zoomCloneUrl': 'http://127.0.0.1:3000/',
    }
    return render(request, 'applicant_portal.html', context)

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test

def admin_login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        # In Django, we typically use 'username', so I'll assume email is username
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            return redirect('admin_dashboard')
        else:
            return render(request, 'login.html', {'error': 'Invalid credentials'})
    return render(request, 'login.html')

@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_dashboard(request):
    status_filter = request.GET.get('status')
    if status_filter:
        applicants = Applicant.objects.filter(status=status_filter).order_by('-created_at')
    else:
        applicants = Applicant.objects.all().order_by('-created_at')
    
    # Counts for cards
    stats = [
        {'s': 'Initial Screening', 'total': Applicant.objects.filter(status='Initial Screening').count(), 'key': 'Initial Screening'},
        {'s': 'Demo Evaluation', 'total': Applicant.objects.filter(status='Demo Evaluation').count(), 'key': 'Demo Evaluation'},
        {'s': 'Client Endorsement', 'total': Applicant.objects.filter(status='Endorsement').count(), 'key': 'Endorsement'},
        {'s': 'Training', 'total': Applicant.objects.filter(status='Training').count(), 'key': 'Training'},
        {'s': 'Approved', 'total': Applicant.objects.filter(status='Approved').count(), 'key': 'Approved'},
    ]
    
    context = {
        'applicants': applicants,
        'stats': stats,
        'pending_applicants_count': Applicant.objects.filter(status='Pending').count(),
        'total_applicants': applicants.count(),
        'pdo': True
    }
    return render(request, 'dashboard.html', context)

from .models import Applicant, Schedule, Evaluation, StatusHistory

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
        'zoomCloneUrl': 'http://127.0.0.1:3000/',
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def update_status(request):
    if request.method == 'POST':
        applicant_id = request.POST.get('applicant_id')
        applicant = Applicant.objects.get(applicant_id=applicant_id)
        
        # Check if we are updating status or general info
        if 'new_status' in request.POST:
            old_status = applicant.status
            new_status = request.POST.get('new_status')
            applicant.status = new_status
            
            # Log history
            StatusHistory.objects.create(
                applicant=applicant,
                status=new_status,
                notes=f"Moved from {old_status} via manual update."
            )
        else:
            # Update general info
            applicant.first_name = request.POST.get('first_name')
            applicant.last_name = request.POST.get('last_name')
            applicant.email = request.POST.get('email')
            applicant.phone = request.POST.get('phone')
            applicant.address = request.POST.get('address')
            applicant.city = request.POST.get('city')
            applicant.state = request.POST.get('state')
            
        applicant.save()
        return redirect('applicant_details', applicant_id=applicant_id)
    return redirect('admin_dashboard')

import json
import uuid
from django.utils import timezone
from .models import Applicant, Schedule

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
        'zoomCloneUrl': 'http://127.0.0.1:3000/',
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
        
        # Mapping schedule type to applicant status
        status_map = {
            'initial': 'Initial Screening',
            'demo': 'Demo Evaluation',
            'training': 'Training',
            'onboarding': 'Approved',
        }
        
        if sched_type in status_map:
            old_status = applicant.status
            new_status = status_map[sched_type]
            if old_status != new_status:
                applicant.status = new_status
                applicant.save()
                
                # Log history
                StatusHistory.objects.create(
                    applicant=applicant,
                    status=new_status,
                    notes=f"Automatically moved to {new_status} upon scheduling {title}."
                )
        
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
        
        # Save or Update evaluation
        eval_obj, created = Evaluation.objects.update_or_create(
            applicant=applicant,
            defaults={
                'teaching_performance': int(request.POST.get('teaching_performance_rating', 0)),
                'communication_skills': int(request.POST.get('communication_skills_rating', 0)),
                'curriculum_understanding': int(request.POST.get('curriculum_understanding_rating', 0)),
                'engagement_level': int(request.POST.get('engagement_level_rating', 0)),
                'technical_proficiency': int(request.POST.get('technical_proficiency_rating', 0)),
                'comments': request.POST.get('overall_comments'),
            }
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

    def rating(key):
        try:
            value = int(ratings.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        return max(0, min(value, 5))

    overall_comments = payload.get('overallComments') or '\n'.join(
        f"{label}: {comment}"
        for label, comment in comments.items()
        if comment
    )

    eval_obj, _ = Evaluation.objects.update_or_create(
        applicant=applicant,
        defaults={
            'teaching_performance': rating('teaching_performance'),
            'communication_skills': rating('communication_skills'),
            'curriculum_understanding': rating('curriculum_understanding'),
            'engagement_level': rating('engagement_level'),
            'technical_proficiency': rating('technical_proficiency'),
            'comments': overall_comments,
        }
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
            applicant.teaching_account = request.POST.get('account_slug')
            applicant.teaching_account_notes = request.POST.get('notes')
            applicant.save()
            
            # Log history
            StatusHistory.objects.create(
                applicant=applicant,
                status=applicant.status,
                notes=f"Assigned to {applicant.teaching_account} account."
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
    return render(request, 'video_call.html', {
        'schedule': schedule,
        'room_id': str(schedule_id),
        'room_title': schedule.title,
        'room_subtitle': schedule.scheduled_at.strftime('%B %d, %Y @ %I:%M %p'),
        'user_role': 'admin' if request.user.is_authenticated and request.user.is_staff else 'applicant',
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def new_video_room(request):
    return redirect('video_room', room_id=uuid.uuid4())

def video_room(request, room_id):
    is_admin = request.user.is_authenticated and request.user.is_staff
    return render(request, 'video_call.html', {
        'room_id': str(room_id),
        'room_title': 'Admin Video Conference',
        'room_subtitle': 'Live Zoom-style room',
        'user_role': 'admin' if is_admin else 'applicant',
    })
