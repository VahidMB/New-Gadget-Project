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
                        unique=True,
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
                ("error_message", models.TextField(blank=True)),
                ("check_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Service Health",
                "verbose_name_plural": "Service Health",
                "ordering": ["service_name"],
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
                ("last_config_version", models.PositiveIntegerField(default=0)),
                ("firmware_version", models.CharField(blank=True, max_length=64)),
                ("battery_level", models.PositiveIntegerField(default=0)),
                ("signal_strength", models.IntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
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
                "verbose_name_plural": "Device Status",
            },
        ),
    ]

