from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ats_new', '0007_applicant_work_setup'),
    ]

    operations = [
        migrations.AddField(
            model_name='applicant',
            name='preferred_demo_time',
            field=models.TimeField(blank=True, null=True),
        ),
    ]
