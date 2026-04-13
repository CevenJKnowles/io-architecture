"""
io_iii.api._sse — Server-Sent Events support (Phase 9 M9.2, ADR-025 §5).

Provides SSE formatting and the session stream handler.

SSE event sequence for GET /session/{id}/stream:
    turn_started          — content-safe: session_id, turn_index, persona_mode
    turn_output           — model response text (user-facing; not logged/forwarded)
    turn_completed        — content-safe governance metadata
    steward_gate_triggered — emitted instead of turn_completed when gate fires

Execution is synchronous (engine is frozen; no token streaming). Events are
emitted after the full turn completes — pseudo-streaming over SSE.

Content policy (ADR-003 / ADR-025 §4 + §5):
    turn_output is the only event carrying model output. It is never written
    to metadata.jsonl or included in webhook payloads (M9.3).
"""
from __future__ import annotations

import json
from typing import IO, Optional

from io_iii.api._handlers import execute_session_turn, _turn_result_payload


# ---------------------------------------------------------------------------
# SSE formatting
# ---------------------------------------------------------------------------

def format_sse(event: str, data: dict) -> bytes:
    """
    Encode a single SSE event as bytes.

    Format:
        event: <name>\\n
        data: <json>\\n
        \\n

    Args:
        event: SSE event name (e.g. "turn_started")
        data:  content-safe dict payload

    Returns:
        UTF-8 encoded SSE message bytes.
    """
    json_data = json.dumps(data, separators=(",", ":"))
    return f"event: {event}\ndata: {json_data}\n\n".encode("utf-8")


# ---------------------------------------------------------------------------
# SSE event names (frozen set — analogous to _RUNBOOK_LIFECYCLE_EVENTS)
# ---------------------------------------------------------------------------

_SSE_SESSION_EVENTS: frozenset = frozenset({
    "turn_started",
    "turn_output",
    "turn_completed",
    "steward_gate_triggered",
    "turn_error",
})
"""
Frozen set of SSE event names emitted by the session stream handler (ADR-025 §5).
"""


def _flush(wfile: IO[bytes]) -> None:
    """Flush write buffer if supported (not all file-like objects implement flush)."""
    try:
        wfile.flush()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Session stream handler
# ---------------------------------------------------------------------------

def stream_session_turn(
    session_id: str,
    prompt: str,
    cfg,
    wfile: IO[bytes],
    *,
    persona_mode: str = "executor",
    audit: bool = False,
) -> None:
    """
    Execute one bounded session turn and emit SSE events to wfile (M9.2).

    The caller is responsible for writing the HTTP response line and headers
    before calling this function. wfile should be the raw socket write buffer.

    Event sequence:
        1. turn_started          — emitted immediately (content-safe metadata)
        2. [turn execution runs synchronously]
        3a. turn_output          — model response text (on success)
            turn_completed       — governance metadata (on success, no pause)
        3b. turn_output          — model response text (on pause)
            steward_gate_triggered — pause metadata (on steward gate fire)
        3c. turn_error           — error code (on failure)

    Args:
        session_id:   target session identifier
        prompt:       user turn prompt (content-plane; not stored in events except turn_output)
        cfg:          IO3Config
        wfile:        writable byte stream (HTTP response body)
        persona_mode: persona route (default "executor")
        audit:        challenger audit flag

    Content policy (ADR-025 §5):
        turn_output carries model text — it is the user-facing result.
        All other events are content-safe (structural metadata only).
    """
    # Emit turn_started immediately so the client gets feedback before execution
    wfile.write(format_sse("turn_started", {
        "session_id": session_id,
        "persona_mode": persona_mode,
    }))
    _flush(wfile)

    # Execute the turn synchronously (engine is frozen; no token streaming)
    turn_result, error_code = execute_session_turn(
        session_id=session_id,
        prompt=prompt,
        cfg=cfg,
        persona_mode=persona_mode,
        audit=audit,
    )

    if error_code is not None:
        wfile.write(format_sse("turn_error", {"error_code": error_code}))
        _flush(wfile)
        return

    # Emit turn_output (model response — user-facing; not logged or forwarded)
    wfile.write(format_sse("turn_output", {
        "session_id": session_id,
        "output": turn_result.result.message,
    }))
    _flush(wfile)

    # Emit turn_completed or steward_gate_triggered
    if turn_result.pause_state is not None:
        wfile.write(format_sse("steward_gate_triggered", {
            "threshold_key": turn_result.pause_state.threshold_key,
            "step_index": turn_result.pause_state.step_index,
            "steps_total": turn_result.pause_state.steps_total,
            "session_mode": turn_result.pause_state.session_mode.value,
            "run_id": turn_result.pause_state.run_id,
            "valid_actions": sorted(turn_result.pause_state.VALID_ACTIONS),
        }))
    else:
        wfile.write(format_sse("turn_completed", _turn_result_payload(turn_result)))
    _flush(wfile)
