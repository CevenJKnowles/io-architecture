"""
test_execution_trace_invalid_transitions.py — Phase 4 M4.3 trace lifecycle tests.

Verifies the explicit lifecycle state machine defined in execution_trace.py:

  created  → running   (start() or first step() auto-start)
  created  → failed    (fail() before any step)
  running  → completed (complete())
  running  → failed    (fail())
  completed → terminal (no further transitions)
  failed    → terminal (no further transitions)

All invalid transitions must raise TraceLifecycleError explicitly.
Terminal states must block both lifecycle transitions and new step recording.
"""
from __future__ import annotations

import pytest

from io_iii.core.execution_trace import ExecutionTrace, TraceLifecycleError, TraceRecorder


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_initial_status_is_created():
    """Fresh TraceRecorder must report 'created' status."""
    rec = TraceRecorder(trace_id="t-init")
    assert rec.status == "created"
    assert rec.trace.status == "created"


def test_to_dict_includes_status_created():
    """to_dict() must include the lifecycle status field."""
    rec = TraceRecorder(trace_id="t-dict")
    d = rec.trace.to_dict()
    assert "status" in d
    assert d["status"] == "created"


# ---------------------------------------------------------------------------
# Valid transitions: happy paths
# ---------------------------------------------------------------------------

def test_explicit_start_transitions_to_running():
    """start() must transition 'created' → 'running'."""
    rec = TraceRecorder(trace_id="t-start")
    rec.start()
    assert rec.status == "running"


def test_complete_transitions_to_completed():
    """complete() must transition 'running' → 'completed'."""
    rec = TraceRecorder(trace_id="t-complete")
    rec.start()
    rec.complete()
    assert rec.status == "completed"


def test_fail_from_running_transitions_to_failed():
    """fail() must transition 'running' → 'failed'."""
    rec = TraceRecorder(trace_id="t-fail-running")
    rec.start()
    rec.fail()
    assert rec.status == "failed"


def test_fail_from_created_transitions_to_failed():
    """fail() must be valid from 'created' state (error before any step)."""
    rec = TraceRecorder(trace_id="t-fail-created")
    rec.fail()
    assert rec.status == "failed"


def test_step_auto_starts_from_created():
    """First step() call must auto-start the trace ('created' → 'running')."""
    rec = TraceRecorder(trace_id="t-autostart")
    assert rec.status == "created"

    with rec.step("first-step"):
        pass

    assert rec.status == "running"


def test_to_dict_status_after_complete():
    """to_dict() must reflect 'completed' status after complete()."""
    rec = TraceRecorder(trace_id="t-dict-complete")
    rec.start()
    rec.complete()
    d = rec.trace.to_dict()
    assert d["status"] == "completed"


def test_to_dict_status_after_fail():
    """to_dict() must reflect 'failed' status after fail()."""
    rec = TraceRecorder(trace_id="t-dict-fail")
    rec.start()
    rec.fail()
    d = rec.trace.to_dict()
    assert d["status"] == "failed"


# ---------------------------------------------------------------------------
# Invalid transitions: all must raise TraceLifecycleError
# ---------------------------------------------------------------------------

def test_complete_without_start_raises():
    """complete() from 'created' (skipping 'running') must raise TraceLifecycleError."""
    rec = TraceRecorder(trace_id="t-no-start-complete")
    with pytest.raises(TraceLifecycleError, match="TRACE_INVALID_TRANSITION"):
        rec.complete()


def test_double_start_raises():
    """Calling start() twice must raise — 'running' → 'running' is not permitted."""
    rec = TraceRecorder(trace_id="t-double-start")
    rec.start()
    with pytest.raises(TraceLifecycleError, match="TRACE_INVALID_TRANSITION"):
        rec.start()


def test_double_complete_raises():
    """Calling complete() twice must raise — 'completed' is terminal."""
    rec = TraceRecorder(trace_id="t-double-complete")
    rec.start()
    rec.complete()
    with pytest.raises(TraceLifecycleError, match="TRACE_INVALID_TRANSITION"):
        rec.complete()


def test_double_fail_raises():
    """Calling fail() twice must raise — 'failed' is terminal."""
    rec = TraceRecorder(trace_id="t-double-fail")
    rec.start()
    rec.fail()
    with pytest.raises(TraceLifecycleError, match="TRACE_INVALID_TRANSITION"):
        rec.fail()


def test_completed_to_running_raises():
    """start() on a completed trace must raise — backward transition forbidden."""
    rec = TraceRecorder(trace_id="t-completed-start")
    rec.start()
    rec.complete()
    with pytest.raises(TraceLifecycleError, match="TRACE_INVALID_TRANSITION"):
        rec.start()


