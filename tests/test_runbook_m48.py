"""
test_runbook_m48.py — Phase 4 M4.8 Runbook Traceability and Metadata Correlation tests.

Verifies the observability contract defined in ADR-015:

Lifecycle event presence:
  - runbook_started is emitted on every run
  - runbook_step_started is emitted before each step
  - runbook_step_completed is emitted after each successful step
  - runbook_step_failed is emitted when a step raises
  - runbook_completed is the terminal event on success
  - runbook_terminated is the terminal event on failure

Lifecycle event ordering:
  - Success path: runbook_started → (step_started → step_completed)* → runbook_completed
  - Failure path: runbook_started → step_started* → step_failed → runbook_terminated
  - No extra events after terminal failure
  - No extra events after runbook_completed

Correlation field correctness:
  - runbook_id matches originating Runbook in all events
  - task_spec_id matches originating TaskSpec in step-level events
  - step_index is correct and zero-based in step-level events
  - steps_total matches len(runbook.steps) in all events
  - request_id present and correct in runbook_step_completed

Timing field presence and sanity:
  - duration_ms is a non-negative int on step_completed and step_failed
  - total_duration_ms is a non-negative int on runbook_completed and runbook_terminated
  - timing fields absent (None) where not applicable

Failure propagation consistency with ADR-013:
  - failure_kind and failure_code populated from RuntimeFailure envelope
  - failure_kind and failure_code are None when no envelope present
  - failure_kind and failure_code match ADR-013 values exactly

No prompt/model-output leakage:
  - no content-bearing fields on any event
  - event field values are structural identifiers only

No regression to M4.7 boundedness guarantees:
  - RunbookResult existing fields unchanged
  - metadata field defaults to None when not from runner
  - M4.7 tests remain unaffected (structural, not re-verified here)

All tests use the null-provider path to avoid live provider dependency.
"""
from __future__ import annotations

import types
from typing import Dict, List, Optional

import pytest

from io_iii.capabilities.builtins import builtin_registry
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.runbook import Runbook
from io_iii.core.runbook_runner import (
    RunbookLifecycleEvent,
    RunbookMetadataProjection,
    RunbookResult,
    _RUNBOOK_LIFECYCLE_EVENTS,
    run as runner_run,
)
from io_iii.core.task_spec import TaskSpec
import io_iii.core.runbook_runner as runbook_runner_module


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _null_cfg() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        config_dir=".",
        providers={"providers": {"ollama": {"enabled": False}}},
        routing={
            "routing_table": {
                "rules": {"boundaries": {}},
                "modes": {
                    "executor": {
                        "primary": "local:test-model",
                        "secondary": "local:fallback-model",
                    }
                },
            }
        },
        logging={"schema": "test"},
    )


def _null_deps() -> RuntimeDependencies:
    return RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )


def _step(n: int = 0) -> TaskSpec:
    return TaskSpec.create(mode="executor", prompt=f"Step {n} prompt.")


def _steps(count: int) -> List[TaskSpec]:
    return [_step(i) for i in range(count)]


def _event_names(projection: RunbookMetadataProjection) -> List[str]:
    return [e.event for e in projection.events]


def _step_events(projection: RunbookMetadataProjection, step_index: int) -> List[RunbookLifecycleEvent]:
    return [e for e in projection.events if e.step_index == step_index]


def _inject_failure(monkeypatch, fail_at_index: int, failure_envelope=None):
    """Monkeypatch orchestrator.run to raise on a specific step index."""
    call_index: Dict[str, int] = {"n": 0}
    real_orch_run = runbook_runner_module._orchestrator.run

    def conditionally_failing_run(*, task_spec, **kwargs):
        idx = call_index["n"]
        call_index["n"] += 1
        if idx == fail_at_index:
            exc = ValueError(f"SIMULATED_STEP_FAILURE: step {idx}")
            if failure_envelope is not None:
                exc.runtime_failure = failure_envelope  # type: ignore[attr-defined]
            raise exc
        return real_orch_run(task_spec=task_spec, **kwargs)

    monkeypatch.setattr(runbook_runner_module._orchestrator, "run", conditionally_failing_run)


# ---------------------------------------------------------------------------
# Taxonomy contract
# ---------------------------------------------------------------------------

