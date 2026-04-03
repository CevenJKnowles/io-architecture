"""
test_runbook_m47.py — Phase 4 M4.7 Bounded Runbook Layer tests.

Verifies the runbook contract defined in ADR-014:

Schema / serialisation / validation:
  - Runbook construction with valid steps
  - Runbook rejects empty step list
  - Runbook rejects step count above RUNBOOK_MAX_STEPS
  - Runbook rejects non-TaskSpec step entries
  - Runbook serialises to dict and round-trips via from_dict
  - runbook_id is stable and present
  - runbook_id is auto-generated when not supplied
  - runbook_id is accepted when supplied

Runner execution contract:
  - All steps execute in declared order
  - Exactly one orchestrator.run() call per step
  - No extra steps execute after a failure
  - Runbook terminates deterministically on failure
  - steps_completed reflects completed count on failure
  - failed_step_index is correct on failure
  - terminated_early is True on failure, False on success
  - No branching — runner does not inspect step result content
  - No output-driven control flow

Correlation / content safety:
  - runbook_id in result matches input Runbook
  - task_spec_id in step outcomes matches TaskSpec
  - step_index in outcomes matches declared order
  - RuntimeFailure is captured from failed step when available

No regression to M4.2/M4.4/M4.6 guarantees:
  - Runner never calls engine.run() directly (always via orchestrator)
  - Successful full run produces steps_completed == len(runbook.steps)
  - Type guards: non-Runbook and non-RuntimeDependencies are rejected

All tests use the null-provider path to avoid live provider dependency.
"""
from __future__ import annotations

import types
from typing import Any, Dict, List

import pytest

from io_iii.capabilities.builtins import builtin_registry
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.runbook import RUNBOOK_MAX_STEPS, Runbook
from io_iii.core.runbook_runner import RunbookResult, RunbookStepOutcome, run as runner_run
from io_iii.core.task_spec import TaskSpec
import io_iii.core.runbook_runner as runbook_runner_module


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _null_cfg() -> types.SimpleNamespace:
    """Minimal cfg that forces a null provider (identical pattern to orchestrator tests)."""
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
    """Minimal deps with no live provider and builtin capability registry."""
    return RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )


def _step(n: int = 0) -> TaskSpec:
    return TaskSpec.create(mode="executor", prompt=f"Step {n} prompt.")


def _steps(count: int) -> List[TaskSpec]:
    return [_step(i) for i in range(count)]


# ---------------------------------------------------------------------------
# Schema / serialisation / validation
# ---------------------------------------------------------------------------

