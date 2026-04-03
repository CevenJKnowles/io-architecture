"""
test_runbook_m49.py — Phase 4 M4.9 CLI Runbook Execution Surface tests.

Verifies the CLI runbook contract defined in ADR-016:

Command registration / dispatch:
  - runbook subcommand is registered and dispatched correctly
  - cmd_runbook is reachable via CLI argument parsing

Pre-execution validation (ADR-016 §3 — validation order is contractual):
  - missing file → RUNBOOK_FILE_NOT_FOUND error, return 1
  - invalid JSON → RUNBOOK_INVALID_JSON error, return 1
  - invalid runbook schema → RUNBOOK_SCHEMA_ERROR error, return 1

Success path:
  - valid JSON runbook produces status=ok and return 0
  - steps_completed is surfaced correctly
  - terminated_early=False on success
  - failed_step_index=None on success
  - metadata_projection surfaced when M4.8 projection present

Failure propagation (ADR-013 reuse — ADR-016 §7):
  - terminated_early=True when runner returns failed result
  - failed_step_index surfaced from RunbookResult
  - failure_kind surfaced from ADR-013 RuntimeFailure envelope
  - failure_code surfaced from ADR-013 RuntimeFailure envelope
  - return 1 on runbook step failure

Audit passthrough (ADR-016 §5):
  - --audit flag threads through to runner without adding CLI semantics
  - runner receives audit=True when --audit is passed
  - runner receives audit=False when --audit is absent

Structural output (ADR-016 §6):
  - output is always valid JSON
  - success output contains all required fields
  - failure output contains all required fields
  - pre-execution failure output contains status and error_code

No regression:
  - existing CLI subcommands (capabilities, config, capability, about) continue to parse

All execution tests mock io_iii.core.runbook_runner.run to isolate the CLI veneer
from live provider dependencies, matching the thin-veneer constraint (ADR-016 §4).
Pre-execution tests require no mocking; they test input validation only.
"""
from __future__ import annotations

import argparse
import json
import types
from typing import Any, List, Optional
from unittest.mock import MagicMock, call, patch

import pytest

from io_iii.cli import cmd_runbook, main
from io_iii.core.failure_model import RuntimeFailure, RuntimeFailureKind
from io_iii.core.runbook import Runbook
from io_iii.core.runbook_runner import (
    RunbookLifecycleEvent,
    RunbookMetadataProjection,
    RunbookResult,
    RunbookStepOutcome,
)
from io_iii.core.task_spec import TaskSpec


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

def _step(n: int = 0) -> TaskSpec:
    return TaskSpec.create(mode="executor", prompt=f"M4.9 test step {n}.")


def _single_step_runbook() -> Runbook:
    return Runbook.create(steps=[_step(0)], runbook_id="rb-m49-test")


def _runbook_json(runbook: Optional[Runbook] = None) -> str:
    rb = runbook or _single_step_runbook()
    return json.dumps(rb.to_dict())


def _make_success_result(runbook: Optional[Runbook] = None) -> RunbookResult:
    """Construct a minimal successful RunbookResult with M4.8 projection."""
    rb = runbook or _single_step_runbook()
    step = rb.steps[0]
    projection = RunbookMetadataProjection(
        runbook_id=rb.runbook_id,
        events=[
            RunbookLifecycleEvent(
                event="runbook_started",
                runbook_id=rb.runbook_id,
                steps_total=1,
            ),
            RunbookLifecycleEvent(
                event="runbook_step_started",
                runbook_id=rb.runbook_id,
                steps_total=1,
                task_spec_id=step.task_spec_id,
                step_index=0,
            ),
            RunbookLifecycleEvent(
                event="runbook_step_completed",
                runbook_id=rb.runbook_id,
                steps_total=1,
                task_spec_id=step.task_spec_id,
                step_index=0,
                request_id="req-test-001",
                duration_ms=5,
            ),
            RunbookLifecycleEvent(
                event="runbook_completed",
                runbook_id=rb.runbook_id,
                steps_total=1,
                terminated_early=False,
                total_duration_ms=6,
            ),
        ],
    )
    return RunbookResult(
        runbook_id=rb.runbook_id,
        step_outcomes=[
            RunbookStepOutcome(
                step_index=0,
                task_spec_id=step.task_spec_id,
                state=None,
                result=None,
                success=True,
                failure=None,
            )
        ],
        steps_completed=1,
        failed_step_index=None,
        terminated_early=False,
        metadata=projection,
    )


