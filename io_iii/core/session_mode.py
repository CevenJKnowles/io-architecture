"""
io_iii.core.session_mode — SessionMode type, steward threshold contract,
pause protocol, and mode gate (ADR-024, Phase 8 M8.1 + M8.4).

Implements:
  - SessionMode closed two-value enum (§1)
  - StewardThresholds dataclass (§5)
  - PauseState content-safe pause summary (§6)
  - StewardGate — threshold evaluator and pause protocol (§5–§6)
  - ModeTransitionEvent — content-safe telemetry record (ADR-021)
  - transition_mode — user-initiated-only mode switch (§4)
  - load_steward_thresholds — reads steward_thresholds from runtime config (§7.2)

Content policy (ADR-003 / ADR-024 §6.2):
    Pause state summaries must not contain model names, prompt content, persona
    content, or config values (paths, URLs, threshold numbers). Only structural
    identifiers and mode/step metadata.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# SessionMode type (ADR-024 §1)
# ---------------------------------------------------------------------------

class SessionMode(str, enum.Enum):
    """
    Two-value SessionMode type (ADR-024 §1.1).

    WORK    — active execution; no pause for human review (§2)
    STEWARD — human-supervised; declared thresholds fire pauses at step
              boundaries (§3)

    The type is closed: no other values are valid. Default at session start
    is WORK unless the session config explicitly sets STEWARD (§1.2).
    """
    WORK = "work"
    STEWARD = "steward"


DEFAULT_SESSION_MODE: SessionMode = SessionMode.WORK


# ---------------------------------------------------------------------------
# Steward threshold configuration (ADR-024 §5)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StewardThresholds:
    """
    Declared steward threshold configuration (ADR-024 §5.2).

    All fields are optional. The absence of a field means no threshold of
    that type is active. No default values are hardcoded (ADR-024 §5.6).

    Fields:
        step_count          — pause every N cumulative steps (from session start;
                              not reset after a pause — ADR-024 §5.5)
        token_budget        — pause when cumulative session token count exceeds N
        capability_classes  — pause when any listed capability class is invoked
    """
    step_count: Optional[int] = None
    token_budget: Optional[int] = None
    capability_classes: List[str] = field(default_factory=list)


def load_steward_thresholds(runtime_config: Dict[str, Any]) -> StewardThresholds:
    """
    Load StewardThresholds from a runtime config dict (ADR-024 §5.2, §7.2).

    Reads the optional ``steward_thresholds`` key from the dict produced by
    loading ``runtime.yaml``. If the key is absent, returns StewardThresholds
    with no active thresholds (safe — ADR-024 §5.6, §7.2).

    Args:
        runtime_config: the ``runtime`` sub-dict from IO3Config (may be empty).

    Returns:
        StewardThresholds

    Raises:
        ValueError('STEWARD_THRESHOLD_INVALID: ...') if declared threshold values
        have incorrect types (e.g. step_count is not a positive integer).
    """
    raw = runtime_config.get("steward_thresholds")
    if not raw:
        return StewardThresholds()

    if not isinstance(raw, dict):
        raise ValueError(
            "STEWARD_THRESHOLD_INVALID: steward_thresholds must be a mapping"
        )

    step_count: Optional[int] = None
    if "step_count" in raw:
        sc = raw["step_count"]
        if not isinstance(sc, int) or sc <= 0:
            raise ValueError(
                "STEWARD_THRESHOLD_INVALID: step_count must be a positive integer"
            )
        step_count = sc

    token_budget: Optional[int] = None
    if "token_budget" in raw:
        tb = raw["token_budget"]
        if not isinstance(tb, int) or tb <= 0:
            raise ValueError(
                "STEWARD_THRESHOLD_INVALID: token_budget must be a positive integer"
            )
        token_budget = tb

    capability_classes: List[str] = []
    if "capability_classes" in raw:
        cc = raw["capability_classes"]
        if not isinstance(cc, list):
            raise ValueError(
                "STEWARD_THRESHOLD_INVALID: capability_classes must be a list"
            )
        for item in cc:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    "STEWARD_THRESHOLD_INVALID: capability_classes entries must be "
                    "non-empty strings"
                )
        capability_classes = list(cc)

    return StewardThresholds(
        step_count=step_count,
        token_budget=token_budget,
        capability_classes=capability_classes,
    )


# ---------------------------------------------------------------------------
# Pause state — content-safe summary (ADR-024 §6.2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PauseState:
    """
    Content-safe steward pause state summary (ADR-024 §6.2).

    Surfaced to the user when a steward-mode threshold fires. Must comply with
    ADR-003 content safety invariants in full.

    Must NOT contain:
        - model names
        - prompt content or task descriptions
        - persona content
        - config values (paths, URLs, threshold numbers)

    Fields:
        threshold_key   — key name of the fired threshold (e.g. "step_count",
                          "token_budget", "capability_classes"); never the value
        step_index      — zero-based index of the step where the pause fired
        steps_total     — total declared step count for the current runbook
        session_mode    — current SessionMode at pause time
        run_id          — active run identity (ADR-018); content-safe identifier
    """
    threshold_key: str
    step_index: int
    steps_total: int
    session_mode: SessionMode
    run_id: str

    # Three valid user actions at a pause point (ADR-024 §6.3)
    VALID_ACTIONS: frozenset = frozenset({"approve", "redirect", "close"})


# ---------------------------------------------------------------------------
# Mode transition event — content-safe telemetry (ADR-021 / ADR-024 §4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModeTransitionEvent:
    """
    Content-safe telemetry event for a session mode transition (ADR-021,
    ADR-024 §4).

    Logged when the user initiates a work ↔ steward transition. Fields carry
    only direction and action identifiers — no model names, prompt content,
    config values, or threshold numbers.

    Fields:
        from_mode    — SessionMode value before transition
        to_mode      — SessionMode value after transition
        user_action  — label for the triggering user action (e.g. "user_request")
        step_index   — step boundary at which the transition takes effect (§4.3);
                       None if the transition is applied at session start
    """
    from_mode: str
    to_mode: str
    user_action: str
    step_index: Optional[int] = None


# ---------------------------------------------------------------------------
# Mode transition (ADR-024 §4)
# ---------------------------------------------------------------------------

def transition_mode(
    current: SessionMode,
    target: SessionMode,
    *,
    user_action: str = "user_request",
    step_index: Optional[int] = None,
) -> tuple[SessionMode, ModeTransitionEvent]:
    """
    Execute a user-initiated session mode transition (ADR-024 §4).

    All transitions are user-initiated only. The runtime must never call this
    function autonomously. Transitions take effect at the next step boundary
    (ADR-024 §4.3) — callers are responsible for queuing and applying at the
    correct boundary; this function performs the state change only.

    Args:
        current:     current SessionMode
        target:      desired SessionMode
        user_action: label identifying the triggering user action (telemetry)
        step_index:  step boundary at which the transition takes effect

    Returns:
        Tuple of (new SessionMode, ModeTransitionEvent) for telemetry logging.

    Raises:
        TypeError if current or target are not SessionMode instances.
    """
    if not isinstance(current, SessionMode):
        raise TypeError(
            f"current must be a SessionMode instance, got {type(current).__name__}"
        )
    if not isinstance(target, SessionMode):
        raise TypeError(
            f"target must be a SessionMode instance, got {type(target).__name__}"
        )

    event = ModeTransitionEvent(
        from_mode=current.value,
        to_mode=target.value,
        user_action=user_action,
        step_index=step_index,
    )
    return target, event


# ---------------------------------------------------------------------------
# Steward gate — threshold evaluation and pause protocol (ADR-024 §5–§6)
# ---------------------------------------------------------------------------

def evaluate_thresholds(
    *,
    thresholds: StewardThresholds,
    step_index: int,
    cumulative_tokens: int = 0,
    invoked_capability_classes: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Return the key name of the first threshold that fires, or None.

    Evaluated at each step boundary — after a step completes and before the
    next step begins. All declared thresholds are checked; the first match
    wins (ADR-024 §5.4).

    In work mode this function should not be called (the gate short-circuits
    before reaching it). It is pure: callers control when it is invoked.

    Args:
        thresholds:                  declared StewardThresholds
        step_index:                  zero-based index of the step just completed
        cumulative_tokens:           cumulative session token count so far
        invoked_capability_classes:  capability class(es) invoked in last step

    Returns:
        Threshold key string if a threshold fired, else None.
    """
    if invoked_capability_classes is None:
        invoked_capability_classes = []

    # step_count: fires when (step_index + 1) is a multiple of step_count
    # (step_index is zero-based; step_count is 1-based "every N steps")
    if thresholds.step_count is not None:
        if (step_index + 1) % thresholds.step_count == 0:
            return "step_count"

    # token_budget: fires when cumulative tokens exceed the declared budget
    if thresholds.token_budget is not None:
        if cumulative_tokens > thresholds.token_budget:
            return "token_budget"

    # capability_classes: fires when any invoked class appears in the list
    if thresholds.capability_classes:
        for cls in invoked_capability_classes:
            if cls in thresholds.capability_classes:
                return "capability_classes"

    return None


