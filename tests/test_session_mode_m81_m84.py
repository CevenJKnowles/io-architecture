"""
tests/test_session_mode_m81_m84.py

Phase 8 M8.1 + M8.4 — Work Mode / Steward Mode implementation tests.

Governing ADR: ADR-024 — Work Mode / Steward Mode Contract.

Coverage:
  - SessionMode type: valid values, str coercions, default (§1)
  - StewardThresholds: construction, field defaults (§5)
  - load_steward_thresholds: absent key, partial config, full config,
    invalid types (§5.2, §7.2)
  - evaluate_thresholds: step_count, token_budget, capability_classes,
    multi-threshold resolution, no-threshold case (§5.3–§5.4)
  - StewardGate.check: work mode always open, steward mode with no
    thresholds, each threshold type, content-safety of PauseState (§5–§6)
  - StewardGate.update_mode: transition events, TypeError on bad input (§4)
  - transition_mode: work→steward, steward→work, TypeError guards (§4)
  - ModeTransitionEvent: content-safe fields (ADR-021)
  - PauseState: content-safe summary, valid actions frozenset (§6.2–§6.3)
  - SessionState.session_mode: default WORK, STEWARD accepted,
    validate_session_state passes/fails correctly (§1.3)
"""
from __future__ import annotations

import pytest

from io_iii.core.session_mode import (
    DEFAULT_SESSION_MODE,
    ModeTransitionEvent,
    PauseState,
    SessionMode,
    StewardGate,
    StewardThresholds,
    evaluate_thresholds,
    load_steward_thresholds,
    transition_mode,
)
from io_iii.core.session_state import SessionState, validate_session_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**kwargs) -> SessionState:
    defaults = dict(request_id="req-test", started_at_ms=1_000_000)
    defaults.update(kwargs)
    return SessionState(**defaults)


# ===========================================================================
# 1. SessionMode type (ADR-024 §1)
# ===========================================================================

class TestSessionModeType:
    def test_two_valid_values(self):
        assert SessionMode.WORK is not None
        assert SessionMode.STEWARD is not None

    def test_work_string_value(self):
        assert SessionMode.WORK.value == "work"

    def test_steward_string_value(self):
        assert SessionMode.STEWARD.value == "steward"

    def test_str_enum_equality(self):
        # SessionMode inherits str — can compare with plain strings
        assert SessionMode.WORK == "work"
        assert SessionMode.STEWARD == "steward"

    def test_from_string(self):
        assert SessionMode("work") is SessionMode.WORK
        assert SessionMode("steward") is SessionMode.STEWARD

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            SessionMode("autonomous")

    def test_type_is_closed(self):
        members = list(SessionMode)
        assert len(members) == 2

    def test_default_is_work(self):
        assert DEFAULT_SESSION_MODE is SessionMode.WORK


# ===========================================================================
# 2. StewardThresholds (ADR-024 §5)
# ===========================================================================

class TestStewardThresholds:
    def test_all_optional_defaults(self):
        t = StewardThresholds()
        assert t.step_count is None
        assert t.token_budget is None
        assert t.capability_classes == []

    def test_step_count_set(self):
        t = StewardThresholds(step_count=5)
        assert t.step_count == 5

    def test_token_budget_set(self):
        t = StewardThresholds(token_budget=50_000)
        assert t.token_budget == 50_000

    def test_capability_classes_set(self):
        t = StewardThresholds(capability_classes=["file_write", "network"])
        assert t.capability_classes == ["file_write", "network"]

    def test_frozen(self):
        t = StewardThresholds(step_count=3)
        with pytest.raises(Exception):
            t.step_count = 99  # type: ignore[misc]


# ===========================================================================
# 3. load_steward_thresholds (ADR-024 §5.2, §7.2)
# ===========================================================================