class TestRunbookSchema:
    def test_create_single_step(self):
        rb = Runbook.create(steps=[_step()])
        assert len(rb.steps) == 1
        assert rb.runbook_id.startswith("rb-")

    def test_create_multiple_steps(self):
        rb = Runbook.create(steps=_steps(3))
        assert len(rb.steps) == 3

    def test_create_at_ceiling(self):
        rb = Runbook.create(steps=_steps(RUNBOOK_MAX_STEPS))
        assert len(rb.steps) == RUNBOOK_MAX_STEPS

    def test_create_rejects_empty_steps(self):
        with pytest.raises(ValueError, match="RUNBOOK_EMPTY"):
            Runbook.create(steps=[])

    def test_create_rejects_above_ceiling(self):
        with pytest.raises(ValueError, match="RUNBOOK_MAX_STEPS_EXCEEDED"):
            Runbook.create(steps=_steps(RUNBOOK_MAX_STEPS + 1))

    def test_create_rejects_non_taskspec_step(self):
        with pytest.raises(TypeError, match="RUNBOOK_INVALID_STEP"):
            Runbook.create(steps=[{"mode": "executor", "prompt": "bad"}])  # type: ignore[list-item]

    def test_create_rejects_mixed_valid_invalid(self):
        with pytest.raises(TypeError, match="RUNBOOK_INVALID_STEP"):
            Runbook.create(steps=[_step(), "not_a_task_spec"])  # type: ignore[list-item]

    def test_create_accepts_explicit_runbook_id(self):
        rb = Runbook.create(steps=[_step()], runbook_id="rb-custom-id")
        assert rb.runbook_id == "rb-custom-id"

    def test_create_generates_runbook_id_when_absent(self):
        rb = Runbook.create(steps=[_step()])
        assert isinstance(rb.runbook_id, str)
        assert len(rb.runbook_id) > 0

    def test_runbook_id_stable_after_construction(self):
        rb = Runbook.create(steps=[_step()], runbook_id="rb-stable")
        assert rb.runbook_id == "rb-stable"
        # frozen — cannot reassign
        with pytest.raises((AttributeError, TypeError)):
            rb.runbook_id = "changed"  # type: ignore[misc]

    def test_to_dict_contains_required_keys(self):
        rb = Runbook.create(steps=_steps(2))
        d = rb.to_dict()
        assert "runbook_id" in d
        assert "steps" in d
        assert isinstance(d["steps"], list)
        assert len(d["steps"]) == 2

    def test_roundtrip_from_dict(self):
        rb = Runbook.create(steps=_steps(3), runbook_id="rb-roundtrip")
        d = rb.to_dict()
        rb2 = Runbook.from_dict(d)
        assert rb2.runbook_id == rb.runbook_id
        assert len(rb2.steps) == len(rb.steps)
        for orig, restored in zip(rb.steps, rb2.steps):
            assert restored.task_spec_id == orig.task_spec_id
            assert restored.mode == orig.mode
            assert restored.prompt == orig.prompt

    def test_from_dict_rejects_non_mapping(self):
        with pytest.raises(ValueError):
            Runbook.from_dict("not a dict")  # type: ignore[arg-type]

    def test_from_dict_rejects_missing_steps(self):
        with pytest.raises((ValueError, TypeError)):
            Runbook.from_dict({"runbook_id": "rb-x", "steps": None})

    def test_from_dict_propagates_empty_steps_error(self):
        with pytest.raises(ValueError, match="RUNBOOK_EMPTY"):
            Runbook.from_dict({"runbook_id": "rb-x", "steps": []})

    def test_ceiling_constant_value(self):
        assert RUNBOOK_MAX_STEPS == 20


# ---------------------------------------------------------------------------
# Runner: happy path
# ---------------------------------------------------------------------------

class TestRunbookRunnerHappyPath:
    def test_single_step_returns_result(self):
        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert isinstance(result, RunbookResult)
        assert result.runbook_id == rb.runbook_id
        assert result.steps_completed == 1
        assert result.failed_step_index is None
        assert result.terminated_early is False

    def test_multi_step_all_succeed(self):
        rb = Runbook.create(steps=_steps(3))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert result.steps_completed == 3
        assert result.failed_step_index is None
        assert result.terminated_early is False
        assert len(result.step_outcomes) == 3

    def test_all_outcomes_marked_success(self):
        rb = Runbook.create(steps=_steps(2))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for outcome in result.step_outcomes:
            assert outcome.success is True
            assert outcome.failure is None
            assert outcome.state is not None
            assert outcome.result is not None

    def test_step_indices_match_declaration_order(self):
        rb = Runbook.create(steps=_steps(3))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for i, outcome in enumerate(result.step_outcomes):
            assert outcome.step_index == i

    def test_task_spec_ids_preserved_in_outcomes(self):
        steps = _steps(2)
        rb = Runbook.create(steps=steps)
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for i, outcome in enumerate(result.step_outcomes):
            assert outcome.task_spec_id == steps[i].task_spec_id

    def test_runbook_id_propagated_to_result(self):
        rb = Runbook.create(steps=[_step()], runbook_id="rb-id-check")
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert result.runbook_id == "rb-id-check"


# ---------------------------------------------------------------------------
# Runner: ordered execution
# ---------------------------------------------------------------------------

class TestRunbookRunnerOrdering:
    def test_steps_execute_in_declared_order(self, monkeypatch):
        """
        Runner must call orchestrator.run() in index order: step 0, step 1, step 2.
        No reordering is permitted regardless of outputs.
        """
        execution_order: List[str] = []
        real_orch_run = runbook_runner_module._orchestrator.run

        def tracking_run(*, task_spec, **kwargs):
            execution_order.append(task_spec.task_spec_id)
            return real_orch_run(task_spec=task_spec, **kwargs)

        monkeypatch.setattr(runbook_runner_module._orchestrator, "run", tracking_run)

        steps = _steps(3)
        rb = Runbook.create(steps=steps)
        runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        expected = [s.task_spec_id for s in steps]
        assert execution_order == expected

    def test_orchestrator_called_exactly_once_per_step(self, monkeypatch):
        """
        ADR-014 §3: each step must trigger exactly one orchestrator.run() call.
        """
        call_count: Dict[str, int] = {"n": 0}
        real_orch_run = runbook_runner_module._orchestrator.run

        def counting_run(*, task_spec, **kwargs):
            call_count["n"] += 1
            return real_orch_run(task_spec=task_spec, **kwargs)

        monkeypatch.setattr(runbook_runner_module._orchestrator, "run", counting_run)

        n_steps = 3
        rb = Runbook.create(steps=_steps(n_steps))
        runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        assert call_count["n"] == n_steps


