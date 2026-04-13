"""
io_iii.api._webhooks — Fire-and-forget webhook dispatch (Phase 9 M9.3).

Fires an HTTP POST to the configured webhook_url on the following events:
    SESSION_COMPLETE        — session closed normally or at_limit
    RUNBOOK_COMPLETE        — runbook execution finished
    STEWARD_GATE_TRIGGERED  — session status transitioned to paused

Payloads are content-safe (ADR-003): structural metadata only.
No prompt text, model output, persona content, or memory values.

Configuration (runtime.yaml):
    webhook_url: https://example.com/hooks/io-iii   # optional

Dispatch is non-blocking: each call spawns a daemon thread that fires
the request and discards the result.  Errors are silently swallowed —
webhook delivery is best-effort only (ADR-025 §6).
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


# Event type constants (used by server.py)
WEBHOOK_SESSION_COMPLETE = "SESSION_COMPLETE"
WEBHOOK_RUNBOOK_COMPLETE = "RUNBOOK_COMPLETE"
WEBHOOK_STEWARD_GATE_TRIGGERED = "STEWARD_GATE_TRIGGERED"

_WEBHOOK_TIMEOUT_S = 5


def _fire(url: str, body: Dict[str, Any]) -> None:
    """Send a single HTTP POST (called from a daemon thread)."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_WEBHOOK_TIMEOUT_S):
            pass
    except Exception:
        pass  # fire-and-forget; delivery is best-effort


def dispatch(
    url: Optional[str],
    event_type: str,
    payload: Dict[str, Any],
) -> None:
    """
    Dispatch a content-safe webhook in a background daemon thread.

    No-op when *url* is None or empty.

    Args:
        url:        Webhook endpoint URL (from runtime.yaml ``webhook_url``).
        event_type: One of SESSION_COMPLETE, RUNBOOK_COMPLETE,
                    STEWARD_GATE_TRIGGERED.
        payload:    Content-safe structural metadata dict (ADR-003).
    """
    if not url:
        return
    body = {"event": event_type, **payload}
    t = threading.Thread(target=_fire, args=(url, body), daemon=True)
    t.start()


def get_webhook_url(runtime_cfg: Dict[str, Any]) -> Optional[str]:
    """Extract webhook_url from runtime.yaml config dict (may be None)."""
    url = runtime_cfg.get("webhook_url")
    return url if isinstance(url, str) and url.strip() else None


class WebhookDispatcher:
    """Stateful webhook dispatcher bound to a URL from runtime config."""

    def __init__(self, url: Optional[str]) -> None:
        self._url = url

    @classmethod
    def from_runtime_config(cls, runtime_cfg: Dict[str, Any]) -> "WebhookDispatcher":
        return cls(get_webhook_url(runtime_cfg))

    def dispatch(self, event_type: str, payload: Dict[str, Any]) -> None:
        dispatch(self._url, event_type, payload)
