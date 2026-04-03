"""
Replay/Resume execution layer (Phase 4 M4.11 / ADR-020).

Implements bounded re-execution of prior runbook runs above the frozen M4.9 surface.
Checkpoint resolution follows ADR-019 §7 (six-step lookup) + §8 (integrity checks).
Execution flows through the existing bounded runbook_runner.run() unchanged.
"""
from __future__ import annotations

import datetime
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from io_iii.core.failure_model import RuntimeFailureKind
from io_iii.core.runbook import Runbook
import io_iii.core.runbook_runner as _runbook_runner
from io_iii.core.runbook_runner import RunbookResult


# ---------------------------------------------------------------------------
# Constants (ADR-019 §4, §7)
# ---------------------------------------------------------------------------

CHECKPOINT_SCHEMA_VERSION: str = "1.0"
DEFAULT_STORAGE_ROOT: Path = Path(".io_iii/checkpoints")


# ---------------------------------------------------------------------------
# Public result type (ADR-020 §8.2)
# ---------------------------------------------------------------------------

@dataclass
class ReplayResumeResult:
    """
    Bounded, content-safe result of a replay or resume execution (ADR-020 §8.2).

    Content policy: no prompt text, model output, exception messages, or stack
    traces appear in any field. All identifiers are machine-generated.
    """

    status: str                          # "success" or "error"
    mode: str                            # "replay" or "resume"
    run_id: str
    source_run_id: str
    runbook_id: str
    steps_completed: int
    total_steps: int
    metadata_summary: Optional[Dict[str, Any]]
    # Failure fields (present when status = "error")
    failure_kind: Optional[str] = None
    failure_code: Optional[str] = None
    failed_step_index: Optional[int] = None
    terminated_early: Optional[bool] = None


# ---------------------------------------------------------------------------
# Internal checkpoint resolution error
# ---------------------------------------------------------------------------

