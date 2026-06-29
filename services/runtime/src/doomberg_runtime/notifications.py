"""Notification dispatcher for trigger alerts and other durable outbox events."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "NotificationDispatcher",
    "PermanentDeliveryError",
    "TemporaryDeliveryError",
    "webhook_signature",
]


class TemporaryDeliveryError(RuntimeError):
    """A delivery target may succeed on retry."""


class PermanentDeliveryError(RuntimeError):
    """A delivery target cannot be delivered without configuration changes."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sterile_payload(notification: dict[str, Any]) -> dict[str, Any]:
    payload = dict(notification.get("payload") or {})
    return {
        "type": notification["event_type"],
        "notification_id": notification["notification_id"],
        "priority": notification["priority"],
        "created_at": notification["created_at"],
        **payload,
    }


def webhook_signature(secret: str, timestamp: str, body: bytes) -> str:
    signed = timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"hmac-sha256={digest}"


def _local_env_allows_private_webhooks() -> bool:
    env = (os.environ.get("DOOMBERG_ENV") or "").strip().lower()
    if env not in {"test", "local", "dev", "development"}:
        return False
    return os.environ.get("DOOMBERG_ALLOW_PRIVATE_WEBHOOKS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _host_is_public(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address(hostname.strip("[]"))
        addresses = [ip]
    except ValueError:
        try:
            infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise PermanentDeliveryError(f"webhook host cannot be resolved: {hostname}") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]

    for address in addresses:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            return False
    return True


