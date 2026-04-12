"""
tests/test_session_shell_m82_m83.py

Phase 8 M8.2 + M8.3 — Bounded session loop + Session shell CLI tests.

Governing ADR: ADR-024 — Work Mode / Steward Mode Contract.

Coverage:
  M8.2 — Bounded session loop (dialogue_session module):
    - new_session: defaults, session_mode override, max_turns from config
    - DialogueSession: fields, is_at_limit, is_active, is_paused
    - TurnRecord: frozen, content-safe fields
    - run_turn: at-limit raises, not-active raises, turn appended, gate evaluated,
                pause state fires in steward mode, work mode never pauses,
                turn count increments, session status transitions
    - save/load round-trip: content-safe JSON, schema version, all fields preserved
    - list_sessions: returns session IDs, empty when no sessions
    - session_status_summary: content-safe dict, no prompt/output content
    - _load_max_turns: default fallback, config override, invalid raises
    - _deserialise_session: missing fields raise, bad schema_version raises,
                            bad session_mode raises, bad status raises

  M8.3 — Session shell CLI:
    - session start: registered, produces session_id, initialises fields
    - session continue: registered, requires --session-id
    - session status: registered, requires --session-id
    - session close: registered, requires --session-id, marks closed
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from io_iii.core.dialogue_session import (
    DEFAULT_SESSION_STORAGE,
    DIALOGUE_SESSION_SCHEMA_VERSION,
    SESSION_MAX_TURNS,
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_AT_LIMIT,
    SESSION_STATUS_CLOSED,
    SESSION_STATUS_PAUSED,
    DialogueSession,
    DialogueTurnResult,
    TurnRecord,
    _deserialise_session,
    _load_max_turns,
    list_sessions,
    load_session,
    new_session,
    run_turn,
    save_session,
    session_status_summary,
)
from io_iii.core.session_mode import (
    PauseState,
    SessionMode,
    StewardGate,
    StewardThresholds,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _make_session(**kwargs) -> DialogueSession:
    defaults = dict(session_mode=SessionMode.WORK)
    defaults.update(kwargs)
    return new_session(**defaults)


def _make_gate(
    mode: SessionMode = SessionMode.WORK,
    step_count: int | None = None,
) -> StewardGate:
    return StewardGate(
        session_mode=mode,
        thresholds=StewardThresholds(step_count=step_count),
    )


def _fake_orch_result(request_id: str = "req-001", latency_ms: int = 42):
    """Return (mock_state, mock_result) as orchestrator.run() would."""
    from io_iii.core.session_state import SessionState
    from io_iii.core.engine import ExecutionResult
    state = SessionState(request_id=request_id, started_at_ms=1_000_000, latency_ms=latency_ms)
    result = ExecutionResult(
        message="ok",
        meta={},
        provider="null",
        model=None,
        prompt_hash="abc",
        audit_meta=None,
        route_id="executor",
    )
    return state, result


# ===========================================================================
# 1. new_session (M8.2)
# ===========================================================================

class TestNewSession:
    def test_defaults(self):
        s = new_session()
        assert s.session_mode is SessionMode.WORK
        assert s.turn_count == 0
        assert s.max_turns == SESSION_MAX_TURNS
        assert s.status == SESSION_STATUS_ACTIVE
        assert s.turns == []
        assert s.session_id  # non-empty

    def test_steward_mode(self):
        s = new_session(session_mode=SessionMode.STEWARD)
        assert s.session_mode is SessionMode.STEWARD

    def test_max_turns_override(self):
        s = new_session(max_turns=10)
        assert s.max_turns == 10

    def test_max_turns_from_runtime_config(self):
        s = new_session(runtime_config={"session_max_turns": 7})
        assert s.max_turns == 7

    def test_max_turns_config_ignored_when_explicit(self):
        s = new_session(max_turns=3, runtime_config={"session_max_turns": 99})
        assert s.max_turns == 3

    def test_unique_session_ids(self):
        ids = {new_session().session_id for _ in range(10)}
        assert len(ids) == 10

    def test_created_at_set(self):
        s = new_session()
        assert s.created_at.startswith("20")  # ISO timestamp

    def test_invalid_max_turns_from_config(self):
        with pytest.raises(ValueError, match="SESSION_MAX_TURNS_INVALID"):
            new_session(runtime_config={"session_max_turns": 0})


# ===========================================================================
# 2. DialogueSession state methods (M8.2)
# ===========================================================================

class TestDialogueSessionState:
    def test_is_at_limit_false_when_below(self):
        s = new_session(max_turns=5)
        assert not s.is_at_limit()

    def test_is_at_limit_true_when_equal(self):
        s = new_session(max_turns=2)
        s.turn_count = 2
        assert s.is_at_limit()

    def test_is_active(self):
        s = new_session()
        assert s.is_active()

    def test_is_paused_false_by_default(self):
        s = new_session()
        assert not s.is_paused()

    def test_is_paused_true_when_paused(self):
        s = new_session()
        s.status = SESSION_STATUS_PAUSED
        assert s.is_paused()


# ===========================================================================
# 3. TurnRecord (M8.2)
# ===========================================================================

class TestTurnRecord:
    def test_frozen(self):
        t = TurnRecord(
            turn_index=0, run_id="r1", status="ok",
            persona_mode="executor", latency_ms=100,
        )
        with pytest.raises(Exception):
            t.status = "error"  # type: ignore[misc]

    def test_content_safe_fields_only(self):
        t = TurnRecord(
            turn_index=2, run_id="r2", status="ok",
            persona_mode="explorer", latency_ms=50, error_code=None,
        )
        assert t.turn_index == 2
        assert t.run_id == "r2"
        assert t.persona_mode == "explorer"
        assert t.latency_ms == 50
        assert t.error_code is None


# ===========================================================================
# 4. run_turn (M8.2)
# ===========================================================================

class TestRunTurn:
    def _mock_orch(self, request_id="req-test", latency_ms=10):
        """Patch orchestrator.run to return a fake (state, result)."""
        state, result = _fake_orch_result(request_id=request_id, latency_ms=latency_ms)
        return patch(
            "io_iii.core.dialogue_session._orchestrator.run",
            return_value=(state, result),
        )

    def test_not_active_raises(self):
        s = new_session()
        s.status = SESSION_STATUS_CLOSED
        gate = _make_gate()
        deps = MagicMock()
        cfg = MagicMock()
        with pytest.raises(ValueError, match="SESSION_NOT_ACTIVE"):
            run_turn(
                session=s, user_prompt="hi", cfg=cfg, deps=deps, gate=gate,
            )

    def test_at_limit_raises_and_updates_status(self):
        s = new_session(max_turns=2)
        s.turn_count = 2
        gate = _make_gate()
        deps = MagicMock()
        cfg = MagicMock()
        with pytest.raises(ValueError, match="SESSION_AT_LIMIT"):
            run_turn(session=s, user_prompt="hi", cfg=cfg, deps=deps, gate=gate)
        assert s.status == SESSION_STATUS_AT_LIMIT

    def test_invalid_session_type_raises(self):
        gate = _make_gate()
        deps = MagicMock()
        with pytest.raises(TypeError):
            run_turn(
                session="not a session",  # type: ignore[arg-type]
                user_prompt="hi",
                cfg=MagicMock(),
                deps=deps,
                gate=gate,
            )

    def test_turn_appended_and_count_incremented(self):
        s = new_session()
        gate = _make_gate(SessionMode.WORK)
        deps = MagicMock()
        cfg = MagicMock()
        with self._mock_orch():
            result = run_turn(session=s, user_prompt="hello", cfg=cfg, deps=deps, gate=gate)
        assert result.session.turn_count == 1
        assert len(result.session.turns) == 1
        assert result.turn_record.turn_index == 0
        assert result.turn_record.status == "ok"

    def test_work_mode_no_pause(self):
        s = new_session(session_mode=SessionMode.WORK)
        gate = _make_gate(SessionMode.WORK, step_count=1)
        deps = MagicMock()
        cfg = MagicMock()
        with self._mock_orch():
            result = run_turn(session=s, user_prompt="hello", cfg=cfg, deps=deps, gate=gate)
        assert result.pause_state is None
        assert result.session.status == SESSION_STATUS_ACTIVE

    def test_steward_mode_threshold_fires_pause(self):
        s = new_session(session_mode=SessionMode.STEWARD)
        gate = _make_gate(SessionMode.STEWARD, step_count=1)  # fires at every step
        deps = MagicMock()
        cfg = MagicMock()
        with self._mock_orch():
            result = run_turn(session=s, user_prompt="hello", cfg=cfg, deps=deps, gate=gate)
        assert result.pause_state is not None
        assert result.pause_state.threshold_key == "step_count"
        assert result.session.status == SESSION_STATUS_PAUSED

    def test_steward_mode_no_threshold_no_pause(self):
        s = new_session(session_mode=SessionMode.STEWARD)
        gate = _make_gate(SessionMode.STEWARD, step_count=None)  # no thresholds
        deps = MagicMock()
        cfg = MagicMock()
        with self._mock_orch():
            result = run_turn(session=s, user_prompt="hi", cfg=cfg, deps=deps, gate=gate)
        assert result.pause_state is None
        assert result.session.status == SESSION_STATUS_ACTIVE

    def test_run_id_from_engine_state(self):
        s = new_session()
        gate = _make_gate()
        deps = MagicMock()
        cfg = MagicMock()
        with self._mock_orch(request_id="engine-run-id"):
            result = run_turn(session=s, user_prompt="x", cfg=cfg, deps=deps, gate=gate)
        assert result.turn_record.run_id == "engine-run-id"

    def test_second_turn_index(self):
        s = new_session()
        gate = _make_gate()
        deps = MagicMock()
        cfg = MagicMock()
        with self._mock_orch(request_id="r1"):
            run_turn(session=s, user_prompt="first", cfg=cfg, deps=deps, gate=gate)
        with self._mock_orch(request_id="r2"):
            result = run_turn(session=s, user_prompt="second", cfg=cfg, deps=deps, gate=gate)
        assert result.turn_record.turn_index == 1
        assert result.session.turn_count == 2

    def test_at_limit_after_last_turn(self):
        s = new_session(max_turns=1)
        gate = _make_gate()
        deps = MagicMock()
        cfg = MagicMock()
        with self._mock_orch():
            result = run_turn(session=s, user_prompt="only", cfg=cfg, deps=deps, gate=gate)
        assert result.session.status == SESSION_STATUS_AT_LIMIT


# ===========================================================================
# 5. Session persistence (M8.2)
# ===========================================================================

class TestSessionPersistence:
    def test_save_and_load_round_trip(self, tmp_path):
        s = new_session(session_mode=SessionMode.STEWARD, max_turns=5)
        path = save_session(s, tmp_path)
        assert path.exists()
        loaded = load_session(s.session_id, tmp_path)
        assert loaded.session_id == s.session_id
        assert loaded.session_mode is SessionMode.STEWARD
        assert loaded.max_turns == 5
        assert loaded.status == SESSION_STATUS_ACTIVE
        assert loaded.turn_count == 0

    def test_saved_json_no_prompt_content(self, tmp_path):
        s = new_session()
        path = save_session(s, tmp_path)
        data = json.loads(path.read_text())
        # No prompt, output, or model content
        assert "prompt" not in data
        assert "message" not in data
        assert "model" not in data

    def test_saved_json_has_schema_version(self, tmp_path):
        s = new_session()
        path = save_session(s, tmp_path)
        data = json.loads(path.read_text())
        assert data["schema_version"] == DIALOGUE_SESSION_SCHEMA_VERSION

    def test_saved_json_has_turns(self, tmp_path):
        s = new_session()
        s.turns.append(TurnRecord(
            turn_index=0, run_id="r1", status="ok",
            persona_mode="executor", latency_ms=50,
        ))
        s.turn_count = 1
        path = save_session(s, tmp_path)
        data = json.loads(path.read_text())
        assert len(data["turns"]) == 1
        assert data["turns"][0]["run_id"] == "r1"
        assert "prompt" not in data["turns"][0]

    def test_load_not_found_raises(self, tmp_path):
        with pytest.raises(ValueError, match="SESSION_NOT_FOUND"):
            load_session("nonexistent-id", tmp_path)

    def test_load_invalid_json_raises(self, tmp_path):
        p = tmp_path / "bad.session.json"
        p.write_text("not json")
        with pytest.raises(ValueError, match="SESSION_SCHEMA_INVALID"):
            load_session("bad", tmp_path)

    def test_list_sessions_empty(self, tmp_path):
        assert list_sessions(tmp_path) == []

    def test_list_sessions_nonexistent_dir(self, tmp_path):
        assert list_sessions(tmp_path / "does_not_exist") == []

    def test_list_sessions_returns_ids(self, tmp_path):
        s1 = new_session()
        s2 = new_session()
        save_session(s1, tmp_path)
        save_session(s2, tmp_path)
        ids = list_sessions(tmp_path)
        assert s1.session_id in ids
        assert s2.session_id in ids

    def test_load_preserves_turns(self, tmp_path):
        s = new_session()
        s.turns.append(TurnRecord(
            turn_index=0, run_id="run-42", status="ok",
            persona_mode="explorer", latency_ms=100,
        ))
        s.turn_count = 1
        save_session(s, tmp_path)
        loaded = load_session(s.session_id, tmp_path)
        assert len(loaded.turns) == 1
        assert loaded.turns[0].run_id == "run-42"
        assert loaded.turns[0].persona_mode == "explorer"


# ===========================================================================
# 6. _deserialise_session validation (M8.2)
# ===========================================================================

class TestDeserialiseSession:
    def _base(self) -> dict:
        return {
            "schema_version": DIALOGUE_SESSION_SCHEMA_VERSION,
            "session_id": "test-id",
            "session_mode": "work",
            "turn_count": 0,
            "max_turns": 50,
            "status": "active",
            "created_at": "2026-04-12T00:00:00Z",
            "updated_at": "2026-04-12T00:00:00Z",
            "turns": [],
        }

    def test_valid_deserialises(self):
        s = _deserialise_session(self._base())
        assert s.session_id == "test-id"
        assert s.session_mode is SessionMode.WORK

    def test_missing_field_raises(self):
        d = self._base()
        del d["session_id"]
        with pytest.raises(ValueError, match="SESSION_SCHEMA_INVALID"):
            _deserialise_session(d)

    def test_bad_schema_version_raises(self):
        d = self._base()
        d["schema_version"] = "v99"
        with pytest.raises(ValueError, match="SESSION_SCHEMA_INVALID"):
            _deserialise_session(d)

    def test_bad_session_mode_raises(self):
        d = self._base()
        d["session_mode"] = "autonomous"
        with pytest.raises(ValueError, match="SESSION_SCHEMA_INVALID"):
            _deserialise_session(d)

    def test_bad_status_raises(self):
        d = self._base()
        d["status"] = "running"
        with pytest.raises(ValueError, match="SESSION_SCHEMA_INVALID"):
            _deserialise_session(d)

    def test_not_dict_raises(self):
        with pytest.raises(ValueError, match="SESSION_SCHEMA_INVALID"):
            _deserialise_session(["not", "a", "dict"])

    def test_steward_mode_deserialised(self):
        d = self._base()
        d["session_mode"] = "steward"
        s = _deserialise_session(d)
        assert s.session_mode is SessionMode.STEWARD


# ===========================================================================
# 7. session_status_summary (M8.2 / content safety)
# ===========================================================================

class TestSessionStatusSummary:
    def test_content_safe_fields(self):
        s = new_session(max_turns=10)
        summary = session_status_summary(s)
        assert "session_id" in summary
        assert "session_mode" in summary
        assert "status" in summary
        assert "turn_count" in summary
        assert "max_turns" in summary
        assert "turns_remaining" in summary
        assert "created_at" in summary
        assert "updated_at" in summary

    def test_no_prompt_in_summary(self):
        s = new_session()
        summary = session_status_summary(s)
        assert "prompt" not in summary
        assert "message" not in summary
        assert "model" not in summary

    def test_turns_remaining_calculation(self):
        s = new_session(max_turns=5)
        s.turn_count = 3
        summary = session_status_summary(s)
        assert summary["turns_remaining"] == 2

    def test_turns_remaining_at_zero_when_at_limit(self):
        s = new_session(max_turns=3)
        s.turn_count = 3
        summary = session_status_summary(s)
        assert summary["turns_remaining"] == 0


# ===========================================================================
# 8. _load_max_turns (M8.2)
# ===========================================================================

class TestLoadMaxTurns:
    def test_absent_returns_default(self):
        assert _load_max_turns({}) == SESSION_MAX_TURNS

    def test_config_override(self):
        assert _load_max_turns({"session_max_turns": 20}) == 20

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="SESSION_MAX_TURNS_INVALID"):
            _load_max_turns({"session_max_turns": 0})

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="SESSION_MAX_TURNS_INVALID"):
            _load_max_turns({"session_max_turns": -5})

    def test_string_raises(self):
        with pytest.raises(ValueError, match="SESSION_MAX_TURNS_INVALID"):
            _load_max_turns({"session_max_turns": "fifty"})


# ===========================================================================
# 9. CLI registration (M8.3) — smoke tests on argument parser
# ===========================================================================

class TestSessionShellCLIRegistration:
    def _invoke(self, argv: list) -> int:
        from io_iii.cli import main
        try:
            return main(argv)
        except SystemExit as e:
            return int(e.code) if e.code is not None else 0

    def test_session_start_registered(self):
        # Parsing 'session start' should not raise SystemExit(2)
        # It will fail on config load — that's expected (not SystemExit 2)
        from io_iii.cli import main
        import argparse
        parser_ok = True
        try:
            main(["session", "start", "--help"])
        except SystemExit as e:
            # --help exits with 0
            assert e.code == 0
        assert parser_ok

    def test_session_continue_registered(self):
        from io_iii.cli import main
        try:
            main(["session", "continue", "--help"])
        except SystemExit as e:
            assert e.code == 0

    def test_session_status_registered(self):
        from io_iii.cli import main
        try:
            main(["session", "status", "--help"])
        except SystemExit as e:
            assert e.code == 0

    def test_session_close_registered(self):
        from io_iii.cli import main
        try:
            main(["session", "close", "--help"])
        except SystemExit as e:
            assert e.code == 0

    def test_session_start_initialises_session(self, tmp_path, capsys):
        """session start with no prompt creates and saves a session."""
        from io_iii.cli._session_shell import cmd_session_start

        fake_cfg = MagicMock()
        fake_cfg.runtime = {}

        with patch("io_iii.cli._session_shell.load_io3_config", return_value=fake_cfg), \
             patch("io_iii.cli._session_shell._session_storage", return_value=tmp_path):
            args = MagicMock()
            args.mode = "work"
            args.persona_mode = "executor"
            args.prompt = None
            args.config_dir = None
            ret = cmd_session_start(args)

        assert ret == 0
        sessions = list_sessions(tmp_path)
        assert len(sessions) == 1

    def test_session_close_marks_closed(self, tmp_path, capsys):
        """session close marks an existing session as closed."""
        from io_iii.cli._session_shell import cmd_session_close

        # Create a session to close
        s = new_session()
        save_session(s, tmp_path)

        fake_cfg = MagicMock()
        fake_cfg.runtime = {}

        with patch("io_iii.cli._session_shell.load_io3_config", return_value=fake_cfg), \
             patch("io_iii.cli._session_shell._session_storage", return_value=tmp_path):
            args = MagicMock()
            args.session_id = s.session_id
            args.config_dir = None
            ret = cmd_session_close(args)

        assert ret == 0
        reloaded = load_session(s.session_id, tmp_path)
        assert reloaded.status == SESSION_STATUS_CLOSED

    def test_session_status_returns_summary(self, tmp_path, capsys):
        """session status prints a content-safe summary."""
        from io_iii.cli._session_shell import cmd_session_status

        s = new_session(session_mode=SessionMode.STEWARD, max_turns=10)
        save_session(s, tmp_path)

        fake_cfg = MagicMock()
        fake_cfg.runtime = {}

        with patch("io_iii.cli._session_shell.load_io3_config", return_value=fake_cfg), \
             patch("io_iii.cli._session_shell._session_storage", return_value=tmp_path):
            args = MagicMock()
            args.session_id = s.session_id
            args.config_dir = None
            ret = cmd_session_status(args)

        assert ret == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["session_id"] == s.session_id
        assert data["session_mode"] == "steward"
        assert data["max_turns"] == 10

    def test_session_status_missing_id_returns_1(self, tmp_path, capsys):
        from io_iii.cli._session_shell import cmd_session_status

        fake_cfg = MagicMock()
        fake_cfg.runtime = {}

        with patch("io_iii.cli._session_shell.load_io3_config", return_value=fake_cfg), \
             patch("io_iii.cli._session_shell._session_storage", return_value=tmp_path):
            args = MagicMock()
            args.session_id = "nonexistent-000"
            args.config_dir = None
            ret = cmd_session_status(args)

        assert ret == 1
