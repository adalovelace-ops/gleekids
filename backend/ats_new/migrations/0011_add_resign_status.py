from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ats_new', '0010_evaluation_type_client_decision'),
    ]

    operations = [
        migrations.AlterField(
            model_name='applicant',
            name='status',
            field=models.CharField(choices=[('Pending', 'Pending'), ('Initial Screening', 'Initial Screening'), ('Demo Evaluation', 'Demo Evaluation'), ('Endorsement', 'Endorsement'), ('Training', 'Training'), ('Onboarding', 'Onboarding'), ('Approved', 'Approved'), ('Resign', 'Resign'), ('Withdrawn', 'Withdrawn')], default='Pending', max_length=50),
        ),
    ]
