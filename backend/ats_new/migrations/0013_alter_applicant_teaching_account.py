from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ats_new', '0012_applicant_video_2_tefl_certificate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='applicant',
            name='teaching_account',
            field=models.CharField(
                blank=True,
                choices=[
                    ('Vietnamese', 'Vietnamese Account'),
                    ('Chinese', 'Chinese Account'),
                    ('Direct', 'Direct Account'),
                ],
                max_length=50,
                null=True,
            ),
        ),
    ]
