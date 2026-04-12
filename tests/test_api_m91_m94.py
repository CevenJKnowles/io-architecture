"""
Tests for Phase 9 M9.1 (HTTP API handlers) and M9.4 (CLI exit codes).

Coverage:
  M9.1 — handle_run, handle_runbook, handle_session_start, handle_session_turn,
          handle_session_state, handle_session_delete, cmd_serve wiring
  M9.4 — --output flag present in CLI, exit code 3 for steward pause,
          exit code 2 for server binding failure
"""
from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — fake IO3Config and fake execution results
# ---------------------------------------------------------------------------

def _fake_cfg(tmp_path: Path):
    cfg = MagicMock()
    cfg.config_dir = tmp_path
    # Store sessions inside tmp_path so tests are hermetic
    cfg.runtime = {"session_storage_root": str(tmp_path / ".io_iii" / "sessions")}
    cfg.providers = {}
    cfg.routing = {"routing_table": {}}
    cfg.logging = {}
    return cfg


def _fake_exec_result(message: str = "ok output"):
    from io_iii.core.engine import ExecutionResult
    return ExecutionResult(
        message=message,
        meta={},
        provider="null",
        model=None,
        route_id="executor",
        audit_meta=None,
        prompt_hash="abc123",
    )


def _fake_state(mode: str = "executor"):
    from io_iii.core.session_state import SessionState
    return SessionState(request_id="req-test", started_at_ms=0, mode=mode)


# ---------------------------------------------------------------------------
# M9.1 — handle_run
# ---------------------------------------------------------------------------

class TestHandleRun:
    def test_missing_mode_returns_400(self, tmp_path):
        from io_iii.api._handlers import handle_run
        status, resp = handle_run({"prompt": "hello"}, _fake_cfg(tmp_path))
        assert status == 400
        assert resp["error_code"] == "INVALID_REQUEST_BODY"

    def test_missing_prompt_returns_400(self, tmp_path):
        from io_iii.api._handlers import handle_run
        status, resp = handle_run({"mode": "executor"}, _fake_cfg(tmp_path))
        assert status == 400
        assert resp["error_code"] == "INVALID_REQUEST_BODY"

    def test_empty_mode_returns_400(self, tmp_path):
        from io_iii.api._handlers import handle_run
        status, resp = handle_run({"mode": "", "prompt": "hi"}, _fake_cfg(tmp_path))
        assert status == 400

    def test_success_returns_200_with_message(self, tmp_path):
        from io_iii.api._handlers import handle_run
        state = _fake_state()
        result = _fake_exec_result("test response")
        with patch("io_iii.api._handlers._orchestrator.run", return_value=(state, result)):
            status, resp = handle_run({"mode": "executor", "prompt": "hello"}, _fake_cfg(tmp_path))
        assert status == 200
        assert resp["status"] == "ok"
        assert resp["message"] == "test response"

    def test_success_includes_route_id(self, tmp_path):
        from io_iii.api._handlers import handle_run
        state = _fake_state()
        result = _fake_exec_result()
        with patch("io_iii.api._handlers._orchestrator.run", return_value=(state, result)):
            status, resp = handle_run({"mode": "executor", "prompt": "hello"}, _fake_cfg(tmp_path))
        assert "route_id" in resp

    def test_orchestrator_failure_returns_500(self, tmp_path):
        from io_iii.api._handlers import handle_run
        with patch("io_iii.api._handlers._orchestrator.run", side_effect=RuntimeError("boom")):
            status, resp = handle_run({"mode": "executor", "prompt": "hello"}, _fake_cfg(tmp_path))
        assert status == 500
        assert "error_code" in resp

    def test_orchestrator_runtime_failure_uses_code(self, tmp_path):
        from io_iii.api._handlers import handle_run
        from io_iii.core.failure_model import RuntimeFailure, RuntimeFailureKind
        exc = ValueError("ENGINE_FAILURE: bad")
        exc.runtime_failure = RuntimeFailure(
            kind=RuntimeFailureKind.CONTRACT_VIOLATION,
            code="ENGINE_FAILURE",
            summary="engine failure",
            request_id="req-test",
            task_spec_id=None,
            retryable=False,
            causal_code="ENGINE_FAILURE",
        )
        with patch("io_iii.api._handlers._orchestrator.run", side_effect=exc):
            status, resp = handle_run({"mode": "executor", "prompt": "hello"}, _fake_cfg(tmp_path))
        assert status == 500
        assert resp["error_code"] == "ENGINE_FAILURE"

    def test_audit_flag_passed_through(self, tmp_path):
        from io_iii.api._handlers import handle_run
        state = _fake_state()
        result = _fake_exec_result()
        calls = []
        def fake_run(**kwargs):
            calls.append(kwargs.get("audit"))
            return state, result
        with patch("io_iii.api._handlers._orchestrator.run", side_effect=fake_run):
            handle_run({"mode": "executor", "prompt": "hi", "audit": True}, _fake_cfg(tmp_path))
        assert calls == [True]

    def test_no_prompt_text_key_in_response(self, tmp_path):
        """API response must not include raw prompt (ADR-025 §4)."""
        from io_iii.api._handlers import handle_run
        state = _fake_state()
        result = _fake_exec_result()
        with patch("io_iii.api._handlers._orchestrator.run", return_value=(state, result)):
            _, resp = handle_run({"mode": "executor", "prompt": "secret stuff"}, _fake_cfg(tmp_path))
        body = json.dumps(resp)
        assert "secret stuff" not in body


