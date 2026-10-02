from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
import mimetypes
import calendar
from datetime import date

from django.http import FileResponse, Http404, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.views.decorators.http import require_POST

from .decorators import admin_required, intern_required, mentor_required, role_required
from .forms import (AgendaForm, AnnouncementForm, AttendanceForm, DocumentForm, EvaluationForm,
                    InternUserForm, InternshipRecordForm, LoginForm, ProfileForm,
                    RegistrationForm, ReportSubmissionForm, PhotoSubmissionForm, TaskForm)
from .models import (Agenda, Announcement, Attendance, Document, InternProfile, InternshipRecord,
                     PerformanceEvaluation, PhotoSubmission, ReportSubmission, Task, User)

User = get_user_model()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if not user.is_active:
                messages.error(request, 'Your account has been deactivated. Contact your coordinator.')
                return render(request, 'login.html', {'form': form})
            login(request, user)
            messages.success(request, f'Welcome back, {user.first_name or user.username}!')
            return redirect('home')
        messages.error(request, 'Invalid username/email or password.')
    return render(request, 'login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def home(request):
    if request.user.is_admin_role:
        return redirect('admin_dashboard')
    if request.user.is_mentor_role:
        return redirect('mentor_dashboard')
    return redirect('intern_dashboard')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, 'Your intern account has been created.')
        return redirect('intern_dashboard')
    return render(request, 'registration/register.html', {'form': form})


# ---------------------------------------------------------------------------
# Intern views
# ---------------------------------------------------------------------------

@intern_required
def intern_dashboard(request):
    submissions = request.user.submissions.all()
    stats = submissions.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status=PhotoSubmission.Status.PENDING)),
        approved=Count('id', filter=Q(status=PhotoSubmission.Status.APPROVED)),
        rejected=Count('id', filter=Q(status=PhotoSubmission.Status.REJECTED)),
    )
    context = {
        'stats': stats,
        'profile': getattr(request.user, 'profile', None),
        'announcements': Announcement.objects.all()[:5],
        'recent': submissions[:5],
        'active_page': 'dashboard',
    }
    return render(request, 'intern/dashboard.html', context)


@intern_required
def submit_photo(request):
    if request.method == 'POST':
        form = PhotoSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.intern = request.user
            submission.save()
            messages.success(request, 'Photo submitted successfully! It is now pending review.')
            return redirect('my_submissions')
        messages.error(request, 'Please fix the errors below.')
    else:
        form = PhotoSubmissionForm()
    return render(request, 'intern/submit_photo.html', {'form': form, 'active_page': 'submit'})


@intern_required
def my_submissions(request):
    submissions = request.user.submissions.all()
    status = request.GET.get('status', '')
    if status in dict(PhotoSubmission.Status.choices):
        submissions = submissions.filter(status=status)
    return render(request, 'intern/submissions.html', {
        'submissions': submissions,
        'status': status,
        'choices': PhotoSubmission.Status.choices,
        'active_page': 'submissions',
    })


@intern_required
def intern_profile(request):
    profile = getattr(request.user, 'profile', None)
    documents = request.user.documents.select_related('reviewed_by')
    document_form = DocumentForm()

    if request.method == 'POST':
        if request.POST.get('form_kind') != 'document':
            return HttpResponseForbidden('Invalid form submission.')

        document_form = DocumentForm(request.POST, request.FILES)
        if document_form.is_valid():
            document = document_form.save(commit=False)
            document.intern = request.user
            document.status = Document.Status.PENDING
            document.save()
            messages.success(request, 'Document uploaded successfully. It is now pending review.')
            return redirect('intern_profile')

        messages.error(request, 'Please fix the document errors below.')

    return render(request, 'intern/profile.html', {
        'profile': profile,
        'documents': documents,
        'document_form': document_form,
        'active_page': 'profile',
    })


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------

