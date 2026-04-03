"""
test_runbook_m411.py — Phase 4 M4.11 Replay/Resume Layer tests (ADR-020).

Contract coverage:
  - replay happy path (full re-execution from step 0)
  - resume happy path (continuation from first incomplete step)
  - checkpoint not found → CHECKPOINT_NOT_FOUND (ADR-020 §6.2)
  - checkpoint integrity failure → CHECKPOINT_INTEGRITY_ERROR (ADR-020 §6.2)
  - invalid resume state (completed run) → RESUME_INVALID_STATE (ADR-020 §3.3, §6.2)
  - completed run cannot be resumed
  - failed run resumes from failed_step_index (ADR-020 §3.2)
  - replay/resume each generate a distinct new run_id (ADR-018, ADR-020 §4.1)
  - source_run_id binds to the input run_id (ADR-020 §4.2)
  - audit flag threads through to runner unchanged (ADR-020 §5.3)
  - CLI subcommands (replay, resume) are registered and dispatch correctly

All execution tests mock io_iii.core.runbook_runner.run to isolate the replay/resume
layer from live provider dependencies. Checkpoint fixtures are written to tmp_path.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from io_iii.cli import main
from io_iii.core.failure_model import RuntimeFailure, RuntimeFailureKind
from io_iii.core.replay_resume import (
    CHECKPOINT_SCHEMA_VERSION,
    ReplayResumeResult,
    replay,
    resume,
)
from io_iii.core.runbook import Runbook
from io_iii.core.runbook_runner import (
    RunbookLifecycleEvent,
    RunbookMetadataProjection,
    RunbookResult,
    RunbookStepOutcome,
)
from io_iii.core.task_spec import TaskSpec


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _step(n: int = 0) -> TaskSpec:
    return TaskSpec.create(mode="executor", prompt=f"M4.11 test step {n}.")


def _three_step_runbook(runbook_id: str = "rb-m411-test") -> Runbook:
    return Runbook.create(
        steps=[_step(0), _step(1), _step(2)],
        runbook_id=runbook_id,
    )


def _write_checkpoint(
    storage_root: Path,
    run_id: str,
    runbook: Runbook,
    *,
    status: str = "completed",
    steps_completed: int = 3,
    last_completed_step_index: Optional[int] = 2,
    total_steps: int = 3,
    source_run_id: Optional[str] = None,
    failure_kind: Optional[str] = None,
    failure_code: Optional[str] = None,
    failed_step_index: Optional[int] = None,
) -> None:
    """Write a valid checkpoint fixture to storage_root/<run_id>.json."""
    data: Dict[str, Any] = {
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "run_id": run_id,
        "runbook_id": runbook.runbook_id,
        "source_run_id": source_run_id,
        "runbook_snapshot": runbook.to_dict(),
        "created_at": "2026-04-03T00:00:00+00:00",
        "updated_at": "2026-04-03T00:00:00+00:00",
        "steps_completed": steps_completed,
        "last_completed_step_index": last_completed_step_index,
        "total_steps": total_steps,
        "status": status,
    }
    if status == "failed":
        data["failure_kind"] = failure_kind or RuntimeFailureKind.PROVIDER_EXECUTION.value
        data["failure_code"] = failure_code or "PROVIDER_UNAVAILABLE"
        data["failed_step_index"] = failed_step_index if failed_step_index is not None else 1
    storage_root.mkdir(parents=True, exist_ok=True)
    (storage_root / f"{run_id}.json").write_text(json.dumps(data), encoding="utf-8")


def _make_success_result(runbook: Runbook, steps_run: int = 3) -> RunbookResult:
    """Minimal successful RunbookResult for the given runbook slice."""
    outcomes = []
    events: List[RunbookLifecycleEvent] = [
        RunbookLifecycleEvent(
            event="runbook_started",
            runbook_id=runbook.runbook_id,
            steps_total=steps_run,
        )
    ]
    for i, step in enumerate(runbook.steps[:steps_run]):
        outcomes.append(
            RunbookStepOutcome(
                step_index=i,
                task_spec_id=step.task_spec_id,
                state=None,
                result=None,
                success=True,
                failure=None,
            )
        )
        events.append(
            RunbookLifecycleEvent(
                event="runbook_step_completed",
                runbook_id=runbook.runbook_id,
                steps_total=steps_run,
                step_index=i,
            )
        )
    events.append(
        RunbookLifecycleEvent(
            event="runbook_completed",
            runbook_id=runbook.runbook_id,
            steps_total=steps_run,
            terminated_early=False,
        )
    )
    projection = RunbookMetadataProjection(
        runbook_id=runbook.runbook_id, events=events
    )
    return RunbookResult(
        runbook_id=runbook.runbook_id,
        step_outcomes=outcomes,
        steps_completed=steps_run,
        failed_step_index=None,
        terminated_early=False,
        metadata=projection,
    )


def _make_failure_result(runbook: Runbook, fail_at: int = 0) -> RunbookResult:
    """Minimal failed RunbookResult, failing at relative step fail_at."""
    failure = RuntimeFailure(
        kind=RuntimeFailureKind.PROVIDER_EXECUTION,
        code="PROVIDER_UNAVAILABLE",
        summary="test failure",
        request_id="req-m411-test",
        task_spec_id=runbook.steps[fail_at].task_spec_id,
        retryable=True,
        causal_code=None,
    )
    outcomes = [
        RunbookStepOutcome(
            step_index=fail_at,
            task_spec_id=runbook.steps[fail_at].task_spec_id,
            state=None,
            result=None,
            success=False,
            failure=failure,
        )
    ]
    projection = RunbookMetadataProjection(
        runbook_id=runbook.runbook_id,
        events=[
            RunbookLifecycleEvent(
                event="runbook_step_failed",
                runbook_id=runbook.runbook_id,
                steps_total=len(runbook.steps),
                step_index=fail_at,
                failed_step_index=fail_at,
                failure_kind=failure.kind.value,
                failure_code=failure.code,
            )
        ],
    )
    return RunbookResult(
        runbook_id=runbook.runbook_id,
        step_outcomes=outcomes,
        steps_completed=fail_at,
        failed_step_index=fail_at,
        terminated_early=True,
        metadata=projection,
    )


def _mock_cfg() -> MagicMock:
    return MagicMock()


def _mock_deps() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# Replay happy path
# ---------------------------------------------------------------------------

def test_replay_happy_path(tmp_path: Path) -> None:
    """replay() succeeds and returns status=success with correct fields."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(tmp_path, source_id, rb)

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)) as mock_run:
        result = replay(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.status == "success"
    assert result.mode == "replay"
    assert result.runbook_id == rb.runbook_id
    assert result.steps_completed == 3
    assert result.total_steps == 3
    assert result.metadata_summary is not None
    mock_run.assert_called_once()


def test_replay_starts_from_step_zero(tmp_path: Path) -> None:
    """replay() always passes the full runbook (start_index=0) to the runner."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    # Source checkpoint shows 1 step completed — replay ignores this and starts at 0.
    _write_checkpoint(
        tmp_path, source_id, rb,
        status="in_progress", steps_completed=1, last_completed_step_index=0
    )

    captured: list = []

    def _capture(**kwargs):
        captured.append(kwargs["runbook"])
        return _make_success_result(kwargs["runbook"])

    with patch("io_iii.core.runbook_runner.run", side_effect=_capture):
        result = replay(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.status == "success"
    assert len(captured) == 1
    assert len(captured[0].steps) == 3   # full runbook, not a slice


# ---------------------------------------------------------------------------
# Resume happy path
# ---------------------------------------------------------------------------

def test_resume_happy_path(tmp_path: Path) -> None:
    """resume() succeeds and returns status=success with correct fields."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    # 1 step completed in source run; resume starts at step 1.
    _write_checkpoint(
        tmp_path, source_id, rb,
        status="in_progress", steps_completed=1, last_completed_step_index=0, total_steps=3
    )
    # Sliced runbook has 2 steps (steps 1 and 2); runner returns 2 completed.
    slice_rb = Runbook.create(steps=rb.steps[1:], runbook_id=rb.runbook_id)

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(slice_rb, 2)):
        result = resume(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.status == "success"
    assert result.mode == "resume"
    assert result.steps_completed == 2
    assert result.total_steps == 3


def test_resume_starts_from_correct_step(tmp_path: Path) -> None:
    """resume() passes the correct step slice to the runner based on last_completed."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    # last_completed_step_index=0 → start_index=1; runner gets steps[1:]
    _write_checkpoint(
        tmp_path, source_id, rb,
        status="in_progress", steps_completed=1, last_completed_step_index=0, total_steps=3
    )

    captured: list = []

    def _capture(**kwargs):
        captured.append(kwargs["runbook"])
        return _make_success_result(kwargs["runbook"], len(kwargs["runbook"].steps))

    with patch("io_iii.core.runbook_runner.run", side_effect=_capture):
        resume(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert len(captured) == 1
    assert len(captured[0].steps) == 2   # steps[1:] → 2 steps remain


# ---------------------------------------------------------------------------
# Checkpoint not found
# ---------------------------------------------------------------------------

def test_checkpoint_not_found(tmp_path: Path) -> None:
    """Missing checkpoint file → status=error, failure_code=CHECKPOINT_NOT_FOUND."""
    missing_id = str(uuid.uuid4())

    result = replay(missing_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.status == "error"
    assert result.failure_code == "CHECKPOINT_NOT_FOUND"
    assert result.failure_kind == RuntimeFailureKind.CONTRACT_VIOLATION.value
    assert result.terminated_early is True


def test_checkpoint_not_found_resume(tmp_path: Path) -> None:
    """resume() with missing checkpoint → CHECKPOINT_NOT_FOUND."""
    missing_id = str(uuid.uuid4())

    result = resume(missing_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.status == "error"
    assert result.failure_code == "CHECKPOINT_NOT_FOUND"


# ---------------------------------------------------------------------------
# Checkpoint integrity failure
# ---------------------------------------------------------------------------

def test_checkpoint_integrity_error_bad_json(tmp_path: Path) -> None:
    """Unparseable checkpoint file → CHECKPOINT_INTEGRITY_ERROR."""
    bad_id = str(uuid.uuid4())
    (tmp_path / f"{bad_id}.json").write_text("not valid json {{", encoding="utf-8")

    result = replay(bad_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.status == "error"
    assert result.failure_code == "CHECKPOINT_INTEGRITY_ERROR"
    assert result.failure_kind == RuntimeFailureKind.CONTRACT_VIOLATION.value


def test_checkpoint_integrity_error_wrong_schema_version(tmp_path: Path) -> None:
    """Wrong checkpoint_schema_version → CHECKPOINT_INTEGRITY_ERROR."""
    rb = _three_step_runbook()
    bad_id = str(uuid.uuid4())
    data = {
        "checkpoint_schema_version": "2.0",
        "run_id": bad_id,
        "runbook_id": rb.runbook_id,
        "source_run_id": None,
        "runbook_snapshot": rb.to_dict(),
        "created_at": "2026-04-03T00:00:00+00:00",
        "updated_at": "2026-04-03T00:00:00+00:00",
        "steps_completed": 3,
        "last_completed_step_index": 2,
        "total_steps": 3,
        "status": "completed",
    }
    (tmp_path / f"{bad_id}.json").write_text(json.dumps(data), encoding="utf-8")

    result = replay(bad_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.failure_code == "CHECKPOINT_INTEGRITY_ERROR"


def test_checkpoint_integrity_error_run_id_mismatch(tmp_path: Path) -> None:
    """run_id in file mismatches requested run_id → CHECKPOINT_INTEGRITY_ERROR."""
    rb = _three_step_runbook()
    request_id = str(uuid.uuid4())
    different_id = str(uuid.uuid4())
    data = {
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "run_id": different_id,       # mismatch
        "runbook_id": rb.runbook_id,
        "source_run_id": None,
        "runbook_snapshot": rb.to_dict(),
        "created_at": "2026-04-03T00:00:00+00:00",
        "updated_at": "2026-04-03T00:00:00+00:00",
        "steps_completed": 3,
        "last_completed_step_index": 2,
        "total_steps": 3,
        "status": "completed",
    }
    (tmp_path / f"{request_id}.json").write_text(json.dumps(data), encoding="utf-8")

    result = replay(request_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.failure_code == "CHECKPOINT_INTEGRITY_ERROR"


def test_checkpoint_integrity_error_progress_inconsistency(tmp_path: Path) -> None:
    """steps_completed=0 with non-null last_completed_step_index → CHECKPOINT_INTEGRITY_ERROR."""
    rb = _three_step_runbook()
    bad_id = str(uuid.uuid4())
    data = {
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "run_id": bad_id,
        "runbook_id": rb.runbook_id,
        "source_run_id": None,
        "runbook_snapshot": rb.to_dict(),
        "created_at": "2026-04-03T00:00:00+00:00",
        "updated_at": "2026-04-03T00:00:00+00:00",
        "steps_completed": 0,
        "last_completed_step_index": 0,   # inconsistent with steps_completed=0
        "total_steps": 3,
        "status": "in_progress",
    }
    (tmp_path / f"{bad_id}.json").write_text(json.dumps(data), encoding="utf-8")

    result = resume(bad_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.failure_code == "CHECKPOINT_INTEGRITY_ERROR"


# ---------------------------------------------------------------------------
# Invalid resume state
# ---------------------------------------------------------------------------

def test_resume_invalid_state_completed_run(tmp_path: Path) -> None:
    """Attempting to resume a completed run → RESUME_INVALID_STATE (ADR-020 §3.3)."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(tmp_path, source_id, rb, status="completed")

    result = resume(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.status == "error"
    assert result.failure_code == "RESUME_INVALID_STATE"
    assert result.failure_kind == RuntimeFailureKind.CONTRACT_VIOLATION.value
    assert result.terminated_early is True


def test_completed_run_cannot_resume_no_runner_call(tmp_path: Path) -> None:
    """Runner must not be called when resume rejects a completed source run."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(tmp_path, source_id, rb, status="completed")

    with patch("io_iii.core.runbook_runner.run") as mock_run:
        resume(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    mock_run.assert_not_called()


def test_replay_of_completed_run_is_permitted(tmp_path: Path) -> None:
    """Replay of a completed run is allowed (ADR-020 §1.1)."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(tmp_path, source_id, rb, status="completed")

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
        result = replay(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.status == "success"


# ---------------------------------------------------------------------------
# Failed run resumes from failed_step_index
# ---------------------------------------------------------------------------

def test_resume_failed_run_starts_from_failed_step_index(tmp_path: Path) -> None:
    """
    For a failed source run, resume starts from failed_step_index (= last_completed + 1).

    Source: steps_completed=1, last_completed_step_index=0, failed_step_index=1.
    Resume should pass steps[1:] to the runner (2 steps).
    """
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(
        tmp_path, source_id, rb,
        status="failed",
        steps_completed=1,
        last_completed_step_index=0,
        total_steps=3,
        failed_step_index=1,
        failure_kind=RuntimeFailureKind.PROVIDER_EXECUTION.value,
        failure_code="PROVIDER_UNAVAILABLE",
    )

    captured: list = []

    def _capture(**kwargs):
        captured.append(kwargs["runbook"])
        rb_arg = kwargs["runbook"]
        return _make_success_result(rb_arg, len(rb_arg.steps))

    with patch("io_iii.core.runbook_runner.run", side_effect=_capture):
        result = resume(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.status == "success"
    assert len(captured) == 1
    # Runner receives steps[1:] — 2 steps
    assert len(captured[0].steps) == 2
    # First step given to runner is the original step at index 1
    assert captured[0].steps[0].task_spec_id == rb.steps[1].task_spec_id


def test_resume_zero_completed_starts_from_step_zero(tmp_path: Path) -> None:
    """
    Source run with steps_completed=0 → resume starts at step 0 (ADR-020 §3.2).
    """
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(
        tmp_path, source_id, rb,
        status="in_progress",
        steps_completed=0,
        last_completed_step_index=None,
        total_steps=3,
    )

    captured: list = []

    def _capture(**kwargs):
        captured.append(kwargs["runbook"])
        rb_arg = kwargs["runbook"]
        return _make_success_result(rb_arg, len(rb_arg.steps))

    with patch("io_iii.core.runbook_runner.run", side_effect=_capture):
        resume(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert len(captured[0].steps) == 3   # full runbook from step 0


# ---------------------------------------------------------------------------
# New run_id generation (ADR-020 §4.1)
# ---------------------------------------------------------------------------

def test_replay_generates_new_run_id(tmp_path: Path) -> None:
    """replay() must generate a new run_id distinct from the source_run_id."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(tmp_path, source_id, rb)

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
        result = replay(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.run_id != source_id
    assert result.run_id  # non-empty


def test_resume_generates_new_run_id(tmp_path: Path) -> None:
    """resume() must generate a new run_id distinct from the source_run_id."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(
        tmp_path, source_id, rb,
        status="in_progress", steps_completed=1, last_completed_step_index=0, total_steps=3
    )
    slice_rb = Runbook.create(steps=rb.steps[1:], runbook_id=rb.runbook_id)

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(slice_rb, 2)):
        result = resume(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.run_id != source_id
    assert result.run_id


def test_two_replays_generate_different_run_ids(tmp_path: Path) -> None:
    """Each replay call generates a unique run_id."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(tmp_path, source_id, rb)

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
        r1 = replay(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)
    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
        r2 = replay(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert r1.run_id != r2.run_id


# ---------------------------------------------------------------------------
# source_run_id binding (ADR-020 §4.2)
# ---------------------------------------------------------------------------

def test_replay_source_run_id_binds_to_input(tmp_path: Path) -> None:
    """result.source_run_id must equal the input run_id."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(tmp_path, source_id, rb)

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
        result = replay(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.source_run_id == source_id


def test_resume_source_run_id_binds_to_input(tmp_path: Path) -> None:
    """resume() result.source_run_id must equal the input run_id."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(
        tmp_path, source_id, rb,
        status="in_progress", steps_completed=1, last_completed_step_index=0, total_steps=3
    )
    slice_rb = Runbook.create(steps=rb.steps[1:], runbook_id=rb.runbook_id)

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(slice_rb, 2)):
        result = resume(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    assert result.source_run_id == source_id


def test_source_run_id_in_written_checkpoint(tmp_path: Path) -> None:
    """The checkpoint written by replay contains source_run_id = input run_id."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(tmp_path, source_id, rb)

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)) as _m:
        result = replay(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    new_cp_path = tmp_path / f"{result.run_id}.json"
    assert new_cp_path.exists()
    written = json.loads(new_cp_path.read_text())
    assert written["source_run_id"] == source_id
    assert written["run_id"] == result.run_id


# ---------------------------------------------------------------------------
# Audit passthrough (ADR-020 §5.3, §8.1)
# ---------------------------------------------------------------------------

def test_replay_audit_true_threads_to_runner(tmp_path: Path) -> None:
    """--audit=True reaches the runner (ADR-020 §8.1, §5.3)."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(tmp_path, source_id, rb)

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)) as mock_run:
        replay(source_id, cfg=_mock_cfg(), deps=_mock_deps(), audit=True, storage_root=tmp_path)

    _, kwargs = mock_run.call_args
    assert kwargs.get("audit") is True


def test_replay_audit_false_threads_to_runner(tmp_path: Path) -> None:
    """--audit=False (default) reaches the runner unchanged."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(tmp_path, source_id, rb)

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)) as mock_run:
        replay(source_id, cfg=_mock_cfg(), deps=_mock_deps(), audit=False, storage_root=tmp_path)

    _, kwargs = mock_run.call_args
    assert kwargs.get("audit") is False


def test_resume_audit_passthrough(tmp_path: Path) -> None:
    """resume() audit flag reaches the runner unchanged."""
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(
        tmp_path, source_id, rb,
        status="in_progress", steps_completed=1, last_completed_step_index=0, total_steps=3
    )
    slice_rb = Runbook.create(steps=rb.steps[1:], runbook_id=rb.runbook_id)

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(slice_rb, 2)) as mock_run:
        resume(source_id, cfg=_mock_cfg(), deps=_mock_deps(), audit=True, storage_root=tmp_path)

    _, kwargs = mock_run.call_args
    assert kwargs.get("audit") is True


# ---------------------------------------------------------------------------
# Absolute index mapping in checkpoint
# ---------------------------------------------------------------------------

def test_resume_checkpoint_uses_absolute_step_indices(tmp_path: Path) -> None:
    """
    Written checkpoint for a resume run carries absolute step indices,
    not runner-relative indices (ADR-020 §7.2).

    Source: 1 step completed (index 0). Resume starts at index 1 and completes 2 more.
    Expected: last_completed_step_index=2, steps_completed=2.
    """
    rb = _three_step_runbook()
    source_id = str(uuid.uuid4())
    _write_checkpoint(
        tmp_path, source_id, rb,
        status="in_progress", steps_completed=1, last_completed_step_index=0, total_steps=3
    )
    slice_rb = Runbook.create(steps=rb.steps[1:], runbook_id=rb.runbook_id)

    with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(slice_rb, 2)):
        result = resume(source_id, cfg=_mock_cfg(), deps=_mock_deps(), storage_root=tmp_path)

    new_cp_path = tmp_path / f"{result.run_id}.json"
    written = json.loads(new_cp_path.read_text())
    # Absolute: steps 1 and 2 completed → last_completed_step_index = 2
    assert written["last_completed_step_index"] == 2
    assert written["steps_completed"] == 2
    assert written["total_steps"] == 3
    assert written["status"] == "completed"


