"""Per-device token generation and verification helpers.

Plaintext device tokens are intentionally returned only by ``generate_device_token``
so callers can display them once during provisioning. Persist only a salted verifier.
"""

import secrets

from django.contrib.auth.hashers import check_password, make_password


def hash_device_token(token: str) -> str:
    """Return the database representation for a non-empty device token."""
    return make_password(token)


def generate_device_token() -> tuple[str, str]:
    """Create a high-entropy plaintext token and its persistent hash."""
    token = secrets.token_urlsafe(32)
    return token, hash_device_token(token)


def check_device_token(provided_token: str, stored_token_hash: str) -> bool:
    """Constant-time verification without retaining plaintext tokens."""
    if not provided_token or not stored_token_hash:
        return False
    return check_password(provided_token, stored_token_hash)