def _submission_stats(queryset=None):
    qs = queryset if queryset is not None else PhotoSubmission.objects.all()
    return qs.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status=PhotoSubmission.Status.PENDING)),
        approved=Count('id', filter=Q(status=PhotoSubmission.Status.APPROVED)),
        rejected=Count('id', filter=Q(status=PhotoSubmission.Status.REJECTED)),
    )


def _document_stats(queryset=None):
    documents = queryset if queryset is not None else Document.objects.all()
    return documents.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status=Document.Status.PENDING)),
        approved=Count('id', filter=Q(status=Document.Status.APPROVED)),
        rejected=Count('id', filter=Q(status=Document.Status.REJECTED)),
    )


def _scope_to_mentor_interns(queryset, user):
    if user.is_mentor_role and not user.is_admin_role:
        return queryset.filter(intern__internship_record__mentor=user)
    return queryset


def _can_access_document(user, document):
    return user.is_admin_role or document.intern_id == user.id


def _review_document(request, document):
    if request.method != 'POST':
        return redirect('review_documents')

    new_status = request.POST.get('status')
    if new_status not in (Document.Status.APPROVED, Document.Status.REJECTED):
        return HttpResponseForbidden('Invalid review status.')

    document.status = new_status
    document.feedback = request.POST.get('feedback', '').strip()
    document.reviewed_by = request.user
    document.reviewed_at = timezone.now()
    document.save(update_fields=['status', 'feedback', 'reviewed_by', 'reviewed_at'])
    messages.success(
        request,
        f'"{document.name}" was marked as {document.get_status_display().lower()}.',
    )

    next_url = request.POST.get('next')
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = None
    return redirect(next_url or 'review_documents')


@login_required
def document_file(request, pk, action='download'):
    if action not in ('view', 'download'):
        return HttpResponseForbidden('Invalid file action.')

    document = get_object_or_404(Document.objects.select_related('intern'), pk=pk)
    if not _can_access_document(request.user, document):
        return HttpResponseForbidden('You do not have access to this document.')
    if not document.file:
        raise Http404('The requested document file no longer exists.')

    content_type, _ = mimetypes.guess_type(document.file.name)
    document.file.open('rb')
    response = FileResponse(
        document.file,
        as_attachment=action == 'download',
        filename=document.file.name,
    )
    if action == 'view' and content_type:
        response['Content-Type'] = content_type
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@mentor_required
def review_document(request, pk):
    documents = _scope_to_mentor_interns(Document.objects.all(), request.user)
    document = get_object_or_404(documents, pk=pk)
    return _review_document(request, document)