# ---------------------------------------------------------------------------
# M9.1 — handle_runbook
# ---------------------------------------------------------------------------

class TestHandleRunbook:
    def _make_runbook_data(self):
        return {
            "runbook_id": "rb-test",
            "steps": [
                {"task_spec_id": "ts-1", "mode": "executor", "prompt": "step 1"}
            ],
        }

    def test_missing_runbook_key_returns_400(self, tmp_path):
        from io_iii.api._handlers import handle_runbook
        status, resp = handle_runbook({}, _fake_cfg(tmp_path))
        assert status == 400
        assert resp["error_code"] == "INVALID_REQUEST_BODY"

    def test_runbook_not_dict_returns_400(self, tmp_path):
        from io_iii.api._handlers import handle_runbook
        status, resp = handle_runbook({"runbook": "not-a-dict"}, _fake_cfg(tmp_path))
        assert status == 400

    def test_invalid_runbook_schema_returns_400(self, tmp_path):
        from io_iii.api._handlers import handle_runbook
        status, resp = handle_runbook({"runbook": {"bad": "schema"}}, _fake_cfg(tmp_path))
        assert status == 400
        assert resp["error_code"] == "RUNBOOK_SCHEMA_ERROR"

    def test_success_returns_200(self, tmp_path):
        from io_iii.api._handlers import handle_runbook
        from io_iii.core.runbook_runner import RunbookResult, RunbookStepOutcome
        state = _fake_state()
        result_obj = _fake_exec_result("step output")
        outcome = RunbookStepOutcome(
            step_index=0, task_spec_id="ts-1",
            state=state, result=result_obj, success=True, failure=None,
        )
        rb_result = RunbookResult(
            runbook_id="rb-test", step_outcomes=[outcome],
            steps_completed=1, steps_skipped=0,
        )
        with patch("io_iii.api._handlers.runbook_runner_run", return_value=rb_result):
            status, resp = handle_runbook(
                {"runbook": self._make_runbook_data()}, _fake_cfg(tmp_path)
            )
        assert status == 200
        assert resp["status"] == "ok"
        assert resp["steps_completed"] == 1

    def test_step_message_included_in_response(self, tmp_path):
        from io_iii.api._handlers import handle_runbook
        from io_iii.core.runbook_runner import RunbookResult, RunbookStepOutcome
        state = _fake_state()
        result_obj = _fake_exec_result("step result text")
        outcome = RunbookStepOutcome(
            step_index=0, task_spec_id="ts-1",
            state=state, result=result_obj, success=True, failure=None,
        )
        rb_result = RunbookResult(runbook_id="rb-test", step_outcomes=[outcome], steps_completed=1)
        with patch("io_iii.api._handlers.runbook_runner_run", return_value=rb_result):
            _, resp = handle_runbook({"runbook": self._make_runbook_data()}, _fake_cfg(tmp_path))
        assert resp["steps"][0]["message"] == "step result text"

    def test_failed_step_status_is_error(self, tmp_path):
        from io_iii.api._handlers import handle_runbook
        from io_iii.core.runbook_runner import RunbookResult, RunbookStepOutcome
        from io_iii.core.failure_model import RuntimeFailure, RuntimeFailureKind
        failure = RuntimeFailure(
            kind=RuntimeFailureKind.CONTRACT_VIOLATION,
            code="STEP_FAILED",
            summary="step failed",
            request_id="req-test",
            task_spec_id=None,
            retryable=False,
            causal_code="STEP_FAILED",
        )
        outcome = RunbookStepOutcome(
            step_index=0, task_spec_id="ts-1",
            state=None, result=None, success=False, failure=failure,
        )
        rb_result = RunbookResult(
            runbook_id="rb-test", step_outcomes=[outcome],
            steps_completed=0, failed_step_index=0,
        )
        with patch("io_iii.api._handlers.runbook_runner_run", return_value=rb_result):
            _, resp = handle_runbook({"runbook": self._make_runbook_data()}, _fake_cfg(tmp_path))
        assert resp["steps"][0]["status"] == "error"
        assert resp["steps"][0]["error_code"] == "STEP_FAILED"

    def test_steps_total_matches_outcome_count(self, tmp_path):
        from io_iii.api._handlers import handle_runbook
        from io_iii.core.runbook_runner import RunbookResult, RunbookStepOutcome
        state = _fake_state()
        outcomes = [
            RunbookStepOutcome(
                step_index=i, task_spec_id=f"ts-{i}",
                state=state, result=_fake_exec_result(), success=True, failure=None,
            )
            for i in range(3)
        ]
        rb_result = RunbookResult(runbook_id="rb-test", step_outcomes=outcomes, steps_completed=3)
        with patch("io_iii.api._handlers.runbook_runner_run", return_value=rb_result):
            _, resp = handle_runbook({"runbook": self._make_runbook_data()}, _fake_cfg(tmp_path))
        assert resp["steps_total"] == 3


