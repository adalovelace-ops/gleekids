from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase, Client
from django.urls import reverse
from django.utils import timezone

from .admin import LogEntryAdmin, ApplicantAdmin
from .models import Applicant, StatusHistory, Placement


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

    def test_update_profile_records_log(self):
        change_perm = Permission.objects.get(codename='change_applicant')
        self.staff_user.user_permissions.add(change_perm)

        self.client.login(username='staff', password='secret123')
        response = self.client.post(reverse('update_status'), {
            'applicant_id': str(self.applicant.applicant_id),
            'first_name': 'Jonathan',
            'last_name': 'Doe'
        })
        self.assertEqual(response.status_code, 302)

        history_entry = self.applicant.history.latest('created_at')
        self.assertIn("Updated profile details", history_entry.notes)
        self.assertIn("first name", history_entry.notes)
        self.assertEqual(history_entry.changed_by, self.staff_user)

    def test_save_evaluation_redirects_to_popup(self):
        eval_perm = Permission.objects.get(codename='add_evaluation')
        self.staff_user.user_permissions.add(eval_perm)

        self.client.login(username='staff', password='secret123')

        # Test Demo Evaluation redirect
        response = self.client.post(reverse('save_evaluation'), {
            'applicant_identifier': str(self.applicant.applicant_id),
            'evaluation_type': 'demo',
            'teaching_performance_rating': '5',
            'communication_skills_rating': '5',
            'curriculum_understanding_rating': '5',
            'engagement_level_rating': '5',
            'technical_proficiency_rating': '5',
            'overall_comments': 'Excellent job.'
        })
        self.assertEqual(response.status_code, 302)
        expected_url = f"/floating-evaluation/{self.applicant.applicant_id}/?type=demo&saved=1"
        self.assertRedirects(response, expected_url, fetch_redirect_response=False)

        # Test Client Evaluation redirect
        response = self.client.post(reverse('save_evaluation'), {
            'applicant_identifier': str(self.applicant.applicant_id),
            'evaluation_type': 'client',
            'client_decision': 'Pass',
            'overall_comments': 'Endorsed by client.'
        })
        self.assertEqual(response.status_code, 302)
        expected_url_client = f"/floating-evaluation/{self.applicant.applicant_id}/?type=client&saved=1"
        self.assertRedirects(response, expected_url_client, fetch_redirect_response=False)

    def test_update_preferred_demo_time_validation(self):
        session = self.client.session
        session['applicant_id'] = str(self.applicant.applicant_id)
        session.save()

        # Valid slot (2:30 PM)
        response = self.client.post(reverse('applicant_portal'), {
            'action': 'update_preferred_demo_time',
            'preferred_demo_time': '14:30'
        })
        self.assertEqual(response.status_code, 200)
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.preferred_demo_time.strftime('%H:%M'), '14:30')

        # Invalid slot (9:00 AM)
        response = self.client.post(reverse('applicant_portal'), {
            'action': 'update_preferred_demo_time',
            'preferred_demo_time': '09:00'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please select a time between 1:00 PM and 5:00 PM.')

    def test_admin_schedule_demo_time_validation(self):
        self.client.login(username='superuser', password='secret123')

        # Valid admin demo slot (2:00 PM)
        response = self.client.post(reverse('schedule_action'), {
            'applicant_identifier': str(self.applicant.applicant_id),
            'type': 'demo',
            'scheduled_date': '2026-07-20',
            'scheduled_time': '14:00',
            'title': 'Teaching Demo Interview',
            'redirect_to': '/demo-evaluation/'
        })
        self.assertEqual(response.status_code, 302)
        demo_schedule = self.applicant.schedules.filter(type='demo').first()
        self.assertIsNotNone(demo_schedule)
        self.assertEqual(timezone.localtime(demo_schedule.scheduled_at).time().strftime('%H:%M'), '14:00')

        # Invalid admin demo slot (9:00 AM)
        response = self.client.post(reverse('schedule_action'), {
            'applicant_identifier': str(self.applicant.applicant_id),
            'type': 'demo',
            'scheduled_date': '2026-07-20',
            'scheduled_time': '09:00',
            'title': 'Teaching Demo Interview',
            'redirect_to': '/demo-evaluation/'
        })
        self.assertEqual(response.status_code, 302)
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), 'Demo interviews must be scheduled between 1:00 PM and 5:00 PM.')

    def test_admin_schedule_client_time_validation(self):
        self.client.login(username='superuser', password='secret123')

        # Valid admin client slot (9:30 AM)
        response = self.client.post(reverse('schedule_action'), {
            'applicant_identifier': str(self.applicant.applicant_id),
            'type': 'endorsement',
            'scheduled_date': '2026-07-20',
            'scheduled_time': '09:30',
            'title': 'Client Final Interview',
            'redirect_to': '/client-endorsement/'
        })
        self.assertEqual(response.status_code, 302)
        client_schedule = self.applicant.schedules.filter(type='endorsement').first()
        self.assertIsNotNone(client_schedule)
        self.assertEqual(timezone.localtime(client_schedule.scheduled_at).time().strftime('%H:%M'), '09:30')

        # Invalid admin client slot (5:00 AM)
        response = self.client.post(reverse('schedule_action'), {
            'applicant_identifier': str(self.applicant.applicant_id),
            'type': 'endorsement',
            'scheduled_date': '2026-07-20',
            'scheduled_time': '05:00',
            'title': 'Client Final Interview',
            'redirect_to': '/client-endorsement/'
        })
        self.assertEqual(response.status_code, 302)
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), 'Client interviews must be scheduled between 7:00 AM and 11:00 PM.')

    def test_admin_schedule_training_time_validation(self):
        self.client.login(username='superuser', password='secret123')

        # Valid admin training slot (10:00 AM)
        response = self.client.post(reverse('schedule_action'), {
            'applicant_identifier': str(self.applicant.applicant_id),
            'type': 'training',
            'scheduled_date': '2026-07-20',
            'scheduled_time': '10:00',
            'title': 'Recruitment Training Session',
            'redirect_to': '/training-schedule/'
        })
        self.assertEqual(response.status_code, 302)
        training_schedule = self.applicant.schedules.filter(type='training').first()
        self.assertIsNotNone(training_schedule)
        self.assertEqual(timezone.localtime(training_schedule.scheduled_at).time().strftime('%H:%M'), '10:00')

        # Invalid admin training slot (6:00 AM)
        response = self.client.post(reverse('schedule_action'), {
            'applicant_identifier': str(self.applicant.applicant_id),
            'type': 'training',
            'scheduled_date': '2026-07-20',
            'scheduled_time': '06:00',
            'title': 'Recruitment Training Session',
            'redirect_to': '/training-schedule/'
        })
        self.assertEqual(response.status_code, 302)
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), 'Training sessions must be scheduled between 7:00 AM and 11:00 PM.')


class PlacementCRUDTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.User = get_user_model()
        self.superuser = self.User.objects.create_superuser(
            username='superuser',
            email='super@example.com',
            password='secret123'
        )
        self.staff_user = self.User.objects.create_user(
            username='staff',
            email='staff@example.com',
            password='secret123',
            is_staff=True
        )
        # Give view_applicant permission to staff_user
        view_perm = Permission.objects.get(codename='view_applicant')
        self.staff_user.user_permissions.add(view_perm)
        
        self.applicant = Applicant.objects.create(
            first_name='John',
            last_name='Doe',
            email='john.doe@example.com',
            country='Philippines',
            status='Approved'
        )

    def test_placement_crud_requires_login(self):
        response = self.client.get(reverse('placements_list'))
        self.assertEqual(response.status_code, 302)

    def test_placement_crud_view_allowed_for_staff(self):
        self.client.login(username='staff', password='secret123')
        response = self.client.get(reverse('placements_list'))
        self.assertEqual(response.status_code, 200)

    def test_placement_crud_create(self):
        self.client.login(username='superuser', password='secret123')
        response = self.client.post(reverse('placements_list'), {
            'action': 'create',
            'name': 'Korean Account',
            'description': 'Online tutoring for Korean students'
        })
        self.assertEqual(response.status_code, 302)
        korean_placement = Placement.objects.filter(slug='korean-account').first()
        self.assertIsNotNone(korean_placement)
        self.assertEqual(korean_placement.name, 'Korean Account')
        self.assertEqual(korean_placement.description, 'Online tutoring for Korean students')

    def test_placement_crud_update(self):
        self.client.login(username='superuser', password='secret123')
        placement = Placement.objects.create(name='Japanese Account', slug='japanese-account')
        response = self.client.post(reverse('placements_list'), {
            'action': 'update',
            'placement_id': placement.id,
            'name': 'Updated Japanese Account',
            'description': 'Tutoring in Tokyo'
        })
        self.assertEqual(response.status_code, 302)
        placement.refresh_from_db()
        self.assertEqual(placement.name, 'Updated Japanese Account')
        self.assertEqual(placement.description, 'Tutoring in Tokyo')

    def test_placement_crud_delete(self):
        self.client.login(username='superuser', password='secret123')
        placement = Placement.objects.create(name='Spanish Account', slug='spanish-account')
        response = self.client.post(reverse('placements_list'), {
            'action': 'delete',
            'placement_id': placement.id
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Placement.objects.filter(id=placement.id).exists())

    def test_placement_delete_blocked_when_has_applicants(self):
        self.client.login(username='superuser', password='secret123')
        placement = Placement.objects.create(name='French Account', slug='french-account')
        self.applicant.teaching_account = placement
        self.applicant.save()
        
        response = self.client.post(reverse('placements_list'), {
            'action': 'delete',
            'placement_id': placement.id
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Placement.objects.filter(id=placement.id).exists())


class ScheduleActionTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.staff_user = self.User.objects.create_user(
            username='staff_recruiter',
            email='recruiter@example.com',
            password='secret123',
            is_staff=True,
        )
        for perm_code in ['view_schedule', 'change_schedule']:
            perm = Permission.objects.get(codename=perm_code)
            self.staff_user.user_permissions.add(perm)

        self.applicant = Applicant.objects.create(
            first_name='Jane',
            last_name='Smith',
            email='jane.smith@example.com',
            status='Pending'
        )

    def test_schedule_action_with_scheduled_at_field(self):
        self.client.login(username='staff_recruiter', password='secret123')
        response = self.client.post(reverse('schedule_action'), {
            'applicant_identifier': self.applicant.applicant_id,
            'type': 'initial',
            'title': 'Initial Screening',
            'scheduled_at': '2026-07-25T14:30',
            'meeting_link': 'https://zoom.us/j/123456789'
        })
        self.assertEqual(response.status_code, 302)

        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.status, 'Initial Screening')
        sched = self.applicant.schedules.filter(type='initial').first()
        self.assertIsNotNone(sched)
        self.assertEqual(sched.meeting_link, 'https://zoom.us/j/123456789')

    def test_applicant_portal_renders_schedule(self):
        # Create a schedule
        from .models import Schedule
        sched = Schedule.objects.create(
            applicant=self.applicant,
            type='initial',
            title='Initial Screening',
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            meeting_link='https://zoom.us/j/123456789'
        )
        self.applicant.status = 'Initial Screening'
        self.applicant.save()

        # Set session
        session = self.client.session
        session['applicant_id'] = str(self.applicant.applicant_id)
        session.save()

        response = self.client.get(reverse('applicant_portal'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'https://zoom.us/j/123456789')
        self.assertContains(response, 'Your interview is scheduled')


