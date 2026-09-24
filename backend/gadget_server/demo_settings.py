"""Local preview only; never use this profile for an internet-facing deployment."""
from .test_settings import *  # noqa: F403
from .settings import BASE_DIR

DEBUG = True
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "runtime" / "demo.sqlite3"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.filebased.FileBasedCache", "LOCATION": BASE_DIR / "runtime" / "demo-cache"}}
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
INTERNAL_API_URL = "http://127.0.0.1:8000"