def _validate_webhook_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise PermanentDeliveryError("webhook target must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise PermanentDeliveryError("webhook target URL must not include userinfo")
    private_allowed = _local_env_allows_private_webhooks()
    if parsed.scheme != "https" and not private_allowed:
        raise PermanentDeliveryError("webhook target must use HTTPS")
    if not private_allowed and not _host_is_public(parsed.hostname):
        raise PermanentDeliveryError("webhook target must resolve to a public address")


class _NoWebhookRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class WebhookAdapter:
    def __init__(self, *, timeout_s: float = 5.0) -> None:
        self.timeout_s = timeout_s
        self._opener = urllib.request.build_opener(_NoWebhookRedirects)

    def deliver(self, notification: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
        config = target.get("config") or {}
        url = str(config.get("url") or "").strip()
        if not url:
            raise PermanentDeliveryError("webhook target missing config.url")
        _validate_webhook_url(url)
        secret = str(config.get("hmac_secret") or target.get("secret_ref") or "").strip()
        if not secret:
            raise PermanentDeliveryError("webhook target missing hmac secret")
        body = json.dumps(
            _sterile_payload(notification), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        timestamp = _now()
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Doomberg-Event-Id": notification["notification_id"],
                "X-Doomberg-Timestamp": timestamp,
                "X-Doomberg-Signature": webhook_signature(secret, timestamp, body),
                "User-Agent": "doomberg-notification-dispatcher/1",
            },
        )
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                status = int(getattr(resp, "status", 200))
                text = resp.read(8192).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read(8192).decode("utf-8", errors="replace")
            if 300 <= exc.code < 400:
                raise PermanentDeliveryError("webhook redirects are not allowed") from exc
            if 400 <= exc.code < 500 and exc.code not in {408, 409, 425, 429}:
                raise PermanentDeliveryError(f"webhook HTTP {exc.code}: {detail[:200]}") from exc
            raise TemporaryDeliveryError(f"webhook HTTP {exc.code}: {detail[:200]}") from exc
        except urllib.error.URLError as exc:
            raise TemporaryDeliveryError(f"webhook request failed: {exc}") from exc
        if status >= 500 or status in {408, 409, 425, 429}:
            raise TemporaryDeliveryError(f"webhook HTTP {status}: {text[:200]}")
        if status >= 400:
            raise PermanentDeliveryError(f"webhook HTTP {status}: {text[:200]}")
        return {"status": status, "body": text[:1000]}


class DurableSubscriberAdapter:
    """No-op adapter for subscribers that replay directly from notification_outbox.

    Doomberg UI tenant-level SSE and generic MCP alert polling do not require an external
    network send. Recording a successful attempt keeps dispatcher state honest while the
    durable row remains the source of truth.
    """

    def deliver(self, notification: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "durable",
            "kind": target["kind"],
            "notification_id": notification["notification_id"],
        }


class NotificationDispatcher:
    def __init__(
        self,
        platform: Any,
        *,
        worker_id: str = "notification-dispatcher",
        batch: int = 25,
    ) -> None:
        self.platform = platform
        self.worker_id = worker_id
        self.batch = batch
        durable = DurableSubscriberAdapter()
        webhook = WebhookAdapter()
        self.adapters = {
            "doomberg_ui": durable,
            "generic_mcp_resource": durable,
            "claude_channel": durable,
            "claude_ws": durable,
            "webhook": webhook,
            "openclaw_webhook": webhook,
            "hermes_webhook": webhook,
        }

    def poll_once(self) -> dict[str, Any]:
        notifications = self.platform.notifications.claim_available(
            worker_id=self.worker_id,
            limit=self.batch,
        )
        delivered: list[str] = []
        failed: list[str] = []
        for notification in notifications:
            channels = notification.get("payload", {}).get("channels") or ["doomberg_ui"]
            targets = self.platform.delivery_targets.list(
                notification["tenant_id"],
                kinds=[str(c) for c in channels],
                state="active",
                limit=100,
            )
            if not targets and "doomberg_ui" in channels:
                targets = [
                    {
                        "tenant_id": notification["tenant_id"],
                        "target_id": "doomberg_ui:implicit",
                        "kind": "doomberg_ui",
                        "state": "active",
                        "config": {},
                    }
                ]
            failures = 0
            for target in targets:
                adapter = self.adapters.get(target["kind"])
                if adapter is None:
                    failures += 1
                    self.platform.notifications.record_attempt(
                        notification["tenant_id"],
                        notification["notification_id"],
                        target["target_id"],
                        state="failed",
                        request={"kind": target["kind"]},
                        error=f"unsupported delivery target kind: {target['kind']}",
                    )
                    continue
                request = {"kind": target["kind"], "target_id": target["target_id"]}
                try:
                    response = adapter.deliver(notification, target)
                    self.platform.notifications.record_attempt(
                        notification["tenant_id"],
                        notification["notification_id"],
                        target["target_id"],
                        state="succeeded",
                        request=request,
                        response=response,
                    )
                except PermanentDeliveryError as exc:
                    failures += 1
                    self.platform.notifications.record_attempt(
                        notification["tenant_id"],
                        notification["notification_id"],
                        target["target_id"],
                        state="failed",
                        request=request,
                        error=str(exc),
                    )
                except TemporaryDeliveryError as exc:
                    failures += 1
                    self.platform.notifications.record_attempt(
                        notification["tenant_id"],
                        notification["notification_id"],
                        target["target_id"],
                        state="failed",
                        request=request,
                        error=str(exc),
                    )
            if failures:
                failed.append(notification["notification_id"])
                delay = min(3600, 2 ** min(int(notification.get("attempts") or 1), 10))
                self.platform.notifications.retry_later(
                    notification["tenant_id"],
                    notification["notification_id"],
                    delay_seconds=delay,
                    state="failed",
                )
            else:
                delivered.append(notification["notification_id"])
                self.platform.notifications.mark_sent_or_partial(
                    notification["tenant_id"],
                    notification["notification_id"],
                    failures=0,
                )
        return {"claimed": len(notifications), "delivered": delivered, "failed": failed}

    def run_forever(self, *, interval_s: float = 2.0, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        while not stop.is_set():
            self.poll_once()
            stop.wait(interval_s)