class TestTaxonomyContract:
    def test_frozen_taxonomy_has_exactly_six_events(self):
        assert len(_RUNBOOK_LIFECYCLE_EVENTS) == 6

    def test_frozen_taxonomy_contains_required_events(self):
        required = {
            "runbook_started",
            "runbook_step_started",
            "runbook_step_completed",
            "runbook_step_failed",
            "runbook_completed",
            "runbook_terminated",
        }
        assert _RUNBOOK_LIFECYCLE_EVENTS == required

    def test_lifecycle_event_is_frozen(self):
        evt = RunbookLifecycleEvent(
            event="runbook_started",
            runbook_id="rb-test",
            steps_total=1,
        )
        with pytest.raises((AttributeError, TypeError)):
            evt.event = "runbook_completed"  # type: ignore[misc]

    def test_metadata_projection_is_mutable(self):
        proj = RunbookMetadataProjection(runbook_id="rb-test")
        evt = RunbookLifecycleEvent(
            event="runbook_started",
            runbook_id="rb-test",
            steps_total=1,
        )
        proj.events.append(evt)
        assert len(proj.events) == 1


# ---------------------------------------------------------------------------
# Metadata projection structure
# ---------------------------------------------------------------------------

class TestMetadataProjectionStructure:
    def test_result_carries_metadata_on_success(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert result.metadata is not None
        assert isinstance(result.metadata, RunbookMetadataProjection)

    def test_result_carries_metadata_on_failure(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=0)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert result.metadata is not None
        assert isinstance(result.metadata, RunbookMetadataProjection)

    def test_projection_runbook_id_matches_runbook(self):
        rb = Runbook.create(steps=[_step()], runbook_id="rb-proj-check")
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert result.metadata.runbook_id == "rb-proj-check"

    def test_runbook_result_metadata_defaults_to_none_when_constructed_directly(self):
        rr = RunbookResult(runbook_id="rb-direct")
        assert rr.metadata is None

    def test_result_existing_fields_unchanged_by_m48(self):
        rb = Runbook.create(steps=_steps(2), runbook_id="rb-compat")
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert result.runbook_id == "rb-compat"
        assert result.steps_completed == 2
        assert result.failed_step_index is None
        assert result.terminated_early is False
        assert len(result.step_outcomes) == 2


# ---------------------------------------------------------------------------
# Event presence — success path
# ---------------------------------------------------------------------------

class TestEventPresenceSuccess:
    def test_runbook_started_emitted(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        names = _event_names(result.metadata)
        assert "runbook_started" in names

    def test_runbook_step_started_emitted_for_each_step(self):
        n = 3
        rb = Runbook.create(steps=_steps(n))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        started_events = [e for e in result.metadata.events if e.event == "runbook_step_started"]
        assert len(started_events) == n

    def test_runbook_step_completed_emitted_for_each_step(self):
        n = 3
        rb = Runbook.create(steps=_steps(n))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        completed_events = [e for e in result.metadata.events if e.event == "runbook_step_completed"]
        assert len(completed_events) == n

    def test_runbook_completed_emitted_on_success(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        names = _event_names(result.metadata)
        assert "runbook_completed" in names

    def test_runbook_terminated_not_emitted_on_success(self):
        rb = Runbook.create(steps=_steps(2))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        names = _event_names(result.metadata)
        assert "runbook_terminated" not in names

    def test_runbook_step_failed_not_emitted_on_success(self):
        rb = Runbook.create(steps=_steps(2))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        names = _event_names(result.metadata)
        assert "runbook_step_failed" not in names


# ---------------------------------------------------------------------------
# Event presence — failure path
# ---------------------------------------------------------------------------

class TestEventPresenceFailure:
    def test_runbook_started_emitted_on_failure(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=0)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert "runbook_started" in _event_names(result.metadata)

    def test_runbook_step_started_emitted_before_failing_step(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=1)
        rb = Runbook.create(steps=_steps(3))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        started = [e for e in result.metadata.events if e.event == "runbook_step_started"]
        # Steps 0 and 1 started (step 1 failed)
        assert len(started) == 2

    def test_runbook_step_failed_emitted_on_failure(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=0)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert "runbook_step_failed" in _event_names(result.metadata)

    def test_runbook_terminated_emitted_on_failure(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=0)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert "runbook_terminated" in _event_names(result.metadata)

    def test_runbook_completed_not_emitted_on_failure(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=0)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert "runbook_completed" not in _event_names(result.metadata)


# ---------------------------------------------------------------------------
# Event ordering — success path (ADR-015 §4)
# ---------------------------------------------------------------------------

class TestEventOrderingSuccess:
    def test_single_step_success_event_sequence(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        expected = [
            "runbook_started",
            "runbook_step_started",
            "runbook_step_completed",
            "runbook_completed",
        ]
        assert _event_names(result.metadata) == expected

    def test_two_step_success_event_sequence(self):
        rb = Runbook.create(steps=_steps(2))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        expected = [
            "runbook_started",
            "runbook_step_started",
            "runbook_step_completed",
            "runbook_step_started",
            "runbook_step_completed",
            "runbook_completed",
        ]
        assert _event_names(result.metadata) == expected

    def test_three_step_success_event_sequence(self):
        rb = Runbook.create(steps=_steps(3))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        expected = [
            "runbook_started",
            "runbook_step_started",
            "runbook_step_completed",
            "runbook_step_started",
            "runbook_step_completed",
            "runbook_step_started",
            "runbook_step_completed",
            "runbook_completed",
        ]
        assert _event_names(result.metadata) == expected

    def test_runbook_started_is_first_event(self):
        rb = Runbook.create(steps=_steps(2))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert result.metadata.events[0].event == "runbook_started"

    def test_runbook_completed_is_last_event_on_success(self):
        rb = Runbook.create(steps=_steps(2))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert result.metadata.events[-1].event == "runbook_completed"

    def test_no_extra_events_after_runbook_completed(self):
        rb = Runbook.create(steps=_steps(2))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        last_idx = len(result.metadata.events) - 1
        last_event = result.metadata.events[last_idx].event
        assert last_event == "runbook_completed"
        # All events after the last completed are absent (total count is deterministic)
        n = len(rb.steps)
        expected_count = 1 + (n * 2) + 1  # started + (step_started + step_completed)*n + completed
        assert len(result.metadata.events) == expected_count


# ---------------------------------------------------------------------------
# Event ordering — failure path (ADR-015 §4)
# ---------------------------------------------------------------------------

class TestEventOrderingFailure:
    def test_failure_at_step_0_event_sequence(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=0)
        rb = Runbook.create(steps=_steps(3))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        expected = [
            "runbook_started",
            "runbook_step_started",
            "runbook_step_failed",
            "runbook_terminated",
        ]
        assert _event_names(result.metadata) == expected

    def test_failure_at_step_1_event_sequence(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=1)
        rb = Runbook.create(steps=_steps(3))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        expected = [
            "runbook_started",
            "runbook_step_started",
            "runbook_step_completed",
            "runbook_step_started",
            "runbook_step_failed",
            "runbook_terminated",
        ]
        assert _event_names(result.metadata) == expected

    def test_runbook_terminated_is_last_event_on_failure(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=0)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert result.metadata.events[-1].event == "runbook_terminated"

    def test_no_extra_events_after_runbook_terminated(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=1)
        rb = Runbook.create(steps=_steps(4))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        # After runbook_terminated, there must be no more events.
        terminated_idx = next(
            i for i, e in enumerate(result.metadata.events) if e.event == "runbook_terminated"
        )
        assert terminated_idx == len(result.metadata.events) - 1

    def test_step_completed_for_successful_steps_before_failure(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=2)
        rb = Runbook.create(steps=_steps(4))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        completed_events = [e for e in result.metadata.events if e.event == "runbook_step_completed"]
        # Steps 0 and 1 completed; step 2 failed
        assert len(completed_events) == 2
        assert completed_events[0].step_index == 0
        assert completed_events[1].step_index == 1


# ---------------------------------------------------------------------------
# Correlation field correctness (ADR-015 §3)
# ---------------------------------------------------------------------------

class TestCorrelationFields:
    def test_all_events_carry_correct_runbook_id(self):
        rb = Runbook.create(steps=_steps(2), runbook_id="rb-corr-test")
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for evt in result.metadata.events:
            assert evt.runbook_id == "rb-corr-test", f"Wrong runbook_id on event {evt.event}"

    def test_all_events_carry_correct_steps_total(self):
        rb = Runbook.create(steps=_steps(3))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for evt in result.metadata.events:
            assert evt.steps_total == 3, f"Wrong steps_total on event {evt.event}"

    def test_step_events_carry_correct_task_spec_id(self):
        steps = _steps(2)
        rb = Runbook.create(steps=steps)
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        step_events = [e for e in result.metadata.events if e.step_index is not None]
        for evt in step_events:
            expected_spec_id = steps[evt.step_index].task_spec_id
            assert evt.task_spec_id == expected_spec_id

    def test_step_events_carry_correct_step_index(self):
        rb = Runbook.create(steps=_steps(3))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for evt in result.metadata.events:
            if evt.step_index is not None:
                assert 0 <= evt.step_index < 3

    def test_runbook_started_has_no_step_index(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        started = next(e for e in result.metadata.events if e.event == "runbook_started")
        assert started.step_index is None

    def test_runbook_completed_has_no_step_index(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        completed = next(e for e in result.metadata.events if e.event == "runbook_completed")
        assert completed.step_index is None

    def test_step_completed_carries_request_id_from_session_state(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        completed_evt = next(e for e in result.metadata.events if e.event == "runbook_step_completed")
        # request_id must be a non-empty string sourced from SessionState
        assert isinstance(completed_evt.request_id, str)
        assert len(completed_evt.request_id) > 0

    def test_step_started_has_no_request_id(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        started_evt = next(e for e in result.metadata.events if e.event == "runbook_step_started")
        assert started_evt.request_id is None

    def test_runbook_started_has_no_task_spec_id(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        started = next(e for e in result.metadata.events if e.event == "runbook_started")
        assert started.task_spec_id is None

    def test_runbook_completed_carries_terminated_early_false(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        completed = next(e for e in result.metadata.events if e.event == "runbook_completed")
        assert completed.terminated_early is False

    def test_runbook_terminated_carries_terminated_early_true(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=0)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        terminated = next(e for e in result.metadata.events if e.event == "runbook_terminated")
        assert terminated.terminated_early is True

    def test_runbook_terminated_carries_failed_step_index(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=1)
        rb = Runbook.create(steps=_steps(3))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        terminated = next(e for e in result.metadata.events if e.event == "runbook_terminated")
        assert terminated.failed_step_index == 1

    def test_step_failed_carries_failed_step_index(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=2)
        rb = Runbook.create(steps=_steps(4))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        failed_evt = next(e for e in result.metadata.events if e.event == "runbook_step_failed")
        assert failed_evt.failed_step_index == 2
        assert failed_evt.step_index == 2


# ---------------------------------------------------------------------------
# Timing field presence and sanity (ADR-015 §5)
# ---------------------------------------------------------------------------

class TestTimingFields:
    def test_step_completed_carries_non_negative_duration_ms(self):
        rb = Runbook.create(steps=_steps(2))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for evt in result.metadata.events:
            if evt.event == "runbook_step_completed":
                assert isinstance(evt.duration_ms, int)
                assert evt.duration_ms >= 0

    def test_step_failed_carries_non_negative_duration_ms(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=0)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        failed_evt = next(e for e in result.metadata.events if e.event == "runbook_step_failed")
        assert isinstance(failed_evt.duration_ms, int)
        assert failed_evt.duration_ms >= 0

    def test_runbook_completed_carries_non_negative_total_duration_ms(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        completed = next(e for e in result.metadata.events if e.event == "runbook_completed")
        assert isinstance(completed.total_duration_ms, int)
        assert completed.total_duration_ms >= 0

    def test_runbook_terminated_carries_non_negative_total_duration_ms(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=0)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        terminated = next(e for e in result.metadata.events if e.event == "runbook_terminated")
        assert isinstance(terminated.total_duration_ms, int)
        assert terminated.total_duration_ms >= 0

    def test_runbook_started_has_no_timing_fields(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        started = next(e for e in result.metadata.events if e.event == "runbook_started")
        assert started.duration_ms is None
        assert started.total_duration_ms is None

    def test_step_started_has_no_timing_fields(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        step_started = next(e for e in result.metadata.events if e.event == "runbook_step_started")
        assert step_started.duration_ms is None
        assert step_started.total_duration_ms is None

    def test_step_completed_has_no_total_duration(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        step_completed = next(e for e in result.metadata.events if e.event == "runbook_step_completed")
        assert step_completed.total_duration_ms is None

    def test_runbook_completed_has_no_step_duration(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        completed = next(e for e in result.metadata.events if e.event == "runbook_completed")
        assert completed.duration_ms is None


# ---------------------------------------------------------------------------
# Failure propagation consistency with ADR-013
# ---------------------------------------------------------------------------

class TestFailurePropagationADR013:
    def _make_failure_envelope(self):
        from io_iii.core.failure_model import RuntimeFailure, RuntimeFailureKind
        return RuntimeFailure(
            kind=RuntimeFailureKind.PROVIDER_EXECUTION,
            code="PROVIDER_UNAVAILABLE",
            summary="Test provider failure",
            request_id="req-m48-test",
            task_spec_id=None,
            retryable=True,
            causal_code="PROVIDER_UNAVAILABLE",
        )

    def test_failure_kind_and_code_populated_from_envelope(self, monkeypatch):
        envelope = self._make_failure_envelope()
        _inject_failure(monkeypatch, fail_at_index=0, failure_envelope=envelope)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        failed_evt = next(e for e in result.metadata.events if e.event == "runbook_step_failed")
        assert failed_evt.failure_kind == "provider_execution"
        assert failed_evt.failure_code == "PROVIDER_UNAVAILABLE"

    def test_terminated_event_carries_failure_kind_and_code(self, monkeypatch):
        envelope = self._make_failure_envelope()
        _inject_failure(monkeypatch, fail_at_index=0, failure_envelope=envelope)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        terminated = next(e for e in result.metadata.events if e.event == "runbook_terminated")
        assert terminated.failure_kind == "provider_execution"
        assert terminated.failure_code == "PROVIDER_UNAVAILABLE"

    def test_failure_kind_none_when_no_envelope(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=0, failure_envelope=None)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        failed_evt = next(e for e in result.metadata.events if e.event == "runbook_step_failed")
        assert failed_evt.failure_kind is None
        assert failed_evt.failure_code is None

    def test_failure_code_matches_adr013_kind_value_exactly(self, monkeypatch):
        from io_iii.core.failure_model import RuntimeFailure, RuntimeFailureKind
        envelope = RuntimeFailure(
            kind=RuntimeFailureKind.CAPABILITY,
            code="CAPABILITY_TIMEOUT",
            summary="Capability timed out",
            request_id="req-cap-test",
            task_spec_id=None,
            retryable=False,
            causal_code="CAPABILITY_TIMEOUT",
        )
        _inject_failure(monkeypatch, fail_at_index=0, failure_envelope=envelope)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        failed_evt = next(e for e in result.metadata.events if e.event == "runbook_step_failed")
        # failure_kind must be the .value of RuntimeFailureKind.CAPABILITY
        assert failed_evt.failure_kind == RuntimeFailureKind.CAPABILITY.value
        assert failed_evt.failure_code == "CAPABILITY_TIMEOUT"

    def test_step_failed_carries_request_id_from_failure_envelope(self, monkeypatch):
        envelope = self._make_failure_envelope()
        _inject_failure(monkeypatch, fail_at_index=0, failure_envelope=envelope)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        failed_evt = next(e for e in result.metadata.events if e.event == "runbook_step_failed")
        assert failed_evt.request_id == "req-m48-test"

    def test_success_events_carry_no_failure_fields(self):
        rb = Runbook.create(steps=_steps(2))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for evt in result.metadata.events:
            if evt.event in ("runbook_started", "runbook_step_started", "runbook_step_completed"):
                assert evt.failure_kind is None
                assert evt.failure_code is None

    def test_runbook_completed_carries_no_failure_fields(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        completed = next(e for e in result.metadata.events if e.event == "runbook_completed")
        assert completed.failure_kind is None
        assert completed.failure_code is None


# ---------------------------------------------------------------------------
# Content safety — no prompt/model-output leakage
# ---------------------------------------------------------------------------

class TestContentSafety:
    _FORBIDDEN_KEYS = {"prompt", "completion", "draft", "revision", "content", "output"}

    def test_lifecycle_event_has_no_content_bearing_fields(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for evt in result.metadata.events:
            evt_dict = vars(evt) if not hasattr(evt, "__dataclass_fields__") else {
                f: getattr(evt, f) for f in evt.__dataclass_fields__
            }
            for forbidden in self._FORBIDDEN_KEYS:
                assert forbidden not in evt_dict, (
                    f"Content-bearing field '{forbidden}' found on event {evt.event}"
                )

    def test_task_spec_id_does_not_contain_prompt_text(self):
        steps = _steps(2)
        rb = Runbook.create(steps=steps)
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for evt in result.metadata.events:
            if evt.task_spec_id is not None:
                # task_spec_id is a machine-generated identifier, not a prompt
                assert evt.task_spec_id.startswith("ts-"), (
                    f"task_spec_id '{evt.task_spec_id}' does not look like a stable identifier"
                )

    def test_failure_code_is_not_free_form_message(self, monkeypatch):
        from io_iii.core.failure_model import RuntimeFailure, RuntimeFailureKind
        envelope = RuntimeFailure(
            kind=RuntimeFailureKind.INTERNAL,
            code="INTERNAL_ERROR",
            summary="Structured code only",
            request_id="req-safety-test",
            task_spec_id=None,
            retryable=False,
            causal_code=None,
        )
        _inject_failure(monkeypatch, fail_at_index=0, failure_envelope=envelope)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        for evt in result.metadata.events:
            if evt.failure_code is not None:
                # failure_code must be an uppercase, underscore-delimited identifier
                assert evt.failure_code == evt.failure_code.upper(), (
                    f"failure_code '{evt.failure_code}' is not a stable uppercase identifier"
                )
                assert " " not in evt.failure_code, (
                    f"failure_code '{evt.failure_code}' contains spaces — looks like free-form text"
                )

    def test_projection_has_no_content_fields_on_failure(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=0)
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for evt in result.metadata.events:
            evt_fields = {f: getattr(evt, f) for f in evt.__dataclass_fields__}
            for forbidden in self._FORBIDDEN_KEYS:
                assert forbidden not in evt_fields


# ---------------------------------------------------------------------------
# No regression to M4.7 boundedness guarantees
# ---------------------------------------------------------------------------

class TestNoRegressionM47:
    def test_m47_result_fields_unchanged_on_success(self):
        rb = Runbook.create(steps=_steps(3), runbook_id="rb-m47-check")
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        # M4.7 fields must remain unchanged
        assert result.runbook_id == "rb-m47-check"
        assert result.steps_completed == 3
        assert result.failed_step_index is None
        assert result.terminated_early is False
        assert len(result.step_outcomes) == 3
        # M4.8 addition
        assert result.metadata is not None

    def test_m47_result_fields_unchanged_on_failure(self, monkeypatch):
        _inject_failure(monkeypatch, fail_at_index=1)
        rb = Runbook.create(steps=_steps(3))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        # M4.7 fields unchanged
        assert result.terminated_early is True
        assert result.failed_step_index == 1
        assert result.steps_completed == 1
        assert len(result.step_outcomes) == 2
        # M4.8 addition
        assert result.metadata is not None

    def test_step_outcomes_unchanged_by_m48(self):
        steps = _steps(2)
        rb = Runbook.create(steps=steps)
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for i, outcome in enumerate(result.step_outcomes):
            assert outcome.step_index == i
            assert outcome.task_spec_id == steps[i].task_spec_id
            assert outcome.success is True
            assert outcome.failure is None
            assert outcome.state is not None
            assert outcome.result is not None

    def test_m48_does_not_change_step_termination_semantics(self, monkeypatch):
        """M4.8 must not alter the runner's ADR-014 termination contract."""
        _inject_failure(monkeypatch, fail_at_index=1)
        rb = Runbook.create(steps=_steps(4))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        # Only steps 0 and 1 should appear in outcomes
        assert len(result.step_outcomes) == 2
        assert result.step_outcomes[0].success is True
        assert result.step_outcomes[1].success is False
        # Metadata projection must agree with step outcome count
        step_started_count = sum(
            1 for e in result.metadata.events if e.event == "runbook_step_started"
        )
        assert step_started_count == 2

    def test_runner_type_guards_unchanged(self):
        with pytest.raises(TypeError, match="Runbook"):
            runner_run(
                runbook={"steps": []},  # type: ignore[arg-type]
                cfg=_null_cfg(),
                deps=_null_deps(),
            )