class TestLoadStewardThresholds:
    def test_absent_key_returns_empty(self):
        result = load_steward_thresholds({})
        assert result == StewardThresholds()

    def test_none_value_returns_empty(self):
        result = load_steward_thresholds({"steward_thresholds": None})
        assert result == StewardThresholds()

    def test_full_config(self):
        cfg = {"steward_thresholds": {
            "step_count": 5,
            "token_budget": 50_000,
            "capability_classes": ["file_write"],
        }}
        result = load_steward_thresholds(cfg)
        assert result.step_count == 5
        assert result.token_budget == 50_000
        assert result.capability_classes == ["file_write"]

    def test_partial_step_count_only(self):
        cfg = {"steward_thresholds": {"step_count": 3}}
        result = load_steward_thresholds(cfg)
        assert result.step_count == 3
        assert result.token_budget is None
        assert result.capability_classes == []

    def test_partial_token_budget_only(self):
        cfg = {"steward_thresholds": {"token_budget": 10_000}}
        result = load_steward_thresholds(cfg)
        assert result.token_budget == 10_000
        assert result.step_count is None

    def test_empty_capability_classes(self):
        cfg = {"steward_thresholds": {"capability_classes": []}}
        result = load_steward_thresholds(cfg)
        assert result.capability_classes == []

    def test_invalid_step_count_zero(self):
        with pytest.raises(ValueError, match="STEWARD_THRESHOLD_INVALID"):
            load_steward_thresholds({"steward_thresholds": {"step_count": 0}})

    def test_invalid_step_count_negative(self):
        with pytest.raises(ValueError, match="STEWARD_THRESHOLD_INVALID"):
            load_steward_thresholds({"steward_thresholds": {"step_count": -1}})

    def test_invalid_step_count_string(self):
        with pytest.raises(ValueError, match="STEWARD_THRESHOLD_INVALID"):
            load_steward_thresholds({"steward_thresholds": {"step_count": "five"}})

    def test_invalid_token_budget_zero(self):
        with pytest.raises(ValueError, match="STEWARD_THRESHOLD_INVALID"):
            load_steward_thresholds({"steward_thresholds": {"token_budget": 0}})

    def test_invalid_capability_classes_not_list(self):
        with pytest.raises(ValueError, match="STEWARD_THRESHOLD_INVALID"):
            load_steward_thresholds({"steward_thresholds": {"capability_classes": "file"}})

    def test_invalid_capability_class_empty_string(self):
        with pytest.raises(ValueError, match="STEWARD_THRESHOLD_INVALID"):
            load_steward_thresholds({"steward_thresholds": {"capability_classes": [""]}})

    def test_invalid_steward_thresholds_not_mapping(self):
        with pytest.raises(ValueError, match="STEWARD_THRESHOLD_INVALID"):
            load_steward_thresholds({"steward_thresholds": "bad"})

    def test_extra_runtime_config_keys_ignored(self):
        cfg = {
            "context_limit_chars": 32000,
            "steward_thresholds": {"step_count": 2},
        }
        result = load_steward_thresholds(cfg)
        assert result.step_count == 2


# ===========================================================================
# 4. evaluate_thresholds (ADR-024 §5.3–§5.5)
# ===========================================================================