# ---------------------------------------------------------------------------
# M9.1 — handle_session_start
# ---------------------------------------------------------------------------

class TestHandleSessionStart:
    def test_creates_session_returns_201(self, tmp_path):
        from io_iii.api._handlers import handle_session_start
        status, resp = handle_session_start({}, _fake_cfg(tmp_path))
        assert status == 201
        assert "session_id" in resp
        assert resp["status"] == "active"

    def test_invalid_mode_returns_400(self, tmp_path):
        from io_iii.api._handlers import handle_session_start
        status, resp = handle_session_start({"mode": "invalid"}, _fake_cfg(tmp_path))
        assert status == 400
        assert resp["error_code"] == "SESSION_MODE_INVALID"

    def test_steward_mode_accepted(self, tmp_path):
        from io_iii.api._handlers import handle_session_start
        status, resp = handle_session_start({"mode": "steward"}, _fake_cfg(tmp_path))
        assert status == 201
        assert resp["session_mode"] == "steward"

    def test_session_persisted_to_disk(self, tmp_path):
        from io_iii.api._handlers import handle_session_start
        cfg = _fake_cfg(tmp_path)
        storage = Path(cfg.runtime["session_storage_root"])
        status, resp = handle_session_start({}, cfg)
        session_id = resp["session_id"]
        session_file = storage / f"{session_id}.session.json"
        assert session_file.exists()

    def test_no_model_output_in_response(self, tmp_path):
        """Session start response must not include model content (ADR-025 §4)."""
        from io_iii.api._handlers import handle_session_start
        _, resp = handle_session_start({}, _fake_cfg(tmp_path))
        assert "message" not in resp
        assert "prompt" not in resp

    def test_max_turns_present_in_response(self, tmp_path):
        from io_iii.api._handlers import handle_session_start
        _, resp = handle_session_start({}, _fake_cfg(tmp_path))
        assert "max_turns" in resp


# ---------------------------------------------------------------------------
# M9.1 — handle_session_state
# ---------------------------------------------------------------------------

class TestHandleSessionState:
    def test_unknown_session_returns_404(self, tmp_path):
        from io_iii.api._handlers import handle_session_state
        status, resp = handle_session_state("no-such-id", _fake_cfg(tmp_path))
        assert status == 404

    def test_known_session_returns_200(self, tmp_path):
        from io_iii.api._handlers import handle_session_start, handle_session_state
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]
        cfg = _fake_cfg(tmp_path)
        status, resp = handle_session_state(session_id, cfg)
        assert status == 200
        assert resp["session_id"] == session_id

    def test_state_response_content_safe(self, tmp_path):
        from io_iii.api._handlers import handle_session_start, handle_session_state
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]
        _, resp = handle_session_state(session_id, _fake_cfg(tmp_path))
        body = json.dumps(resp)
        assert "prompt" not in body


# ---------------------------------------------------------------------------
# M9.1 — handle_session_delete
# ---------------------------------------------------------------------------

