# Service & Device Health Monitoring

**Status:** Real-time operational visibility for services and devices  
**Audience:** System operators, DevOps, developers  
**Last Updated:** 2025

## Overview

The gadget platform provides two-tier health monitoring:

1. **Service Health**: API, Database, Redis, MQTT broker, Celery worker status
2. **Device Status**: Individual device online/offline state, firmware version, battery, signal strength

Both are visible in Django Admin and queryable via REST API.

---

## 1. Service Health Monitoring

### Models

**ServiceHealth** tracks infrastructure component status:

```python
class ServiceHealth(models.Model):
    SERVICE_CHOICES = [
        ("api", "API"),
        ("db", "Database"),
        ("redis", "Redis"),
        ("mqtt", "MQTT"),
        ("worker", "Celery Worker"),
    ]
    
    service_name = CharField(choices=SERVICE_CHOICES)  # Which service
    status = CharField(choices=[("up", "Up"), ("down", "Down"), ("degraded", "Degraded")])
    response_time_ms = PositiveIntegerField()           # Last check latency
    last_check_at = DateTimeField(auto_now=True)        # When last checked
    error_message = TextField()                         # If down, why
    check_count = PositiveIntegerField()                # Total health checks
    failed_count = PositiveIntegerField()               # Number of failures
```

### Viewing Service Health

#### Via Django Admin

1. Navigate to **http://localhost:8000/admin/**
2. Click **"Service Health"** in the left sidebar
3. View all services with their current status, response time, and failure counts
4. Click any service to see detailed history

**List View Columns:**
- Service: Which service (API, DB, Redis, MQTT, Worker)
- Status: Up / Down / Degraded
- Response Time (ms): Latency of last health check
- Last Check At: Timestamp of most recent check
- Failed Count: Cumulative failures

#### Via REST API