class TestEvaluateThresholds:
    def test_no_thresholds_never_fires(self):
        t = StewardThresholds()
        for step in range(10):
            result = evaluate_thresholds(
                thresholds=t,
                step_index=step,
                cumulative_tokens=100_000,
                invoked_capability_classes=["file_write"],
            )
            assert result is None

    def test_step_count_fires_at_multiple(self):
        t = StewardThresholds(step_count=5)
        # step 0–3: not a multiple of 5
        for i in range(4):
            assert evaluate_thresholds(thresholds=t, step_index=i) is None
        # step 4 → (4+1)=5, 5 % 5 == 0 → fires
        assert evaluate_thresholds(thresholds=t, step_index=4) == "step_count"

    def test_step_count_fires_every_n(self):
        t = StewardThresholds(step_count=3)
        # fires at step_index 2 (3rd step), 5 (6th step), 8 (9th step)
        fire_points = {2, 5, 8}
        for i in range(10):
            result = evaluate_thresholds(thresholds=t, step_index=i)
            if i in fire_points:
                assert result == "step_count", f"expected fire at step {i}"
            else:
                assert result is None, f"unexpected fire at step {i}"

    def test_step_count_of_one_fires_every_step(self):
        t = StewardThresholds(step_count=1)
        for i in range(5):
            assert evaluate_thresholds(thresholds=t, step_index=i) == "step_count"

    def test_token_budget_fires_when_exceeded(self):
        t = StewardThresholds(token_budget=100)
        assert evaluate_thresholds(thresholds=t, step_index=0, cumulative_tokens=101) == "token_budget"

    def test_token_budget_not_at_equals(self):
        # fires when >N, not at exactly N
        t = StewardThresholds(token_budget=100)
        assert evaluate_thresholds(thresholds=t, step_index=0, cumulative_tokens=100) is None

    def test_token_budget_not_below(self):
        t = StewardThresholds(token_budget=100)
        assert evaluate_thresholds(thresholds=t, step_index=0, cumulative_tokens=50) is None

    def test_capability_classes_fires_on_match(self):
        t = StewardThresholds(capability_classes=["file_write", "network"])
        result = evaluate_thresholds(
            thresholds=t,
            step_index=0,
            invoked_capability_classes=["network"],
        )
        assert result == "capability_classes"

    def test_capability_classes_no_fire_on_mismatch(self):
        t = StewardThresholds(capability_classes=["file_write"])
        result = evaluate_thresholds(
            thresholds=t,
            step_index=0,
            invoked_capability_classes=["read_only"],
        )
        assert result is None

    def test_capability_classes_no_fire_on_empty_invoked(self):
        t = StewardThresholds(capability_classes=["file_write"])
        result = evaluate_thresholds(
            thresholds=t,
            step_index=0,
            invoked_capability_classes=[],
        )
        assert result is None

    def test_capability_classes_empty_declaration_never_fires(self):
        t = StewardThresholds(capability_classes=[])
        result = evaluate_thresholds(
            thresholds=t,
            step_index=0,
            invoked_capability_classes=["anything"],
        )
        assert result is None

    def test_step_count_takes_priority_over_token_budget(self):
        # Both fire: step_count checked first → returns "step_count"
        t = StewardThresholds(step_count=1, token_budget=0)
        result = evaluate_thresholds(
            thresholds=t,
            step_index=0,
            cumulative_tokens=999,
        )
        assert result == "step_count"

    def test_token_budget_fires_when_step_count_does_not(self):
        t = StewardThresholds(step_count=5, token_budget=100)
        # step 0 → not a multiple of 5; tokens=200 > 100
        result = evaluate_thresholds(
            thresholds=t,
            step_index=0,
            cumulative_tokens=200,
        )
        assert result == "token_budget"


# ===========================================================================
# 5. StewardGate (ADR-024 §5–§6)
# ===========================================================================

class TestStewardGateWorkMode:
    def test_work_mode_always_returns_none(self):
        gate = StewardGate(
            session_mode=SessionMode.WORK,
            thresholds=StewardThresholds(step_count=1, token_budget=0),
        )
        for i in range(5):
            result = gate.check(
                step_index=i,
                steps_total=5,
                run_id="run-001",
                cumulative_tokens=999_999,
                invoked_capability_classes=["anything"],
            )
            assert result is None, f"work mode must not pause at step {i}"

    def test_invalid_session_mode_type_raises(self):
        with pytest.raises(TypeError):
            StewardGate(session_mode="work", thresholds=StewardThresholds())  # type: ignore[arg-type]

    def test_invalid_thresholds_type_raises(self):
        with pytest.raises(TypeError):
            StewardGate(session_mode=SessionMode.WORK, thresholds={})  # type: ignore[arg-type]


