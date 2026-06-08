import uuid
from django.db import models
from django.contrib.auth.models import User

class Applicant(models.Model):
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
    
    # Placement
    ACCOUNT_CHOICES = [
        ('Vietnamese', 'Vietnamese Account'),
        ('Chinese', 'Chinese Account'),
        ('Mongolian', 'Mongolian Account'),
    ]
    teaching_account = models.CharField(max_length=50, choices=ACCOUNT_CHOICES, blank=True, null=True)
    teaching_account_notes = models.TextField(blank=True, null=True)
    
    # Files
    resume = models.FileField(upload_to='resumes/')
    video = models.FileField(upload_to='videos/')
    
    # Process Meta
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Initial Screening', 'Initial Screening'),
        ('Demo Evaluation', 'Demo Evaluation'),
        ('Training', 'Training'),
        ('Onboarding', 'Onboarding'),
        ('Approved', 'Approved'),
        ('Withdrawn', 'Withdrawn'),
    ]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

class Schedule(models.Model):
    schedule_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    TYPE_CHOICES = [
        ('initial', 'Initial Screening'),
        ('demo', 'Demo Session'),
        ('training', 'Training'),
        ('onboarding', 'Onboarding'),
    ]
    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name='schedules')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    scheduled_at = models.DateTimeField()
    meeting_link = models.URLField(blank=True, null=True)
    completed = models.BooleanField(default=False)
    video_call_log = models.JSONField(default=dict, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type.capitalize()} - {self.applicant.last_name} @ {self.scheduled_at}"

class Evaluation(models.Model):
    evaluation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name='evaluations')
    evaluator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Scores (1-5 as per the form)
    teaching_performance = models.IntegerField(default=0)
    communication_skills = models.IntegerField(default=0)
    curriculum_understanding = models.IntegerField(default=0)
    engagement_level = models.IntegerField(default=0)
    technical_proficiency = models.IntegerField(default=0)
    
    total_score = models.IntegerField(default=0)
    comments = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Automatically calculate total score
        self.total_score = (
            self.teaching_performance + 
            self.communication_skills + 
            self.curriculum_understanding + 
            self.engagement_level + 
            self.technical_proficiency
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Eval for {self.applicant.last_name} - Score: {self.total_score}/25"
class StatusHistory(models.Model):
    history_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name='history')
    status = models.CharField(max_length=50)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name_plural = "Status Histories"

    def __str__(self):
        return f"{self.applicant.last_name} moved to {self.status} on {self.created_at}"