def test_completed_to_failed_raises():
    """fail() on a completed trace must raise — completed is terminal."""
    rec = TraceRecorder(trace_id="t-completed-fail")
    rec.start()
    rec.complete()
    with pytest.raises(TraceLifecycleError, match="TRACE_INVALID_TRANSITION"):
        rec.fail()


def test_failed_to_running_raises():
    """start() on a failed trace must raise — backward transition forbidden."""
    rec = TraceRecorder(trace_id="t-failed-start")
    rec.fail()
    with pytest.raises(TraceLifecycleError, match="TRACE_INVALID_TRANSITION"):
        rec.start()


def test_failed_to_completed_raises():
    """complete() on a failed trace must raise — failed is terminal."""
    rec = TraceRecorder(trace_id="t-failed-complete")
    rec.start()
    rec.fail()
    with pytest.raises(TraceLifecycleError, match="TRACE_INVALID_TRANSITION"):
        rec.complete()


# ---------------------------------------------------------------------------
# Step recording blocked on terminal states
# ---------------------------------------------------------------------------

def test_step_blocked_after_complete():
    """step() on a completed trace must raise TraceLifecycleError."""
    rec = TraceRecorder(trace_id="t-step-after-complete")
    rec.start()
    rec.complete()
    with pytest.raises(TraceLifecycleError, match="TRACE_STEP_BLOCKED"):
        with rec.step("late-step"):
            pass


def test_step_blocked_after_fail():
    """step() on a failed trace must raise TraceLifecycleError."""
    rec = TraceRecorder(trace_id="t-step-after-fail")
    rec.start()
    rec.fail()
    with pytest.raises(TraceLifecycleError, match="TRACE_STEP_BLOCKED"):
        with rec.step("late-step"):
            pass


def test_step_auto_start_then_blocked_after_complete():
    """
    After auto-start via first step and explicit complete(), further steps must raise.
    Verifies the auto-start path does not bypass terminal guards.
    """
    rec = TraceRecorder(trace_id="t-autostart-then-complete")

    with rec.step("first"):
        pass

    assert rec.status == "running"
    rec.complete()
    assert rec.status == "completed"

    with pytest.raises(TraceLifecycleError, match="TRACE_STEP_BLOCKED"):
        with rec.step("second-after-complete"):
            pass


# ---------------------------------------------------------------------------
# Step recording preserves history even on exception inside step body
# ---------------------------------------------------------------------------

def test_step_records_even_when_body_raises():
    """
    If the step body raises, the step must still be recorded in the trace.
    Lifecycle status remains 'running' after the exception exits the step.
    """
    rec = TraceRecorder(trace_id="t-step-exc")

    with pytest.raises(ValueError, match="step-body-error"):
        with rec.step("failing-step"):
            raise ValueError("step-body-error")

    # Step was recorded despite the exception.
    assert len(rec.trace.steps) == 1
    assert rec.trace.steps[0].stage == "failing-step"

    # Trace remains 'running' — caller must decide to fail() it.
    assert rec.status == "running"


def test_fail_after_step_body_exception():
    """
    Caller can call fail() after a step body raised — 'running' → 'failed'.
    """
    rec = TraceRecorder(trace_id="t-fail-after-step-exc")

    try:
        with rec.step("failing-step"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert rec.status == "running"
    rec.fail()
    assert rec.status == "failed"


# ---------------------------------------------------------------------------
# Error code carried in TraceLifecycleError message
# ---------------------------------------------------------------------------

def test_lifecycle_error_message_includes_states():
    """
    TraceLifecycleError message must name both the source and target states.
    This makes debugging invalid transitions deterministic.
    """
    rec = TraceRecorder(trace_id="t-err-msg")
    rec.start()
    rec.complete()

    try:
        rec.start()
        assert False, "Expected TraceLifecycleError"
    except TraceLifecycleError as exc:
        msg = str(exc)
        assert "completed" in msg
        assert "running" in msg


# ---------------------------------------------------------------------------
# Structural content-safety check on to_dict()
# ---------------------------------------------------------------------------

def test_to_dict_status_field_not_forbidden():
    """
    The 'status' field added in M4.3 must not be a forbidden content key.
    Verified by checking it passes assert_no_forbidden_keys.
    """
    from io_iii.core.content_safety import assert_no_forbidden_keys

    rec = TraceRecorder(trace_id="t-safety")
    rec.start()
    rec.complete()

    d = rec.trace.to_dict()
    # Must not raise — 'status' is not a forbidden key.
    assert_no_forbidden_keys(d)
