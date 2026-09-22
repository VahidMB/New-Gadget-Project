from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_company_management_portal"),
    ]

    operations = [
        migrations.AddField(
            model_name="externaldatasource",
            name="credential_reference",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="externaldatasource",
            name="display_key",
            field=models.CharField(default="", max_length=128),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="externaldatasource",
            name="image_path",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="externaldatasource",
            name="refresh_interval_seconds",
            field=models.PositiveIntegerField(default=900),
        ),
        migrations.AddField(
            model_name="externaldatasource",
            name="title_path",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="externaldatasource",
            name="value_path",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="externaldatasource",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("http", "HTTP API"),
                    ("telegram", "Telegram"),
                    ("rss", "RSS Feed"),
                    ("internal", "Internal data"),
                ],
                default="http",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="messagecampaign",
            name="target_devices",
            field=models.ManyToManyField(blank=True, related_name="message_campaigns", to="core.wordpressdevice"),
        ),
        migrations.AddConstraint(
            model_name="externaldatasource",
            constraint=models.UniqueConstraint(
                fields=("company", "display_key"),
                name="unique_company_external_data_source_display_key",
            ),
        ),
    ]
