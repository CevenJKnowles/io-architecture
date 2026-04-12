"""
io_iii.api._webhooks — Webhook dispatcher (Phase 9 M9.3, ADR-025 §6).

Fires best-effort HTTP POST callbacks on governed session lifecycle events:
    SESSION_COMPLETE          — session status transitions to closed
    RUNBOOK_COMPLETE          — runbook result status is completed
    STEWARD_GATE_TRIGGERED    — PauseState emitted by StewardGate

Webhook destinations declared in runtime.yaml under ``webhooks:``:

    webhooks:
      session_complete:
        url: "http://localhost:9000/webhook"
      runbook_complete:
        url: "http://localhost:9000/webhook"
      steward_gate_triggered:
        url: "http://localhost:9000/webhook"

Absent ``webhooks:`` key is the safe default — no webhooks are fired (ADR-025 §6).

Delivery is best-effort: single attempt, 5-second timeout, no retry queue.
Delivery failure is silent and never affects execution or session state.

Content policy (ADR-003 / ADR-025 §4 + §6):
    All webhook payloads are strictly content-safe.
    No prompt text, model output, memory values, or config paths.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Webhook event taxonomy (ADR-025 §6)
# ---------------------------------------------------------------------------

WEBHOOK_SESSION_COMPLETE: str = "session_complete"
WEBHOOK_RUNBOOK_COMPLETE: str = "runbook_complete"
WEBHOOK_STEWARD_GATE_TRIGGERED: str = "steward_gate_triggered"

_WEBHOOK_EVENTS: frozenset = frozenset({
    WEBHOOK_SESSION_COMPLETE,
    WEBHOOK_RUNBOOK_COMPLETE,
    WEBHOOK_STEWARD_GATE_TRIGGERED,
})
"""Frozen set of valid webhook event types (ADR-025 §6)."""


# ---------------------------------------------------------------------------
# WebhookDispatcher
# ---------------------------------------------------------------------------

class WebhookDispatcher:
    """
    Best-effort webhook dispatcher (Phase 9 M9.3, ADR-025 §6).

    Loads webhook destinations from runtime.yaml ``webhooks:`` block at
    construction. Absent block or absent event key → no-op on dispatch.

    Dispatch is:
        - best-effort (single attempt, 5s timeout)
        - silent on failure (never raises, never affects session state)
        - content-safe (payloads never contain model output or prompt text)

    Usage:
        dispatcher = WebhookDispatcher.from_runtime_config(cfg.runtime)
        dispatcher.dispatch(WEBHOOK_SESSION_COMPLETE, {"session_id": ..., ...})
    """

    def __init__(self, webhook_config: Dict[str, Any]) -> None:
        """
        Args:
            webhook_config: dict mapping event names to destination config.
                            Each entry must have at least a "url" key.
                            May be empty — safe default.
        """
        self._config: Dict[str, Any] = webhook_config or {}

    @classmethod
    def from_runtime_config(cls, runtime_config: Dict[str, Any]) -> "WebhookDispatcher":
        """
        Build a WebhookDispatcher from runtime.yaml content.

        Absent ``webhooks:`` key → empty dispatcher (safe default, ADR-025 §6).
        """
        raw = runtime_config.get("webhooks")
        if not isinstance(raw, dict):
            raw = {}
        return cls(raw)

    def dispatch(self, event_type: str, payload: dict) -> None:
        """
        Fire a webhook for the given event type (best-effort, ADR-025 §6).

        Args:
            event_type: one of the _WEBHOOK_EVENTS constants
            payload:    content-safe dict (no model output, no prompt, no memory values)

        Delivery failure is silent — no exception is raised to the caller.
        The event_type is validated against the frozen taxonomy; unknown events
        are silently ignored.
        """
        if event_type not in _WEBHOOK_EVENTS:
            return

        entry = self._config.get(event_type)
        if not entry:
            return

        url = entry.get("url") if isinstance(entry, dict) else None
        if not url or not isinstance(url, str):
            return

        headers = {"Content-Type": "application/json", "X-IO3-Event": event_type}
        if isinstance(entry, dict):
            extra_headers = entry.get("headers")
            if isinstance(extra_headers, dict):
                headers.update({k: str(v) for k, v in extra_headers.items()})

        timeout = int(entry.get("timeout_seconds", 5)) if isinstance(entry, dict) else 5

        try:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            urllib.request.urlopen(req, timeout=timeout)
        except Exception:
            # Best-effort: delivery failure is silent (ADR-025 §6)
            pass

    def is_configured(self, event_type: str) -> bool:
        """True if a webhook destination is declared for the given event type."""
        entry = self._config.get(event_type)
        if not isinstance(entry, dict):
            return False
        return bool(entry.get("url"))
