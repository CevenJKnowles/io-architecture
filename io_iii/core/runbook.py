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


# ---------------------------------------------------------------------------
# Conditional branch types (Phase 8 M8.5)
# ---------------------------------------------------------------------------

WHEN_CONDITION_ALLOWED_KEYS: frozenset = frozenset({"session_mode", "persona_mode"})
"""
Structural field names permitted in WhenCondition (M8.5).

Only structural metadata fields may be used as condition keys — never model
output, capability response content, or free-form text. This preserves the
determinism guarantee: conditions evaluate against session context, not
runtime outputs.

Allowed keys:
    session_mode  — "work" | "steward" (ADR-024)
    persona_mode  — "executor" | "explorer" | "draft" (ADR-007)
"""

WHEN_CONDITION_ALLOWED_OPS: frozenset = frozenset({"eq", "neq"})
"""Comparison operators supported by WhenCondition (M8.5)."""


@dataclass(frozen=True)
class WhenCondition:
    """
    A single config-declared predicate for conditional runbook step execution (M8.5).

    Contract:
    - key must be one of WHEN_CONDITION_ALLOWED_KEYS (structural fields only).
    - op must be one of WHEN_CONDITION_ALLOWED_OPS ("eq" or "neq").
    - value must be a string (compared against the structural field value).
    - Conditions evaluate against WhenContext, never model output.
    - Max 1 branch level is structurally enforced: RunbookStep.task_spec is always
      a TaskSpec, never a ConditionalRunbook, so nesting is impossible.

    Usage example (from runbook YAML):
        when:
          key: session_mode
          op: eq
          value: steward
    """

    key: str
    value: str
    op: str = "eq"

    @classmethod
    def create(
        cls,
        *,
        key: str,
        value: str,
        op: str = "eq",
    ) -> "WhenCondition":
        """
        Construct and validate a WhenCondition.

        Raises:
            ValueError: if key is not in WHEN_CONDITION_ALLOWED_KEYS.
            ValueError: if op is not in WHEN_CONDITION_ALLOWED_OPS.
            TypeError: if value is not a string.
        """
        if key not in WHEN_CONDITION_ALLOWED_KEYS:
            raise ValueError(
                f"WHEN_CONDITION_INVALID_KEY: '{key}' is not an allowed condition key; "
                f"allowed: {sorted(WHEN_CONDITION_ALLOWED_KEYS)}"
            )
        if op not in WHEN_CONDITION_ALLOWED_OPS:
            raise ValueError(
                f"WHEN_CONDITION_INVALID_OP: '{op}' is not an allowed operator; "
                f"allowed: {sorted(WHEN_CONDITION_ALLOWED_OPS)}"
            )
        if not isinstance(value, str):
            raise TypeError(
                f"WHEN_CONDITION_INVALID_VALUE: value must be a string, "
                f"got {type(value).__name__}"
            )
        return cls(key=key, value=value, op=op)

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "value": self.value, "op": self.op}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WhenCondition":
        if not isinstance(data, Mapping):
            raise ValueError("WhenCondition input must be a mapping/object")
        return cls.create(
            key=data.get("key", ""),
            value=data.get("value", ""),
            op=data.get("op", "eq"),
        )


