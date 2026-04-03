from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from typing import Any, List, Optional

from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.engine import ExecutionResult
from io_iii.core.failure_model import RuntimeFailure
from io_iii.core.runbook import Runbook
from io_iii.core.session_state import SessionState
import io_iii.core.orchestrator as _orchestrator


# ---------------------------------------------------------------------------
# Frozen lifecycle event taxonomy (ADR-015)
# ---------------------------------------------------------------------------

_RUNBOOK_LIFECYCLE_EVENTS: frozenset = frozenset({
    "runbook_started",
    "runbook_step_started",
    "runbook_step_completed",
    "runbook_step_failed",
    "runbook_completed",
    "runbook_terminated",
})
"""
Frozen set of permitted runbook lifecycle event names (ADR-015).
No event outside this set may be emitted by the runner.
"""


# ---------------------------------------------------------------------------
# Lifecycle event record (ADR-015)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RunbookLifecycleEvent:
    """
    A single content-safe runbook lifecycle event (ADR-015).

    Only structural correlation fields are permitted. No field may carry
    prompt text, model output, capability payload content, or free-form
    exception message strings.

    Fields:
        event             — one of the six frozen taxonomy values (ADR-015)
        runbook_id        — correlation to the originating Runbook
        steps_total       — declared step count of the Runbook at construction
        request_id        — per-step SessionState linkage when available
        task_spec_id      — step-level TaskSpec correlation identifier
        step_index        — zero-based step position within the Runbook
        terminated_early  — True if runbook terminated before all steps completed
        failed_step_index — zero-based index of the failing step, if any
        duration_ms       — step-level wall-clock duration in milliseconds
        total_duration_ms — runbook-level wall-clock duration in milliseconds
        failure_kind      — RuntimeFailureKind value string (ADR-013), if applicable
        failure_code      — stable failure code from ADR-013, if applicable

    Content policy:
        failure_kind and failure_code carry only structured ADR-013 identifiers,
        never free-form message content. task_spec_id and request_id are
        machine-generated identifiers only.
    """

    event: str
    runbook_id: str
    steps_total: int
    request_id: Optional[str] = None
    task_spec_id: Optional[str] = None
    step_index: Optional[int] = None
    terminated_early: Optional[bool] = None
    failed_step_index: Optional[int] = None
    duration_ms: Optional[int] = None
    total_duration_ms: Optional[int] = None
    failure_kind: Optional[str] = None
    failure_code: Optional[str] = None


# ---------------------------------------------------------------------------
# Metadata projection container (ADR-015)
# ---------------------------------------------------------------------------

@dataclass
class RunbookMetadataProjection:
    """
    Ordered projection of runbook lifecycle events (ADR-015).

    This is a read-only observability projection. It does not alter execution
    behaviour, does not drive routing, and cannot be used to resume or replay
    a run. ExecutionTrace remains the canonical runtime truth surface.

    Fields:
        runbook_id — correlation to the originating Runbook
        events     — ordered list of RunbookLifecycleEvents in emission order
    """

    runbook_id: str
    events: List[RunbookLifecycleEvent] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-step outcome record (ADR-014 §14)
# ---------------------------------------------------------------------------

@dataclass
class RunbookStepOutcome:
    """
    Structural record of a single runbook step execution (ADR-014 §14).

    Content policy:
    - No prompt or model output text may appear in any field.
    - state and result carry the orchestrator outputs directly; the content
      policy that governs those types (SessionState, ExecutionResult) applies.
    - failure carries a RuntimeFailure envelope (ADR-013), which is content-safe.
    - task_spec_id and step_index are structural correlation identifiers only.
    """

    step_index: int
    task_spec_id: str
    state: Optional[SessionState]
    result: Optional[ExecutionResult]
    success: bool
    failure: Optional[RuntimeFailure]


# ---------------------------------------------------------------------------
# Runbook execution result (ADR-014 §14 / ADR-015)
# ---------------------------------------------------------------------------