class _CheckpointError(Exception):
    """Raised internally when checkpoint lookup or integrity checks fail."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# Checkpoint resolution (ADR-019 §7 six-step + §8 integrity)
# ---------------------------------------------------------------------------

def _checkpoint_path(run_id: str, storage_root: Path) -> Path:
    return storage_root / f"{run_id}.json"


def _load_and_validate_checkpoint(run_id: str, storage_root: Path) -> Dict[str, Any]:
    """
    Execute the ADR-019 §7 six-step lookup algorithm and §8 integrity checks.

    Raises:
        _CheckpointError("CHECKPOINT_NOT_FOUND")       — step 2 fails
        _CheckpointError("CHECKPOINT_INTEGRITY_ERROR") — any §7 step 3–6 or §8 check fails
    """
    path = _checkpoint_path(run_id, storage_root)

    # §7 step 2: existence check
    if not path.exists():
        raise _CheckpointError("CHECKPOINT_NOT_FOUND")

    # §7 step 3: read and parse
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        raise _CheckpointError("CHECKPOINT_INTEGRITY_ERROR")

    if not isinstance(data, dict):
        raise _CheckpointError("CHECKPOINT_INTEGRITY_ERROR")

    # §7 step 4: schema version
    if data.get("checkpoint_schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise _CheckpointError("CHECKPOINT_INTEGRITY_ERROR")

    # §7 step 5: run_id binding
    if data.get("run_id") != run_id:
        raise _CheckpointError("CHECKPOINT_INTEGRITY_ERROR")

    # §7 step 6: runbook_id vs runbook_snapshot consistency
    snapshot = data.get("runbook_snapshot")
    if not isinstance(snapshot, dict):
        raise _CheckpointError("CHECKPOINT_INTEGRITY_ERROR")
    if data.get("runbook_id") != snapshot.get("runbook_id"):
        raise _CheckpointError("CHECKPOINT_INTEGRITY_ERROR")

    # §8.3: progress consistency
    steps_completed = data.get("steps_completed")
    last_idx = data.get("last_completed_step_index")
    total = data.get("total_steps")
    if not isinstance(steps_completed, int) or not isinstance(total, int):
        raise _CheckpointError("CHECKPOINT_INTEGRITY_ERROR")
    if steps_completed == 0:
        if last_idx is not None:
            raise _CheckpointError("CHECKPOINT_INTEGRITY_ERROR")
    else:
        if not isinstance(last_idx, int) or last_idx < 0 or last_idx >= total:
            raise _CheckpointError("CHECKPOINT_INTEGRITY_ERROR")

    # §8.4: failure field consistency
    status = data.get("status")
    if status == "failed":
        if (
            data.get("failure_kind") is None
            or data.get("failure_code") is None
            or data.get("failed_step_index") is None
        ):
            raise _CheckpointError("CHECKPOINT_INTEGRITY_ERROR")

    return data


# ---------------------------------------------------------------------------
# Checkpoint writer (ADR-019 §3)
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _write_checkpoint_atomic(path: Path, data: Dict[str, Any]) -> None:
    """Atomic write via sibling temp file + rename (ADR-019 §3.3)."""
    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(data), encoding="utf-8")
        tmp_path.replace(path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _write_checkpoint(
    *,
    path: Path,
    run_id: str,
    source_run_id: str,
    runbook_id: str,
    snapshot: Dict[str, Any],
    created_at: str,
    steps_completed: int,
    last_completed_step_index: Optional[int],
    total_steps: int,
    status: str,
    failure_kind: Optional[str] = None,
    failure_code: Optional[str] = None,
    failed_step_index: Optional[int] = None,
) -> None:
    """Write a terminal checkpoint record (ADR-019 §1, §3, §6)."""
    data: Dict[str, Any] = {
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "run_id": run_id,
        "runbook_id": runbook_id,
        "source_run_id": source_run_id,
        "runbook_snapshot": snapshot,
        "created_at": created_at,
        "steps_completed": steps_completed,
        "last_completed_step_index": last_completed_step_index,
        "total_steps": total_steps,
        "status": status,
        "updated_at": _utc_now(),
    }
    if status == "failed":
        data["failure_kind"] = failure_kind
        data["failure_code"] = failure_code
        data["failed_step_index"] = failed_step_index
    _write_checkpoint_atomic(path, data)


# ---------------------------------------------------------------------------
# Run ID generation (ADR-018 §1.2)
# ---------------------------------------------------------------------------

def _new_run_id() -> str:
    """Generate a new UUIDv4 run_id (ADR-018 §1.2)."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _failure_result(
    code: str,
    mode: str,
    run_id: str,
    source_run_id: str,
    runbook_id: str,
) -> ReplayResumeResult:
    """Build a pre-execution failure result (ADR-020 §6.2)."""
    return ReplayResumeResult(
        status="error",
        mode=mode,
        run_id=run_id,
        source_run_id=source_run_id,
        runbook_id=runbook_id,
        steps_completed=0,
        total_steps=0,
        metadata_summary=None,
        failure_kind=RuntimeFailureKind.CONTRACT_VIOLATION.value,
        failure_code=code,
        failed_step_index=None,
        terminated_early=True,
    )