**GET /api/v1/health/**

Returns overall system health plus per-service status:

```bash
curl http://localhost:8000/api/v1/health/ -H "Authorization: Token YOUR_TOKEN"
```

Response:
```json
{
  "status": "ok",  // "ok", "degraded", or "error"
  "service": "gadget-api",
  "services": {
    "API": {
      "status": "up",
      "response_time_ms": 45,
      "last_check": "2025-01-15T14:32:10.123456Z",
      "failed_count": 0
    },
    "Database": {
      "status": "up",
      "response_time_ms": 12,
      "last_check": "2025-01-15T14:32:05.987654Z",
      "failed_count": 0
    },
    "Redis": {
      "status": "up",
      "response_time_ms": 8,
      "last_check": "2025-01-15T14:32:08.456789Z",
      "failed_count": 0
    },
    "MQTT": {
      "status": "degraded",
      "response_time_ms": 523,
      "last_check": "2025-01-15T14:31:55.111111Z",
      "failed_count": 3
    },
    "Celery Worker": {
      "status": "up",
      "response_time_ms": 89,
      "last_check": "2025-01-15T14:31:42.222222Z",
      "failed_count": 0
    }
  }
}
```

---

## 2. Device Status Monitoring

### Models

**DeviceStatus** tracks individual device operational state:

```python
class DeviceStatus(models.Model):
    STATUS_CHOICES = [
        ("online", "Online"),
        ("offline", "Offline"),
        ("updating", "Updating"),
        ("error", "Error"),
    ]
    
    device = OneToOneField(WordPressDevice)         # Link to device
    status = CharField(choices=STATUS_CHOICES)      # Current connectivity
    last_heartbeat_at = DateTimeField()             # Last contact from device
    firmware_version = CharField()                  # Currently installed FW
    battery_level = PositiveIntegerField()          # 0-100
    signal_strength = IntegerField()                # dBm, negative
    error_message = TextField()                     # If error, why
    updated_at = DateTimeField(auto_now=True)       # Status record updated
```

### Viewing Device Status

#### Via Django Admin

1. Navigate to **http://localhost:8000/admin/**

**Option A: View from Device List**

1. Click **"WordPress Devices"** in the left sidebar
2. Select any device to open its detail page
3. Scroll down to the **"Device Status"** inline section at the bottom
4. View real-time status: online/offline/updating/error
5. See firmware version, battery %, signal strength (dBm)

**Option B: View from Status Dashboard**

1. Click **"Device Statuses"** in the left sidebar
2. See all devices with their current status and last contact time
3. Use the filter panel to show only:
   - Online devices
   - Offline devices
   - Devices with errors
4. Sort by "Last Heartbeat" to see which devices are stale

**List View Columns:**
- Device: Device name/ID
- Status: Online / Offline / Updating / Error
- Last Heartbeat: When device last reported in
- Firmware Version: Currently running FW
- Battery Level: Percentage (0-100)
- Signal Strength: dBm (typically -100 to -30)

---

## 3. Device Heartbeat Endpoint

### How Devices Report Status

Devices periodically call the `device_heartbeat` endpoint to report their operational state.

**Endpoint:** `POST /api/v1/devices/{external_id}/heartbeat/`

**Required Headers:**
None (device is identified by external_id in URL)

**Request Body:**

```json
{
  "status": "online",
  "firmware_version": "1.0.2",
  "battery_level": 85,
  "signal_strength": -55,
  "error_message": ""
}
```

**Fields:**
- `status` (required): One of `online`, `offline`, `updating`, `error`
- `firmware_version` (optional): Version string, e.g., "1.0.2"
- `battery_level` (optional): 0-100 (clamped automatically)
- `signal_strength` (optional): Received signal strength indicator (dBm, negative)
- `error_message` (optional): Human-readable error if status is "error"

**Example (cURL):**

```bash
curl -X POST http://localhost:8000/api/v1/devices/ESP32-ABC123/heartbeat/ \
  -H "Content-Type: application/json" \
  -d '{
    "status": "online",
    "firmware_version": "1.0.2",
    "battery_level": 85,
    "signal_strength": -55
  }'
```

**Response (200 OK):**

```json
{
  "acknowledged": true,
  "device_id": "ESP32-ABC123",
  "status": "online",
  "last_heartbeat": "2025-01-15T14:32:01.123456Z"
}
```

**Error Responses:**

- **404 Not Found**: Device `external_id` does not exist
- **400 Bad Request**: Invalid JSON payload

### Recommended Heartbeat Schedule

Devices should call this endpoint:

- **Minimum**: Every 5 minutes when idle
- **Recommended**: Every 1-2 minutes during normal operation
- **During update**: Every 10 seconds (status="updating")
- **On error**: Every 30 seconds with error message

**Example Device Code (Pseudocode):**

```python
def heartbeat():
    payload = {
        "status": "online" if is_connected else "offline",
        "firmware_version": "1.0.2",
        "battery_level": read_battery(),
        "signal_strength": read_wifi_rssi(),
        "error_message": get_last_error() or ""
    }
    response = http.post(
        f"http://server:8000/api/v1/devices/{device_id}/heartbeat/",
        json=payload
    )
    return response.status_code == 200
```

---

## 4. Monitoring Strategies

### Real-Time Dashboard (MVP)

Django Admin provides a real-time view:
1. Open **Service Health** tab → see infrastructure status
2. Open **Device Statuses** tab → see all devices' latest state
3. Refresh (⌘R or Ctrl+R) to update

### Automated Health Checks (Future)

Create a Celery task that periodically:
1. Pings DB, Redis, MQTT broker
2. Checks worker process status
3. Writes results to ServiceHealth table
4. Alerts if status flips from "up" to "down"

**Skeleton (services.py):**

```python
from celery import shared_task
from django.utils import timezone
from core.models import ServiceHealth

@shared_task
def check_service_health():
    """Periodic task: check all services"""
    
    # Check database
    try:
        WordPressDevice.objects.count()  # Quick query
        db_status, db_ms = "up", 5
    except Exception as e:
        db_status, db_ms = "down", 0
    
    ServiceHealth.objects.update_or_create(
        service_name="db",
        defaults=dict(
            status=db_status,
            response_time_ms=db_ms,
            last_check_at=timezone.now(),
            check_count=F('check_count') + 1,
            failed_count=F('failed_count') + (1 if db_status == "down" else 0),
        )
    )
    
    # Similar for redis, mqtt, worker...
```

Run every 1 minute via Celery Beat:
```python
# settings.py
CELERY_BEAT_SCHEDULE = {
    'check-service-health': {
        'task': 'core.tasks.check_service_health',
        'schedule': crontab(minute='*/1'),  # Every minute
    },
}
```

### Device Inactivity Alerts (Future)

Monitor `last_heartbeat_at`:

```python
from django.utils import timezone
from datetime import timedelta
from core.models import DeviceStatus

# Find devices with no heartbeat in last 5 minutes
stale = DeviceStatus.objects.filter(
    last_heartbeat_at__lt=timezone.now() - timedelta(minutes=5)
)
for device_status in stale:
    # Send alert
    notify_ops(f"Device {device_status.device.name} is stale")