@admin_required
def admin_dashboard(request):
    interns = User.objects.filter(role=User.Roles.INTERN)
    tasks = Task.objects.select_related('assigned_to', 'created_by')
    task_query = request.GET.get('task_q', '').strip()
    task_assignee = request.GET.get('task_assignee', '')
    task_status = request.GET.get('task_status', '')
    task_priority = request.GET.get('task_priority', '')
    task_due_date = request.GET.get('task_due_date', '')
    if task_query:
        tasks = tasks.filter(title__icontains=task_query)
    if task_assignee.isdigit():
        tasks = tasks.filter(assigned_to_id=task_assignee)
    if task_status in Task.Status.values:
        tasks = tasks.filter(status=task_status)
    if task_priority in Task.Priority.values:
        tasks = tasks.filter(priority=task_priority)
    if task_due_date:
        try:
            tasks = tasks.filter(due_date=date.fromisoformat(task_due_date))
        except ValueError:
            task_due_date = ''
    task_counts = Task.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status=Task.Status.PENDING)),
        in_progress=Count('id', filter=Q(status=Task.Status.IN_PROGRESS)),
        completed=Count('id', filter=Q(status=Task.Status.COMPLETED)),
        overdue=Count('id', filter=Q(
            due_date__lt=timezone.localdate(),
            status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
        )),
    )
    today = timezone.localdate()
    month = request.GET.get('month', '')
    try:
        month_start = date.fromisoformat(f'{month}-01')
    except ValueError:
        month_start = today.replace(day=1)

    weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(
        month_start.year, month_start.month,
    )
    visible_start = weeks[0][0]
    visible_end = weeks[-1][-1]
    agendas_by_date = {}
    for agenda in Agenda.objects.filter(date__range=(visible_start, visible_end)):
        agendas_by_date.setdefault(agenda.date, []).append(agenda)
    calendar_days = [
        {
            'date': day,
            'in_month': day.month == month_start.month,
            'agendas': agendas_by_date.get(day, []),
        }
        for week in weeks for day in week
    ]
    previous_month = (month_start.replace(day=1) - timezone.timedelta(days=1)).replace(day=1)
    next_month = (month_start.replace(day=28) + timezone.timedelta(days=4)).replace(day=1)
    context = {
        'total_interns': interns.count(),
        'active_interns': interns.filter(is_active=True).count(),
        'inactive_interns': interns.filter(is_active=False).count(),
        'stats': _submission_stats(),
        'pending_submissions': PhotoSubmission.objects.filter(
            status=PhotoSubmission.Status.PENDING)[:8],
        'recent_submissions': PhotoSubmission.objects.all()[:8],
        'announcements': Announcement.objects.all()[:5],
        'calendar_days': calendar_days,
        'calendar_month': month_start.strftime('%B %Y'),
        'calendar_month_value': month_start.strftime('%Y-%m'),
        'calendar_weekdays': ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
        'today': today,
        'previous_month': previous_month.strftime('%Y-%m'),
        'next_month': next_month.strftime('%Y-%m'),
        'agenda_form': AgendaForm(),
        'tasks': tasks,
        'task_counts': task_counts,
        'task_form': TaskForm(),
        'task_admins': User.objects.filter(
            Q(role=User.Roles.ADMIN) | Q(is_superuser=True), is_active=True,
        ).order_by('first_name', 'last_name', 'username'),
        'task_filters': {
            'q': task_query, 'assignee': task_assignee, 'status': task_status,
            'priority': task_priority, 'due_date': task_due_date,
        },
        'active_page': 'dashboard',
    }
    return render(request, 'admin/dashboard.html', context)


@admin_required
@require_POST
def task_create(request):
    form = TaskForm(request.POST)
    if form.is_valid():
        task = form.save(commit=False)
        task.created_by = request.user
        task.save()
        if task.status == Task.Status.COMPLETED:
            task.completed_at = timezone.now()
            task.save(update_fields=['completed_at', 'updated_at'])
        messages.success(request, 'Task created.')
    else:
        messages.error(request, 'Please check the task details and try again.')
    return redirect('admin_dashboard')


@admin_required
@require_POST
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)
    form = TaskForm(request.POST, instance=task)
    if form.is_valid():
        was_completed = task.status == Task.Status.COMPLETED
        task = form.save(commit=False)
        if task.status == Task.Status.COMPLETED:
            task.completed_at = task.completed_at or timezone.now()
        elif was_completed:
            task.completed_at = None
        task.save()
        messages.success(request, 'Task updated.')
    else:
        messages.error(request, 'Please check the task details and try again.')
    return redirect('admin_dashboard')


