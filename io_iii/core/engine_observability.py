from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from io_iii.core.content_safety import assert_no_forbidden_keys


# ---------------------------------------------------------------------------
# Event kind enumeration (Phase 4 M4.5)
# ---------------------------------------------------------------------------

class EngineEventKind(str, Enum):
    """
    Enumeration of content-safe engine lifecycle event identifiers (M4.5).

    Values are stable strings suitable for direct JSON serialization.
    No value matches a forbidden content key.

    Canonical lifecycle order per engine run (success path):
      RUN_STARTED                 — entry into engine.run()
      ROUTE_RESOLVED              — routing snapshot confirmed from SessionState
      PROVIDER_EXECUTION_COMPLETE — provider delivered its result
      CHALLENGER_AUDIT_COMPLETE   — challenger verdict received (audit=True path only)
      REVISION_COMPLETE           — controlled revision applied (needs_work path only)
      OUTPUT_EMITTED              — ExecutionResult constructed; about to return
      RUN_COMPLETE                — engine.run() returning; trace terminal (completed)

    Failure terminal event (M4.6):
      RUN_FAILED                  — engine.run() exiting via exception; trace terminal (failed)
        meta includes: failure_kind, failure_code, phase

    Exactly one of RUN_COMPLETE or RUN_FAILED is emitted per run.
    Only events on the active path are emitted; optional events are absent, not null.
    """
    RUN_STARTED                 = "engine_run_started"
    ROUTE_RESOLVED              = "route_resolved"
    PROVIDER_EXECUTION_COMPLETE = "provider_execution_complete"
    CHALLENGER_AUDIT_COMPLETE   = "challenger_audit_complete"
    REVISION_COMPLETE           = "revision_complete"
    OUTPUT_EMITTED              = "output_emitted"
    RUN_COMPLETE                = "engine_run_complete"
    RUN_FAILED                  = "engine_run_failed"


# ---------------------------------------------------------------------------
# Event record (frozen, content-safe)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineEvent:
    """
    One content-safe engine lifecycle event (M4.5).

    Immutable once emitted. Carries only structural metadata.

    Fields:
        kind          — EngineEventKind value (stable string identifier)
        timestamp_ms  — epoch ms at emission (monotonic wall-clock; not perf_counter)
        request_id    — session linkage (equals SessionState.request_id)
        task_spec_id  — upstream TaskSpec binding; None for CLI paths
        meta          — small structural dict (provider/model/bools/codes/counts only)

    Content policy:
        meta must never contain prompt text, completion text, or model output.
        Enforced by EngineObservabilityLog.emit() at emit time.
    """
    kind: str
    timestamp_ms: int
    request_id: str
    task_spec_id: Optional[str]
    meta: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Observability log (engine-internal, bounded)
# ---------------------------------------------------------------------------

# Bounded maximum events per engine run.
# Headroom above the 7 canonical hooks to accommodate audit/revision path
# variants without a bounds change.
_MAX_EVENTS: int = 16


class EngineObservabilityLog:
    """
    Bounded accumulator for engine lifecycle events (Phase 4 M4.5).

    Lifecycle:
      Created inside engine.run() alongside TraceRecorder.
      Not injected via RuntimeDependencies — engine-internal concern.
      Serialized into ExecutionResult.meta["engine_events"] before return.

    Contract:
      - At most _MAX_EVENTS events per log. Overflow raises RuntimeError.
      - Content-safe: each meta dict is checked via assert_no_forbidden_keys at emit time.
      - to_list() returns a JSON-safe list; safe to attach to meta directly.
    """

    def __init__(self) -> None:
        self._events: List[EngineEvent] = []

    @property
    def event_count(self) -> int:
        """Current number of recorded events."""
        return len(self._events)

    def emit(
        self,
        kind: EngineEventKind,
        *,
        request_id: str,
        task_spec_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record one lifecycle event.

        Raises:
            RuntimeError: if the log has reached _MAX_EVENTS capacity.
            ValueError:   if meta contains a forbidden content key (assert_no_forbidden_keys).
        """
        if len(self._events) >= _MAX_EVENTS:
            raise RuntimeError(
                f"OBSERVABILITY_LOG_CAPACITY: cannot emit '{kind.value}' — "
                f"log is at capacity ({_MAX_EVENTS} events)"
            )
        safe_meta: Dict[str, Any] = meta if meta is not None else {}
        # Fail-fast content-leak guard — checked at emit time, not only at serialization.
        assert_no_forbidden_keys(safe_meta)
        self._events.append(
            EngineEvent(
                kind=kind.value,
                timestamp_ms=int(time.time() * 1000),
                request_id=request_id,
                task_spec_id=task_spec_id,
                meta=safe_meta,
            )
        )

    def to_list(self) -> List[Dict[str, Any]]:
        """Serialize all events to a list of content-safe dicts.

        Ordering is preserved (insertion order = emission order = lifecycle order).
        """
        return [
            {
                "kind": e.kind,
                "timestamp_ms": e.timestamp_ms,
                "request_id": e.request_id,
                "task_spec_id": e.task_spec_id,
                "meta": dict(e.meta),
            }
            for e in self._events
        ]
