"""Generate infrastructure secrets once; all application integrations live in the GUI."""
import argparse
import os
from pathlib import Path
import secrets
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--test", action="store_true", help="Bind the test server to localhost")
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
path = root / ".env.guided"
if not path.exists():
    config = {
        "POSTGRES_DB": "gadget", "POSTGRES_USER": "gadget", "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(48), "DJANGO_DEBUG": "0", "DJANGO_SECURE_SSL_REDIRECT": "0",
        "BIND_ADDRESS": "127.0.0.1", "GADGET_TEST_MODE": "1" if args.test else "0",
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write("\n".join(f"{key}={value}" for key, value in config.items())+"\n")
command = ["docker", "compose", "--env-file", str(path), "-f", str(root / "docker-compose.guided.yml")]
if not args.test:
    command += ["--profile", "public"]
subprocess.run(command + ["up", "-d", "--build"], check=True, cwd=root)
print("Open http://localhost:8000/setup/ (or use an SSH tunnel to your server).")
print("First-run setup code is shown in the API container logs:")
subprocess.run(["docker", "compose", "--env-file", str(path), "-f", str(root / "docker-compose.guided.yml"), "logs", "--tail=40", "api"], check=True, cwd=root)
