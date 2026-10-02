from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Auth
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='registration/password_change_form.html',
        success_url='/password-change/done/',
    ), name='password_change'),
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='registration/password_change_done.html',
    ), name='password_change_done'),
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset.html',
        email_template_name='registration/password_reset_email.html',
        success_url='/password-reset/done/',
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html',
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url='/reset/done/',
    ), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html',
    ), name='password_reset_complete'),

    # Intern
    path('intern/', views.portal_dashboard, name='intern_dashboard'),
    path('intern/submit/', views.submit_photo, name='submit_photo'),
    path('intern/submissions/', views.my_submissions, name='my_submissions'),
    path('intern/profile/', views.intern_profile, name='intern_profile'),

    # Shared portal modules
    path('profile/', views.profile_edit, name='profile_edit'),
    path('users/', views.user_management, name='user_management'),
    path('records/', views.record_list, name='record_list'),
    path('records/add/', views.record_create, name='record_create'),
    path('records/<int:pk>/edit/', views.record_edit, name='record_edit'),
    path('records/<int:pk>/delete/', views.record_delete, name='record_delete'),
    path('documents/', views.documents, name='documents'),
    path('documents/<int:pk>/view/', views.document_file, {'action': 'view'}, name='document_view'),
    path('documents/<int:pk>/download/', views.document_file, {'action': 'download'}, name='document_download'),
    path('documents/review/', views.review_documents, name='review_documents'),
    path('documents/<int:pk>/review/', views.review_document, name='review_document'),
    path('progress/', views.progress, name='progress'),
    path('announcements/', views.announcement_feed, name='announcement_feed'),

    # Admin
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/tasks/add/', views.task_create, name='task_create'),
    path('admin-panel/tasks/<int:pk>/edit/', views.task_edit, name='task_edit'),
    path('admin-panel/tasks/<int:pk>/status/', views.task_update_status, name='task_update_status'),
    path('admin-panel/tasks/<int:pk>/delete/', views.task_delete, name='task_delete'),
    path('admin-panel/agendas/add/', views.agenda_create, name='agenda_create'),
    path('admin-panel/agendas/<int:pk>/edit/', views.agenda_edit, name='agenda_edit'),
    path('admin-panel/agendas/<int:pk>/delete/', views.agenda_delete, name='agenda_delete'),
    path('admin-panel/interns/', views.intern_list, name='intern_list'),
    path('admin-panel/interns/add/', views.intern_create, name='intern_create'),
    path('admin-panel/interns/<int:pk>/', views.intern_detail, name='intern_detail'),
    path('admin-panel/interns/<int:pk>/edit/', views.intern_edit, name='intern_edit'),
    path('admin-panel/interns/<int:pk>/delete/', views.intern_delete, name='intern_delete'),
    path('admin-panel/submissions/', views.admin_submissions, name='admin_submissions'),
    path('admin-panel/submissions/<int:pk>/review/', views.review_submission, name='review_submission'),
    path('admin-panel/announcements/', views.announcements, name='announcements'),
    path('mentor/', views.portal_dashboard, name='mentor_dashboard'),
]
