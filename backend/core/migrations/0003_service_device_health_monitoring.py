# Generated migration for ServiceHealth and DeviceStatus monitoring

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_admin_panel_schema"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceHealth",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "service_name",
                    models.CharField(
                        choices=[
                            ("api", "API"),
                            ("db", "Database"),
                            ("redis", "Redis"),
                            ("mqtt", "MQTT"),
                            ("worker", "Celery Worker"),
                        ],
                        max_length=64,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("up", "Up"), ("down", "Down"), ("degraded", "Degraded")],
                        default="up",
                        max_length=32,
                    ),
                ),
                ("response_time_ms", models.PositiveIntegerField(default=0)),
                ("last_check_at", models.DateTimeField(auto_now=True)),
                ("error_message", models.TextField(blank=True, default="")),
                ("check_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Service Health",
                "verbose_name_plural": "Service Health",
                "ordering": ["-last_check_at"],
            },
        ),
        migrations.CreateModel(
            name="DeviceStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("online", "Online"),
                            ("offline", "Offline"),
                            ("updating", "Updating"),
                            ("error", "Error"),
                        ],
                        default="offline",
                        max_length=32,
                    ),
                ),
                ("last_heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("firmware_version", models.CharField(blank=True, default="", max_length=64)),
                ("battery_level", models.PositiveIntegerField(blank=True, default=0)),
                ("signal_strength", models.IntegerField(blank=True, default=0)),
                ("error_message", models.TextField(blank=True, default="")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "device",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status",
                        to="core.wordpressdevice",
                    ),
                ),
            ],
            options={
                "verbose_name": "Device Status",
                "verbose_name_plural": "Device Statuses",
                "ordering": ["-updated_at"],
            },
        ),
    ]

