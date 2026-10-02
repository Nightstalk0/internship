from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import FileExtensionValidator


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, email, password=None, **extra_fields):
        if not username:
            raise ValueError('The username field must be set.')
        email = self.normalize_email(email) if email else ''
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('role', User.Roles.INTERN)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Roles.ADMIN)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self._create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    class Roles(models.TextChoices):
        INTERN = 'INTERN', 'Intern'
        MENTOR = 'MENTOR', 'Mentor/Instructor'
        ADMIN = 'ADMIN', 'Admin'

    role = models.CharField(max_length=10, choices=Roles.choices, default=Roles.INTERN)
    email = models.EmailField(unique=True)

    objects = UserManager()

    @property
    def is_admin_role(self):
        return self.role == self.Roles.ADMIN or self.is_superuser

    @property
    def is_mentor_role(self):
        return self.role == self.Roles.MENTOR

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.username})'


class InternProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    student_number = models.CharField(max_length=30, blank=True)
    course = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    company_name = models.CharField(max_length=150, blank=True)
    company_address = models.CharField(max_length=255, blank=True)
    supervisor_name = models.CharField(max_length=120, blank=True)
    position = models.CharField(max_length=120, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    hours_required = models.PositiveIntegerField(default=240)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Profile of {self.user.username}'


class InternshipRecord(models.Model):
    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planned'
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'

    intern = models.OneToOneField(User, on_delete=models.CASCADE, related_name='internship_record')
    student_id = models.CharField(max_length=40)
    course = models.CharField(max_length=120)
    year_level = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    hours_required = models.PositiveIntegerField(default=240)
    mentor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='mentored_records')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def completed_hours(self):
        from django.db.models import Sum
        total = self.intern.attendance_records.aggregate(total=Sum('hours'))['total']
        return round(total or 0, 2)

    @property
    def remaining_hours(self):
        return max(self.hours_required - self.completed_hours, 0)


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    class DocumentType(models.TextChoices):
        RESUME = 'RESUME', 'Resume'
        ACADEMIC_RECORD = 'ACADEMIC_RECORD', 'Academic Record'
        OTHER_REQUIREMENT = 'OTHER_REQUIREMENT', 'Other Requirement'

    intern = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    name = models.CharField(max_length=150)
    document_type = models.CharField(
        max_length=30,
        choices=DocumentType.choices,
        default=DocumentType.OTHER_REQUIREMENT,
    )
    file = models.FileField(upload_to='documents/%Y/%m/')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    feedback = models.TextField(blank=True, max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_documents')
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.get_document_type_display()} - {self.name}'


class ReportSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    intern = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports')
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to='reports/%Y/%m/')
    status = models.CharField(max_length=10, choices=Status.choices, default='PENDING')
    feedback = models.TextField(blank=True, max_length=500)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_reports')
    reviewed_at = models.DateTimeField(null=True, blank=True)


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'PRESENT', 'Present'
        LATE = 'LATE', 'Late'
        ABSENT = 'ABSENT', 'Absent'

    intern = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()
    time_in = models.TimeField(null=True, blank=True)
    time_out = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PRESENT)
    hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        constraints = [models.UniqueConstraint(fields=['intern', 'date'], name='unique_intern_attendance_date')]

    def save(self, *args, **kwargs):
        if self.time_in and self.time_out:
            from datetime import datetime
            start = datetime.combine(self.date, self.time_in)
            end = datetime.combine(self.date, self.time_out)
            if end >= start:
                self.hours = round((end - start).total_seconds() / 3600, 2)
        super().save(*args, **kwargs)


class PerformanceEvaluation(models.Model):
    intern = models.ForeignKey(User, on_delete=models.CASCADE, related_name='evaluations')
    evaluator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='given_evaluations')
    score = models.DecimalField(max_digits=5, decimal_places=2)
    remarks = models.TextField(max_length=1000)
    evaluation_date = models.DateField(auto_now_add=True)


class PhotoSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    intern = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    image = models.ImageField(
        upload_to='submissions/%Y/%m/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'gif', 'webp'])],
    )
    caption = models.TextField(max_length=500)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    feedback = models.TextField(max_length=500, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_submissions',
    )

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f'{self.intern.username} - {self.submitted_at:%b %d, %Y}'


class Announcement(models.Model):
    title = models.CharField(max_length=150)
    message = models.TextField(max_length=1000)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='announcements')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Agenda(models.Model):
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, max_length=1000)
    date = models.DateField()
    time = models.TimeField()
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='agendas',
    )

    class Meta:
        ordering = ['date', 'time', 'title']

    def __str__(self):
        return f'{self.title} - {self.date:%b %d, %Y}'


class Task(models.Model):
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        URGENT = 'URGENT', 'Urgent'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tasks',
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='created_tasks',
    )
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['due_date', '-created_at']

    def __str__(self):
        return self.title