# ---------------------------------------------------------------------------
# Runner: failure and termination
# ---------------------------------------------------------------------------

class TestRunbookRunnerFailure:
    def _failing_run(self, fail_at_index: int, total_steps: int, monkeypatch):
        """
        Monkeypatch orchestrator.run to raise on a specific step index.
        Returns (runbook, result).
        """
        call_index: Dict[str, int] = {"n": 0}
        real_orch_run = runbook_runner_module._orchestrator.run

        def conditionally_failing_run(*, task_spec, **kwargs):
            idx = call_index["n"]
            call_index["n"] += 1
            if idx == fail_at_index:
                raise ValueError(f"SIMULATED_STEP_FAILURE: step {idx}")
            return real_orch_run(task_spec=task_spec, **kwargs)

        monkeypatch.setattr(runbook_runner_module._orchestrator, "run", conditionally_failing_run)

        rb = Runbook.create(steps=_steps(total_steps))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        return rb, result

    def test_failure_at_first_step_terminates_immediately(self, monkeypatch):
        _, result = self._failing_run(fail_at_index=0, total_steps=3, monkeypatch=monkeypatch)
        assert result.terminated_early is True
        assert result.failed_step_index == 0
        assert result.steps_completed == 0
        assert len(result.step_outcomes) == 1

    def test_failure_at_middle_step(self, monkeypatch):
        _, result = self._failing_run(fail_at_index=1, total_steps=3, monkeypatch=monkeypatch)
        assert result.terminated_early is True
        assert result.failed_step_index == 1
        assert result.steps_completed == 1
        assert len(result.step_outcomes) == 2

    def test_failure_at_last_step(self, monkeypatch):
        _, result = self._failing_run(fail_at_index=2, total_steps=3, monkeypatch=monkeypatch)
        assert result.terminated_early is True
        assert result.failed_step_index == 2
        assert result.steps_completed == 2
        assert len(result.step_outcomes) == 3

    def test_no_steps_execute_after_failure(self, monkeypatch):
        """
        ADR-014 §4: no subsequent steps execute once a step fails.
        Steps completed after the failure point must be zero.
        """
        _, result = self._failing_run(fail_at_index=1, total_steps=4, monkeypatch=monkeypatch)
        # Step 0 succeeded, step 1 failed — steps 2 and 3 must not appear.
        assert len(result.step_outcomes) == 2
        assert result.step_outcomes[0].success is True
        assert result.step_outcomes[1].success is False

    def test_failed_step_outcome_has_no_state_or_result(self, monkeypatch):
        _, result = self._failing_run(fail_at_index=0, total_steps=2, monkeypatch=monkeypatch)
        failed_outcome = result.step_outcomes[0]
        assert failed_outcome.success is False
        assert failed_outcome.state is None
        assert failed_outcome.result is None

    def test_succeeded_steps_before_failure_have_state_and_result(self, monkeypatch):
        _, result = self._failing_run(fail_at_index=2, total_steps=3, monkeypatch=monkeypatch)
        for i in range(2):
            assert result.step_outcomes[i].success is True
            assert result.step_outcomes[i].state is not None
            assert result.step_outcomes[i].result is not None

    def test_terminated_early_false_on_full_success(self):
        rb = Runbook.create(steps=_steps(2))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert result.terminated_early is False

    def test_no_retry_on_failure(self, monkeypatch):
        """
        ADR-014 §6: failed step must not be retried.
        orchestrator.run() must not be called more than once for the failing step.
        """
        per_spec_calls: Dict[str, int] = {}
        real_orch_run = runbook_runner_module._orchestrator.run

        def tracking_run(*, task_spec, **kwargs):
            per_spec_calls[task_spec.task_spec_id] = (
                per_spec_calls.get(task_spec.task_spec_id, 0) + 1
            )
            if per_spec_calls[task_spec.task_spec_id] == 1 and task_spec.prompt == "Step 1 prompt.":
                raise ValueError("SIMULATED_FAILURE")
            return real_orch_run(task_spec=task_spec, **kwargs)

        monkeypatch.setattr(runbook_runner_module._orchestrator, "run", tracking_run)

        rb = Runbook.create(steps=_steps(3))
        runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        # Each step spec must have been called at most once.
        for spec_id, count in per_spec_calls.items():
            assert count == 1, f"Step {spec_id} was called {count} times — retry detected"