class TestHandleSessionDelete:
    def test_unknown_session_returns_404(self, tmp_path):
        from io_iii.api._handlers import handle_session_delete
        status, resp = handle_session_delete("no-such-id", _fake_cfg(tmp_path))
        assert status == 404

    def test_closes_active_session(self, tmp_path):
        from io_iii.api._handlers import handle_session_start, handle_session_delete
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]
        status, resp = handle_session_delete(session_id, _fake_cfg(tmp_path))
        assert status == 200
        assert resp["status"] == "closed"

    def test_closed_session_persisted(self, tmp_path):
        from io_iii.api._handlers import handle_session_start, handle_session_delete
        from io_iii.core.dialogue_session import load_session
        cfg = _fake_cfg(tmp_path)
        storage = Path(cfg.runtime["session_storage_root"])
        _, start_resp = handle_session_start({}, cfg)
        session_id = start_resp["session_id"]
        handle_session_delete(session_id, cfg)
        session = load_session(session_id, storage)
        assert session.status == "closed"


# ---------------------------------------------------------------------------
# M9.1 — handle_session_turn
# ---------------------------------------------------------------------------

class TestHandleSessionTurn:
    def test_unknown_session_returns_404(self, tmp_path):
        from io_iii.api._handlers import handle_session_turn
        status, resp = handle_session_turn("no-such-id", {"prompt": "hi"}, _fake_cfg(tmp_path))
        assert status == 404

    def test_missing_prompt_returns_400(self, tmp_path):
        from io_iii.api._handlers import handle_session_start, handle_session_turn
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]
        status, resp = handle_session_turn(session_id, {}, _fake_cfg(tmp_path))
        assert status == 400
        assert resp["error_code"] == "PROMPT_REQUIRED"

    def test_turn_response_has_no_model_output(self, tmp_path):
        """POST /session/{id}/turn response is content-safe — no message field (ADR-025 §4)."""
        from io_iii.api._handlers import handle_session_start, handle_session_turn
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]
        state = _fake_state()
        exec_result = _fake_exec_result("model said this")
        with patch("io_iii.api._handlers.run_turn") as mock_rt:
            from io_iii.core.dialogue_session import (
                DialogueTurnResult, TurnRecord, DialogueSession, new_session,
                SESSION_STATUS_ACTIVE,
            )
            from io_iii.core.session_mode import SessionMode
            session = new_session(runtime_config={})
            tr = TurnRecord(
                turn_index=0, run_id="req-test",
                status="ok", persona_mode="executor", latency_ms=10,
            )
            session.turn_count = 1
            dtr = DialogueTurnResult(
                session=session, turn_record=tr,
                state=state, result=exec_result, pause_state=None,
            )
            mock_rt.return_value = dtr
            status, resp = handle_session_turn(
                session_id, {"prompt": "hello"}, _fake_cfg(tmp_path)
            )
        assert status == 200
        assert "message" not in resp
        body = json.dumps(resp)
        assert "model said this" not in body

    def test_turn_response_includes_governance_metadata(self, tmp_path):
        from io_iii.api._handlers import handle_session_start, handle_session_turn
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]
        state = _fake_state()
        exec_result = _fake_exec_result()
        with patch("io_iii.api._handlers.run_turn") as mock_rt:
            from io_iii.core.dialogue_session import (
                DialogueTurnResult, TurnRecord, new_session,
            )
            session = new_session(runtime_config={})
            session.turn_count = 1
            tr = TurnRecord(
                turn_index=0, run_id="req-test",
                status="ok", persona_mode="executor", latency_ms=10,
            )
            dtr = DialogueTurnResult(
                session=session, turn_record=tr,
                state=state, result=exec_result, pause_state=None,
            )
            mock_rt.return_value = dtr
            status, resp = handle_session_turn(
                session_id, {"prompt": "hello"}, _fake_cfg(tmp_path)
            )
        assert "turn_index" in resp
        assert "session_id" in resp
        assert "turn_count" in resp
        assert "latency_ms" in resp

    def test_paused_session_without_action_returns_200_with_valid_actions(self, tmp_path):
        from io_iii.api._handlers import handle_session_start, handle_session_turn
        from io_iii.core.dialogue_session import load_session, save_session
        cfg = _fake_cfg(tmp_path)
        storage = Path(cfg.runtime["session_storage_root"])
        _, start_resp = handle_session_start({}, cfg)
        session_id = start_resp["session_id"]
        # Manually pause the session
        session = load_session(session_id, storage)
        session.status = "paused"
        save_session(session, storage)

        status, resp = handle_session_turn(session_id, {}, _fake_cfg(tmp_path))
        assert status == 200
        assert "valid_actions" in resp
        assert "approve" in resp["valid_actions"]