@dataclass
class RunbookResult:
    """
    Bounded, content-safe result of a full runbook execution (ADR-014 §14 / ADR-015).

    Fields:
        runbook_id         — matches the originating Runbook.runbook_id
        step_outcomes      — ordered list of per-step outcome records
        steps_completed    — count of steps that completed without exception
        failed_step_index  — index of the failing step, or None if all succeeded
        terminated_early   — True when a step failure caused early termination
        metadata           — ordered lifecycle event projection (ADR-015);
                             None only when constructed outside the runner

    Content policy:
    - runbook_id, step_outcomes task_spec_id/step_index, steps_completed,
      failed_step_index, and terminated_early are all structural identifiers.
    - No prompt or model output content may appear directly in this record.
    - metadata carries the RunbookMetadataProjection (projection-only, ADR-015).
    """

    runbook_id: str
    step_outcomes: List[RunbookStepOutcome] = field(default_factory=list)
    steps_completed: int = 0
    failed_step_index: Optional[int] = None
    terminated_early: bool = False
    metadata: Optional[RunbookMetadataProjection] = None


# ---------------------------------------------------------------------------
# Internal timing helper
# ---------------------------------------------------------------------------

def _elapsed_ms(start_ns: int) -> int:
    """Return wall-clock milliseconds elapsed since start_ns (monotonic_ns)."""
    return (_time.monotonic_ns() - start_ns) // 1_000_000


# ---------------------------------------------------------------------------
# Runner (ADR-014 §3–§13 / ADR-015)
# ---------------------------------------------------------------------------

