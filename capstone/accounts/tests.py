from django.test import TestCase
from django.urls import reverse

from .models import Document, InternshipRecord, ReportSubmission, Task, User


class MentorAccessTests(TestCase):
    def setUp(self):
        self.mentor = User.objects.create_user(
            username='mentor', email='mentor@example.com', password='test-password',
            role=User.Roles.MENTOR,
        )
        self.other_mentor = User.objects.create_user(
            username='other-mentor', email='other-mentor@example.com', password='test-password',
            role=User.Roles.MENTOR,
        )
        self.assigned_intern = User.objects.create_user(
            username='assigned-intern', email='assigned@example.com', password='test-password',
            role=User.Roles.INTERN,
        )
        self.unassigned_intern = User.objects.create_user(
            username='unassigned-intern', email='unassigned@example.com', password='test-password',
            role=User.Roles.INTERN,
        )
        InternshipRecord.objects.create(
            intern=self.assigned_intern, student_id='STU-001', course='Computing', mentor=self.mentor,
        )
        InternshipRecord.objects.create(
            intern=self.unassigned_intern, student_id='STU-002', course='Computing', mentor=self.other_mentor,
        )
        self.assigned_document = Document.objects.create(
            intern=self.assigned_intern, name='Assigned document', file='documents/assigned.pdf',
        )
        self.unassigned_document = Document.objects.create(
            intern=self.unassigned_intern, name='Unassigned document', file='documents/unassigned.pdf',
        )
        self.assigned_report = ReportSubmission.objects.create(
            intern=self.assigned_intern, title='Assigned report', file='reports/assigned.pdf',
        )
        self.unassigned_report = ReportSubmission.objects.create(
            intern=self.unassigned_intern, title='Unassigned report', file='reports/unassigned.pdf',
        )
        self.client.force_login(self.mentor)

    def test_mentor_dashboard_and_review_queues_only_show_assigned_interns(self):
        dashboard = self.client.get(reverse('mentor_dashboard'))
        review_queue = self.client.get(reverse('review_documents'))

        self.assertEqual(
            list(dashboard.context['pending_documents'].values_list('pk', flat=True)),
            [self.assigned_document.pk],
        )
        self.assertEqual(
            list(dashboard.context['pending_reports'].values_list('pk', flat=True)),
            [self.assigned_report.pk],
        )
        self.assertEqual(
            list(review_queue.context['documents'].values_list('pk', flat=True)),
            [self.assigned_document.pk],
        )
        self.assertEqual(
            list(review_queue.context['reports'].values_list('pk', flat=True)),
            [self.assigned_report.pk],
        )

    def test_mentor_cannot_review_unassigned_documents_or_reports(self):
        document_response = self.client.post(
            reverse('review_document', args=[self.unassigned_document.pk]),
            {'status': Document.Status.APPROVED},
        )
        report_response = self.client.post(
            reverse('review_documents'),
            {
                'kind': 'report',
                'pk': self.unassigned_report.pk,
                'status': ReportSubmission.Status.APPROVED,
            },
        )

        self.assertEqual(document_response.status_code, 404)
        self.assertEqual(report_response.status_code, 404)
        self.unassigned_document.refresh_from_db()
        self.unassigned_report.refresh_from_db()
        self.assertEqual(self.unassigned_document.status, Document.Status.PENDING)
        self.assertEqual(self.unassigned_report.status, ReportSubmission.Status.PENDING)

    def test_mentor_can_review_assigned_documents_and_reports(self):
        document_response = self.client.post(
            reverse('review_document', args=[self.assigned_document.pk]),
            {'status': Document.Status.APPROVED},
        )
        report_response = self.client.post(
            reverse('review_documents'),
            {
                'kind': 'report',
                'pk': self.assigned_report.pk,
                'status': ReportSubmission.Status.APPROVED,
            },
        )

        self.assertEqual(document_response.status_code, 302)
        self.assertEqual(report_response.status_code, 302)
        self.assigned_document.refresh_from_db()
        self.assigned_report.refresh_from_db()
        self.assertEqual(self.assigned_document.status, Document.Status.APPROVED)
        self.assertEqual(self.assigned_report.status, ReportSubmission.Status.APPROVED)

    def test_admin_can_review_unassigned_submissions(self):
        admin = User.objects.create_user(
            username='test-admin', email='test-admin@example.com', password='test-password',
            role=User.Roles.ADMIN,
        )
        self.client.force_login(admin)

        document_response = self.client.post(
            reverse('review_document', args=[self.unassigned_document.pk]),
            {'status': Document.Status.APPROVED},
        )
        report_response = self.client.post(
            reverse('review_documents'),
            {
                'kind': 'report',
                'pk': self.unassigned_report.pk,
                'status': ReportSubmission.Status.APPROVED,
            },
        )

        self.assertEqual(document_response.status_code, 302)
        self.assertEqual(report_response.status_code, 302)


class TaskManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='task-admin', email='task-admin@example.com', password='test-password',
            role=User.Roles.ADMIN,
        )
        self.assignee = User.objects.create_user(
            username='assignee', email='assignee@example.com', password='test-password',
            role=User.Roles.ADMIN,
        )
        self.mentor = User.objects.create_user(
            username='task-mentor', email='task-mentor@example.com', password='test-password',
            role=User.Roles.MENTOR,
        )

    def test_admin_can_create_assign_and_complete_task(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('task_create'), {
            'title': 'Review submissions',
            'description': 'Check this week',
            'assigned_to': self.assignee.pk,
            'priority': Task.Priority.HIGH,
            'status': Task.Status.PENDING,
            'due_date': '2026-10-20',
        })

        self.assertRedirects(response, reverse('admin_dashboard'))
        task = Task.objects.get(title='Review submissions')
        self.assertEqual(task.assigned_to, self.assignee)
        self.assertEqual(task.created_by, self.admin)

        response = self.client.post(reverse('task_update_status', args=[task.pk]), {
            'status': Task.Status.COMPLETED,
        })
        self.assertRedirects(response, reverse('admin_dashboard'))
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.COMPLETED)
        self.assertIsNotNone(task.completed_at)

    def test_assigned_admin_can_update_status_and_other_roles_cannot(self):
        task = Task.objects.create(title='Assigned', assigned_to=self.assignee, created_by=self.admin)
        self.client.force_login(self.assignee)
        allowed = self.client.post(reverse('task_update_status', args=[task.pk]), {
            'status': Task.Status.IN_PROGRESS,
        })
        self.assertEqual(allowed.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.IN_PROGRESS)

        self.client.force_login(self.mentor)
        denied = self.client.post(reverse('task_update_status', args=[task.pk]), {
            'status': Task.Status.COMPLETED,
        })
        self.assertEqual(denied.status_code, 403)

    def test_admin_dashboard_filters_tasks_and_counts_overdue(self):
        overdue = Task.objects.create(
            title='Overdue task', assigned_to=self.assignee, created_by=self.admin,
            due_date='2026-09-30', priority=Task.Priority.URGENT,
        )
        Task.objects.create(
            title='Finished task', assigned_to=self.admin, created_by=self.admin,
            due_date='2026-09-30', status=Task.Status.COMPLETED,
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse('admin_dashboard'), {
            'task_q': 'Overdue', 'task_assignee': str(self.assignee.pk),
            'task_status': Task.Status.PENDING, 'task_priority': Task.Priority.URGENT,
            'task_due_date': '2026-09-30',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Task Management')
        self.assertEqual(list(response.context['tasks']), [overdue])
        self.assertEqual(response.context['task_counts']['overdue'], 1)

    def test_non_admin_cannot_create_tasks(self):
        self.client.force_login(self.mentor)
        response = self.client.post(reverse('task_create'), {'title': 'Not allowed'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Task.objects.exists())