@login_required
@require_POST
def task_update_status(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not request.user.is_admin_role:
        return HttpResponseForbidden()
    status = request.POST.get('status')
    if status not in Task.Status.values:
        messages.error(request, 'Choose a valid task status.')
        return redirect('admin_dashboard')
    task.status = status
    if status == Task.Status.COMPLETED:
        task.completed_at = task.completed_at or timezone.now()
    else:
        task.completed_at = None
    task.save(update_fields=['status', 'completed_at', 'updated_at'])
    messages.success(request, 'Task status updated.')
    return redirect('admin_dashboard')


@admin_required
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    task.delete()
    messages.success(request, 'Task deleted.')
    return redirect('admin_dashboard')


def _agenda_dashboard_redirect(request):
    month = request.POST.get('month', '')
    try:
        valid_month = date.fromisoformat(f'{month}-01').strftime('%Y-%m') == month
    except ValueError:
        valid_month = False
    if valid_month:
        return HttpResponseRedirect(f"{reverse('admin_dashboard')}?month={month}")
    return redirect('admin_dashboard')


@admin_required
@require_POST
def agenda_create(request):
    form = AgendaForm(request.POST)
    if form.is_valid():
        agenda = form.save(commit=False)
        agenda.created_by = request.user
        agenda.save()
        messages.success(request, 'Agenda added to the calendar.')
    else:
        messages.error(request, 'Please check the agenda details and try again.')
    return _agenda_dashboard_redirect(request)


@admin_required
@require_POST
def agenda_edit(request, pk):
    agenda = get_object_or_404(Agenda, pk=pk)
    form = AgendaForm(request.POST, instance=agenda)
    if form.is_valid():
        form.save()
        messages.success(request, 'Agenda updated.')
    else:
        messages.error(request, 'Please check the agenda details and try again.')
    return _agenda_dashboard_redirect(request)


@admin_required
@require_POST
def agenda_delete(request, pk):
    agenda = get_object_or_404(Agenda, pk=pk)
    agenda.delete()
    messages.success(request, 'Agenda deleted.')
    return _agenda_dashboard_redirect(request)


@admin_required
def intern_list(request):
    interns = User.objects.filter(role=User.Roles.INTERN).select_related('profile').order_by('last_name')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    company = request.GET.get('company', '').strip()

    if q:
        interns = interns.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) |
            Q(username__icontains=q) | Q(email__icontains=q) |
            Q(profile__student_number__icontains=q)
        )
    if status == 'active':
        interns = interns.filter(is_active=True)
    elif status == 'inactive':
        interns = interns.filter(is_active=False)
    if company:
        interns = interns.filter(profile__company_name__icontains=company)

    return render(request, 'admin/intern_list.html', {
        'interns': interns,
        'q': q, 'status': status, 'company': company,
        'active_page': 'interns',
    })


@admin_required
def intern_detail(request, pk):
    intern = get_object_or_404(User, pk=pk, role=User.Roles.INTERN)
    submissions = intern.submissions.all()
    documents = intern.documents.select_related('reviewed_by')
    return render(request, 'admin/intern_detail.html', {
        'intern': intern,
        'profile': getattr(intern, 'profile', None),
        'submissions': submissions,
        'stats': _submission_stats(submissions),
        'documents': documents,
        'document_stats': _document_stats(documents),
        'active_page': 'interns',
    })


@admin_required
def intern_create(request):
    if request.method == 'POST':
        form = InternUserForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Intern account for {user.get_full_name() or user.username} created.')
            return redirect('intern_detail', pk=user.pk)
        messages.error(request, 'Please fix the errors below.')
    else:
        form = InternUserForm()
    return render(request, 'admin/intern_form.html', {
        'form': form, 'active_page': 'interns', 'title': 'Add New Intern',
    })


@admin_required
def intern_edit(request, pk):
    intern = get_object_or_404(User, pk=pk, role=User.Roles.INTERN)
    if request.method == 'POST':
        form = InternUserForm(request.POST, instance=intern)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Intern {user.get_full_name() or user.username} updated.')
            return redirect('intern_detail', pk=user.pk)
        messages.error(request, 'Please fix the errors below.')
    else:
        form = InternUserForm(instance=intern)
    return render(request, 'admin/intern_form.html', {
        'form': form, 'active_page': 'interns', 'title': f'Edit Intern: {intern.get_full_name() or intern.username}',
        'intern': intern,
    })


@admin_required
def intern_delete(request, pk):
    intern = get_object_or_404(User, pk=pk, role=User.Roles.INTERN)
    if request.method == 'POST':
        confirm = request.POST.get('confirm_name', '')
        if confirm == intern.username:
            name = intern.get_full_name() or intern.username
            intern.delete()
            messages.success(request, f'Intern {name} and all their submissions were deleted.')
            return redirect('intern_list')
        messages.error(request, 'Confirmation failed. Type the username exactly to delete.')
    return render(request, 'admin/intern_confirm_delete.html', {
        'intern': intern, 'active_page': 'interns',
    })