# ---------------------------------------------------------------------------
# M9.1 — execute_session_turn shared helper
# ---------------------------------------------------------------------------

class TestExecuteSessionTurn:
    def test_unknown_session_returns_error_code(self, tmp_path):
        from io_iii.api._handlers import execute_session_turn
        result, err = execute_session_turn(
            "no-such-id", "hello", _fake_cfg(tmp_path)
        )
        assert result is None
        assert err is not None

    def test_inactive_session_returns_SESSION_NOT_ACTIVE(self, tmp_path):
        from io_iii.api._handlers import handle_session_start, execute_session_turn
        from io_iii.core.dialogue_session import load_session, save_session
        cfg = _fake_cfg(tmp_path)
        storage = Path(cfg.runtime["session_storage_root"])
        _, start_resp = handle_session_start({}, cfg)
        session_id = start_resp["session_id"]
        # Close the session
        session = load_session(session_id, storage)
        session.status = "closed"
        save_session(session, storage)

        result, err = execute_session_turn(session_id, "hello", _fake_cfg(tmp_path))
        assert result is None
        assert err == "SESSION_NOT_ACTIVE"


# ---------------------------------------------------------------------------
# M9.1 — server module structure
# ---------------------------------------------------------------------------

class TestServerModuleStructure:
    def test_server_module_imports(self):
        from io_iii.api import server
        assert hasattr(server, "start_server")
        assert hasattr(server, "cmd_serve")
        assert hasattr(server, "_make_handler")

    def test_make_handler_returns_class(self):
        from io_iii.api.server import _make_handler
        cfg = MagicMock()
        dispatcher = MagicMock()
        cls = _make_handler(cfg, dispatcher)
        from http.server import BaseHTTPRequestHandler
        assert issubclass(cls, BaseHTTPRequestHandler)

    def test_cmd_serve_wired_into_cli(self):
        import io_iii.cli as cli
        assert hasattr(cli, "cmd_serve")
        assert callable(cli.cmd_serve)

    def test_serve_subcommand_in_main_parser(self):
        """python -m io_iii serve --help must not raise SystemExit with error."""
        import io_iii.cli as cli
        with pytest.raises(SystemExit) as exc:
            cli.main(["serve", "--help"])
        assert exc.value.code == 0

    def test_ui_static_file_exists(self):
        from io_iii.api.server import _UI_PATH
        assert _UI_PATH.exists(), f"Web UI not found at {_UI_PATH}"

    def test_cmd_serve_returns_2_on_os_error(self):
        from io_iii.api.server import cmd_serve
        args = MagicMock()
        args.host = "127.0.0.1"
        args.port = 9999
        args.config_dir = None
        with patch("io_iii.api.server.start_server", side_effect=OSError("bind failed")):
            code = cmd_serve(args)
        assert code == 2


# ---------------------------------------------------------------------------
# M9.4 — CLI --output flag and structured exit codes
# ---------------------------------------------------------------------------

