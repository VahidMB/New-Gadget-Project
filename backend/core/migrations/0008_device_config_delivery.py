from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0007_firmware_file_upload")]

    operations = [
        migrations.AddField(
            model_name="wordpressdevice",
            name="config_sync_pending",
            field=models.BooleanField(default=False, editable=False),
        ),
    ]
