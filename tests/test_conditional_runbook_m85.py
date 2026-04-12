"""
test_conditional_runbook_m85.py — Phase 8 M8.5 Conditional Runbook Branches.

Contract coverage:
  WhenCondition:
    - create() happy path (eq and neq operators)
    - invalid key → WHEN_CONDITION_INVALID_KEY
    - invalid op  → WHEN_CONDITION_INVALID_OP
    - non-string value → WHEN_CONDITION_INVALID_VALUE (TypeError)
    - to_dict / from_dict round-trip
    - from_dict with default op

  RunbookStep:
    - create() with and without when condition
    - invalid task_spec type → RUNBOOK_STEP_INVALID_TASK_SPEC (TypeError)
    - invalid when type → RUNBOOK_STEP_INVALID_WHEN (TypeError)
    - to_dict: when absent → no 'when' key; when present → serialised
    - from_dict round-trip with and without when

  ConditionalRunbook:
    - create() happy path: one step, multiple steps, mixed conditional
    - empty steps → CONDITIONAL_RUNBOOK_EMPTY
    - too many steps → CONDITIONAL_RUNBOOK_MAX_STEPS_EXCEEDED
    - non-RunbookStep entry → CONDITIONAL_RUNBOOK_INVALID_STEP (TypeError)
    - to_dict / from_dict round-trip
    - runbook_id auto-generated; explicit runbook_id preserved
    - max 1 branch level guaranteed structurally (no nesting possible)

  WhenContext:
    - construction and field access

  evaluate_when:
    - eq: matching value → True
    - eq: non-matching value → False
    - neq: non-matching value → True
    - neq: matching value → False
    - session_mode key
    - persona_mode key

  run_with_context:
    - all steps unconditional → all executed, steps_skipped=0
    - some steps conditional → matching executed, non-matching skipped
    - all steps conditional, all pass → all executed
    - all steps conditional, none pass → none executed, steps_skipped=N, steps_completed=0
    - step failure terminates immediately; skipped count preserved
    - lifecycle events: runbook_started, step_started, step_completed, step_skipped,
      runbook_completed (success path)
    - lifecycle events: terminated path with skipped steps before failure
    - content safety: runbook_step_skipped event carries no prompt/output content
    - type guards: non-ConditionalRunbook, non-WhenContext, non-RuntimeDependencies
    - steps_skipped field present on RunbookResult (default 0 for plain run())
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.engine import ExecutionResult
from io_iii.core.runbook import (
    RUNBOOK_MAX_STEPS,
    WHEN_CONDITION_ALLOWED_KEYS,
    WHEN_CONDITION_ALLOWED_OPS,
    ConditionalRunbook,
    Runbook,
    RunbookStep,
    WhenCondition,
)
from io_iii.core.runbook_runner import (
    RunbookResult,
    WhenContext,
    evaluate_when,
    run_with_context,
)
from io_iii.core.session_state import SessionState
from io_iii.core.task_spec import TaskSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(n: int = 0) -> TaskSpec:
    return TaskSpec.create(mode="executor", prompt=f"M8.5 test step {n}.")


def _step(n: int = 0, when: Optional[WhenCondition] = None) -> RunbookStep:
    return RunbookStep.create(task_spec=_ts(n), when=when)


def _when(key: str = "session_mode", value: str = "work", op: str = "eq") -> WhenCondition:
    return WhenCondition.create(key=key, value=value, op=op)


def _ctx(session_mode: str = "work", persona_mode: str = "executor") -> WhenContext:
    return WhenContext(session_mode=session_mode, persona_mode=persona_mode)


def _fake_state() -> SessionState:
    return SessionState(
        request_id="req-test",
        started_at_ms=0,
    )


def _fake_result() -> ExecutionResult:
    return ExecutionResult(
        message="ok",
        meta={},
        provider="null",
        model=None,
        route_id="executor",
        audit_meta=None,
        prompt_hash=None,
    )


def _mock_orch_success():
    """Patch orchestrator.run to return a successful (state, result) pair."""
    return patch(
        "io_iii.core.runbook_runner._orchestrator.run",
        return_value=(_fake_state(), _fake_result()),
    )


def _mock_orch_failure(exc: Exception):
    """Patch orchestrator.run to raise exc."""
    return patch(
        "io_iii.core.runbook_runner._orchestrator.run",
        side_effect=exc,
    )


def _deps() -> RuntimeDependencies:
    return RuntimeDependencies(
        ollama_provider_factory=MagicMock(),
        challenger_fn=None,
        capability_registry=MagicMock(),
    )


# ---------------------------------------------------------------------------
# WhenCondition tests
# ---------------------------------------------------------------------------

class TestWhenCondition:

    def test_create_eq_session_mode(self):
        c = WhenCondition.create(key="session_mode", value="steward")
        assert c.key == "session_mode"
        assert c.value == "steward"
        assert c.op == "eq"

    def test_create_neq_persona_mode(self):
        c = WhenCondition.create(key="persona_mode", value="draft", op="neq")
        assert c.op == "neq"
        assert c.key == "persona_mode"

    def test_invalid_key_raises(self):
        with pytest.raises(ValueError, match="WHEN_CONDITION_INVALID_KEY"):
            WhenCondition.create(key="model_name", value="llama3")

    def test_invalid_op_raises(self):
        with pytest.raises(ValueError, match="WHEN_CONDITION_INVALID_OP"):
            WhenCondition.create(key="session_mode", value="work", op="gte")

    def test_non_string_value_raises(self):
        with pytest.raises(TypeError, match="WHEN_CONDITION_INVALID_VALUE"):
            WhenCondition.create(key="session_mode", value=42)  # type: ignore

    def test_to_dict(self):
        c = WhenCondition.create(key="session_mode", value="steward", op="eq")
        d = c.to_dict()
        assert d == {"key": "session_mode", "value": "steward", "op": "eq"}

    def test_from_dict_round_trip(self):
        c = WhenCondition.create(key="persona_mode", value="explorer", op="neq")
        restored = WhenCondition.from_dict(c.to_dict())
        assert restored == c

    def test_from_dict_default_op(self):
        c = WhenCondition.from_dict({"key": "session_mode", "value": "work"})
        assert c.op == "eq"

    def test_from_dict_non_mapping_raises(self):
        with pytest.raises(ValueError, match="mapping"):
            WhenCondition.from_dict("not-a-dict")  # type: ignore

    def test_allowed_keys_coverage(self):
        for key in WHEN_CONDITION_ALLOWED_KEYS:
            c = WhenCondition.create(key=key, value="x")
            assert c.key == key

    def test_allowed_ops_coverage(self):
        for op in WHEN_CONDITION_ALLOWED_OPS:
            c = WhenCondition.create(key="session_mode", value="work", op=op)
            assert c.op == op


# ---------------------------------------------------------------------------
# RunbookStep tests
# ---------------------------------------------------------------------------

class TestRunbookStep:

    def test_create_unconditional(self):
        ts = _ts(0)
        step = RunbookStep.create(task_spec=ts)
        assert step.task_spec is ts
        assert step.when is None

    def test_create_with_when(self):
        w = _when()
        step = RunbookStep.create(task_spec=_ts(0), when=w)
        assert step.when is w

    def test_invalid_task_spec_raises(self):
        with pytest.raises(TypeError, match="RUNBOOK_STEP_INVALID_TASK_SPEC"):
            RunbookStep.create(task_spec="not-a-taskspec")  # type: ignore

    def test_invalid_when_raises(self):
        with pytest.raises(TypeError, match="RUNBOOK_STEP_INVALID_WHEN"):
            RunbookStep.create(task_spec=_ts(0), when="not-a-condition")  # type: ignore

    def test_to_dict_no_when(self):
        step = RunbookStep.create(task_spec=_ts(0))
        d = step.to_dict()
        assert "task_spec" in d
        assert "when" not in d

    def test_to_dict_with_when(self):
        step = RunbookStep.create(task_spec=_ts(0), when=_when("session_mode", "steward"))
        d = step.to_dict()
        assert "when" in d
        assert d["when"]["key"] == "session_mode"
        assert d["when"]["value"] == "steward"

    def test_from_dict_round_trip_no_when(self):
        step = RunbookStep.create(task_spec=_ts(1))
        restored = RunbookStep.from_dict(step.to_dict())
        assert restored.when is None
        assert restored.task_spec.prompt == step.task_spec.prompt

    def test_from_dict_round_trip_with_when(self):
        step = RunbookStep.create(task_spec=_ts(2), when=_when("persona_mode", "explorer"))
        restored = RunbookStep.from_dict(step.to_dict())
        assert restored.when is not None
        assert restored.when.key == "persona_mode"
        assert restored.when.value == "explorer"

    def test_from_dict_missing_task_spec_raises(self):
        with pytest.raises(ValueError):
            RunbookStep.from_dict({"when": {"key": "session_mode", "value": "work", "op": "eq"}})

    def test_from_dict_non_mapping_raises(self):
        with pytest.raises(ValueError, match="mapping"):
            RunbookStep.from_dict("bad")  # type: ignore


# ---------------------------------------------------------------------------
# ConditionalRunbook tests
# ---------------------------------------------------------------------------

class TestConditionalRunbook:

    def test_create_single_step(self):
        rb = ConditionalRunbook.create(steps=[_step(0)])
        assert len(rb.steps) == 1

    def test_create_multiple_steps_mixed(self):
        steps = [
            _step(0),
            _step(1, when=_when("session_mode", "steward")),
            _step(2),
        ]
        rb = ConditionalRunbook.create(steps=steps)
        assert len(rb.steps) == 3
        assert rb.steps[1].when is not None

    def test_empty_steps_raises(self):
        with pytest.raises(ValueError, match="CONDITIONAL_RUNBOOK_EMPTY"):
            ConditionalRunbook.create(steps=[])

    def test_too_many_steps_raises(self):
        steps = [_step(i) for i in range(RUNBOOK_MAX_STEPS + 1)]
        with pytest.raises(ValueError, match="CONDITIONAL_RUNBOOK_MAX_STEPS_EXCEEDED"):
            ConditionalRunbook.create(steps=steps)

    def test_non_runbook_step_raises(self):
        with pytest.raises(TypeError, match="CONDITIONAL_RUNBOOK_INVALID_STEP"):
            ConditionalRunbook.create(steps=[_ts(0)])  # type: ignore

    def test_runbook_id_auto_generated(self):
        rb = ConditionalRunbook.create(steps=[_step(0)])
        assert rb.runbook_id.startswith("crb-")

    def test_runbook_id_explicit(self):
        rb = ConditionalRunbook.create(steps=[_step(0)], runbook_id="crb-custom")
        assert rb.runbook_id == "crb-custom"

    def test_to_dict_from_dict_round_trip(self):
        steps = [
            _step(0),
            _step(1, when=_when("persona_mode", "draft", "neq")),
        ]
        rb = ConditionalRunbook.create(steps=steps, runbook_id="crb-roundtrip")
        restored = ConditionalRunbook.from_dict(rb.to_dict())
        assert restored.runbook_id == "crb-roundtrip"
        assert len(restored.steps) == 2
        assert restored.steps[1].when is not None
        assert restored.steps[1].when.value == "draft"

    def test_from_dict_non_mapping_raises(self):
        with pytest.raises(ValueError, match="mapping"):
            ConditionalRunbook.from_dict("bad")  # type: ignore

    def test_from_dict_missing_steps_raises(self):
        with pytest.raises(ValueError, match="'steps' must be a list"):
            ConditionalRunbook.from_dict({"runbook_id": "crb-x"})

    def test_max_one_branch_level_structurally_guaranteed(self):
        # RunbookStep.task_spec is always a TaskSpec — cannot hold a ConditionalRunbook.
        # Attempting to put a ConditionalRunbook as task_spec fails at RunbookStep.create().
        nested = ConditionalRunbook.create(steps=[_step(0)])
        with pytest.raises(TypeError, match="RUNBOOK_STEP_INVALID_TASK_SPEC"):
            RunbookStep.create(task_spec=nested)  # type: ignore

    def test_immutable(self):
        rb = ConditionalRunbook.create(steps=[_step(0)])
        with pytest.raises(Exception):
            rb.runbook_id = "changed"  # type: ignore


# ---------------------------------------------------------------------------
# WhenContext tests
# ---------------------------------------------------------------------------

class TestWhenContext:

    def test_construction(self):
        ctx = WhenContext(session_mode="work", persona_mode="executor")
        assert ctx.session_mode == "work"
        assert ctx.persona_mode == "executor"

    def test_frozen(self):
        ctx = WhenContext(session_mode="work", persona_mode="executor")
        with pytest.raises(Exception):
            ctx.session_mode = "steward"  # type: ignore


# ---------------------------------------------------------------------------
# evaluate_when tests
# ---------------------------------------------------------------------------

class TestEvaluateWhen:

    def test_eq_session_mode_match(self):
        c = _when("session_mode", "work")
        ctx = _ctx(session_mode="work")
        assert evaluate_when(c, ctx) is True

    def test_eq_session_mode_no_match(self):
        c = _when("session_mode", "steward")
        ctx = _ctx(session_mode="work")
        assert evaluate_when(c, ctx) is False

    def test_neq_session_mode_no_match(self):
        c = _when("session_mode", "work", "neq")
        ctx = _ctx(session_mode="work")
        assert evaluate_when(c, ctx) is False

    def test_neq_session_mode_match(self):
        c = _when("session_mode", "steward", "neq")
        ctx = _ctx(session_mode="work")
        assert evaluate_when(c, ctx) is True

    def test_eq_persona_mode_match(self):
        c = _when("persona_mode", "explorer")
        ctx = _ctx(persona_mode="explorer")
        assert evaluate_when(c, ctx) is True

    def test_eq_persona_mode_no_match(self):
        c = _when("persona_mode", "draft")
        ctx = _ctx(persona_mode="executor")
        assert evaluate_when(c, ctx) is False


# ---------------------------------------------------------------------------
# run_with_context tests
# ---------------------------------------------------------------------------

class TestRunWithContext:

    # --- Happy path: all unconditional ---

    def test_all_unconditional_all_executed(self):
        rb = ConditionalRunbook.create(steps=[_step(0), _step(1)])
        ctx = _ctx()
        with _mock_orch_success():
            result = run_with_context(runbook=rb, context=ctx, cfg=MagicMock(), deps=_deps())
        assert result.steps_completed == 2
        assert result.steps_skipped == 0
        assert result.terminated_early is False
        assert result.failed_step_index is None

    # --- Happy path: conditional — some skipped ---

    def test_conditional_step_skipped_when_no_match(self):
        steps = [
            _step(0),                                           # unconditional — runs
            _step(1, when=_when("session_mode", "steward")),   # steward only — skipped
            _step(2),                                           # unconditional — runs
        ]
        rb = ConditionalRunbook.create(steps=steps)
        ctx = _ctx(session_mode="work")
        with _mock_orch_success():
            result = run_with_context(runbook=rb, context=ctx, cfg=MagicMock(), deps=_deps())
        assert result.steps_completed == 2
        assert result.steps_skipped == 1
        assert not result.terminated_early

    def test_conditional_step_executed_when_match(self):
        steps = [
            _step(0, when=_when("session_mode", "steward")),   # matches context
            _step(1, when=_when("persona_mode", "executor")),   # matches context
        ]
        rb = ConditionalRunbook.create(steps=steps)
        ctx = _ctx(session_mode="steward", persona_mode="executor")
        with _mock_orch_success():
            result = run_with_context(runbook=rb, context=ctx, cfg=MagicMock(), deps=_deps())
        assert result.steps_completed == 2
        assert result.steps_skipped == 0

    def test_all_conditional_none_pass(self):
        steps = [
            _step(0, when=_when("session_mode", "steward")),
            _step(1, when=_when("persona_mode", "draft")),
        ]
        rb = ConditionalRunbook.create(steps=steps)
        ctx = _ctx(session_mode="work", persona_mode="executor")
        with _mock_orch_success():
            result = run_with_context(runbook=rb, context=ctx, cfg=MagicMock(), deps=_deps())
        assert result.steps_completed == 0
        assert result.steps_skipped == 2
        assert not result.terminated_early

    def test_neq_condition_skips_matching(self):
        # "not draft" — executor context → should run
        step_runs = _step(0, when=_when("persona_mode", "draft", "neq"))
        # "not executor" — executor context → should skip
        step_skips = _step(1, when=_when("persona_mode", "executor", "neq"))
        rb = ConditionalRunbook.create(steps=[step_runs, step_skips])
        ctx = _ctx(persona_mode="executor")
        with _mock_orch_success():
            result = run_with_context(runbook=rb, context=ctx, cfg=MagicMock(), deps=_deps())
        assert result.steps_completed == 1
        assert result.steps_skipped == 1

    # --- Failure path ---

    def test_step_failure_terminates_immediately(self):
        steps = [_step(0), _step(1), _step(2)]
        rb = ConditionalRunbook.create(steps=steps)
        ctx = _ctx()
        call_count = 0

        def _side_effect(**_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("step 1 failed")
            return (_fake_state(), _fake_result())

        with patch("io_iii.core.runbook_runner._orchestrator.run", side_effect=_side_effect):
            result = run_with_context(runbook=rb, context=ctx, cfg=MagicMock(), deps=_deps())

        assert result.terminated_early is True
        assert result.failed_step_index == 1
        assert call_count == 2   # step 2 never ran

    def test_skipped_count_preserved_on_failure(self):
        steps = [
            _step(0, when=_when("session_mode", "steward")),   # skipped
            _step(1),                                           # runs and fails
        ]
        rb = ConditionalRunbook.create(steps=steps)
        ctx = _ctx(session_mode="work")

        with _mock_orch_failure(RuntimeError("boom")):
            result = run_with_context(runbook=rb, context=ctx, cfg=MagicMock(), deps=_deps())

        assert result.steps_skipped == 1
        assert result.terminated_early is True

    # --- Lifecycle events ---

    def test_success_lifecycle_event_sequence(self):
        steps = [
            _step(0),
            _step(1, when=_when("session_mode", "steward")),   # skipped (context=work)
            _step(2),
        ]
        rb = ConditionalRunbook.create(steps=steps)
        ctx = _ctx(session_mode="work")
        with _mock_orch_success():
            result = run_with_context(runbook=rb, context=ctx, cfg=MagicMock(), deps=_deps())

        events = [e.event for e in result.metadata.events]
        assert events[0] == "runbook_started"
        assert "runbook_step_skipped" in events
        assert events[-1] == "runbook_completed"
        # No terminated event on success path
        assert "runbook_terminated" not in events

    def test_step_skipped_event_content_safe(self):
        step = _step(0, when=_when("session_mode", "steward"))
        rb = ConditionalRunbook.create(steps=[step])
        ctx = _ctx(session_mode="work")
        with _mock_orch_success():
            result = run_with_context(runbook=rb, context=ctx, cfg=MagicMock(), deps=_deps())

        skipped_events = [
            e for e in result.metadata.events if e.event == "runbook_step_skipped"
        ]
        assert len(skipped_events) == 1
        e = skipped_events[0]
        # Content safety: no prompt text, model output, or config values
        assert e.task_spec_id is not None          # structural identifier only
        assert e.step_index == 0
        assert e.failure_kind is None
        assert e.failure_code is None
        assert e.request_id is None                # no request was made

    def test_failure_lifecycle_includes_terminated(self):
        rb = ConditionalRunbook.create(steps=[_step(0)])
        ctx = _ctx()
        with _mock_orch_failure(RuntimeError("fail")):
            result = run_with_context(runbook=rb, context=ctx, cfg=MagicMock(), deps=_deps())

        events = [e.event for e in result.metadata.events]
        assert "runbook_step_failed" in events
        assert events[-1] == "runbook_terminated"

    # --- Type guards ---

    def test_non_conditional_runbook_raises(self):
        plain = Runbook.create(steps=[_ts(0)])
        with pytest.raises(TypeError, match="ConditionalRunbook"):
            run_with_context(
                runbook=plain,  # type: ignore
                context=_ctx(),
                cfg=MagicMock(),
                deps=_deps(),
            )

    def test_non_when_context_raises(self):
        rb = ConditionalRunbook.create(steps=[_step(0)])
        with pytest.raises(TypeError, match="WhenContext"):
            run_with_context(
                runbook=rb,
                context={"session_mode": "work"},  # type: ignore
                cfg=MagicMock(),
                deps=_deps(),
            )

    def test_non_deps_raises(self):
        rb = ConditionalRunbook.create(steps=[_step(0)])
        with pytest.raises(TypeError, match="RuntimeDependencies"):
            run_with_context(
                runbook=rb,
                context=_ctx(),
                cfg=MagicMock(),
                deps=MagicMock(),  # type: ignore
            )

    # --- steps_skipped default on plain RunbookResult ---

    def test_runbook_result_steps_skipped_default(self):
        result = RunbookResult(runbook_id="rb-test")
        assert result.steps_skipped == 0

    # --- runbook_step_skipped is in the taxonomy ---

    def test_step_skipped_in_lifecycle_taxonomy(self):
        from io_iii.core.runbook_runner import _RUNBOOK_LIFECYCLE_EVENTS
        assert "runbook_step_skipped" in _RUNBOOK_LIFECYCLE_EVENTS
