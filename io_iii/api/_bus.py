"""
io_iii.api._bus — In-process session event log (Phase 9 M9.2).

Provides a content-safe, append-only event log per session.  SSE subscribers
read from the log using a cursor (integer offset into the list).

Design: poll-based rather than push-based.
- publish() appends to the per-session list under a threading.Lock.
- get_events_since() returns all events from `cursor` onward.

Content-safety (ADR-003): events contain structural metadata only.
No prompt text, model output, persona content, or memory values appear in
any event payload.

Event types (ADR-025 §4):
    session_state           — current state on stream connect
    turn_started            — before cmd_session_continue executes
    turn_completed          — after cmd_session_continue returns
    steward_gate_triggered  — when session status → paused
    session_closed          — when session status → closed
    runbook_completed       — after cmd_runbook returns
    keepalive               — synthetic; emitted by SSE endpoint, not stored here
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List

_lock = threading.Lock()
# session_id → ordered list of event dicts
_log: Dict[str, List[Dict[str, Any]]] = {}


def publish(session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    """Append a content-safe event to the session log (thread-safe)."""
    entry = {
        "event": event_type,
        "data": payload,
        "ts": time.time(),
    }
    with _lock:
        _log.setdefault(session_id, []).append(entry)


def get_events_since(session_id: str, cursor: int) -> List[Dict[str, Any]]:
    """Return all events from *cursor* onward (non-blocking, thread-safe)."""
    with _lock:
        events = _log.get(session_id, [])
        return list(events[cursor:])


def clear(session_id: str) -> None:
    """Remove all stored events for a session (e.g. after TTL expiry)."""
    with _lock:
        _log.pop(session_id, None)


# Sentinel event type: causes the SSE generator to terminate gracefully.
STREAM_CLOSE_EVENT = "__stream_close__"


def close_stream(session_id: str) -> None:
    """Publish a sentinel that terminates the SSE generator for this session."""
    publish(session_id, STREAM_CLOSE_EVENT, {})