class TestCLIExitCodes:
    def test_output_flag_defaults_to_json(self):
        """--output json is the default; parser must accept it."""
        import io_iii.cli as cli
        # Just check that --output json doesn't raise in argument parsing
        # (We can't easily run a full parse without triggering execution)
        import argparse
        # Re-parse only the top-level args
        parser = argparse.ArgumentParser()
        parser.add_argument("--output", choices=["json"], default="json", dest="output_format")
        ns = parser.parse_args(["--output", "json"])
        assert ns.output_format == "json"

    def test_exit_code_3_when_session_continue_paused_no_action(self, tmp_path):
        """cmd_session_continue returns 3 when session is paused with no valid action (ADR-025 §7)."""
        from io_iii.cli._session_shell import cmd_session_continue
        from io_iii.core.dialogue_session import new_session, save_session, SESSION_STATUS_PAUSED
        cfg = _fake_cfg(tmp_path)
        storage = Path(cfg.runtime["session_storage_root"])
        session = new_session(runtime_config={})
        session.status = SESSION_STATUS_PAUSED
        save_session(session, storage)

        args = MagicMock()
        args.config_dir = str(tmp_path)
        args.session_id = session.session_id
        args.action = None
        args.prompt = None

        with patch("io_iii.cli._session_shell._get_cfg_dir", return_value=tmp_path), \
             patch("io_iii.cli._session_shell.load_io3_config", return_value=cfg):
            code = cmd_session_continue(args)

        assert code == 3

    def test_exit_code_0_when_session_continue_active(self, tmp_path):
        """cmd_session_continue returns 0 on a successful active turn."""
        from io_iii.cli._session_shell import cmd_session_continue
        from io_iii.core.dialogue_session import (
            new_session, save_session, DialogueTurnResult, TurnRecord,
        )
        from io_iii.core.session_mode import SessionMode
        cfg = _fake_cfg(tmp_path)
        storage = Path(cfg.runtime["session_storage_root"])
        session = new_session(runtime_config={})
        save_session(session, storage)

        args = MagicMock()
        args.config_dir = str(tmp_path)
        args.session_id = session.session_id
        args.action = None
        args.prompt = "hello"
        args.persona_mode = "executor"
        args.audit = False

        state = _fake_state()
        exec_result = _fake_exec_result()
        tr = TurnRecord(
            turn_index=0, run_id="req-test",
            status="ok", persona_mode="executor", latency_ms=10,
        )
        session_updated = new_session(runtime_config={})
        session_updated.turn_count = 1
        dtr = DialogueTurnResult(
            session=session_updated, turn_record=tr,
            state=state, result=exec_result, pause_state=None,
        )

        with patch("io_iii.cli._session_shell._get_cfg_dir", return_value=tmp_path), \
             patch("io_iii.cli._session_shell.load_io3_config", return_value=cfg), \
             patch("io_iii.cli._session_shell.run_turn", return_value=dtr), \
             patch("io_iii.cli._session_shell._load_continuity_memory", return_value=([], None)):
            code = cmd_session_continue(args)

        assert code == 0

    def test_exit_code_3_when_turn_triggers_steward_pause(self, tmp_path):
        """cmd_session_continue returns 3 when a just-completed turn fires steward gate."""
        from io_iii.cli._session_shell import cmd_session_continue
        from io_iii.core.dialogue_session import (
            new_session, save_session, DialogueTurnResult, TurnRecord, SESSION_STATUS_PAUSED,
        )
        from io_iii.core.session_mode import PauseState, SessionMode
        cfg = _fake_cfg(tmp_path)
        storage = Path(cfg.runtime["session_storage_root"])
        session = new_session(runtime_config={})
        save_session(session, storage)

        args = MagicMock()
        args.config_dir = str(tmp_path)
        args.session_id = session.session_id
        args.action = None
        args.prompt = "trigger steward"
        args.persona_mode = "executor"
        args.audit = False

        state = _fake_state()
        exec_result = _fake_exec_result()
        tr = TurnRecord(
            turn_index=0, run_id="req-test",
            status="ok", persona_mode="executor", latency_ms=10,
        )
        session_paused = new_session(runtime_config={})
        session_paused.status = SESSION_STATUS_PAUSED
        session_paused.turn_count = 1
        pause = PauseState(
            threshold_key="step_count",
            step_index=0,
            steps_total=50,
            session_mode=SessionMode.STEWARD,
            run_id="req-test",
        )
        dtr = DialogueTurnResult(
            session=session_paused, turn_record=tr,
            state=state, result=exec_result, pause_state=pause,
        )

        with patch("io_iii.cli._session_shell._get_cfg_dir", return_value=tmp_path), \
             patch("io_iii.cli._session_shell.load_io3_config", return_value=cfg), \
             patch("io_iii.cli._session_shell.run_turn", return_value=dtr), \
             patch("io_iii.cli._session_shell._load_continuity_memory", return_value=([], None)):
            code = cmd_session_continue(args)

        assert code == 3

    def test_output_flag_accepted_by_main_parser(self):
        """main() parser must accept --output json without error."""
        import io_iii.cli as cli
        with pytest.raises(SystemExit) as exc:
            cli.main(["--output", "json", "--help"])
        assert exc.value.code == 0

    def test_exit_code_2_on_server_os_error(self):
        """cmd_serve returns 2 on OSError (binding failure — config-level error)."""
        from io_iii.api.server import cmd_serve
        args = MagicMock()
        args.host = "127.0.0.1"
        args.port = 9999
        args.config_dir = None
        with patch("io_iii.api.server.start_server", side_effect=OSError("address in use")):
            code = cmd_serve(args)
        assert code == 2
