from django.db import migrations
from django.contrib.auth.hashers import make_password


def seed_demo_accounts(apps, schema_editor):
    User = apps.get_model('accounts', 'User')

    admin, _ = User.objects.get_or_create(
        username='admin',
        defaults={
            'email': 'admin@example.com',
            'first_name': 'Admin',
            'last_name': 'User',
            'role': 'ADMIN',
            'is_active': True,
            'is_staff': True,
            'is_superuser': True,
            'password': make_password('admin123'),
        },
    )
    if not admin.password or admin.password.startswith('!') or admin.password.startswith('pbkdf2_'):
        admin.password = make_password('admin123')
    admin.role = 'ADMIN'
    admin.is_active = True
    admin.is_staff = True
    admin.is_superuser = True
    admin.save()

    intern, _ = User.objects.get_or_create(
        username='intern1',
        defaults={
            'email': 'intern1@example.com',
            'first_name': 'Intern',
            'last_name': 'One',
            'role': 'INTERN',
            'is_active': True,
            'is_staff': False,
            'is_superuser': False,
            'password': make_password('intern123'),
        },
    )
    if not intern.password or intern.password.startswith('!') or intern.password.startswith('pbkdf2_'):
        intern.password = make_password('intern123')
    intern.role = 'INTERN'
    intern.is_active = True
    intern.is_staff = False
    intern.is_superuser = False
    intern.save()


def reverse_seed_demo_accounts(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(username__in=['admin', 'intern1']).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_demo_accounts, reverse_seed_demo_accounts),
    ]