def run(
    *,
    runbook: Runbook,
    cfg: Any,
    deps: RuntimeDependencies,
    audit: bool = False,
) -> RunbookResult:
    """
    Execute a Runbook by delegating each step through orchestrator.run() (ADR-014).
    Emits a deterministic ordered RunbookMetadataProjection during execution (ADR-015).

    Contract (ADR-014):
    - Steps execute strictly in declared order (step 0, step 1, …).
    - Each step is exactly one orchestrator.run() call — never engine.run() directly.
    - ADR-009 bounds (max 1 audit pass, max 1 revision pass) are enforced per step
      by the orchestrator/engine layer.
    - If a step raises, the runbook terminates immediately at that step.
    - No steps execute after a failure.
    - No retry of the failed step.
    - No branching — runtime outputs from any step do not influence step order.
    - No output-driven control flow of any kind.

    Observability contract (ADR-015):
    - Emits exactly six lifecycle event classes in deterministic order.
    - All events are structural and content-safe (no prompt/output text).
    - ExecutionTrace remains the canonical runtime truth; projection is read-only.
    - Timing captured via time.monotonic_ns(); reported as integer milliseconds.

    Success path event ordering:
        runbook_started
        → runbook_step_started   (step i)
        → runbook_step_completed (step i)
        → ...
        → runbook_completed

    Failure path event ordering:
        runbook_started
        → runbook_step_started (step K)
        → runbook_step_failed  (step K)
        → runbook_terminated

    Args:
        runbook  — the Runbook to execute; must be a Runbook instance
        cfg      — runtime config (same contract as orchestrator.run)
        deps     — RuntimeDependencies (same contract as orchestrator.run)
        audit    — whether to enable the challenger audit pass per step

    Returns:
        RunbookResult with per-step outcomes, termination metadata, and
        an attached RunbookMetadataProjection (ADR-015).

    Raises:
        TypeError: if runbook is not a Runbook instance.
        TypeError: if deps is not a RuntimeDependencies instance.
    """
    if not isinstance(runbook, Runbook):
        raise TypeError(
            f"runbook must be a Runbook instance, got {type(runbook).__name__}"
        )

    if not isinstance(deps, RuntimeDependencies):
        raise TypeError(
            f"deps must be a RuntimeDependencies instance, got {type(deps).__name__}"
        )

    steps_total = len(runbook.steps)
    projection = RunbookMetadataProjection(runbook_id=runbook.runbook_id)
    runbook_start_ns = _time.monotonic_ns()

    # runbook_started — emitted once before step iteration begins (ADR-015 §2).
    projection.events.append(RunbookLifecycleEvent(
        event="runbook_started",
        runbook_id=runbook.runbook_id,
        steps_total=steps_total,
    ))

    outcomes: List[RunbookStepOutcome] = []

    for i, task_spec in enumerate(runbook.steps):

        # runbook_step_started — emitted before each orchestrator.run() call (ADR-015 §2).
        projection.events.append(RunbookLifecycleEvent(
            event="runbook_step_started",
            runbook_id=runbook.runbook_id,
            steps_total=steps_total,
            task_spec_id=task_spec.task_spec_id,
            step_index=i,
        ))

        step_start_ns = _time.monotonic_ns()

        try:
            # Exactly one orchestrator.run() call per step (ADR-014 §3).
            # Never calls engine.run() directly.
            # ADR-009 bounds enforced by the orchestrator/engine layer.
            state, result = _orchestrator.run(
                task_spec=task_spec,
                cfg=cfg,
                deps=deps,
                audit=audit,
            )

            step_duration_ms = _elapsed_ms(step_start_ns)

            outcomes.append(RunbookStepOutcome(
                step_index=i,
                task_spec_id=task_spec.task_spec_id,
                state=state,
                result=result,
                success=True,
                failure=None,
            ))

            # runbook_step_completed — emitted after successful step (ADR-015 §2).
            # request_id sourced from the returned SessionState (structural, not content).
            projection.events.append(RunbookLifecycleEvent(
                event="runbook_step_completed",
                runbook_id=runbook.runbook_id,
                steps_total=steps_total,
                task_spec_id=task_spec.task_spec_id,
                step_index=i,
                request_id=state.request_id,
                duration_ms=step_duration_ms,
            ))

        except Exception as exc:
            step_duration_ms = _elapsed_ms(step_start_ns)

            # Attach RuntimeFailure envelope if the engine decorated the exception (ADR-013).
            failure: Optional[RuntimeFailure] = getattr(exc, "runtime_failure", None)

            outcomes.append(RunbookStepOutcome(
                step_index=i,
                task_spec_id=task_spec.task_spec_id,
                state=None,
                result=None,
                success=False,
                failure=failure,
            ))

            # runbook_step_failed — emitted immediately after a step raises (ADR-015 §2).
            # failure_kind and failure_code sourced from ADR-013 envelope only.
            projection.events.append(RunbookLifecycleEvent(
                event="runbook_step_failed",
                runbook_id=runbook.runbook_id,
                steps_total=steps_total,
                task_spec_id=task_spec.task_spec_id,
                step_index=i,
                request_id=failure.request_id if failure is not None else None,
                terminated_early=True,
                failed_step_index=i,
                duration_ms=step_duration_ms,
                failure_kind=failure.kind.value if failure is not None else None,
                failure_code=failure.code if failure is not None else None,
            ))

            total_duration_ms = _elapsed_ms(runbook_start_ns)

            # runbook_terminated — terminal event on failure path (ADR-015 §2, §4).
            # No events are emitted after this point.
            projection.events.append(RunbookLifecycleEvent(
                event="runbook_terminated",
                runbook_id=runbook.runbook_id,
                steps_total=steps_total,
                terminated_early=True,
                failed_step_index=i,
                total_duration_ms=total_duration_ms,
                failure_kind=failure.kind.value if failure is not None else None,
                failure_code=failure.code if failure is not None else None,
            ))

            # Step failure: terminate immediately (ADR-014 §4).
            # No retry. No continuation. No steps execute after this point.
            return RunbookResult(
                runbook_id=runbook.runbook_id,
                step_outcomes=outcomes,
                steps_completed=i,          # steps 0..(i-1) completed; step i failed
                failed_step_index=i,
                terminated_early=True,
                metadata=projection,
            )

    total_duration_ms = _elapsed_ms(runbook_start_ns)

    # runbook_completed — terminal event on success path (ADR-015 §2, §4).
    # No events are emitted after this point.
    projection.events.append(RunbookLifecycleEvent(
        event="runbook_completed",
        runbook_id=runbook.runbook_id,
        steps_total=steps_total,
        terminated_early=False,
        total_duration_ms=total_duration_ms,
    ))

    # All steps completed without exception.
    return RunbookResult(
        runbook_id=runbook.runbook_id,
        step_outcomes=outcomes,
        steps_completed=len(runbook.steps),
        failed_step_index=None,
        terminated_early=False,
        metadata=projection,
    )