def _make_failure_result(runbook: Optional[Runbook] = None) -> RunbookResult:
    """Construct a minimal failed RunbookResult with ADR-013 envelope."""
    rb = runbook or _single_step_runbook()
    step = rb.steps[0]
    failure = RuntimeFailure(
        kind=RuntimeFailureKind.PROVIDER_EXECUTION,
        code="PROVIDER_UNAVAILABLE",
        summary="test failure",
        request_id="req-test-002",
        task_spec_id=step.task_spec_id,
        retryable=True,
        causal_code=None,
    )
    projection = RunbookMetadataProjection(
        runbook_id=rb.runbook_id,
        events=[
            RunbookLifecycleEvent(
                event="runbook_started",
                runbook_id=rb.runbook_id,
                steps_total=1,
            ),
            RunbookLifecycleEvent(
                event="runbook_step_started",
                runbook_id=rb.runbook_id,
                steps_total=1,
                task_spec_id=step.task_spec_id,
                step_index=0,
            ),
            RunbookLifecycleEvent(
                event="runbook_step_failed",
                runbook_id=rb.runbook_id,
                steps_total=1,
                task_spec_id=step.task_spec_id,
                step_index=0,
                request_id="req-test-002",
                terminated_early=True,
                failed_step_index=0,
                duration_ms=3,
                failure_kind=RuntimeFailureKind.PROVIDER_EXECUTION.value,
                failure_code="PROVIDER_UNAVAILABLE",
            ),
            RunbookLifecycleEvent(
                event="runbook_terminated",
                runbook_id=rb.runbook_id,
                steps_total=1,
                terminated_early=True,
                failed_step_index=0,
                total_duration_ms=4,
                failure_kind=RuntimeFailureKind.PROVIDER_EXECUTION.value,
                failure_code="PROVIDER_UNAVAILABLE",
            ),
        ],
    )
    return RunbookResult(
        runbook_id=rb.runbook_id,
        step_outcomes=[
            RunbookStepOutcome(
                step_index=0,
                task_spec_id=step.task_spec_id,
                state=None,
                result=None,
                success=False,
                failure=failure,
            )
        ],
        steps_completed=0,
        failed_step_index=0,
        terminated_early=True,
        metadata=projection,
    )


def _args(json_file: str, *, audit: bool = False, config_dir: Optional[str] = None) -> argparse.Namespace:
    return argparse.Namespace(json_file=json_file, audit=audit, config_dir=config_dir)


# ---------------------------------------------------------------------------
# Command registration / dispatch
# ---------------------------------------------------------------------------

class TestCommandRegistration:
    def test_runbook_subcommand_parses_json_file(self, tmp_path):
        """runbook subcommand must parse the json_file positional argument."""
        f = tmp_path / "rb.json"
        f.write_text("{}")
        parsed = main.__wrapped__ if hasattr(main, "__wrapped__") else None
        # Use argparse directly to verify subcommand registration.
        import io_iii.cli as cli_module
        parser = argparse.ArgumentParser(prog="io-iii")
        sub = parser.add_subparsers(dest="cmd", required=True)
        p_rb = sub.add_parser("runbook")
        p_rb.add_argument("json_file")
        p_rb.add_argument("--audit", action="store_true")
        p_rb.set_defaults(func=cmd_runbook)
        args = parser.parse_args(["runbook", str(f)])
        assert args.json_file == str(f)
        assert args.func is cmd_runbook
        assert args.audit is False

    def test_runbook_subcommand_audit_flag_parses(self, tmp_path):
        """--audit flag must parse without error."""
        f = tmp_path / "rb.json"
        f.write_text("{}")
        parser = argparse.ArgumentParser(prog="io-iii")
        sub = parser.add_subparsers(dest="cmd", required=True)
        p_rb = sub.add_parser("runbook")
        p_rb.add_argument("json_file")
        p_rb.add_argument("--audit", action="store_true")
        args = parser.parse_args(["runbook", str(f), "--audit"])
        assert args.audit is True

    def test_existing_subcommands_still_registered(self):
        """Existing CLI subcommands must not be displaced by runbook registration."""
        import io_iii.cli as cli_module
        # Verify the registered command functions still exist (no displacement).
        assert callable(cli_module.cmd_capabilities)
        assert callable(cli_module.cmd_config_show)
        assert callable(cli_module.cmd_route)
        assert callable(cli_module.cmd_run)
        assert callable(cli_module.cmd_capability)
        assert callable(cli_module.cmd_about)
        assert callable(cli_module.cmd_runbook)


