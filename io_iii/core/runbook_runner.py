from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.engine import ExecutionResult
from io_iii.core.failure_model import RuntimeFailure
from io_iii.core.runbook import Runbook
from io_iii.core.session_state import SessionState
import io_iii.core.orchestrator as _orchestrator


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
# Runbook execution result (ADR-014 §14)
# ---------------------------------------------------------------------------

@dataclass
class RunbookResult:
    """
    Bounded, content-safe result of a full runbook execution (ADR-014 §14).

    Fields:
        runbook_id         — matches the originating Runbook.runbook_id
        step_outcomes      — ordered list of per-step outcome records
        steps_completed    — count of steps that completed without exception
        failed_step_index  — index of the failing step, or None if all succeeded
        terminated_early   — True when a step failure caused early termination

    Content policy:
    - runbook_id, step_outcomes task_spec_id/step_index, steps_completed,
      failed_step_index, and terminated_early are all structural identifiers.
    - No prompt or model output content may appear directly in this record.
    """

    runbook_id: str
    step_outcomes: List[RunbookStepOutcome] = field(default_factory=list)
    steps_completed: int = 0
    failed_step_index: Optional[int] = None
    terminated_early: bool = False


# ---------------------------------------------------------------------------
# Runner (ADR-014 §3–§13)
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

    Contract:
    - Steps execute strictly in declared order (step 0, step 1, …).
    - Each step is exactly one orchestrator.run() call — never engine.run() directly.
    - ADR-009 bounds (max 1 audit pass, max 1 revision pass) are enforced per step
      by the orchestrator/engine layer.
    - If a step raises, the runbook terminates immediately at that step.
    - No steps execute after a failure.
    - No retry of the failed step.
    - No branching — runtime outputs from any step do not influence step order.
    - No output-driven control flow of any kind.

    This function is a coordination loop only. It does not:
    - inspect step result content
    - route based on model output
    - mutate TaskSpec objects
    - call engine.run() or resolve_route() directly
    - carry state across steps (each step is independent)

    Args:
        runbook  — the Runbook to execute; must be a Runbook instance
        cfg      — runtime config (same contract as orchestrator.run)
        deps     — RuntimeDependencies (same contract as orchestrator.run)
        audit    — whether to enable the challenger audit pass per step

    Returns:
        RunbookResult with per-step outcomes and termination metadata.

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

    outcomes: List[RunbookStepOutcome] = []

    for i, task_spec in enumerate(runbook.steps):
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

            outcomes.append(RunbookStepOutcome(
                step_index=i,
                task_spec_id=task_spec.task_spec_id,
                state=state,
                result=result,
                success=True,
                failure=None,
            ))

        except Exception as exc:
            # Step failure: terminate immediately (ADR-014 §4).
            # No retry. No continuation. No steps execute after this point.
            # Attach RuntimeFailure envelope if the engine decorated the exception.
            failure: Optional[RuntimeFailure] = getattr(exc, "runtime_failure", None)

            outcomes.append(RunbookStepOutcome(
                step_index=i,
                task_spec_id=task_spec.task_spec_id,
                state=None,
                result=None,
                success=False,
                failure=failure,
            ))

            return RunbookResult(
                runbook_id=runbook.runbook_id,
                step_outcomes=outcomes,
                steps_completed=i,          # steps 0..(i-1) completed; step i failed
                failed_step_index=i,
                terminated_early=True,
            )

    # All steps completed without exception.
    return RunbookResult(
        runbook_id=runbook.runbook_id,
        step_outcomes=outcomes,
        steps_completed=len(runbook.steps),
        failed_step_index=None,
        terminated_early=False,
    )
