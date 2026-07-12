from django.contrib import admin
from django import forms
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin, GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from django.utils import timezone
from django.utils.html import format_html

from .models import Applicant, Evaluation, Schedule, StatusHistory

User = get_user_model()


class EmailUserCreationForm(UserCreationForm):
    username = forms.CharField(required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('email', 'username', 'is_staff', 'is_superuser', 'is_active')

    def clean_username(self):
        return self.cleaned_data.get('username') or self.cleaned_data.get('email')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email

admin.site.site_header = 'Gleekids Admin'
admin.site.site_title = 'Gleekids Admin'
admin.site.index_title = 'Admin Dashboard'

try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass

@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin):
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_module_permission(self, request):
        return request.user.is_superuser

# Group model is registered by default to allow superuser to assign group permissions.


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = EmailUserCreationForm
    list_display = ('user_identity', 'role_badge', 'is_active_badge', 'last_login')
    list_display_links = ('user_identity',)
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('email', 'username')
    list_per_page = 25
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Gmail account', {'fields': ('email', 'first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2', 'is_staff', 'is_superuser', 'is_active'),
        }),
    )

    def save_model(self, request, obj, form, change):
        if obj.email and not obj.username:
            obj.username = obj.email
        super().save_model(request, obj, form, change)

    @admin.display(description='User', ordering='email')
    def user_identity(self, obj):
        name = obj.get_full_name() or obj.username
        return format_html('<strong>{}</strong><br><span class="table-subtext">{}</span>', name, obj.email or 'No email address')

    @admin.display(description='Access', ordering='is_superuser')
    def role_badge(self, obj):
        if obj.is_superuser:
            label, css_class = 'Superuser', 'badge-superuser'
        elif obj.is_staff:
            label, css_class = 'Staff admin', 'badge-staff'
        else:
            label, css_class = 'Standard user', 'badge-neutral'
        return format_html('<span class="admin-badge {}">{}</span>', css_class, label)

    @admin.display(description='Status', ordering='is_active')
    def is_active_badge(self, obj):
        label = 'Active' if obj.is_active else 'Inactive'
        css_class = 'badge-active' if obj.is_active else 'badge-inactive'
        return format_html('<span class="admin-badge {}">{}</span>', css_class, label)

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_module_permission(self, request):
        return request.user.is_superuser



@admin.register(Applicant)
class ApplicantAdmin(admin.ModelAdmin):
    list_display = ('applicant_identity', 'status_badge', 'work_setup', 'teaching_account', 'created_at', 'updated_at')
    list_display_links = ('applicant_identity',)
    list_filter = ('status', 'work_setup', 'teaching_account')
    search_fields = ('first_name', 'last_name', 'email')

    @admin.display(description='Applicant', ordering='last_name')
    def applicant_identity(self, obj):
        return format_html('<strong>{}</strong><br><span class="table-subtext">{}</span>', obj.full_name, obj.email)

    @admin.display(description='Stage', ordering='status')
    def status_badge(self, obj):
        status_class = {'Pending': 'badge-pending', 'Initial Screening': 'badge-screening', 'Demo Evaluation': 'badge-demo', 'Endorsement': 'badge-endorsement', 'Training': 'badge-training', 'Onboarding': 'badge-onboarding', 'Approved': 'badge-approved', 'Resign': 'badge-inactive', 'Withdrawn': 'badge-inactive'}.get(obj.status, 'badge-neutral')
        return format_html('<span class="admin-badge {}">{}</span>', status_class, obj.status)


    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 25

    def save_model(self, request, obj, form, change):
        is_new = obj._state.adding
        old_status = None
        if change:
            try:
                old_status = Applicant.objects.get(pk=obj.pk).status
            except Applicant.DoesNotExist:
                pass

        super().save_model(request, obj, form, change)

        if is_new:
            StatusHistory.objects.create(
                applicant=obj,
                status=obj.status,
                notes="Applicant account created by admin.",
                changed_by=request.user
            )
        elif change:
            if old_status and old_status != obj.status:
                StatusHistory.objects.create(
                    applicant=obj,
                    status=obj.status,
                    notes=f"Moved from {old_status} via Django Admin update.",
                    changed_by=request.user
                )
            else:
                StatusHistory.objects.create(
                    applicant=obj,
                    status=obj.status,
                    notes="Updated applicant details via Django Admin.",
                    changed_by=request.user
                )


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('title', 'applicant', 'type', 'scheduled_at', 'completed')
    list_filter = ('type', 'completed')
    search_fields = ('title', 'applicant__first_name', 'applicant__last_name', 'applicant__email')


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ('applicant', 'evaluation_type', 'total_score', 'client_decision', 'created_at')
    list_filter = ('evaluation_type', 'client_decision')
    search_fields = ('applicant__first_name', 'applicant__last_name', 'applicant__email')


@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('activity_timestamp', 'applicant', 'logged_by_display', 'activity_details')
    list_display_links = ('applicant',)
    list_filter = ('status', 'created_at')
    search_fields = ('applicant__first_name', 'applicant__last_name', 'applicant__email', 'notes')
    ordering = ('-created_at',)
    readonly_fields = ('applicant', 'status', 'notes', 'changed_by', 'created_at')
    list_per_page = 25

    @admin.display(description='Timestamp', ordering='created_at')
    def activity_timestamp(self, obj):
        return timezone.localtime(obj.created_at).strftime('%b %d, %Y • %I:%M %p')

    @admin.display(description='Logged By', ordering='changed_by__username')
    def logged_by_display(self, obj):
        if obj.changed_by:
            name = obj.changed_by.get_full_name() or obj.changed_by.username or obj.changed_by.email
            return format_html('<strong>{}</strong><br><span class="table-subtext">{}</span>', name, obj.changed_by.email or 'No email')
        return 'System'

    @admin.display(description='What happened', ordering='status')
    def activity_details(self, obj):
        note = obj.notes or f'Applicant moved to {obj.status}.'
        return format_html('<strong>Moved to {}</strong><br><span class="table-subtext">{}</span>', obj.status, note)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_module_permission(self, request):
        return request.user.is_superuser


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ('timestamp_display', 'admin_user', 'action_label', 'target_object', 'content_type')
    list_filter = ('action_time', 'user', 'content_type', 'action_flag')
    search_fields = ('object_repr', 'change_message', 'user__username', 'user__email')
    ordering = ('-action_time',)
    readonly_fields = ('action_time', 'user', 'content_type', 'object_id', 'object_repr', 'action_flag', 'change_message')
    list_per_page = 25

    @admin.display(description='Timestamp', ordering='action_time')
    def timestamp_display(self, obj):
        return timezone.localtime(obj.action_time).strftime('%b %d, %Y • %I:%M %p')

    @admin.display(description='Admin', ordering='user__username')
    def admin_user(self, obj):
        if obj.user_id:
            name = obj.user.get_full_name() or obj.user.username or obj.user.email or 'Unknown admin'
            return format_html('<strong>{}</strong><br><span class="table-subtext">{}</span>', name, obj.user.email or 'No email')
        return 'System'

    @admin.display(description='Action', ordering='action_flag')
    def action_label(self, obj):
        action_map = {
            1: 'Added',
            2: 'Changed',
            3: 'Deleted',
        }
        return action_map.get(obj.action_flag, 'Unknown')

    @admin.display(description='Target', ordering='object_repr')
    def target_object(self, obj):
        return obj.object_repr or '—'

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_module_permission(self, request):
        return request.user.is_superuser