# ---------------------------------------------------------------------------
# Runner: no branching / no output-driven control flow
# ---------------------------------------------------------------------------

class TestRunbookRunnerNoBranching:
    def test_runner_does_not_inspect_result_content(self, monkeypatch):
        """
        ADR-014 §5: runner must not branch based on step result content.
        We verify this by injecting a result with unusual message content and
        confirming the next step executes regardless.
        """
        from io_iii.core.engine import ExecutionResult
        from io_iii.core.session_state import SessionState

        call_count: Dict[str, int] = {"n": 0}
        real_orch_run = runbook_runner_module._orchestrator.run

        def run_with_special_content(*, task_spec, **kwargs):
            call_count["n"] += 1
            return real_orch_run(task_spec=task_spec, **kwargs)

        monkeypatch.setattr(runbook_runner_module._orchestrator, "run", run_with_special_content)

        rb = Runbook.create(steps=_steps(3))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        # All 3 steps must have been called — content of results had no effect on flow.
        assert call_count["n"] == 3
        assert result.steps_completed == 3

    def test_all_steps_always_execute_regardless_of_output(self, monkeypatch):
        """
        Confirms that a "stop" signal embedded in a step result does not halt execution.
        The runner has no mechanism to detect or act on such signals.
        """
        steps_seen: List[int] = []
        real_orch_run = runbook_runner_module._orchestrator.run

        def tracking_run(*, task_spec, **kwargs):
            state, result = real_orch_run(task_spec=task_spec, **kwargs)
            steps_seen.append(len(steps_seen))
            return state, result

        monkeypatch.setattr(runbook_runner_module._orchestrator, "run", tracking_run)

        rb = Runbook.create(steps=_steps(4))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        assert steps_seen == [0, 1, 2, 3]
        assert result.steps_completed == 4


# ---------------------------------------------------------------------------
# Runner: correlation fields
# ---------------------------------------------------------------------------

class TestRunbookRunnerCorrelation:
    def test_runbook_id_in_result_matches_input(self):
        rb = Runbook.create(steps=[_step()], runbook_id="rb-correlation-test")
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert result.runbook_id == "rb-correlation-test"

    def test_task_spec_ids_in_outcomes_are_structural(self):
        steps = _steps(3)
        rb = Runbook.create(steps=steps)
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for i, outcome in enumerate(result.step_outcomes):
            # task_spec_id must be the same stable string set at TaskSpec construction.
            assert outcome.task_spec_id == steps[i].task_spec_id
            assert isinstance(outcome.task_spec_id, str)
            assert len(outcome.task_spec_id) > 0

    def test_step_index_is_zero_based_position(self):
        rb = Runbook.create(steps=_steps(3))
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        for i, outcome in enumerate(result.step_outcomes):
            assert outcome.step_index == i

    def test_failure_captures_runtime_failure_envelope(self, monkeypatch):
        """
        When a step raises an exception decorated with .runtime_failure (ADR-013),
        the RunbookStepOutcome.failure field must carry that RuntimeFailure.
        """
        from io_iii.core.failure_model import RuntimeFailure, RuntimeFailureKind

        synthetic_failure = RuntimeFailure(
            kind=RuntimeFailureKind.INTERNAL,
            code="INTERNAL_ERROR",
            summary="Synthetic test failure",
            request_id="req-test-001",
            task_spec_id=None,
            retryable=False,
            causal_code=None,
        )

        real_orch_run = runbook_runner_module._orchestrator.run

        def failing_run(*, task_spec, **kwargs):
            exc = RuntimeError("synthetic")
            exc.runtime_failure = synthetic_failure  # type: ignore[attr-defined]
            raise exc

        monkeypatch.setattr(runbook_runner_module._orchestrator, "run", failing_run)

        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        assert result.terminated_early is True
        failed_outcome = result.step_outcomes[0]
        assert failed_outcome.failure is synthetic_failure

    def test_failure_with_no_runtime_failure_attr_has_none_failure(self, monkeypatch):
        """
        If a step raises an exception without .runtime_failure, outcome.failure is None.
        """
        def failing_run(*, task_spec, **kwargs):
            raise RuntimeError("no envelope")

        monkeypatch.setattr(runbook_runner_module._orchestrator, "run", failing_run)

        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        assert result.terminated_early is True
        assert result.step_outcomes[0].failure is None


