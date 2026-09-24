"""Bounded, DNS-pinned ingestion. Values live only in the expiring cache."""
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import regex
from bs4 import BeautifulSoup
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from core.models import ExternalDataSource, Integration

MAX_BYTES = 1024 * 1024


def fetch_public(url, headers=None):
    parts = urlsplit(url)
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("آدرس باید HTTP یا HTTPS عمومی و بدون نام کاربری باشد.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in {80, 443}:
        raise ValueError("فقط پورت‌های ۸۰ و ۴۴۳ برای منابع عمومی مجازند.")
    addresses = list({item[4][0] for item in socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("آدرس‌های داخلی و محلی به عنوان منبع مجاز نیستند.")
    address = addresses[0]
    # Connect to the validated numeric address, with original Host and TLS SNI.
    class PinnedHTTP(http.client.HTTPConnection):
        def connect(self):
            self.sock = socket.create_connection((address, port), timeout=5)
    class PinnedHTTPS(http.client.HTTPSConnection):
        def connect(self):
            raw = socket.create_connection((address, port), timeout=5)
            self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parts.hostname)
    connection = (PinnedHTTPS if parts.scheme == "https" else PinnedHTTP)(parts.hostname, port, timeout=5)
    request_headers = {"User-Agent": "GadgetPlatform/2.0", "Accept": "application/json,text/html,application/rss+xml", "Accept-Encoding": "identity"}
    for key, value in (headers or {}).items():
        if regex.fullmatch(r"[A-Za-z0-9_-]{1,64}", key) and key.lower() not in {"host", "connection", "content-length", "transfer-encoding", "cookie", "proxy-authorization"}:
            request_headers[key] = value
    try:
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        connection.request("GET", path, headers=request_headers)
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"پاسخ نامعتبر منبع: HTTP {response.status}")
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("حجم پاسخ منبع بیشتر از حد مجاز است.")
        return body.decode("utf-8", errors="replace")
    finally:
        connection.close()


def path_value(data, path):
    value = data
    for part in path.split(".") if path else []:
        value = value[int(part)] if isinstance(value, list) else value[part]
    if isinstance(value, (dict, list)):
        raise ValueError("مسیر استخراج باید به یک مقدار ختم شود.")
    return str(value)[:2000]


def extract(source, raw):
    if source.source_type == "http":
        data = json.loads(raw)
        title = path_value(data, source.title_path) if source.title_path else source.name
        value = path_value(data, source.value_path)
    elif source.source_type == "web":
        soup = BeautifulSoup(raw, "html.parser")
        for node in soup(["script", "style"]):
            node.decompose()
        node = soup.select_one(source.value_path or "body")
        if node is None:
            raise ValueError("انتخابگر CSS نتیجه‌ای نداشت.")
        value = node.get_text(" ", strip=True)[:4000]
        title = source.name
    elif source.source_type == "rss":
        # HTML parser intentionally avoids XML entity expansion.
        soup = BeautifulSoup(raw, "html.parser")
        item = soup.find("item") or soup.find("entry")
        if item is None:
            raise ValueError("فید خبری خالی است.")
        title_node = item.find("title")
        title = title_node.get_text(strip=True) if title_node else source.name
        value_node = item.find(source.value_path or "description") or item.find("summary") or title_node
        value = value_node.get_text(" ", strip=True) if value_node else title
    else:
        title, value = source.name, raw[:4000]
    if source.extraction_pattern:
        match = regex.search(source.extraction_pattern, value, timeout=0.05)
        if not match:
            raise ValueError("الگوی استخراج در متن پیدا نشد.")
        value = match.group(1) if match.groups() else match.group(0)
    return {"title": title[:200], "value": value[:2000], "unit": source.unit}


def cache_key(source):
    # Editing mappings invalidates old data without ever serving the old mapping.
    signature = hashlib.sha256(f"{source.pk}:{source.updated_at.isoformat()}".encode()).hexdigest()
    return "source:" + signature


@transaction.atomic
def store_value(source, content, observed_at=None):
    locked = ExternalDataSource.objects.select_for_update().get(pk=source.pk)
    if locked.updated_at != source.updated_at or not locked.is_active:
        return False
    now = timezone.now()
    observed_at = observed_at or now
    remaining = int((observed_at + timedelta(seconds=source.ttl_seconds) - now).total_seconds())
    if remaining <= 0:
        return False
    previous = read_value(source)
    if previous and previous["observed_at"] > observed_at.isoformat():
        return False
    expires = observed_at + timedelta(seconds=source.ttl_seconds)
    cache.set(cache_key(source), {**content, "source_id": source.pk, "source": source.name, "category": source.category, "observed_at": observed_at.isoformat(), "expires_at": expires.isoformat()}, timeout=remaining)
    ExternalDataSource.objects.filter(pk=source.pk).update(last_success_at=now, last_attempt_at=now, last_error="")
    cache.set("source-revision:" + str(source.pk), now.isoformat(), source.ttl_seconds)
    if source.selections.filter(device__provisioning_state="provisioned").exists():
        from core.buzzer import notify_source
        transaction.on_commit(lambda: notify_source(source.pk))
    return True


def read_value(source):
    if not source.is_active:
        return None
    value = cache.get(cache_key(source))
    if value and value["expires_at"] <= timezone.now().isoformat():
        cache.delete(cache_key(source))
        return None
    return value


def refresh_source(source):
    if not source.is_active or source.update_mode == "push" or source.source_type in {"telegram", "internal"}:
        return False
    ExternalDataSource.objects.filter(pk=source.pk).update(last_attempt_at=timezone.now())
    try:
        headers = {}
        request_url = source.endpoint_url
        if source.credential_reference:
            credential = Integration.objects.filter(key=source.credential_reference, kind="provider", is_active=True, company_id=source.company_id).first()
            if credential is None:
                raise ValueError("اعتبارنامهٔ مجاز برای منبع پیدا نشد.")
            target, allowed = urlsplit(source.endpoint_url), urlsplit(credential.endpoint)
            if not allowed.hostname or (target.scheme, target.hostname, target.port) != (allowed.scheme, allowed.hostname, allowed.port):
                raise ValueError("اعتبارنامه فقط برای میزبان ثبت‌شده مجاز است.")
            header = credential.options.get("auth_header", "Authorization")
            if not regex.fullmatch(r"[A-Za-z0-9_-]{1,64}", header) or header.lower() in {"host", "connection", "content-length", "transfer-encoding", "cookie", "proxy-authorization"}:
                raise ValueError("Unsupported authentication header")
            scheme = credential.options.get("auth_scheme", "Bearer" if header == "Authorization" else "")
            if credential.options.get("auth_location") == "query":
                parameter = credential.options.get("auth_parameter", "api_key")
                query = [(key, value) for key, value in parse_qsl(target.query, keep_blank_values=True) if key != parameter]
                query.append((parameter, credential.secret()))
                request_url = urlunsplit((target.scheme, target.netloc, target.path, urlencode(query), ""))
            else:
                headers = {header: (str(scheme) + " " if scheme else "") + credential.secret()}
        raw = fetch_public(request_url, headers)
        return store_value(source, extract(source, raw))
    except Exception:
        # Never persist exception URLs, provider response bodies or secret headers.
        ExternalDataSource.objects.filter(pk=source.pk).update(last_error="دریافت یا استخراج ناموفق؛ آدرس، قالب پاسخ و اتصال را بررسی کنید.")
        return False