# ---------------------------------------------------------------------------
# CLI subcommand registration
# ---------------------------------------------------------------------------

def test_cli_replay_subcommand_registered() -> None:
    """'replay' subcommand is registered in main() and dispatches to cmd_replay."""
    from unittest.mock import patch as _patch

    # Patch the name as imported into cli.py (already bound at import time)
    with _patch("io_iii.cli._replay") as mock_replay:
        mock_replay.return_value = ReplayResumeResult(
            status="success",
            mode="replay",
            run_id="new-run-id",
            source_run_id="src-run-id",
            runbook_id="rb-test",
            steps_completed=1,
            total_steps=1,
            metadata_summary=None,
        )
        ret = main(["replay", "src-run-id"])

    assert ret == 0
    mock_replay.assert_called_once()
    call_args = mock_replay.call_args
    assert call_args[0][0] == "src-run-id"


def test_cli_resume_subcommand_registered() -> None:
    """'resume' subcommand is registered in main() and dispatches to cmd_resume."""
    from unittest.mock import patch as _patch

    with _patch("io_iii.cli._resume") as mock_resume:
        mock_resume.return_value = ReplayResumeResult(
            status="error",
            mode="resume",
            run_id="new-run-id",
            source_run_id="src-run-id",
            runbook_id="rb-test",
            steps_completed=0,
            total_steps=0,
            metadata_summary=None,
            failure_kind=RuntimeFailureKind.CONTRACT_VIOLATION.value,
            failure_code="RESUME_INVALID_STATE",
            failed_step_index=None,
            terminated_early=True,
        )
        ret = main(["resume", "src-run-id"])

    assert ret == 1
    mock_resume.assert_called_once()


def test_cli_replay_audit_flag() -> None:
    """--audit flag threads through the CLI replay path."""
    from unittest.mock import patch as _patch

    with _patch("io_iii.cli._replay") as mock_replay:
        mock_replay.return_value = ReplayResumeResult(
            status="success",
            mode="replay",
            run_id="rid",
            source_run_id="src",
            runbook_id="rb",
            steps_completed=1,
            total_steps=1,
            metadata_summary=None,
        )
        main(["replay", "src", "--audit"])

    _, kwargs = mock_replay.call_args
    assert kwargs.get("audit") is True
