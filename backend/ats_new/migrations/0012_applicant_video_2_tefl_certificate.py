from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ats_new', '0011_add_resign_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='applicant',
            name='tefl_certificate',
            field=models.FileField(blank=True, null=True, upload_to='certificates/'),
        ),
        migrations.AddField(
            model_name='applicant',
            name='video_2',
            field=models.FileField(blank=True, null=True, upload_to='videos/'),
        ),
    ]
