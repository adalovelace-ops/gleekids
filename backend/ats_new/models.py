import uuid
from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password, identify_hasher, make_password

class Placement(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Applicant(models.Model):
    NEXT_STEP_TEXT = {
        'Pending': 'Our team is currently reviewing your application. Please wait for an approval email to proceed.',
        'Initial Screening': 'Our team is reviewing your screening result. Please check your email for the next step.',
        'Demo Evaluation': 'Prepare your teaching materials! Your demo evaluation session has been scheduled.',
        'Endorsement': 'You have passed the demo! We are now presenting your profile to our clients for final review.',
        'Training': 'Congratulations! You are now in the training phase. Please follow the instructions provided by your trainer.',
        'Onboarding': 'You are in onboarding. Please complete the remaining placement and account requirements.',
        'Approved': 'Welcome to the team! We are finalizing your onboarding documents.',
        'Resign': 'Your application record is currently marked as resigned.',
        'Withdrawn': 'Your application is currently marked as withdrawn.',
    }
    PROGRESS_STAGES = [
        {'label': 'Pending', 'status': 'Pending', 'percent': 10},
        {'label': 'Screening', 'status': 'Initial Screening', 'percent': 25},
        {'label': 'Demo', 'status': 'Demo Evaluation', 'percent': 45},
        {'label': 'Endorsement', 'status': 'Endorsement', 'percent': 65},
        {'label': 'Training', 'status': 'Training', 'percent': 85},
        {'label': 'Onboarding', 'status': 'Onboarding', 'percent': 95},
        {'label': 'Approved', 'status': 'Approved', 'percent': 100},
    ]

    applicant_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Personal Info
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100)
    date_of_birth = models.DateField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    referral = models.CharField(max_length=100, blank=True, null=True)
    password = models.CharField(max_length=128)

    WORK_SETUP_CHOICES = [
        ('WFH', 'Work from Home'),
        ('Office Based', 'Office Based'),
    ]
    work_setup = models.CharField(max_length=20, choices=WORK_SETUP_CHOICES, default='WFH')
    preferred_demo_time = models.TimeField(blank=True, null=True)
    
    # Placement
    teaching_account = models.ForeignKey(Placement, on_delete=models.SET_NULL, blank=True, null=True, related_name='applicants')
    teaching_account_notes = models.TextField(blank=True, null=True)
    
    # Files
    resume = models.FileField(upload_to='resumes/')
    video = models.FileField(upload_to='videos/')
    video_2 = models.FileField(upload_to='videos/', blank=True, null=True)
    tefl_certificate = models.FileField(upload_to='certificates/', blank=True, null=True)
    
    # Process Meta
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Initial Screening', 'Initial Screening'),
        ('Demo Evaluation', 'Demo Evaluation'),
        ('Endorsement', 'Endorsement'),
        ('Training', 'Training'),
        ('Onboarding', 'Onboarding'),
        ('Approved', 'Approved'),
        ('Resign', 'Resign'),
        ('Withdrawn', 'Withdrawn'),
    ]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def password_is_hashed(self):
        try:
            identify_hasher(self.password)
            return True
        except ValueError:
            return False

    def check_password(self, raw_password):
        if self.password_is_hashed():
            return check_password(raw_password, self.password)
        return self.password == raw_password

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_next_step_text(self):
        return self.NEXT_STEP_TEXT.get(self.status, 'Check back later for updates.')

    def get_progress_stages(self):
        return list(self.PROGRESS_STAGES)

    def get_progress(self):
        for index, stage in enumerate(self.PROGRESS_STAGES):
            if self.status == stage['status']:
                return stage['percent'], index
        return 0, 0

    def update_status(self, new_status, notes=None, save=True, changed_by=None):
        old_status = self.status
        if old_status == new_status and not notes:
            return
        self.status = new_status
        if save:
            self.save(update_fields=['status', 'updated_at'])

        StatusHistory.objects.create(
            applicant=self,
            status=new_status,
            notes=notes or f"Moved from {old_status} via manual update.",
            changed_by=changed_by
        )

    def update_profile_from_post(self, data, changed_by=None):
        changed_fields = []
        for field in ['first_name', 'last_name', 'email', 'phone', 'address', 'city', 'state']:
            if field in data:
                old_val = getattr(self, field)
                new_val = data.get(field)
                if str(old_val) != str(new_val):
                    setattr(self, field, new_val)
                    changed_fields.append(field.replace('_', ' '))
        if changed_fields:
            self.save()
            StatusHistory.objects.create(
                applicant=self,
                status=self.status,
                notes=f"Updated profile details: {', '.join(changed_fields)}.",
                changed_by=changed_by
            )

    def assign_teaching_account(self, account, notes=None, changed_by=None):
        self.teaching_account = account
        self.teaching_account_notes = notes
        self.save(update_fields=['teaching_account', 'teaching_account_notes', 'updated_at'])
        StatusHistory.objects.create(
            applicant=self,
            status=self.status,
            notes=f"Assigned to {self.teaching_account.name if self.teaching_account else ''} account.",
            changed_by=changed_by
        )

    def clear_teaching_account(self, notes=None, changed_by=None):
        old_account = self.teaching_account
        self.teaching_account = None
        self.teaching_account_notes = ''
        self.save(update_fields=['teaching_account', 'teaching_account_notes', 'updated_at'])
        StatusHistory.objects.create(
            applicant=self,
            status=self.status,
            notes=notes or f"Removed teaching placement{f' from {old_account.name} account' if old_account else ''}.",
            changed_by=changed_by
        )

