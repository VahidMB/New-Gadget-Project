from django.db import migrations, models
from django.db.models import deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlanRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plan_name", models.CharField(max_length=64, unique=True)),
                ("can_customize_ui", models.BooleanField(default=False)),
                ("can_change_theme", models.BooleanField(default=False)),
                ("can_add_pages", models.BooleanField(default=False)),
                ("can_add_sources", models.BooleanField(default=False)),
                ("max_pages", models.PositiveIntegerField(default=0)),
                ("max_elements_per_page", models.PositiveIntegerField(default=0)),
                ("max_sources", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="UITemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("version", models.CharField(default="1.0", max_length=32)),
                ("plan_type", models.CharField(default="simple", max_length=32)),
                ("default_theme", models.JSONField(blank=True, default=dict)),
                ("default_screen", models.JSONField(blank=True, default=dict)),
                ("default_rules", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="DeviceProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("theme_name", models.CharField(default="dark", max_length=64)),
                ("primary_color", models.CharField(default="#00B7FF", max_length=16)),
                ("secondary_color", models.CharField(default="#FFFFFF", max_length=16)),
                ("background_color", models.CharField(default="#000000", max_length=16)),
                ("layout_mode", models.CharField(default="dashboard", max_length=64)),
                ("refresh_interval_ms", models.PositiveIntegerField(default=60000)),
                ("custom_config", models.JSONField(blank=True, default=dict)),
                ("effective_config", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "device",
                    models.OneToOneField(on_delete=deletion.CASCADE, related_name="profile", to="core.wordpressdevice"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="UIPage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page_key", models.CharField(max_length=64)),
                ("page_type", models.CharField(max_length=64)),
                ("priority", models.PositiveIntegerField(default=0)),
                ("refresh_interval_ms", models.PositiveIntegerField(default=60000)),
                ("visible_when", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("template", models.ForeignKey(on_delete=deletion.CASCADE, related_name="pages", to="core.uitemplate")),
            ],
            options={"ordering": ["priority", "id"]},
        ),
        migrations.CreateModel(
            name="UIElement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("element_type", models.CharField(max_length=64)),
                ("label", models.CharField(blank=True, max_length=128)),
                ("source_key", models.CharField(blank=True, max_length=128)),
                ("x", models.PositiveIntegerField(default=0)),
                ("y", models.PositiveIntegerField(default=0)),
                ("width", models.PositiveIntegerField(default=0)),
                ("height", models.PositiveIntegerField(default=0)),
                ("font_size", models.CharField(blank=True, max_length=32)),
                ("color", models.CharField(blank=True, max_length=16)),
                ("style", models.JSONField(blank=True, default=dict)),
                ("z_index", models.IntegerField(default=0)),
                ("is_visible", models.BooleanField(default=True)),
                ("config", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("page", models.ForeignKey(on_delete=deletion.CASCADE, related_name="elements", to="core.uipage")),
            ],
            options={"ordering": ["z_index", "id"]},
        ),
    ]
