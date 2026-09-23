# Reliability upgrade

## Deployment

Back up PostgreSQL before upgrading. This release restores Django migration
discovery by adding `core/migrations/__init__.py` and adds migration 0008 for
durable configuration notification tracking.

On a normal installation, run migrations and rebuild existing configurations:

```bash
docker compose exec api python manage.py migrate
docker compose exec api python manage.py rebuild_device_configs
```

If tables were previously created manually or through `--run-syncdb` while
migrations were undiscovered, reconcile their schema and migration history
against a database backup before deploying. Do not blindly use `--fake` or
`--fake-initial`: later migrations may already be represented in those tables.

Keep both Celery worker and Beat running. Configuration changes are stored
immediately; MQTT publication is queued after commit. A pending flag survives
broker outages, and Beat retries pending notifications every minute. Duplicate
notifications are possible; devices must fetch the current HTTP configuration
and handle repeated revisions idempotently.

## Display configuration

Saving a device through the portal, Admin, or WordPress synchronization rebuilds
its configuration. Saving/deleting profiles, templates, pages, and elements also
rebuilds affected output. Only a changed effective configuration increments the
outer device `ui_version`. The inner `effective_config.ui_version` remains the
UI schema version (1).

For Pro devices, precedence is: built-in defaults, active template, device
custom configuration, then device profile fields and profile custom configuration.
Simple devices ignore device/profile customization. Admin no longer allows
manual editing of the generated revision counter.

ORM bulk updates bypass model signals. Run `rebuild_device_configs` after bulk
imports or direct database maintenance. Template edits currently scan all devices;
larger installations should move this rebuilding work into bounded background jobs.

## OTA

The server compares versions using `packaging.version.Version`, selects the
highest stable version strictly newer than the device, and excludes inactive,
future-dated, malformed, development, and prerelease releases. A blank publication
time preserves the existing immediate-publication behavior. An unknown/invalid
reported device version gets no automatic update; a device with no reported
version gets the highest eligible release.

Uploaded binaries remain limited to 8 MiB by default. Nginx permits 10 MiB requests
to accommodate the multipart body. If `MAX_FIRMWARE_UPLOAD_BYTES` changes, adjust
the proxy limit as well. SHA-256 is an integrity check, not a firmware signature;
signed OTA and secure boot still require coordinated firmware work.

## Production MQTT

The production Compose file now mounts `deploy/linux/mosquitto.acl`, and Mosquitto
enforces it. Before restarting the broker:

1. Add a dedicated `gadget-backend` user to the broker password file; configure
   `MQTT_USERNAME=gadget-backend` and its password for API/worker/Beat.
2. Give each physical device a separate broker account whose username equals its
   `external_id`. Never put backend broker credentials on a device. MQTT passwords
   are separate from HTTP device tokens and must be provisioned separately.
3. Keep `MQTT_TOPIC_ROOT=gadget/v1`, or update both backend settings and ACL paths.
4. Use TLS port 8883 and a broker hostname matching its certificate. Set
   `MQTT_HOST`, `MQTT_PORT=8883`, and `MQTT_USE_TLS=1` accordingly.
5. Verify device A can read only A's commands, cannot read B's commands, and cannot
   publish commands. Verify the backend can publish commands.

The bundled ACL is intentionally read-only for devices because heartbeat and OTA
reports use HTTP. Local-development MQTT configuration remains separate.

## Notifications API

`GET /api/v1/integrations/wordpress/notifications/` now requires an authenticated
platform owner/employee or superuser. Company accounts cannot read global sync
events. `limit` must be an integer between 1 and 200.

## Verification

Existing integration tests now explicitly enable database access via a shared
fixture. CI continues to use PostgreSQL through the existing Docker workflow.
For a lightweight isolated run:

```bash
cd backend
pytest -q --ds=gadget_server.test_settings
python manage.py makemigrations --check --dry-run --settings=gadget_server.test_settings
ruff check .
```

The regression suite covers migration discovery, OTA downgrade protection,
notification access, firmware upload validation, configuration propagation,
post-commit publication, and retry state after broker failures. SQLite tests do
not validate PostgreSQL locking or real TLS/MQTT connectivity.

## Separate feature work

External-source fetching (HTTP/RSS/Telegram), enforcement semantics for `PlanRule`,
fine-grained company role policy, and cryptographic firmware signatures remain
separate features. This patch does not claim to implement them or the ESP32 firmware.
