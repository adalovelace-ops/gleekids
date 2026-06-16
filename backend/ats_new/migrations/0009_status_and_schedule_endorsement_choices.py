from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ats_new', '0008_applicant_preferred_demo_time'),
    ]

    operations = [
        migrations.AlterField(
            model_name='applicant',
            name='status',
            field=models.CharField(
                choices=[
                    ('Pending', 'Pending'),
                    ('Initial Screening', 'Initial Screening'),
                    ('Demo Evaluation', 'Demo Evaluation'),
                    ('Endorsement', 'Endorsement'),
                    ('Training', 'Training'),
                    ('Onboarding', 'Onboarding'),
                    ('Approved', 'Approved'),
                    ('Withdrawn', 'Withdrawn'),
                ],
                default='Pending',
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='schedule',
            name='type',
            field=models.CharField(
                choices=[
                    ('initial', 'Initial Screening'),
                    ('demo', 'Demo Session'),
                    ('endorsement', 'Client Final Interview'),
                    ('training', 'Training'),
                    ('onboarding', 'Onboarding'),
                ],
                max_length=20,
            ),
        ),
    ]
