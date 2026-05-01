"""
io_iii.api._webhooks — Fire-and-forget webhook dispatch (Phase 9 M9.3).

Fires an HTTP POST to the configured webhook URL on the following events:
    session_complete        — session closed normally or at_limit
    runbook_complete        — runbook execution finished
    steward_gate_triggered  — session status transitioned to paused

Payloads are content-safe (ADR-003): structural metadata only.
No prompt text, model output, persona content, or memory values.

Configuration (runtime.yaml):
    webhooks:
        session_complete:
            url: https://example.com/hooks/io-iii
            timeout_seconds: 5          # optional, default 5
        runbook_complete:
            url: https://example.com/hooks/io-iii

Dispatch is non-blocking: each call spawns a daemon thread that fires
the request and discards the result. Errors are silently swallowed —
webhook delivery is best-effort only (ADR-025 §6).

Backward-compatible module-level dispatch() and get_webhook_url() functions
are retained for existing call sites.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Event taxonomy
# ---------------------------------------------------------------------------

WEBHOOK_SESSION_COMPLETE        = "session_complete"
WEBHOOK_RUNBOOK_COMPLETE        = "runbook_complete"
WEBHOOK_STEWARD_GATE_TRIGGERED  = "steward_gate_triggered"

_WEBHOOK_EVENTS: frozenset = frozenset({
    WEBHOOK_SESSION_COMPLETE,
    WEBHOOK_RUNBOOK_COMPLETE,
    WEBHOOK_STEWARD_GATE_TRIGGERED,
})

_DEFAULT_TIMEOUT_S = 5


# ---------------------------------------------------------------------------
# Low-level HTTP fire (module-level; signature must remain (url, body))
# ---------------------------------------------------------------------------

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
        with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT_S):
            pass
    except Exception:
        pass  # fire-and-forget; delivery is best-effort


def _fire_event(url: str, event: str, body: Dict[str, Any], timeout: int) -> None:
    """Send a single HTTP POST with per-event header and configurable timeout."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Io3-Event": event,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            pass
    except Exception:
        pass  # fire-and-forget; delivery is best-effort


# ---------------------------------------------------------------------------
# Module-level dispatch (backward-compatible; used by app.py)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# WebhookDispatcher — per-event config (M9.3 contract)
# ---------------------------------------------------------------------------

class WebhookDispatcher:
    """
    Stateful webhook dispatcher bound to a per-event config dict.

    Config shape (mirrors runtime.yaml webhooks block):
        {
            "session_complete":       {"url": "...", "timeout_seconds": 5},
            "runbook_complete":       {"url": "..."},
            "steward_gate_triggered": {"url": "..."},
        }
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config: Dict[str, Any] = config if isinstance(config, dict) else {}

    @classmethod
    def from_runtime_config(cls, runtime_cfg: Dict[str, Any]) -> "WebhookDispatcher":
        """
        Construct from a full runtime config dict.

        Reads the ``webhooks`` key; returns an empty dispatcher if absent
        or malformed.
        """
        webhooks = runtime_cfg.get("webhooks")
        if not isinstance(webhooks, dict):
            return cls({})
        return cls(webhooks)

    def is_configured(self, event: str) -> bool:
        """Return True if *event* is a known event type and has a non-empty URL."""
        if event not in _WEBHOOK_EVENTS:
            return False
        cfg = self._config.get(event)
        if not isinstance(cfg, dict):
            return False
        url = cfg.get("url")
        return bool(url and isinstance(url, str) and url.strip())

    def dispatch(self, event: str, payload: Dict[str, Any]) -> None:
        """
        Dispatch a content-safe webhook in a background daemon thread.

        No-op when event is unknown, config is absent, or URL is empty.
        Errors are silently swallowed (ADR-025 §6).
        """
        if event not in _WEBHOOK_EVENTS:
            return
        cfg = self._config.get(event)
        if not isinstance(cfg, dict):
            return
        url = cfg.get("url", "")
        if not url:
            return
        timeout = int(cfg.get("timeout_seconds", _DEFAULT_TIMEOUT_S))
        body = {"event": event, **payload}
        t = threading.Thread(
            target=_fire_event,
            args=(url, event, body, timeout),
            daemon=True,
        )
        t.start()
