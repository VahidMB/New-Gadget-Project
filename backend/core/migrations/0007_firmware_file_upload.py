from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_graphical_content_controls"),
    ]

    operations = [
        migrations.AlterField(
            model_name="firmwarerelease",
            name="download_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="firmwarerelease",
            name="firmware_file",
            field=models.FileField(blank=True, upload_to="firmware/%Y/%m/"),
        ),
        migrations.AlterField(
            model_name="firmwarerelease",
            name="checksum_sha256",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
