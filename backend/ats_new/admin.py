from django.contrib import admin
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group

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

admin.site.site_header = 'Admin User'
admin.site.site_title = 'Admin User'
admin.site.index_title = 'Admin User Management'

try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = EmailUserCreationForm
    list_display = ('email', 'username', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('email', 'username')
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


@admin.register(Applicant)
class ApplicantAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'status', 'work_setup', 'created_at')
    list_filter = ('status', 'work_setup', 'teaching_account')
    search_fields = ('first_name', 'last_name', 'email')
    readonly_fields = ('created_at', 'updated_at')


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
    list_display = ('applicant', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('applicant__first_name', 'applicant__last_name', 'applicant__email', 'notes')