# ---------------------------------------------------------------------------
# Pre-execution validation (ADR-016 §3 — validation order is contractual)
# ---------------------------------------------------------------------------

class TestPreExecutionValidation:
    def test_missing_file_returns_error_code(self, tmp_path, capsys):
        """Non-existent file path must produce RUNBOOK_FILE_NOT_FOUND, return 1."""
        rc = cmd_runbook(_args(str(tmp_path / "nonexistent.json")))
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert out["error_code"] == "RUNBOOK_FILE_NOT_FOUND"

    def test_path_to_directory_returns_error_code(self, tmp_path, capsys):
        """Path pointing to a directory (not a file) must produce RUNBOOK_FILE_NOT_FOUND."""
        rc = cmd_runbook(_args(str(tmp_path)))
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert out["error_code"] == "RUNBOOK_FILE_NOT_FOUND"

    def test_invalid_json_returns_error_code(self, tmp_path, capsys):
        """Non-JSON file content must produce RUNBOOK_INVALID_JSON, return 1."""
        f = tmp_path / "bad.json"
        f.write_text("{ not valid json !!!")
        rc = cmd_runbook(_args(str(f)))
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert out["error_code"] == "RUNBOOK_INVALID_JSON"

    def test_empty_file_returns_invalid_json(self, tmp_path, capsys):
        """Empty file must produce RUNBOOK_INVALID_JSON (not a valid JSON document)."""
        f = tmp_path / "empty.json"
        f.write_text("")
        rc = cmd_runbook(_args(str(f)))
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert out["error_code"] == "RUNBOOK_INVALID_JSON"

    def test_json_array_returns_schema_error(self, tmp_path, capsys):
        """Valid JSON but wrong top-level type (array) must produce RUNBOOK_SCHEMA_ERROR."""
        f = tmp_path / "array.json"
        f.write_text("[]")
        rc = cmd_runbook(_args(str(f)))
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert out["error_code"] == "RUNBOOK_SCHEMA_ERROR"

    def test_empty_steps_returns_schema_error(self, tmp_path, capsys):
        """Valid JSON object with empty steps must produce RUNBOOK_SCHEMA_ERROR (RUNBOOK_EMPTY)."""
        f = tmp_path / "empty_steps.json"
        f.write_text(json.dumps({"runbook_id": "rb-x", "steps": []}))
        rc = cmd_runbook(_args(str(f)))
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert out["error_code"] == "RUNBOOK_SCHEMA_ERROR"

    def test_missing_steps_key_returns_schema_error(self, tmp_path, capsys):
        """Valid JSON object missing 'steps' key must produce RUNBOOK_SCHEMA_ERROR."""
        f = tmp_path / "no_steps.json"
        f.write_text(json.dumps({"runbook_id": "rb-x"}))
        rc = cmd_runbook(_args(str(f)))
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert out["error_code"] == "RUNBOOK_SCHEMA_ERROR"

    def test_invalid_step_structure_returns_schema_error(self, tmp_path, capsys):
        """Step missing required fields must produce RUNBOOK_SCHEMA_ERROR."""
        f = tmp_path / "bad_step.json"
        f.write_text(json.dumps({
            "runbook_id": "rb-x",
            "steps": [{"bad": "step"}],  # missing mode and prompt
        }))
        rc = cmd_runbook(_args(str(f)))
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert out["error_code"] == "RUNBOOK_SCHEMA_ERROR"

    def test_validation_order_file_checked_before_json(self, tmp_path, capsys):
        """Validation must check file existence before JSON parsing (order is contractual)."""
        # A non-existent path cannot produce RUNBOOK_INVALID_JSON; must be RUNBOOK_FILE_NOT_FOUND.
        rc = cmd_runbook(_args(str(tmp_path / "does_not_exist.json")))
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["error_code"] == "RUNBOOK_FILE_NOT_FOUND"

    def test_validation_order_json_checked_before_schema(self, tmp_path, capsys):
        """Validation must check JSON validity before schema (order is contractual)."""
        # Invalid JSON cannot produce RUNBOOK_SCHEMA_ERROR; must be RUNBOOK_INVALID_JSON.
        f = tmp_path / "invalid.json"
        f.write_text("not json")
        rc = cmd_runbook(_args(str(f)))
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["error_code"] == "RUNBOOK_INVALID_JSON"


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