def _execute(
    *,
    run_id: str,
    source_run_id: str,
    runbook: Runbook,
    start_index: int,
    total_steps: int,
    mode: str,
    cfg: Any,
    deps: Any,
    audit: bool,
    storage_root: Path,
) -> ReplayResumeResult:
    """
    Slice the runbook, execute through runbook_runner.run(), write terminal checkpoint.

    Step indices stored in the checkpoint are absolute (relative to the full runbook),
    not relative to the slice. The runner's local step indices are offset by start_index.
    """
    runbook_id = runbook.runbook_id
    created_at = _utc_now()
    full_snapshot = runbook.to_dict()   # full runbook, not slice (ADR-020 §7.2)

    # Slice steps from start_index onward (ADR-020 §5.1, §5.2)
    sliced_steps = runbook.steps[start_index:]

    if not sliced_steps:
        # Edge case: no steps remain (all previously completed); treat as success.
        _write_checkpoint(
            path=_checkpoint_path(run_id, storage_root),
            run_id=run_id,
            source_run_id=source_run_id,
            runbook_id=runbook_id,
            snapshot=full_snapshot,
            created_at=created_at,
            steps_completed=0,
            last_completed_step_index=None,
            total_steps=total_steps,
            status="completed",
        )
        return ReplayResumeResult(
            status="success",
            mode=mode,
            run_id=run_id,
            source_run_id=source_run_id,
            runbook_id=runbook_id,
            steps_completed=0,
            total_steps=total_steps,
            metadata_summary={"runbook_id": runbook_id, "event_count": 0},
        )

    # Build sliced Runbook with the same runbook_id (ADR-020 §5.1)
    sliced_runbook = Runbook.create(steps=list(sliced_steps), runbook_id=runbook_id)

    # Execute through the existing bounded runner (ADR-020 §5.1)
    result: RunbookResult = _runbook_runner.run(
        runbook=sliced_runbook,
        cfg=cfg,
        deps=deps,
        audit=audit,
    )

    # Map runner-relative indices to absolute indices (offset by start_index)
    abs_steps_completed: int = result.steps_completed
    abs_last_completed: Optional[int] = (
        start_index + result.steps_completed - 1
        if result.steps_completed > 0
        else None
    )
    abs_failed_step: Optional[int] = (
        start_index + result.failed_step_index
        if result.failed_step_index is not None
        else None
    )

    # Extract failure info from the step outcome (ADR-013 envelope)
    failure_kind: Optional[str] = None
    failure_code: Optional[str] = None
    if result.terminated_early and result.failed_step_index is not None:
        rel_idx = result.failed_step_index
        if 0 <= rel_idx < len(result.step_outcomes):
            step_failure = result.step_outcomes[rel_idx].failure
            if step_failure is not None:
                failure_kind = step_failure.kind.value
                failure_code = step_failure.code

    # Write terminal checkpoint (ADR-019 §3.1, §5.4)
    status_str = "failed" if result.terminated_early else "completed"
    _write_checkpoint(
        path=_checkpoint_path(run_id, storage_root),
        run_id=run_id,
        source_run_id=source_run_id,
        runbook_id=runbook_id,
        snapshot=full_snapshot,
        created_at=created_at,
        steps_completed=abs_steps_completed,
        last_completed_step_index=abs_last_completed,
        total_steps=total_steps,
        status=status_str,
        failure_kind=failure_kind,
        failure_code=failure_code,
        failed_step_index=abs_failed_step,
    )

    # Metadata summary (ADR-020 §8.2)
    metadata_summary: Optional[Dict[str, Any]] = None
    if result.metadata is not None:
        metadata_summary = {
            "runbook_id": result.metadata.runbook_id,
            "event_count": len(result.metadata.events),
        }

    if result.terminated_early:
        return ReplayResumeResult(
            status="error",
            mode=mode,
            run_id=run_id,
            source_run_id=source_run_id,
            runbook_id=runbook_id,
            steps_completed=abs_steps_completed,
            total_steps=total_steps,
            metadata_summary=metadata_summary,
            failure_kind=failure_kind,
            failure_code=failure_code,
            failed_step_index=abs_failed_step,
            terminated_early=True,
        )

    return ReplayResumeResult(
        status="success",
        mode=mode,
        run_id=run_id,
        source_run_id=source_run_id,
        runbook_id=runbook_id,
        steps_completed=abs_steps_completed,
        total_steps=total_steps,
        metadata_summary=metadata_summary,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def replay(
    source_run_id: str,
    *,
    cfg: Any,
    deps: Any,
    audit: bool = False,
    storage_root: Path = DEFAULT_STORAGE_ROOT,
) -> ReplayResumeResult:
    """
    Re-execute a prior runbook run from step 0 (ADR-020 §1.1, §3.1).

    Resolves the source checkpoint via ADR-019 §7, generates a new run_id (ADR-018),
    and executes the full runbook from step 0. Any source checkpoint status is
    permissible for replay (completed, failed, or in_progress).

    Args:
        source_run_id — run_id of the prior run to replay
        cfg           — runtime configuration (same contract as runbook_runner.run)
        deps          — RuntimeDependencies (same contract as runbook_runner.run)
        audit         — enable challenger audit pass per step (ADR-009)
        storage_root  — checkpoint storage root (ADR-019 §4.1)

    Returns:
        ReplayResumeResult carrying status, lineage, and execution summary.
        On pre-execution failure: status="error", failure_code in {CHECKPOINT_NOT_FOUND,
        CHECKPOINT_INTEGRITY_ERROR}. On step failure: status="error" with step failure fields.
    """
    run_id = _new_run_id()

    try:
        checkpoint = _load_and_validate_checkpoint(source_run_id, storage_root)
    except _CheckpointError as exc:
        return _failure_result(exc.code, "replay", run_id, source_run_id, "")

    runbook_id = checkpoint["runbook_id"]
    snapshot = checkpoint["runbook_snapshot"]
    total_steps = checkpoint["total_steps"]

    try:
        runbook = Runbook.from_dict(snapshot)
    except (ValueError, TypeError):
        return _failure_result(
            "CHECKPOINT_INTEGRITY_ERROR", "replay", run_id, source_run_id, runbook_id
        )

    return _execute(
        run_id=run_id,
        source_run_id=source_run_id,
        runbook=runbook,
        start_index=0,
        total_steps=total_steps,
        mode="replay",
        cfg=cfg,
        deps=deps,
        audit=audit,
        storage_root=storage_root,
    )


def resume(
    source_run_id: str,
    *,
    cfg: Any,
    deps: Any,
    audit: bool = False,
    storage_root: Path = DEFAULT_STORAGE_ROOT,
) -> ReplayResumeResult:
    """
    Continue a prior runbook run from the first incomplete step (ADR-020 §1.2, §3.2).

    Resolves the source checkpoint via ADR-019 §7. Raises RESUME_INVALID_STATE if
    the source run completed. Generates a new run_id (ADR-018).

    Starting step derivation (ADR-020 §3.2):
      - last_completed_step_index is None → start at step 0
      - last_completed_step_index = N    → start at step N+1
      (For a failed run, failed_step_index = N+1 per ADR-019 §8.3/8.4, so both
      derivations produce the same result.)

    Args:
        source_run_id — run_id of the prior run to resume
        cfg           — runtime configuration
        deps          — RuntimeDependencies
        audit         — enable challenger audit pass per step (ADR-009)
        storage_root  — checkpoint storage root

    Returns:
        ReplayResumeResult. On completed source run: status="error",
        failure_code="RESUME_INVALID_STATE". On pre-execution failure: status="error",
        failure_code in {CHECKPOINT_NOT_FOUND, CHECKPOINT_INTEGRITY_ERROR}.
    """
    run_id = _new_run_id()

    try:
        checkpoint = _load_and_validate_checkpoint(source_run_id, storage_root)
    except _CheckpointError as exc:
        return _failure_result(exc.code, "resume", run_id, source_run_id, "")

    runbook_id = checkpoint["runbook_id"]
    snapshot = checkpoint["runbook_snapshot"]
    total_steps = checkpoint["total_steps"]
    status = checkpoint["status"]

    # Completed runs cannot be resumed (ADR-020 §3.3)
    if status == "completed":
        return _failure_result(
            "RESUME_INVALID_STATE", "resume", run_id, source_run_id, runbook_id
        )

    # Derive resume start index (ADR-020 §3.2)
    last_completed = checkpoint.get("last_completed_step_index")
    start_index: int = 0 if last_completed is None else last_completed + 1

    try:
        runbook = Runbook.from_dict(snapshot)
    except (ValueError, TypeError):
        return _failure_result(
            "CHECKPOINT_INTEGRITY_ERROR", "resume", run_id, source_run_id, runbook_id
        )

    return _execute(
        run_id=run_id,
        source_run_id=source_run_id,
        runbook=runbook,
        start_index=start_index,
        total_steps=total_steps,
        mode="resume",
        cfg=cfg,
        deps=deps,
        audit=audit,
        storage_root=storage_root,
    )
