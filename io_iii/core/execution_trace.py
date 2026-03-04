from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


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
    """Structured, content-safe execution trace (Phase 3 M3.8).

    Attached to ExecutionResult.meta["trace"].
    """

    trace_id: str
    schema: str = "io-iii-execution-trace"
    schema_version: str = "v1.0"
    started_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    steps: List[TraceStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "started_at_ms": self.started_at_ms,
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


class TraceRecorder:
    """Convenience wrapper for recording ordered trace steps."""

    def __init__(self, *, trace_id: str):
        self._trace = ExecutionTrace(trace_id=trace_id)

    @property
    def trace(self) -> ExecutionTrace:
        return self._trace

    @contextmanager
    def step(self, stage: str, *, meta: Optional[Dict[str, Any]] = None) -> Iterator[None]:
        started_at_ms = int(time.time() * 1000)
        t0 = time.perf_counter_ns()
        try:
            yield
        finally:
            dt_ms = int((time.perf_counter_ns() - t0) / 1_000_000)
            self._trace.steps.append(
                TraceStep(stage=stage, started_at_ms=started_at_ms, duration_ms=dt_ms, meta=meta or {})
            )
