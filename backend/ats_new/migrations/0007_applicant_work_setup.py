from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ats_new', '0006_schedule_video_call_log_delete_room'),
    ]

    operations = [
        migrations.AddField(
            model_name='applicant',
            name='work_setup',
            field=models.CharField(
                choices=[
                    ('WFH', 'Work from Home'),
                    ('Office Based', 'Office Based'),
                ],
                default='WFH',
                max_length=20,
            ),
        ),
    ]