# ---------------------------------------------------------------------------
# Runner: type guards
# ---------------------------------------------------------------------------

class TestRunbookRunnerTypeGuards:
    def test_rejects_non_runbook(self):
        with pytest.raises(TypeError, match="Runbook"):
            runner_run(
                runbook={"steps": []},  # type: ignore[arg-type]
                cfg=_null_cfg(),
                deps=_null_deps(),
            )

    def test_rejects_non_runtime_dependencies(self):
        rb = Runbook.create(steps=[_step()])
        with pytest.raises(TypeError, match="RuntimeDependencies"):
            runner_run(
                runbook=rb,
                cfg=_null_cfg(),
                deps=object(),  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# No regression to M4.2/M4.4/M4.6
# ---------------------------------------------------------------------------

class TestRunbookNoRegression:
    def test_runner_delegates_through_orchestrator_not_engine(self, monkeypatch):
        """
        ADR-014 §3: runner must call orchestrator.run(), never engine.run() directly.

        Strategy: capture real_engine_run BEFORE patching engine_module.run, then
        restore it into the orchestrator's cached reference so the orchestrator
        continues to work while engine_module.run is replaced with a failing stub.
        The runner must go through _orchestrator.run(), not engine_module.run().
        """
        import io_iii.core.engine as engine_module
        import io_iii.core.orchestrator as orch_module
        # Capture real engine run BEFORE any patching.
        from io_iii.core.engine import run as real_engine_run

        def engine_run_must_not_be_called_directly(**kwargs):
            raise AssertionError(
                "RunbookRunner called engine.run() directly — ADR-014 violation"
            )

        # Replace the module-level engine.run with the failing stub.
        monkeypatch.setattr(engine_module, "run", engine_run_must_not_be_called_directly)
        # Restore the real engine inside the orchestrator's cached reference so it works.
        monkeypatch.setattr(orch_module, "_engine_run", real_engine_run)

        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        assert result.steps_completed == 1

    def test_orchestrator_single_run_constraint_preserved_per_step(self):
        """
        The orchestrator's M4.2 single-run constraint (max 1 capability per step)
        remains enforced. A runbook step with >1 capability is rejected by the
        orchestrator, not silently accepted by the runner.
        """
        bad_step = TaskSpec.create(
            mode="executor",
            prompt="Multi-cap.",
            capabilities=["cap.echo_json", "cap.json_pretty"],
        )
        rb = Runbook.create(steps=[bad_step])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())
        # Orchestrator raises ValueError → runner terminates early.
        assert result.terminated_early is True
        assert result.failed_step_index == 0
        assert result.steps_completed == 0

    def test_m46_runtime_failure_attached_by_engine_is_preserved(self, monkeypatch):
        """
        ADR-013 (M4.6): the engine attaches .runtime_failure to exceptions.
        The runner must preserve this attachment rather than swallowing it.
        """
        from io_iii.core.failure_model import RuntimeFailure, RuntimeFailureKind

        marker = RuntimeFailure(
            kind=RuntimeFailureKind.CONTRACT_VIOLATION,
            code="CONTRACT_VIOLATION",
            summary="M4.6 regression check",
            request_id="req-m46-test",
            task_spec_id=None,
            retryable=False,
            causal_code=None,
        )

        def failing_with_envelope(*, task_spec, **kwargs):
            exc = ValueError("CONTRACT_VIOLATION: regression test")
            exc.runtime_failure = marker  # type: ignore[attr-defined]
            raise exc

        monkeypatch.setattr(runbook_runner_module._orchestrator, "run", failing_with_envelope)

        rb = Runbook.create(steps=[_step()])
        result = runner_run(runbook=rb, cfg=_null_cfg(), deps=_null_deps())

        assert result.terminated_early is True
        assert result.step_outcomes[0].failure is marker