class Schedule(models.Model):
    STATUS_BY_TYPE = {
        'initial': 'Initial Screening',
        'demo': 'Demo Evaluation',
        'endorsement': 'Endorsement',
        'training': 'Training',
        'onboarding': 'Onboarding',
    }

    schedule_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    TYPE_CHOICES = [
        ('initial', 'Initial Screening'),
        ('demo', 'Demo Session'),
        ('endorsement', 'Client Final Interview'),
        ('training', 'Training'),
        ('onboarding', 'Onboarding'),
    ]
    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name='schedules')
    evaluator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='schedules')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    scheduled_at = models.DateTimeField()
    meeting_link = models.URLField(blank=True, null=True)
    completed = models.BooleanField(default=False)
    video_call_log = models.JSONField(default=dict, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type.capitalize()} - {self.applicant.last_name} @ {self.scheduled_at}"

    def sync_applicant_status(self, title=None, changed_by=None):
        new_status = self.STATUS_BY_TYPE.get(self.type)
        if not new_status or self.applicant.status == new_status:
            return

        self.applicant.update_status(
            new_status,
            notes=f"Automatically moved to {new_status} upon scheduling {title or self.title}.",
            changed_by=changed_by
        )

class Evaluation(models.Model):
    EVALUATION_TYPE_CHOICES = [
        ('demo', 'Demo Evaluation'),
        ('client', 'Client Endorsement'),
    ]
    CLIENT_DECISION_CHOICES = [
        ('Pass', 'Pass'),
        ('Fail', 'Fail'),
    ]

    evaluation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name='evaluations')
    evaluator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    evaluation_type = models.CharField(max_length=20, choices=EVALUATION_TYPE_CHOICES, default='demo')
    
    # Scores (1-5 as per the form)
    teaching_performance = models.IntegerField(default=0)
    communication_skills = models.IntegerField(default=0)
    curriculum_understanding = models.IntegerField(default=0)
    engagement_level = models.IntegerField(default=0)
    technical_proficiency = models.IntegerField(default=0)
    
    total_score = models.IntegerField(default=0)
    client_decision = models.CharField(max_length=10, choices=CLIENT_DECISION_CHOICES, blank=True, null=True)
    comments = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def calculate_total_score(self):
        return (
            self.teaching_performance + 
            self.communication_skills + 
            self.curriculum_understanding + 
            self.engagement_level + 
            self.technical_proficiency
        )

    @staticmethod
    def normalize_rating(value):
        try:
            rating = int(value or 0)
        except (TypeError, ValueError):
            rating = 0
        return max(0, min(rating, 5))

    @classmethod
    def rating_defaults_from_request(cls, data):
        return {
            'evaluation_type': 'demo',
            'teaching_performance': cls.normalize_rating(data.get('teaching_performance_rating')),
            'communication_skills': cls.normalize_rating(data.get('communication_skills_rating')),
            'curriculum_understanding': cls.normalize_rating(data.get('curriculum_understanding_rating')),
            'engagement_level': cls.normalize_rating(data.get('engagement_level_rating')),
            'technical_proficiency': cls.normalize_rating(data.get('technical_proficiency_rating')),
            'client_decision': None,
            'comments': data.get('overall_comments'),
        }

    @classmethod
    def rating_defaults_from_room_payload(cls, ratings, comments_text):
        ratings = ratings if isinstance(ratings, dict) else {}
        return {
            'evaluation_type': 'demo',
            'teaching_performance': cls.normalize_rating(ratings.get('teaching_performance')),
            'communication_skills': cls.normalize_rating(ratings.get('communication_skills')),
            'curriculum_understanding': cls.normalize_rating(ratings.get('curriculum_understanding')),
            'engagement_level': cls.normalize_rating(ratings.get('engagement_level')),
            'technical_proficiency': cls.normalize_rating(ratings.get('technical_proficiency')),
            'client_decision': None,
            'comments': comments_text,
        }

    @classmethod
    def client_defaults(cls, decision, comments_text):
        return {
            'evaluation_type': 'client',
            'teaching_performance': 0,
            'communication_skills': 0,
            'curriculum_understanding': 0,
            'engagement_level': 0,
            'technical_proficiency': 0,
            'client_decision': decision,
            'comments': comments_text,
        }

    def save(self, *args, **kwargs):
        self.total_score = self.calculate_total_score()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Eval for {self.applicant.last_name} - Score: {self.total_score}/25"


class StatusHistory(models.Model):
    history_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name='history')
    status = models.CharField(max_length=50)
    notes = models.TextField(blank=True, null=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='status_changes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "Activity log"
        verbose_name_plural = "Activity log"

    @property
    def logged_by_name(self):
        if self.changed_by:
            full_name = self.changed_by.get_full_name()
            if full_name.strip():
                return full_name
            username = self.changed_by.username
            if '@' in username:
                return username.split('@')[0].replace('.', ' ').title()
            return username.title()
        return 'System'

    def __str__(self):
        return f"{self.applicant.last_name} moved to {self.status} on {self.created_at}"
