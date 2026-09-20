import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-dev-key")
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "gadget_server.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "gadget_server.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "gadget"),
        "USER": os.getenv("POSTGRES_USER", "gadget"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "gadget"),
        "HOST": os.getenv("POSTGRES_HOST", "db"),
        "PORT": int(os.getenv("POSTGRES_PORT", "5432")),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

WORDPRESS_WEBHOOK_SECRET = os.getenv("WORDPRESS_WEBHOOK_SECRET", "")
WORDPRESS_API_BASE_URL = os.getenv("WORDPRESS_API_BASE_URL", "")
WORDPRESS_API_TOKEN = os.getenv("WORDPRESS_API_TOKEN", "")
WORDPRESS_DEVICES_ENDPOINT = os.getenv("WORDPRESS_DEVICES_ENDPOINT", "/wp-json/gadget/v1/devices")
WORDPRESS_DATA_SOURCES_ENDPOINT = os.getenv("WORDPRESS_DATA_SOURCES_ENDPOINT", "/wp-json/gadget/v1/data-sources")
WORDPRESS_SYNC_TRIGGER_TOKEN = os.getenv("WORDPRESS_SYNC_TRIGGER_TOKEN", "")
SYNC_NOTIFY_WEBHOOK_URL = os.getenv("SYNC_NOTIFY_WEBHOOK_URL", "")

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = False
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