@admin_required
def admin_submissions(request):
    submissions = PhotoSubmission.objects.select_related('intern').all()
    status = request.GET.get('status', '')
    intern_id = request.GET.get('intern', '')
    q = request.GET.get('q', '').strip()

    if status in dict(PhotoSubmission.Status.choices):
        submissions = submissions.filter(status=status)
    if intern_id:
        submissions = submissions.filter(intern_id=intern_id)
    if q:
        submissions = submissions.filter(
            Q(intern__first_name__icontains=q) | Q(intern__last_name__icontains=q) |
            Q(intern__username__icontains=q) | Q(caption__icontains=q)
        )
    return render(request, 'admin/submissions.html', {
        'submissions': submissions,
        'stats': _submission_stats(),
        'choices': PhotoSubmission.Status.choices,
        'interns': User.objects.filter(role=User.Roles.INTERN, is_active=True),
        'status': status, 'intern_id': intern_id, 'q': q,
        'active_page': 'submissions',
    })


@admin_required
def review_submission(request, pk):
    submission = get_object_or_404(PhotoSubmission.objects.select_related('intern'), pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        feedback = request.POST.get('feedback', '').strip()
        if action not in ('approve', 'reject'):
            return HttpResponseForbidden('Invalid action.')
        submission.status = (PhotoSubmission.Status.APPROVED if action == 'approve'
                             else PhotoSubmission.Status.REJECTED)
        submission.feedback = feedback
        submission.reviewed_at = timezone.now()
        submission.reviewed_by = request.user
        submission.save()
        label = 'approved' if action == 'approve' else 'rejected'
        messages.success(request, f'Submission by {submission.intern.get_full_name() or submission.intern.username} {label}.')
        return redirect(request.POST.get('next') or 'admin_submissions')
    return render(request, 'admin/review_submission.html', {
        'submission': submission, 'active_page': 'submissions',
    })


@admin_required
def announcements(request):
    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.created_by = request.user
            announcement.save()
            messages.success(request, 'Announcement published.')
            return redirect('announcements')
        messages.error(request, 'Please fix the errors below.')
    else:
        form = AnnouncementForm()
    return render(request, 'admin/announcements.html', {
        'form': form,
        'announcements': Announcement.objects.all(),
        'active_page': 'announcements',
    })


# ---------------------------------------------------------------------------
# Internship management portal
# ---------------------------------------------------------------------------

@login_required
def portal_dashboard(request):
    user = request.user
    if user.is_admin_role:
        records = InternshipRecord.objects.select_related('intern', 'mentor')
        documents = Document.objects.select_related('intern')
        reports = ReportSubmission.objects.select_related('intern')
        context = {'role_label': 'Administrator', 'records': records[:8],
                   'pending_documents': documents.filter(status='PENDING')[:6],
                   'pending_reports': reports.filter(status='PENDING')[:6],
                   'intern_count': User.objects.filter(role='INTERN').count()}
    elif user.is_mentor_role:
        records = InternshipRecord.objects.filter(mentor=user).select_related('intern')
        documents = _scope_to_mentor_interns(Document.objects.select_related('intern'), user)
        reports = _scope_to_mentor_interns(ReportSubmission.objects.select_related('intern'), user)
        context = {'role_label': 'Mentor / Instructor', 'records': records,
                   'pending_documents': documents.filter(status='PENDING')[:6],
                   'pending_reports': reports.filter(status='PENDING')[:6],
                   'intern_count': records.count()}
    else:
        record = InternshipRecord.objects.filter(intern=user).first()
        context = {'role_label': 'Intern / Student', 'record': record,
                   'documents': user.documents.all()[:5], 'reports': user.reports.all()[:5],
                   'attendance': user.attendance_records.all()[:5],
                   'evaluations': user.evaluations.all()[:3],
                   'completed_hours': record.completed_hours if record else 0,
                   'remaining_hours': record.remaining_hours if record else 0}
    context.update({'announcements': Announcement.objects.all()[:5], 'active_page': 'dashboard'})
    return render(request, 'portal/dashboard.html', context)


@login_required
def profile_edit(request):
    profile, _ = InternProfile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Profile updated successfully.')
        return redirect('profile_edit')
    return render(request, 'portal/form.html', {'form': form, 'title': 'Profile Management', 'active_page': 'profile'})


@login_required
def user_management(request):
    if not request.user.is_admin_role:
        return redirect('profile_edit')
    if request.method == 'POST':
        user = get_object_or_404(User, pk=request.POST.get('user_id'))
        role = request.POST.get('role')
        if role in User.Roles.values and user != request.user:
            user.role = role
            user.is_staff = role == User.Roles.ADMIN
            user.save(update_fields=['role', 'is_staff'])
            messages.success(request, f'{user.username} role updated.')
        return redirect('user_management')
    return render(request, 'portal/users.html', {'users': User.objects.all().order_by('last_name', 'username'), 'roles': User.Roles.choices, 'active_page': 'users'})


@login_required
def record_list(request):
    records = InternshipRecord.objects.select_related('intern', 'mentor')
    if request.user.is_mentor_role:
        records = records.filter(mentor=request.user)
    elif not request.user.is_admin_role:
        records = records.filter(intern=request.user)
    query = request.GET.get('q', '').strip()
    if query:
        records = records.filter(Q(intern__first_name__icontains=query) | Q(intern__last_name__icontains=query) | Q(student_id__icontains=query))
    return render(request, 'portal/records.html', {'records': records, 'q': query, 'active_page': 'records'})


@admin_required
def record_create(request):
    form = InternshipRecordForm(request.POST or None)
    form.fields['intern'].queryset = User.objects.filter(role='INTERN')
    form.fields['mentor'].queryset = User.objects.filter(role='MENTOR')
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Internship record created.')
        return redirect('record_list')
    return render(request, 'portal/form.html', {'form': form, 'title': 'Add Internship Record', 'active_page': 'records'})


@admin_required
def record_edit(request, pk):
    record = get_object_or_404(InternshipRecord, pk=pk)
    form = InternshipRecordForm(request.POST or None, instance=record)
    form.fields['intern'].queryset = User.objects.filter(role='INTERN')
    form.fields['mentor'].queryset = User.objects.filter(role='MENTOR')
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Internship record updated.')
        return redirect('record_list')
    return render(request, 'portal/form.html', {'form': form, 'title': 'Update Internship Record', 'active_page': 'records'})


@admin_required
def record_delete(request, pk):
    record = get_object_or_404(InternshipRecord, pk=pk)
    if request.method == 'POST':
        record.delete()
        messages.success(request, 'Internship record deleted.')
        return redirect('record_list')
    return render(request, 'portal/confirm.html', {'title': 'Delete Internship Record', 'object': record, 'active_page': 'records'})


@intern_required
def documents(request):
    form = DocumentForm()
    report_form = ReportSubmissionForm()
    if request.method == 'POST':
        form_kind = request.POST.get('form_kind')
        if form_kind not in ('document', 'report'):
            return HttpResponseForbidden('Invalid form submission.')
        active_form = (DocumentForm(request.POST, request.FILES)
                       if form_kind == 'document'
                       else ReportSubmissionForm(request.POST, request.FILES))
        if active_form.is_valid():
            item = active_form.save(commit=False)
            item.intern = request.user
            item.save()
            messages.success(request, 'Document uploaded successfully. It is now pending review.'
                             if form_kind == 'document' else 'Report submitted successfully.')
            return redirect('documents')
        messages.error(request, 'Please fix the errors below.')
        if form_kind == 'document':
            form = active_form
        else:
            report_form = active_form
    return render(request, 'portal/documents.html', {
        'documents': request.user.documents.select_related('reviewed_by'),
        'reports': request.user.reports.select_related('reviewed_by'),
        'form': form,
        'report_form': report_form,
        'active_page': 'documents',
    })


@mentor_required
def review_documents(request):
    documents = _scope_to_mentor_interns(
        Document.objects.select_related('intern', 'reviewed_by'), request.user,
    )
    reports = _scope_to_mentor_interns(
        ReportSubmission.objects.select_related('intern', 'reviewed_by'), request.user,
    )
    if request.method == 'POST':
        kind = request.POST.get('kind')
        if kind == 'document':
            return _review_document(request, get_object_or_404(documents, pk=request.POST.get('pk')))
        if kind == 'report':
            report = get_object_or_404(reports, pk=request.POST.get('pk'))
            report.status = (ReportSubmission.Status.APPROVED
                             if request.POST.get('status') == 'APPROVED'
                             else ReportSubmission.Status.REJECTED)
            report.feedback = request.POST.get('feedback', '').strip()
            report.reviewed_by = request.user
            report.reviewed_at = timezone.now()
            report.save(update_fields=['status', 'feedback', 'reviewed_by', 'reviewed_at'])
            messages.success(request, 'Report review saved.')
            return redirect('review_documents')
        return HttpResponseForbidden('Invalid submission type.')

    status = request.GET.get('status', '')
    query = request.GET.get('q', '').strip()
    if status in dict(Document.Status.choices):
        documents = documents.filter(status=status)
    if query:
        documents = documents.filter(
            Q(intern__first_name__icontains=query) |
            Q(intern__last_name__icontains=query) |
            Q(intern__username__icontains=query) |
            Q(name__icontains=query) |
            Q(document_type__icontains=query)
        )
    return render(request, 'portal/review.html', {
        'documents': documents,
        'reports': reports,
        'document_stats': _document_stats(),
        'status': status,
        'q': query,
        'status_choices': Document.Status.choices,
        'active_page': 'documents',
    })


@login_required
def progress(request):
    if request.user.is_admin_role or request.user.is_mentor_role:
        attendance = Attendance.objects.select_related('intern')
        evaluations = PerformanceEvaluation.objects.select_related('intern', 'evaluator')
        if request.user.is_mentor_role:
            attendance = attendance.filter(intern__internship_record__mentor=request.user)
            evaluations = evaluations.filter(intern__internship_record__mentor=request.user)
    else:
        attendance = request.user.attendance_records.all()
        evaluations = request.user.evaluations.all()
    form = AttendanceForm(request.POST or None)
    if request.method == 'POST' and request.user.is_authenticated and not (request.user.is_admin_role or request.user.is_mentor_role):
        if form.is_valid():
            item = form.save(commit=False)
            item.intern = request.user
            item.save()
            messages.success(request, 'Attendance recorded.')
            return redirect('progress')
    evaluation_form = EvaluationForm(request.POST or None)
    if request.method == 'POST' and request.user.is_mentor_role and evaluation_form.is_valid():
        item = evaluation_form.save(commit=False)
        item.evaluator = request.user
        item.save()
        messages.success(request, 'Performance evaluation saved.')
        return redirect('progress')
    return render(request, 'portal/progress.html', {'attendance': attendance, 'evaluations': evaluations, 'form': form, 'evaluation_form': evaluation_form, 'active_page': 'progress'})


@login_required
def announcement_feed(request):
    form = AnnouncementForm(request.POST or None) if (request.user.is_admin_role or request.user.is_mentor_role) else None
    if form and request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.created_by = request.user
        item.save()
        messages.success(request, 'Announcement published.')
        return redirect('announcement_feed')
    return render(request, 'portal/announcements.html', {'announcements': Announcement.objects.all(), 'form': form, 'active_page': 'announcements'})