class StewardGate:
    """
    Steward approval gate evaluated at each step boundary (ADR-024 §5–§6).

    The gate is the single point at which session mode, declared thresholds,
    and step-boundary state converge to decide whether execution should pause
    or continue. In work mode the gate is always open (ADR-024 §2.2).

    Usage:
        gate = StewardGate(session_mode=SessionMode.STEWARD, thresholds=thresholds)
        pause = gate.check(
            step_index=i,
            steps_total=n,
            run_id=run_id,
            cumulative_tokens=tokens,
        )
        if pause is not None:
            # surface pause to user; wait for approve / redirect / close
            ...
    """

    def __init__(
        self,
        *,
        session_mode: SessionMode,
        thresholds: StewardThresholds,
    ) -> None:
        if not isinstance(session_mode, SessionMode):
            raise TypeError(
                f"session_mode must be a SessionMode instance, "
                f"got {type(session_mode).__name__}"
            )
        if not isinstance(thresholds, StewardThresholds):
            raise TypeError(
                f"thresholds must be a StewardThresholds instance, "
                f"got {type(thresholds).__name__}"
            )
        self._session_mode = session_mode
        self._thresholds = thresholds

    @property
    def session_mode(self) -> SessionMode:
        return self._session_mode

    def update_mode(
        self,
        target: SessionMode,
        *,
        user_action: str = "user_request",
        step_index: Optional[int] = None,
    ) -> ModeTransitionEvent:
        """
        Apply a user-initiated mode transition (ADR-024 §4).

        Returns a ModeTransitionEvent for telemetry logging. The caller is
        responsible for logging the event; the gate does not write telemetry
        directly.
        """
        new_mode, event = transition_mode(
            self._session_mode,
            target,
            user_action=user_action,
            step_index=step_index,
        )
        self._session_mode = new_mode
        return event

    def check(
        self,
        *,
        step_index: int,
        steps_total: int,
        run_id: str,
        cumulative_tokens: int = 0,
        invoked_capability_classes: Optional[List[str]] = None,
    ) -> Optional[PauseState]:
        """
        Evaluate the gate at a step boundary (ADR-024 §5.3, §6).

        Returns PauseState if the session should pause, None if execution
        should continue. In work mode always returns None (ADR-024 §2.2).

        Args:
            step_index:                  zero-based index of the step just completed
            steps_total:                 total step count for the current runbook
            run_id:                      active run identity (ADR-018)
            cumulative_tokens:           cumulative session token count
            invoked_capability_classes:  capability classes invoked in the last step

        Returns:
            PauseState if pause required, else None.
        """
        # Thresholds are not evaluated in work mode (ADR-024 §2.2).
        if self._session_mode != SessionMode.STEWARD:
            return None

        fired_key = evaluate_thresholds(
            thresholds=self._thresholds,
            step_index=step_index,
            cumulative_tokens=cumulative_tokens,
            invoked_capability_classes=invoked_capability_classes,
        )

        if fired_key is None:
            return None

        # Build content-safe pause state (ADR-024 §6.2).
        # threshold_key carries only the key name, never the configured value.
        return PauseState(
            threshold_key=fired_key,
            step_index=step_index,
            steps_total=steps_total,
            session_mode=self._session_mode,
            run_id=run_id,
        )