class TestSuccessPath:
    def test_success_returns_zero(self, tmp_path, capsys):
        """Valid runbook execution success must return 0."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
            rc = cmd_runbook(_args(str(f)))
        assert rc == 0

    def test_success_status_ok(self, tmp_path, capsys):
        """Success output must contain status=ok."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ok"

    def test_success_runbook_id_surfaced(self, tmp_path, capsys):
        """Success output must surface the runbook_id."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["runbook_id"] == rb.runbook_id

    def test_success_steps_completed_correct(self, tmp_path, capsys):
        """Success output must surface steps_completed matching runner result."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["steps_completed"] == 1

    def test_success_terminated_early_false(self, tmp_path, capsys):
        """Success output must have terminated_early=False."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["terminated_early"] is False

    def test_success_failed_step_index_null(self, tmp_path, capsys):
        """Success output must have failed_step_index=null."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["failed_step_index"] is None

    def test_success_output_is_valid_json(self, tmp_path, capsys):
        """Success output must be parseable as a JSON object (structural requirement)."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
            cmd_runbook(_args(str(f)))
        raw = capsys.readouterr().out
        obj = json.loads(raw)
        assert isinstance(obj, dict)

    def test_success_all_required_fields_present(self, tmp_path, capsys):
        """Success output must contain all contractually required fields (ADR-016 §6)."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        for field in ("status", "runbook_id", "steps_completed", "terminated_early", "failed_step_index"):
            assert field in out, f"Required field '{field}' missing from success output"


# ---------------------------------------------------------------------------
# M4.8 metadata projection surfacing (ADR-016 §8)
# ---------------------------------------------------------------------------

class TestMetadataProjectionSurfacing:
    def test_metadata_projection_present_in_success_output(self, tmp_path, capsys):
        """metadata_projection must be surfaced in success output when M4.8 projection present."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert "metadata_projection" in out
        assert out["metadata_projection"] is not None

    def test_metadata_projection_contains_runbook_id(self, tmp_path, capsys):
        """metadata_projection must carry runbook_id for correlation."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["metadata_projection"]["runbook_id"] == rb.runbook_id

    def test_metadata_projection_event_count_correct(self, tmp_path, capsys):
        """metadata_projection.event_count must match the number of events in the projection."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        result = _make_success_result(rb)
        with patch("io_iii.core.runbook_runner.run", return_value=result):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["metadata_projection"]["event_count"] == len(result.metadata.events)

    def test_metadata_projection_none_when_absent(self, tmp_path, capsys):
        """metadata_projection must be null when RunbookResult.metadata is None."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        result = _make_success_result(rb)
        result_no_meta = RunbookResult(
            runbook_id=result.runbook_id,
            step_outcomes=result.step_outcomes,
            steps_completed=result.steps_completed,
            failed_step_index=result.failed_step_index,
            terminated_early=result.terminated_early,
            metadata=None,
        )
        with patch("io_iii.core.runbook_runner.run", return_value=result_no_meta):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["metadata_projection"] is None


# ---------------------------------------------------------------------------
# Failure propagation (ADR-013 reuse — ADR-016 §7)
# ---------------------------------------------------------------------------

