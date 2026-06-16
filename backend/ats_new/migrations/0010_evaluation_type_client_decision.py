from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ats_new', '0009_status_and_schedule_endorsement_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='evaluation',
            name='client_decision',
            field=models.CharField(
                blank=True,
                choices=[('Pass', 'Pass'), ('Fail', 'Fail')],
                max_length=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='evaluation',
            name='evaluation_type',
            field=models.CharField(
                choices=[('demo', 'Demo Evaluation'), ('client', 'Client Endorsement')],
                default='demo',
                max_length=20,
            ),
        ),
    ]