class TestStewardGateStewardMode:
    def test_no_thresholds_never_fires(self):
        gate = StewardGate(
            session_mode=SessionMode.STEWARD,
            thresholds=StewardThresholds(),
        )
        for i in range(5):
            result = gate.check(
                step_index=i,
                steps_total=5,
                run_id="run-001",
            )
            assert result is None

    def test_step_count_fires_pause_state(self):
        gate = StewardGate(
            session_mode=SessionMode.STEWARD,
            thresholds=StewardThresholds(step_count=2),
        )
        # step 0: (0+1)=1, 1 % 2 ≠ 0 → no pause
        assert gate.check(step_index=0, steps_total=4, run_id="r1") is None
        # step 1: (1+1)=2, 2 % 2 == 0 → pause
        pause = gate.check(step_index=1, steps_total=4, run_id="r1")
        assert pause is not None
        assert pause.threshold_key == "step_count"

    def test_pause_state_content_safe_fields(self):
        gate = StewardGate(
            session_mode=SessionMode.STEWARD,
            thresholds=StewardThresholds(step_count=1),
        )
        pause = gate.check(step_index=0, steps_total=3, run_id="run-safe")
        assert pause is not None
        assert pause.step_index == 0
        assert pause.steps_total == 3
        assert pause.session_mode is SessionMode.STEWARD
        assert pause.run_id == "run-safe"
        assert pause.threshold_key == "step_count"

    def test_pause_state_no_threshold_value(self):
        # PauseState must not expose threshold numbers (ADR-024 §6.2)
        gate = StewardGate(
            session_mode=SessionMode.STEWARD,
            thresholds=StewardThresholds(token_budget=12345),
        )
        pause = gate.check(
            step_index=0,
            steps_total=1,
            run_id="r1",
            cumulative_tokens=99999,
        )
        assert pause is not None
        # threshold_key is the name; the number 12345 must not appear anywhere
        pause_dict = vars(pause)
        assert 12345 not in pause_dict.values()

    def test_token_budget_fires(self):
        gate = StewardGate(
            session_mode=SessionMode.STEWARD,
            thresholds=StewardThresholds(token_budget=1000),
        )
        pause = gate.check(
            step_index=2,
            steps_total=5,
            run_id="r2",
            cumulative_tokens=1001,
        )
        assert pause is not None
        assert pause.threshold_key == "token_budget"

    def test_capability_classes_fires(self):
        gate = StewardGate(
            session_mode=SessionMode.STEWARD,
            thresholds=StewardThresholds(capability_classes=["sensitive"]),
        )
        pause = gate.check(
            step_index=0,
            steps_total=2,
            run_id="r3",
            invoked_capability_classes=["sensitive"],
        )
        assert pause is not None
        assert pause.threshold_key == "capability_classes"

    def test_session_mode_property(self):
        gate = StewardGate(
            session_mode=SessionMode.WORK,
            thresholds=StewardThresholds(),
        )
        assert gate.session_mode is SessionMode.WORK


# ===========================================================================
# 6. StewardGate.update_mode / transition_mode (ADR-024 §4)
# ===========================================================================

class TestModeTransition:
    def test_work_to_steward(self):
        new_mode, event = transition_mode(SessionMode.WORK, SessionMode.STEWARD)
        assert new_mode is SessionMode.STEWARD
        assert event.from_mode == "work"
        assert event.to_mode == "steward"

    def test_steward_to_work(self):
        new_mode, event = transition_mode(SessionMode.STEWARD, SessionMode.WORK)
        assert new_mode is SessionMode.WORK
        assert event.from_mode == "steward"
        assert event.to_mode == "work"

    def test_transition_returns_event_with_user_action(self):
        _, event = transition_mode(
            SessionMode.WORK,
            SessionMode.STEWARD,
            user_action="explicit_command",
            step_index=3,
        )
        assert event.user_action == "explicit_command"
        assert event.step_index == 3

    def test_transition_invalid_current_type(self):
        with pytest.raises(TypeError):
            transition_mode("work", SessionMode.STEWARD)  # type: ignore[arg-type]

    def test_transition_invalid_target_type(self):
        with pytest.raises(TypeError):
            transition_mode(SessionMode.WORK, "steward")  # type: ignore[arg-type]

    def test_gate_update_mode_work_to_steward(self):
        gate = StewardGate(
            session_mode=SessionMode.WORK,
            thresholds=StewardThresholds(step_count=1),
        )
        event = gate.update_mode(SessionMode.STEWARD, step_index=2)
        assert gate.session_mode is SessionMode.STEWARD
        assert event.from_mode == "work"
        assert event.to_mode == "steward"
        assert event.step_index == 2

    def test_gate_update_mode_steward_to_work(self):
        gate = StewardGate(
            session_mode=SessionMode.STEWARD,
            thresholds=StewardThresholds(step_count=1),
        )
        gate.update_mode(SessionMode.WORK)
        # After switching to work mode, gate is open again
        pause = gate.check(step_index=0, steps_total=3, run_id="r1")
        assert pause is None

    def test_gate_update_mode_then_fires_in_steward(self):
        gate = StewardGate(
            session_mode=SessionMode.WORK,
            thresholds=StewardThresholds(step_count=1),
        )
        # Initially work — no pause
        assert gate.check(step_index=0, steps_total=2, run_id="r1") is None
        # Switch to steward
        gate.update_mode(SessionMode.STEWARD)
        # Now threshold fires
        pause = gate.check(step_index=1, steps_total=2, run_id="r1")
        assert pause is not None

    def test_gate_update_invalid_target_type(self):
        gate = StewardGate(
            session_mode=SessionMode.WORK,
            thresholds=StewardThresholds(),
        )
        with pytest.raises(TypeError):
            gate.update_mode("steward")  # type: ignore[arg-type]