```

---

## 5. Database Schema

### ServiceHealth Table

```sql
CREATE TABLE core_servicehealth (
    id BIGSERIAL PRIMARY KEY,
    service_name VARCHAR(64),           -- api, db, redis, mqtt, worker
    status VARCHAR(32),                 -- up, down, degraded
    response_time_ms INTEGER,           -- Milliseconds
    last_check_at TIMESTAMP,            -- Most recent check
    error_message TEXT,                 -- If down, why
    check_count INTEGER,                -- Total checks performed
    failed_count INTEGER                -- Total failures
);
```

### DeviceStatus Table

```sql
CREATE TABLE core_devicestatus (
    id BIGSERIAL PRIMARY KEY,
    device_id BIGINT UNIQUE REFERENCES core_wordpressdevice(id),
    status VARCHAR(32),                 -- online, offline, updating, error
    last_heartbeat_at TIMESTAMP,        -- When device last called heartbeat
    firmware_version VARCHAR(64),       -- e.g., "1.0.2"
    battery_level INTEGER,              -- 0-100
    signal_strength INTEGER,            -- dBm (negative)
    error_message TEXT,                 -- If error, what happened
    updated_at TIMESTAMP                -- When this record was last updated
);
```

---

## 6. Integration with Alerts

### Prometheus Metrics (Future)

Export ServiceHealth and DeviceStatus to Prometheus:

```python
# prometheus.py
from prometheus_client import Counter, Gauge
from core.models import ServiceHealth, DeviceStatus

service_down_count = Counter(
    'gadget_service_down_total',
    'Number of service failures',
    ['service_name']
)

device_online_gauge = Gauge(
    'gadget_device_online_count',
    'Number of online devices'
)

def export_metrics():
    online_count = DeviceStatus.objects.filter(status='online').count()
    device_online_gauge.set(online_count)
```

### Email/Slack Alerts (Future)

```python
# signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from core.models import ServiceHealth, DeviceStatus

@receiver(post_save, sender=ServiceHealth)
def alert_service_down(sender, instance, **kwargs):
    if instance.status == "down":
        send_slack_alert(f"⚠️ {instance.service_name} is DOWN")
    elif instance.status == "up":
        send_slack_alert(f"✅ {instance.service_name} is UP")

@receiver(post_save, sender=DeviceStatus)
def alert_device_offline(sender, instance, **kwargs):
    if instance.status == "offline":
        send_slack_alert(f"📴 Device {instance.device.name} went OFFLINE")
```

---

## 7. Operational Checklist

- ✅ Run migrations: `make migrate`
- ✅ Start services: `make up`
- ✅ Visit Django Admin: http://localhost:8000/admin/
- ✅ Check Service Health dashboard
- ✅ Check Device Statuses dashboard
- ✅ Test device heartbeat endpoint (curl example above)
- ✅ Verify heartbeat updates DeviceStatus in real-time
- (Future) ✅ Set up Celery health check task
- (Future) ✅ Configure Prometheus scraper
- (Future) ✅ Add Slack webhook for critical alerts

---

## 8. Troubleshooting

### "No ServiceHealth records" after service startup
- ServiceHealth records are created manually (for now)
- Create them in Django Admin or via shell:
```python
from core.models import ServiceHealth
ServiceHealth.objects.create(service_name="api", status="up")
ServiceHealth.objects.create(service_name="db", status="up")
ServiceHealth.objects.create(service_name="redis", status="up")
ServiceHealth.objects.create(service_name="mqtt", status="up")
ServiceHealth.objects.create(service_name="worker", status="up")
```

### Device heartbeat endpoint returns 404
- Verify device `external_id` exists: check **WordPress Devices** in Admin
- Device must exist before it can call heartbeat
- Sync devices from WordPress first: call `/api/v1/integrations/wordpress/sync/`

### Device status not updating
- Check device is calling heartbeat endpoint correctly
- Verify JSON payload is valid (see example above)
- Check response code is 200
- Refresh Django Admin page to see latest status

### Service status stuck on "up" but service is down
- Automated health checks not yet implemented (see Celery task skeleton)
- For now, manually update status in Django Admin
- Or POST to seed the data:

```python
from django.utils import timezone
from core.models import ServiceHealth
ServiceHealth.objects.filter(service_name="redis").update(
    status="down",
    error_message="Connection timeout",
    last_check_at=timezone.now()
)
```

---

## Next Steps

1. **Deploy health checks**: Implement Celery task to sample all services every minute
2. **Export metrics**: Wire ServiceHealth → Prometheus for external monitoring
3. **Build dashboard**: Create custom Django view (not just Admin) for NOC/KPI display
4. **Alert integration**: Send Slack/PagerDuty alerts when services/devices flip states
5. **Historical trending**: Keep 30-day rolling window of health metrics for capacity planning

