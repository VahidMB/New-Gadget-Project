import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_service_device_health_monitoring"),
    ]

    operations = [
        migrations.AddField(
            model_name="wordpressdevice",
            name="device_token_created_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="wordpressdevice",
            name="device_token_hash",
            field=models.CharField(blank=True, editable=False, max_length=128),
        ),
        migrations.AddField(
            model_name="wordpressdevice",
            name="hardware_model",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="wordpressdevice",
            name="provisioning_state",
            field=models.CharField(
                choices=[
                    ("unprovisioned", "Unprovisioned"),
                    ("provisioned", "Provisioned"),
                    ("suspended", "Suspended"),
                ],
                default="unprovisioned",
                max_length=32,
            ),
        ),
        migrations.CreateModel(
            name="FirmwareRelease",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("hardware_model", models.CharField(db_index=True, max_length=128)),
                ("version", models.CharField(max_length=64)),
                ("release_notes", models.TextField(blank=True)),
                ("download_url", models.URLField(max_length=500)),
                ("checksum_sha256", models.CharField(max_length=64)),
                ("is_active", models.BooleanField(default=True)),
                ("is_mandatory", models.BooleanField(default=False)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-published_at", "-id"]},
        ),
        migrations.CreateModel(
            name="FirmwareDeployment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("downloading", "Downloading"),
                            ("installed", "Installed"),
                            ("failed", "Failed"),
                            ("skipped", "Skipped"),
                        ],
                        default="pending",
                        max_length=32,
                    ),
                ),
                ("reported_version", models.CharField(blank=True, max_length=64)),
                ("error_message", models.TextField(blank=True)),
                ("last_reported_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="firmware_deployments", to="core.wordpressdevice")),
                ("release", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="deployments", to="core.firmwarerelease")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="firmwarerelease",
            constraint=models.UniqueConstraint(fields=("hardware_model", "version"), name="unique_firmware_model_version"),
        ),
        migrations.AddConstraint(
            model_name="firmwaredeployment",
            constraint=models.UniqueConstraint(fields=("device", "release"), name="unique_device_firmware_deployment"),
        ),
    ]
