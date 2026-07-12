from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase, Client
from django.urls import reverse

from .admin import LogEntryAdmin, ApplicantAdmin
from .models import Applicant


class LogEntryAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.User = get_user_model()
        self.superuser = self.User.objects.create_superuser(
            username='superuser',
            email='super@example.com',
            password='secret123',
        )
        self.staff_user = self.User.objects.create_user(
            username='staff',
            email='staff@example.com',
            password='secret123',
            is_staff=True,
        )

    def test_log_entry_admin_shows_timestamped_columns(self):
        admin_instance = LogEntryAdmin(LogEntry, admin.site)

        self.assertIn('timestamp_display', admin_instance.list_display)
        self.assertIn('admin_user', admin_instance.list_display)
        self.assertIn('action_label', admin_instance.list_display)
        self.assertIn('target_object', admin_instance.list_display)

    def test_log_entry_admin_is_superuser_only_by_default(self):
        # By default, a staff user without view_logentry permission cannot access it
        admin_instance = LogEntryAdmin(LogEntry, admin.site)

        request = self.factory.get('/admin/')
        request.user = self.staff_user
        self.assertFalse(admin_instance.has_module_permission(request))

        request.user = self.superuser
        self.assertTrue(admin_instance.has_module_permission(request))

    def test_log_entry_admin_allows_staff_with_permission(self):
        # A staff user with explicitly granted view_logentry permission can access it
        admin_instance = LogEntryAdmin(LogEntry, admin.site)
        
        view_logentry = Permission.objects.get(codename='view_logentry')
        self.staff_user.user_permissions.add(view_logentry)
        self.staff_user = self.User.objects.get(pk=self.staff_user.pk) # Refresh permissions cache

        request = self.factory.get('/admin/')
        request.user = self.staff_user
        self.assertTrue(admin_instance.has_module_permission(request))


class AdminPermissionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.User = get_user_model()
        self.superuser = self.User.objects.create_superuser(
            username='superuser',
            email='super@example.com',
            password='secret123',
        )
        self.staff_user = self.User.objects.create_user(
            username='staff',
            email='staff@example.com',
            password='secret123',
            is_staff=True,
        )
        self.applicant_admin = ApplicantAdmin(Applicant, admin.site)

    def test_applicant_admin_permissions_by_default(self):
        # Staff user without permissions has no access
        request = self.factory.get('/admin/')
        request.user = self.staff_user
        self.assertFalse(self.applicant_admin.has_module_permission(request))
        self.assertFalse(self.applicant_admin.has_view_permission(request))
        self.assertFalse(self.applicant_admin.has_delete_permission(request))

    def test_applicant_admin_permissions_granted(self):
        # Grant view_applicant permission
        view_perm = Permission.objects.get(codename='view_applicant')
        self.staff_user.user_permissions.add(view_perm)
        self.staff_user = self.User.objects.get(pk=self.staff_user.pk)

        request = self.factory.get('/admin/')
        request.user = self.staff_user
        self.assertTrue(self.applicant_admin.has_module_permission(request))
        self.assertTrue(self.applicant_admin.has_view_permission(request))
        self.assertFalse(self.applicant_admin.has_delete_permission(request))


class DashboardViewPermissionTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.client = Client()
        self.superuser = self.User.objects.create_superuser(
            username='superuser',
            email='super@example.com',
            password='secret123',
        )
        self.staff_user = self.User.objects.create_user(
            username='staff',
            email='staff@example.com',
            password='secret123',
            is_staff=True,
        )
        self.applicant = Applicant.objects.create(
            first_name='John',
            last_name='Doe',
            email='john@example.com',
            status='Pending'
        )

    def test_dashboard_view_unauthenticated(self):
        # Redirects to login
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_view_staff_no_permissions(self):
        self.client.login(username='staff', password='secret123')
        response = self.client.get(reverse('admin_dashboard'))
        # Lack of 'view_applicant' permission causes 403 Forbidden
        self.assertEqual(response.status_code, 403)

    def test_dashboard_view_staff_with_permission(self):
        view_perm = Permission.objects.get(codename='view_applicant')
        self.staff_user.user_permissions.add(view_perm)

        self.client.login(username='staff', password='secret123')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_delete_applicant_view_staff_no_permission(self):
        self.client.login(username='staff', password='secret123')
        response = self.client.post(reverse('delete_applicant', args=[self.applicant.applicant_id]))
        # 403 Forbidden since staff lacks delete_applicant
        self.assertEqual(response.status_code, 403)

    def test_delete_applicant_view_staff_with_permission(self):
        delete_perm = Permission.objects.get(codename='delete_applicant')
        self.staff_user.user_permissions.add(delete_perm)

        self.client.login(username='staff', password='secret123')
        response = self.client.post(reverse('delete_applicant', args=[self.applicant.applicant_id]))
        self.assertEqual(response.status_code, 302) # Redirects on successful delete
        self.assertFalse(Applicant.objects.filter(pk=self.applicant.pk).exists())
