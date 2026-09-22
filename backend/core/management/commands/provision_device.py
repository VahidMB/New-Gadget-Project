from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.device_auth import generate_device_token
from core.models import WordPressDevice


class Command(BaseCommand):
    help = "Provision a device or rotate its token. The plaintext token is printed exactly once."

    def add_arguments(self, parser):
        parser.add_argument("external_id")
        parser.add_argument("--rotate", action="store_true", help="Replace an existing device token.")

    def handle(self, *args, **options):
        external_id = options["external_id"]
        try:
            device = WordPressDevice.objects.get(external_id=external_id)
        except WordPressDevice.DoesNotExist as exc:
            raise CommandError(f"Device {external_id!r} does not exist.") from exc

        if device.device_token_hash and not options["rotate"]:
            raise CommandError("Device already has a token; use --rotate to replace it.")

        token, token_hash = generate_device_token()
        device.device_token_hash = token_hash
        device.device_token_created_at = timezone.now()
        device.provisioning_state = WordPressDevice.ProvisioningState.PROVISIONED
        device.save(update_fields=["device_token_hash", "device_token_created_at", "provisioning_state", "updated_at"])
        self.stdout.write(token)