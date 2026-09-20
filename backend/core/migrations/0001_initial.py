from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SyncNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(max_length=64)),
                ("title", models.CharField(max_length=255)),
                ("message", models.TextField()),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("delivered", models.BooleanField(default=False)),
                ("delivery_target", models.CharField(blank=True, max_length=512)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="WordPressDataSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.CharField(max_length=128, unique=True)),
                ("key", models.CharField(blank=True, max_length=128)),
                ("label", models.CharField(blank=True, max_length=255)),
                ("enabled", models.BooleanField(default=True)),
                ("config", models.JSONField(blank=True, default=dict)),
                ("last_wordpress_updated_at", models.DateTimeField(blank=True, null=True)),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="WordPressDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.CharField(max_length=128, unique=True)),
                ("customer_external_id", models.CharField(blank=True, max_length=128)),
                ("serial_number", models.CharField(blank=True, max_length=128)),
                ("name", models.CharField(blank=True, max_length=255)),
                ("plan", models.CharField(blank=True, max_length=64)),
                ("is_active", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("custom_config", models.JSONField(blank=True, default=dict)),
                ("effective_config", models.JSONField(blank=True, default=dict)),
                ("ui_version", models.PositiveIntegerField(default=1)),
                ("last_wordpress_updated_at", models.DateTimeField(blank=True, null=True)),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="WordPressSyncEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=128)),
                (
                    "entity_type",
                    models.CharField(
                        choices=[("device", "Device"), ("data_source", "Data Source"), ("unknown", "Unknown")],
                        default="unknown",
                        max_length=32,
                    ),
                ),
                ("entity_external_id", models.CharField(blank=True, max_length=128)),
                ("source", models.CharField(choices=[("webhook", "Webhook"), ("pull", "Pull")], max_length=16)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("payload_hash", models.CharField(max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[("processed", "Processed"), ("ignored", "Ignored"), ("error", "Error")],
                        default="processed",
                        max_length=16,
                    ),
                ),
                ("message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
