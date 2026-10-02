from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import (Agenda, Announcement, Attendance, Document, InternProfile,
                     InternshipRecord, PerformanceEvaluation, PhotoSubmission,
                     ReportSubmission, Task)

User = get_user_model()

ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_DOCUMENT_EXTENSIONS = ('.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx')
MAX_DOCUMENT_SIZE = 5 * 1024 * 1024  # 5 MB


class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Email or username', 'autofocus': True}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Password'}),
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        # Allow login with email OR username
        if '@' in username:
            try:
                user = User.objects.get(email__iexact=username)
                return user.username
            except User.DoesNotExist:
                raise ValidationError('No account found with that email.')
        return username


class InternUserForm(forms.ModelForm):
    """Combined form for creating/editing an intern account + profile."""
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'placeholder': 'Leave blank to keep unchanged'}),
        help_text='Required for new interns. Leave blank when editing to keep the current password.',
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = getattr(self.instance, 'profile', None)
        initial = kwargs.get('initial', {})
        if profile:
            initial.update({
                'student_number': profile.student_number,
                'course': profile.course,
                'phone': profile.phone,
                'company_name': profile.company_name,
                'company_address': profile.company_address,
                'supervisor_name': profile.supervisor_name,
                'position': profile.position,
                'start_date': profile.start_date,
                'end_date': profile.end_date,
                'hours_required': profile.hours_required,
            })
        self.fields.update({
            'student_number': forms.CharField(required=False),
            'course': forms.CharField(required=False),
            'phone': forms.CharField(required=False),
            'company_name': forms.CharField(required=False),
            'company_address': forms.CharField(required=False),
            'supervisor_name': forms.CharField(required=False),
            'position': forms.CharField(required=False),
            'start_date': forms.DateField(
                required=False,
                widget=forms.DateInput(attrs={'type': 'date'}),
            ),
            'end_date': forms.DateField(
                required=False,
                widget=forms.DateInput(attrs={'type': 'date'}),
            ),
            'hours_required': forms.IntegerField(min_value=1, initial=240),
        })
        self.initial = initial

    def clean_email(self):
        email = self.cleaned_data['email']
        qs = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('That email is already in use.')
        return email

    def clean_username(self):
        username = self.cleaned_data['username']
        qs = User.objects.filter(username__iexact=username)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('That username is already taken.')
        return username

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get('password'):
            self.add_error('password', 'Password is required for a new intern.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Roles.INTERN
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
            profile, _ = InternProfile.objects.get_or_create(user=user)
            for field in ['student_number', 'course', 'phone', 'company_name',
                          'company_address', 'supervisor_name', 'position',
                          'start_date', 'end_date', 'hours_required']:
                setattr(profile, field, self.cleaned_data.get(field))
            profile.save()
        return user


class PhotoSubmissionForm(forms.ModelForm):
    class Meta:
        model = PhotoSubmission
        fields = ['image', 'caption']
        widgets = {
            'caption': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Describe what you did in this photo (activity, tasks, hours)...',
                'maxlength': 500,
            }),
        }

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            name = image.name.lower()
            if not name.endswith(ALLOWED_EXTENSIONS):
                raise ValidationError(
                    f'Unsupported file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'
                )
            if image.size > MAX_IMAGE_SIZE:
                raise ValidationError('Image is too large. Maximum size is 5 MB.')
        return image


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ['title', 'message']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Announcement title'}),
            'message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Write your announcement...'}),
        }


class AgendaForm(forms.ModelForm):
    class Meta:
        model = Agenda
        fields = ['title', 'description', 'date', 'time']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Agenda title'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Description'}),
            'date': forms.DateInput(attrs={'type': 'date'}),
            'time': forms.TimeInput(attrs={'type': 'time'}),
        }


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'assigned_to', 'priority', 'due_date', 'status']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Task title'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional details'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = User.objects.filter(
            Q(role=User.Roles.ADMIN) | Q(is_superuser=True), is_active=True,
        ).order_by('first_name', 'last_name', 'username')
        self.fields['assigned_to'].required = False
        self.fields['assigned_to'].empty_label = 'Unassigned'
        self.fields['assigned_to'].label_from_instance = lambda user: (
            f'{user.get_full_name() or user.username} · {user.email or user.username}'
        )


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label='Confirm password')

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email']

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') != cleaned.get('password_confirm'):
            self.add_error('password_confirm', 'Passwords do not match.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Roles.INTERN
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
            InternProfile.objects.get_or_create(user=user)
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = InternProfile
        exclude = ['user', 'updated_at']
        widgets = {'start_date': forms.DateInput(attrs={'type': 'date'}), 'end_date': forms.DateInput(attrs={'type': 'date'})}


class InternshipRecordForm(forms.ModelForm):
    class Meta:
        model = InternshipRecord
        fields = ['intern', 'student_id', 'course', 'year_level', 'status', 'start_date', 'end_date', 'hours_required', 'mentor']
        widgets = {'start_date': forms.DateInput(attrs={'type': 'date'}), 'end_date': forms.DateInput(attrs={'type': 'date'})}


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['name', 'document_type', 'file']
        labels = {'document_type': 'Document type'}
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., Resume, Academic Record',
            }),
            'file': forms.ClearableFileInput(attrs={
                'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx',
            }),
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            name = file.name.lower()
            if not name.endswith(ALLOWED_DOCUMENT_EXTENSIONS):
                raise ValidationError(
                    'Unsupported file type. Allowed: '
                    + ', '.join(ALLOWED_DOCUMENT_EXTENSIONS)
                )
            if file.size > MAX_DOCUMENT_SIZE:
                raise ValidationError('Document is too large. Maximum size is 5 MB.')
        return file


class ReportSubmissionForm(forms.ModelForm):
    class Meta:
        model = ReportSubmission
        fields = ['title', 'file']


class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['date', 'time_in', 'time_out', 'status']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}), 'time_in': forms.TimeInput(attrs={'type': 'time'}), 'time_out': forms.TimeInput(attrs={'type': 'time'})}


class EvaluationForm(forms.ModelForm):
    class Meta:
        model = PerformanceEvaluation
        fields = ['intern', 'score', 'remarks']
