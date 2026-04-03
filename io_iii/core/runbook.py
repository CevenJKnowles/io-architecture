from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional
import uuid

from io_iii.core.task_spec import TaskSpec


# ---------------------------------------------------------------------------
# Step ceiling (ADR-014 §2)
# ---------------------------------------------------------------------------

RUNBOOK_MAX_STEPS: int = 20
"""
Hard maximum number of steps permitted in a single Runbook (ADR-014).

This is a constant, not a configurable value. Any Runbook exceeding this
ceiling is rejected at construction time. Increasing this ceiling requires
a governed ADR update.
"""


# ---------------------------------------------------------------------------
# Runbook schema (ADR-014 §1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Runbook:
    """
    Ordered, serialisable, finite list of TaskSpec steps (Phase 4 M4.7 / ADR-014).

    Contract:
    - Immutable once constructed.
    - Carries a stable runbook_id for cross-surface correlation.
    - Contains an ordered list of TaskSpec objects (1 ≤ len ≤ RUNBOOK_MAX_STEPS).
    - Rejects empty step lists.
    - Rejects step counts above RUNBOOK_MAX_STEPS.
    - Rejects non-TaskSpec step entries.

    This is a coordination contract, not a workflow language. It carries no
    branching semantics, no planner logic, and no output-driven ordering.
    """

    runbook_id: str
    steps: List[TaskSpec] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        steps: List[TaskSpec],
        runbook_id: Optional[str] = None,
    ) -> "Runbook":
        """
        Construct and validate a Runbook.

        Raises:
            ValueError: if steps is empty.
            ValueError: if len(steps) exceeds RUNBOOK_MAX_STEPS.
            TypeError: if any step entry is not a TaskSpec instance.
        """
        if not steps:
            raise ValueError(
                "RUNBOOK_EMPTY: A Runbook must contain at least one step."
            )

        if len(steps) > RUNBOOK_MAX_STEPS:
            raise ValueError(
                f"RUNBOOK_MAX_STEPS_EXCEEDED: Runbook declares {len(steps)} steps; "
                f"the ceiling is {RUNBOOK_MAX_STEPS} (ADR-014)."
            )

        validated: List[TaskSpec] = []
        for i, step in enumerate(steps):
            if not isinstance(step, TaskSpec):
                raise TypeError(
                    f"RUNBOOK_INVALID_STEP: Step {i} must be a TaskSpec instance, "
                    f"got {type(step).__name__}."
                )
            validated.append(step)

        return cls(
            runbook_id=runbook_id or cls.new_id(),
            steps=list(validated),
        )

    @staticmethod
    def new_id() -> str:
        return f"rb-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a stable dict representation."""
        return {
            "runbook_id": self.runbook_id,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Runbook":
        """
        Deserialise from a dict representation produced by to_dict().

        Raises:
            ValueError: if data is not a mapping.
            ValueError: validation failures from create().
            TypeError:  step type failures from create().
        """
        if not isinstance(data, Mapping):
            raise ValueError("Runbook input must be a mapping/object")

        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("Runbook 'steps' must be a list")

        steps = [TaskSpec.from_dict(s) for s in raw_steps]

        return cls.create(
            runbook_id=data.get("runbook_id") or None,
            steps=steps,
        )
