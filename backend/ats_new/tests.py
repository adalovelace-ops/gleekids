from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase, Client
from django.urls import reverse

from .admin import LogEntryAdmin, ApplicantAdmin
from .models import Applicant, StatusHistory


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

    def test_log_entry_admin_blocks_staff_even_with_permission(self):
        # Even with the view_logentry permission, non-superuser staff users are blocked
        admin_instance = LogEntryAdmin(LogEntry, admin.site)
        
        view_logentry = Permission.objects.get(codename='view_logentry')
        self.staff_user.user_permissions.add(view_logentry)
        self.staff_user = self.User.objects.get(pk=self.staff_user.pk) # Refresh permissions cache

        request = self.factory.get('/admin/')
        request.user = self.staff_user
        self.assertFalse(admin_instance.has_module_permission(request))
        self.assertFalse(admin_instance.has_view_permission(request))


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

    def test_status_history_admin_superuser_only(self):
        from .admin import StatusHistoryAdmin
        from .models import StatusHistory
        admin_instance = StatusHistoryAdmin(StatusHistory, admin.site)

        # Superuser has access
        request = self.factory.get('/admin/')
        request.user = self.superuser
        self.assertTrue(admin_instance.has_module_permission(request))
        self.assertTrue(admin_instance.has_view_permission(request))

        # Staff user is blocked, even if they have view_statushistory permission
        view_history = Permission.objects.get(codename='view_statushistory')
        self.staff_user.user_permissions.add(view_history)
        self.staff_user = self.User.objects.get(pk=self.staff_user.pk)
        
        request.user = self.staff_user
        self.assertFalse(admin_instance.has_module_permission(request))
        self.assertFalse(admin_instance.has_view_permission(request))

    def test_user_and_group_admin_superuser_only(self):
        from django.contrib.auth.models import Group
        from .admin import UserAdmin, GroupAdmin

        user_admin = UserAdmin(self.User, admin.site)
        group_admin = GroupAdmin(Group, admin.site)

        # Superuser has access
        request = self.factory.get('/admin/')
        request.user = self.superuser
        self.assertTrue(user_admin.has_module_permission(request))
        self.assertTrue(user_admin.has_view_permission(request))
        self.assertTrue(group_admin.has_module_permission(request))
        self.assertTrue(group_admin.has_view_permission(request))

        # Staff user is blocked, even if they have view_user/view_group permissions
        view_user = Permission.objects.get(codename='view_user')
        view_group = Permission.objects.get(codename='view_group')
        self.staff_user.user_permissions.add(view_user, view_group)
        self.staff_user = self.User.objects.get(pk=self.staff_user.pk)

        request.user = self.staff_user
        self.assertFalse(user_admin.has_module_permission(request))
        self.assertFalse(user_admin.has_view_permission(request))
        self.assertFalse(group_admin.has_module_permission(request))
        self.assertFalse(group_admin.has_view_permission(request))


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

    def test_update_status_records_changed_by_user(self):
        change_perm = Permission.objects.get(codename='change_applicant')
        self.staff_user.user_permissions.add(change_perm)

        self.client.login(username='staff', password='secret123')
        response = self.client.post(reverse('update_status'), {
            'applicant_id': str(self.applicant.applicant_id),
            'new_status': 'Initial Screening',
            'status_note': 'Passed initial check.'
        })
        self.assertEqual(response.status_code, 302)

        history_entry = self.applicant.history.latest('created_at')
        self.assertEqual(history_entry.status, 'Initial Screening')
        self.assertEqual(history_entry.changed_by, self.staff_user)

    def test_status_history_logged_by_name_property(self):
        # Case 1: System
        history_entry_sys = StatusHistory.objects.create(
            applicant=self.applicant,
            status='Pending',
            notes='Auto'
        )
        self.assertEqual(history_entry_sys.logged_by_name, 'System')

        # Case 2: User with first/last name
        self.staff_user.first_name = 'Thea'
        self.staff_user.last_name = 'Salinas'
        self.staff_user.save()
        history_entry_user = StatusHistory.objects.create(
            applicant=self.applicant,
            status='Pending',
            notes='Manual',
            changed_by=self.staff_user
        )
        self.assertEqual(history_entry_user.logged_by_name, 'Thea Salinas')

        # Case 3: User with no name, username is email
        self.staff_user.first_name = ''
        self.staff_user.last_name = ''
        self.staff_user.username = 'salinas.thea2021@gmail.com'
        self.staff_user.save()
        self.assertEqual(history_entry_user.logged_by_name, 'Salinas Thea2021')