@dataclass(frozen=True)
class RunbookStep:
    """
    A single step in a ConditionalRunbook: a TaskSpec with an optional when condition (M8.5).

    When `when` is None the step always executes (unconditional).
    When `when` is a WhenCondition the step is skipped if the condition evaluates
    to False against the WhenContext provided at execution time.

    Max 1 branch level is structurally guaranteed: task_spec is always a TaskSpec,
    never a nested ConditionalRunbook, so branches cannot contain branches.
    """

    task_spec: TaskSpec
    when: Optional[WhenCondition] = None

    @classmethod
    def create(
        cls,
        *,
        task_spec: TaskSpec,
        when: Optional[WhenCondition] = None,
    ) -> "RunbookStep":
        """
        Construct and validate a RunbookStep.

        Raises:
            TypeError: if task_spec is not a TaskSpec instance.
            TypeError: if when is not a WhenCondition instance or None.
        """
        if not isinstance(task_spec, TaskSpec):
            raise TypeError(
                f"RUNBOOK_STEP_INVALID_TASK_SPEC: task_spec must be a TaskSpec, "
                f"got {type(task_spec).__name__}"
            )
        if when is not None and not isinstance(when, WhenCondition):
            raise TypeError(
                f"RUNBOOK_STEP_INVALID_WHEN: when must be a WhenCondition or None, "
                f"got {type(when).__name__}"
            )
        return cls(task_spec=task_spec, when=when)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"task_spec": self.task_spec.to_dict()}
        if self.when is not None:
            d["when"] = self.when.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunbookStep":
        if not isinstance(data, Mapping):
            raise ValueError("RunbookStep input must be a mapping/object")
        task_spec_data = data.get("task_spec")
        if task_spec_data is None:
            raise ValueError("RunbookStep 'task_spec' is required")
        task_spec = TaskSpec.from_dict(task_spec_data)
        when_data = data.get("when")
        when = WhenCondition.from_dict(when_data) if when_data is not None else None
        return cls.create(task_spec=task_spec, when=when)


@dataclass(frozen=True)
class ConditionalRunbook:
    """
    A runbook whose steps may carry when: conditions (Phase 8 M8.5).

    Contract:
    - Immutable once constructed.
    - Carries a stable runbook_id for cross-surface correlation.
    - Contains 1 ≤ len ≤ RUNBOOK_MAX_STEPS RunbookStep objects.
    - Steps with when=None always execute.
    - Steps with when=WhenCondition execute only when the condition is True
      against the WhenContext provided at execution time.
    - Conditions evaluate structural session fields only (never model output).
    - Max 1 branch level is structurally guaranteed by the RunbookStep type.
    - No output-driven control flow of any kind.
    """

    runbook_id: str
    steps: List[RunbookStep] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        steps: List[RunbookStep],
        runbook_id: Optional[str] = None,
    ) -> "ConditionalRunbook":
        """
        Construct and validate a ConditionalRunbook.

        Raises:
            ValueError: if steps is empty.
            ValueError: if len(steps) exceeds RUNBOOK_MAX_STEPS.
            TypeError: if any step entry is not a RunbookStep instance.
        """
        if not steps:
            raise ValueError(
                "CONDITIONAL_RUNBOOK_EMPTY: A ConditionalRunbook must contain at least one step."
            )
        if len(steps) > RUNBOOK_MAX_STEPS:
            raise ValueError(
                f"CONDITIONAL_RUNBOOK_MAX_STEPS_EXCEEDED: ConditionalRunbook declares "
                f"{len(steps)} steps; the ceiling is {RUNBOOK_MAX_STEPS} (ADR-014)."
            )
        validated: List[RunbookStep] = []
        for i, step in enumerate(steps):
            if not isinstance(step, RunbookStep):
                raise TypeError(
                    f"CONDITIONAL_RUNBOOK_INVALID_STEP: Step {i} must be a RunbookStep "
                    f"instance, got {type(step).__name__}."
                )
            validated.append(step)
        return cls(
            runbook_id=runbook_id or cls.new_id(),
            steps=list(validated),
        )

    @staticmethod
    def new_id() -> str:
        return f"crb-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runbook_id": self.runbook_id,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConditionalRunbook":
        """
        Deserialise from a dict representation produced by to_dict().

        Raises:
            ValueError: if data is not a mapping.
            ValueError: validation failures from create().
            TypeError:  step type failures from create().
        """
        if not isinstance(data, Mapping):
            raise ValueError("ConditionalRunbook input must be a mapping/object")
        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("ConditionalRunbook 'steps' must be a list")
        steps = [RunbookStep.from_dict(s) for s in raw_steps]
        return cls.create(
            runbook_id=data.get("runbook_id") or None,
            steps=steps,
        )
