"""Root keys are generated once in a protected persistent volume, never in the DB."""
import os
import secrets
from pathlib import Path
from cryptography.fernet import Fernet
from django.conf import settings


def bootstrap_value(name, factory):
    root = Path(os.environ.get("GADGET_STATE_DIR", Path(__file__).resolve().parent.parent / "runtime"))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / name
    # Atomic creation avoids replacing keys across API/worker processes.
    import fcntl
    with (root / ".bootstrap.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as file:
                file.write(factory())
        return path.read_text().strip()


def root_cipher():
    key = getattr(settings, "GADGET_MASTER_KEY", "") or bootstrap_value("master.key", lambda: Fernet.generate_key().decode())
    return Fernet(key.encode())


def encrypt(value):
    return root_cipher().encrypt(value.encode()).decode() if value else ""


def decrypt(value):
    return root_cipher().decrypt(value.encode()).decode() if value else ""


def setup_code():
    return bootstrap_value("setup.code", lambda: secrets.token_urlsafe(24))
