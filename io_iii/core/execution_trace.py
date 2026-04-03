from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


# ---------------------------------------------------------------------------
# Lifecycle contract (Phase 4 M4.3)
# ---------------------------------------------------------------------------

class TraceLifecycleError(Exception):
    """
    Raised when an invalid lifecycle transition is attempted on a TraceRecorder.

    Valid transitions:
      created  → running   (via start() or first step())
      created  → failed    (via fail(); error before any step)
      running  → completed (via complete())
      running  → failed    (via fail())
      completed → (terminal; no further transitions)
      failed    → (terminal; no further transitions)
    """


# Transition table: maps current status → set of permitted next statuses.
_VALID_TRANSITIONS: Dict[str, frozenset] = {
    "created":   frozenset({"running", "failed"}),
    "running":   frozenset({"completed", "failed"}),
    "completed": frozenset(),   # terminal
    "failed":    frozenset(),   # terminal
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TraceStep:
    """One content-safe execution step.

    Constraints:
    - Never include prompt/completion content.
    - Keep metadata small and structural (provider/model/bools/codes).
    """

    stage: str
    started_at_ms: int
    duration_ms: int
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionTrace:
    """Structured, content-safe execution trace (Phase 3 M3.8 / Phase 4 M4.3).

    Attached to ExecutionResult.meta["trace"].

    Lifecycle field: status
      "created"   — recorder initialised, no steps started
      "running"   — at least one step recorded or start() called explicitly
      "completed" — all steps finished; trace is terminal and safe to serialise
      "failed"    — execution was interrupted; trace is terminal

    The status field is the canonical lifecycle signal. Consumers must not
    infer lifecycle from the steps list alone.
    """

    trace_id: str
    schema: str = "io-iii-execution-trace"
    schema_version: str = "v1.0"
    started_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    steps: List[TraceStep] = field(default_factory=list)
    status: str = "created"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "started_at_ms": self.started_at_ms,
            "status": self.status,
            "steps": [
                {
                    "stage": s.stage,
                    "started_at_ms": s.started_at_ms,
                    "duration_ms": s.duration_ms,
                    "meta": dict(s.meta or {}),
                }
                for s in self.steps
            ],
        }


# ---------------------------------------------------------------------------
# Recorder with explicit lifecycle management
# ---------------------------------------------------------------------------

class TraceRecorder:
    """
    Convenience wrapper for recording ordered trace steps with explicit lifecycle.

    Lifecycle methods:
      start()    — 'created' → 'running' (explicit; also auto-triggered by first step())
      complete() — 'running' → 'completed'
      fail()     — 'created'/'running' → 'failed'

    step() context manager:
      - Auto-calls start() if status is 'created' (implicit first-step start).
      - Raises TraceLifecycleError if status is 'completed' or 'failed'.
      - Always records the step in finally (even if step body raises).
    """

    def __init__(self, *, trace_id: str) -> None:
        self._trace = ExecutionTrace(trace_id=trace_id)

    @property
    def trace(self) -> ExecutionTrace:
        return self._trace

    @property
    def status(self) -> str:
        return self._trace.status

    # ------------------------------------------------------------------
    # Internal transition engine
    # ------------------------------------------------------------------

    def _transition(self, to: str) -> None:
        from_status = self._trace.status
        allowed = _VALID_TRANSITIONS.get(from_status, frozenset())
        if to not in allowed:
            raise TraceLifecycleError(
                f"TRACE_INVALID_TRANSITION: '{from_status}' → '{to}' is not permitted"
            )
        self._trace.status = to

    # ------------------------------------------------------------------
    # Public lifecycle methods
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Explicitly transition 'created' → 'running'.

        Called before the first step when the caller wants an explicit lifecycle
        boundary. Also invoked automatically by the first step() call.
        """
        self._transition("running")

    def complete(self) -> None:
        """Transition 'running' → 'completed'.

        Must be called after all steps are recorded and before to_dict() is
        called on the canonical result path. Marks the trace as terminal.
        """
        self._transition("completed")

    def fail(self) -> None:
        """Transition 'created' or 'running' → 'failed'.

        Called when the execution path that owns this trace raises an exception.
        Marks the trace as terminal without serialising a result.
        """
        self._transition("failed")

    # ------------------------------------------------------------------
    # Step recording
    # ------------------------------------------------------------------

    @contextmanager
    def step(self, stage: str, *, meta: Optional[Dict[str, Any]] = None) -> Iterator[None]:
        """Record one content-safe execution step.

        Auto-starts the trace if still in 'created' state (first step semantics).
        Raises TraceLifecycleError if called on a terminal trace ('completed'/'failed').
        Always appends the step in finally — even if the step body raises.
        """
        # Auto-start on first step (created → running).
        if self._trace.status == "created":
            self.start()

        # Guard: block step recording on terminal traces.
        if self._trace.status != "running":
            raise TraceLifecycleError(
                f"TRACE_STEP_BLOCKED: cannot record step '{stage}' — "
                f"trace is in terminal state '{self._trace.status}'"
            )

        started_at_ms = int(time.time() * 1000)
        t0 = time.perf_counter_ns()
        try:
            yield
        finally:
            dt_ms = int((time.perf_counter_ns() - t0) / 1_000_000)
            self._trace.steps.append(
                TraceStep(
                    stage=stage,
                    started_at_ms=started_at_ms,
                    duration_ms=dt_ms,
                    meta=meta or {},
                )
            )
