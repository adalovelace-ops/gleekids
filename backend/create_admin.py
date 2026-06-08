import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

email = 'admin@gleekids.com'
password = 'AdminPassword123'

if not User.objects.filter(username=email).exists():
    User.objects.create_superuser(email, email, password)
    print(f"Superuser created successfully: {email}")
else:
    print(f"Superuser {email} already exists.")
