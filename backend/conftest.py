import pytest


@pytest.fixture(autouse=True)
def database_access(db):
    """Application tests exercise persisted device and company state."""


@pytest.fixture(autouse=True)
def local_test_settings(settings):
    settings.SECURE_SSL_REDIRECT = False
    settings.SYNC_NOTIFY_WEBHOOK_URL = ""