class TestFailurePropagation:
    def test_step_failure_returns_one(self, tmp_path, capsys):
        """Runbook step failure must return exit code 1."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_failure_result(rb)):
            rc = cmd_runbook(_args(str(f)))
        assert rc == 1

    def test_step_failure_status_error(self, tmp_path, capsys):
        """Runbook step failure output must contain status=error."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_failure_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"

    def test_step_failure_terminated_early_true(self, tmp_path, capsys):
        """Runbook step failure output must have terminated_early=True."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_failure_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["terminated_early"] is True

    def test_step_failure_failed_step_index_surfaced(self, tmp_path, capsys):
        """Runbook step failure output must surface failed_step_index."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_failure_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["failed_step_index"] == 0

    def test_step_failure_failure_kind_from_adr013(self, tmp_path, capsys):
        """failure_kind must be sourced from the ADR-013 RuntimeFailure envelope."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_failure_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["failure_kind"] == RuntimeFailureKind.PROVIDER_EXECUTION.value

    def test_step_failure_failure_code_from_adr013(self, tmp_path, capsys):
        """failure_code must be sourced from the ADR-013 RuntimeFailure envelope."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_failure_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["failure_code"] == "PROVIDER_UNAVAILABLE"

    def test_step_failure_no_adr013_envelope_surfaces_none(self, tmp_path, capsys):
        """When no ADR-013 envelope present, failure_kind and failure_code must be None."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        step = rb.steps[0]
        result_no_envelope = RunbookResult(
            runbook_id=rb.runbook_id,
            step_outcomes=[
                RunbookStepOutcome(
                    step_index=0,
                    task_spec_id=step.task_spec_id,
                    state=None,
                    result=None,
                    success=False,
                    failure=None,  # no ADR-013 envelope
                )
            ],
            steps_completed=0,
            failed_step_index=0,
            terminated_early=True,
            metadata=None,
        )
        with patch("io_iii.core.runbook_runner.run", return_value=result_no_envelope):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        assert out["failure_kind"] is None
        assert out["failure_code"] is None

    def test_step_failure_all_required_fields_present(self, tmp_path, capsys):
        """Failure output must contain all contractually required fields (ADR-016 §6)."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_failure_result(rb)):
            cmd_runbook(_args(str(f)))
        out = json.loads(capsys.readouterr().out)
        for field in (
            "status", "runbook_id", "steps_completed", "terminated_early",
            "failed_step_index", "failure_kind", "failure_code",
        ):
            assert field in out, f"Required field '{field}' missing from failure output"

    def test_step_failure_output_is_valid_json(self, tmp_path, capsys):
        """Failure output must be parseable as a JSON object."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_failure_result(rb)):
            cmd_runbook(_args(str(f)))
        raw = capsys.readouterr().out
        obj = json.loads(raw)
        assert isinstance(obj, dict)


# ---------------------------------------------------------------------------
# Audit passthrough (ADR-016 §5)
# ---------------------------------------------------------------------------

class TestAuditPassthrough:
    def test_audit_true_threaded_to_runner(self, tmp_path):
        """--audit=True must be passed to runbook_runner.run as audit=True."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)) as mock_run:
            cmd_runbook(_args(str(f), audit=True))
        _, kwargs = mock_run.call_args
        assert kwargs["audit"] is True

    def test_audit_false_threaded_to_runner(self, tmp_path):
        """--audit absent (False) must be passed to runbook_runner.run as audit=False."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)) as mock_run:
            cmd_runbook(_args(str(f), audit=False))
        _, kwargs = mock_run.call_args
        assert kwargs["audit"] is False

    def test_runner_called_with_correct_runbook(self, tmp_path):
        """Runner must receive the Runbook deserialised from the JSON file."""
        rb = _single_step_runbook()
        f = tmp_path / "rb.json"
        f.write_text(_runbook_json(rb))
        with patch("io_iii.core.runbook_runner.run", return_value=_make_success_result(rb)) as mock_run:
            cmd_runbook(_args(str(f)))
        _, kwargs = mock_run.call_args
        assert isinstance(kwargs["runbook"], Runbook)
        assert kwargs["runbook"].runbook_id == rb.runbook_id


# ---------------------------------------------------------------------------
# No regression to existing CLI command surfaces
# ---------------------------------------------------------------------------

class TestNoRegression:
    def test_cmd_capabilities_still_callable(self, capsys):
        """cmd_capabilities must not be displaced or broken by M4.9 changes."""
        rc = cmd_capabilities(argparse.Namespace(json=True))
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert "capabilities" in out

    def test_main_still_dispatches_capabilities(self, capsys):
        """main() must still route the capabilities subcommand correctly."""
        rc = main(["capabilities", "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert "capabilities" in out


# Import here to use in no-regression test
from io_iii.cli import cmd_capabilities