# ===========================================================================
# 7. ModeTransitionEvent content-safety (ADR-021)
# ===========================================================================

class TestModeTransitionEvent:
    def test_content_safe_fields_only(self):
        event = ModeTransitionEvent(
            from_mode="work",
            to_mode="steward",
            user_action="user_request",
            step_index=4,
        )
        assert event.from_mode == "work"
        assert event.to_mode == "steward"
        assert event.user_action == "user_request"
        assert event.step_index == 4

    def test_frozen(self):
        event = ModeTransitionEvent(from_mode="work", to_mode="steward", user_action="x")
        with pytest.raises(Exception):
            event.from_mode = "steward"  # type: ignore[misc]

    def test_step_index_optional(self):
        event = ModeTransitionEvent(from_mode="steward", to_mode="work", user_action="y")
        assert event.step_index is None


# ===========================================================================
# 8. PauseState content-safety (ADR-024 §6.2–§6.3)
# ===========================================================================

class TestPauseState:
    def test_valid_actions_frozenset(self):
        assert "approve" in PauseState.VALID_ACTIONS
        assert "redirect" in PauseState.VALID_ACTIONS
        assert "close" in PauseState.VALID_ACTIONS
        assert len(PauseState.VALID_ACTIONS) == 3

    def test_pause_state_frozen(self):
        p = PauseState(
            threshold_key="step_count",
            step_index=0,
            steps_total=5,
            session_mode=SessionMode.STEWARD,
            run_id="r1",
        )
        with pytest.raises(Exception):
            p.threshold_key = "other"  # type: ignore[misc]

    def test_pause_state_fields(self):
        p = PauseState(
            threshold_key="token_budget",
            step_index=2,
            steps_total=10,
            session_mode=SessionMode.STEWARD,
            run_id="run-0042",
        )
        assert p.threshold_key == "token_budget"
        assert p.step_index == 2
        assert p.steps_total == 10
        assert p.session_mode is SessionMode.STEWARD
        assert p.run_id == "run-0042"


# ===========================================================================
# 9. SessionState.session_mode (ADR-024 §1.3)
# ===========================================================================

class TestSessionStateSessionMode:
    def test_default_session_mode_is_work(self):
        state = _make_state()
        assert state.session_mode is SessionMode.WORK

    def test_session_mode_steward_accepted(self):
        state = _make_state(session_mode=SessionMode.STEWARD)
        assert state.session_mode is SessionMode.STEWARD

    def test_validate_passes_with_work(self):
        state = _make_state(session_mode=SessionMode.WORK)
        validate_session_state(state)  # should not raise

    def test_validate_passes_with_steward(self):
        state = _make_state(session_mode=SessionMode.STEWARD)
        validate_session_state(state)  # should not raise

    def test_validate_fails_with_invalid_mode_type(self):
        # Bypass frozen dataclass restriction via object.__setattr__ for testing only
        state = _make_state()
        object.__setattr__(state, "session_mode", "invalid_string")
        with pytest.raises(ValueError, match="session_mode"):
            validate_session_state(state)

    def test_session_state_frozen_mode(self):
        state = _make_state()
        with pytest.raises(Exception):
            state.session_mode = SessionMode.STEWARD  # type: ignore[misc]

    def test_existing_mode_field_unaffected(self):
        # The existing mode (persona mode) must co-exist with session_mode
        state = _make_state(mode="explorer", session_mode=SessionMode.STEWARD)
        assert state.mode == "explorer"
        assert state.session_mode is SessionMode.STEWARD
