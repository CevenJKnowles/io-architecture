"""
Tests for Phase 9 M9.2 (SSE streaming) and M9.3 (webhooks).

Coverage:
  M9.2 — format_sse, _SSE_SESSION_EVENTS taxonomy, stream_session_turn
          (event sequence, content-safety, error path, pause path)
  M9.3 — WebhookDispatcher construction, dispatch logic, content-safety,
          event taxonomy, failure handling, from_runtime_config
"""
from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_cfg(tmp_path):
    cfg = MagicMock()
    cfg.config_dir = tmp_path
    cfg.runtime = {"session_storage_root": str(tmp_path / ".io_iii" / "sessions")}
    cfg.providers = {}
    return cfg


def _fake_exec_result(message: str = "assistant reply"):
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


def _make_dtr(*, message="reply", paused=False):
    from io_iii.core.dialogue_session import (
        DialogueTurnResult, TurnRecord, new_session, SESSION_STATUS_PAUSED,
    )
    from io_iii.core.session_mode import PauseState, SessionMode
    state = _fake_state()
    result = _fake_exec_result(message)
    session = new_session(runtime_config={})
    session.turn_count = 1
    if paused:
        session.status = SESSION_STATUS_PAUSED
    tr = TurnRecord(
        turn_index=0, run_id="req-test",
        status="ok", persona_mode="executor", latency_ms=10,
    )
    pause = None
    if paused:
        pause = PauseState(
            threshold_key="step_count",
            step_index=0,
            steps_total=50,
            session_mode=SessionMode.STEWARD,
            run_id="req-test",
        )
    return DialogueTurnResult(
        session=session, turn_record=tr,
        state=state, result=result, pause_state=pause,
    )


# ---------------------------------------------------------------------------
# M9.2 — format_sse
# ---------------------------------------------------------------------------

class TestFormatSSE:
    def test_returns_bytes(self):
        from io_iii.api._sse import format_sse
        result = format_sse("turn_started", {"session_id": "abc"})
        assert isinstance(result, bytes)

    def test_contains_event_name(self):
        from io_iii.api._sse import format_sse
        result = format_sse("turn_started", {"x": 1}).decode("utf-8")
        assert "event: turn_started" in result

    def test_contains_data_line(self):
        from io_iii.api._sse import format_sse
        result = format_sse("turn_completed", {"y": 2}).decode("utf-8")
        assert "data: " in result

    def test_data_is_valid_json(self):
        from io_iii.api._sse import format_sse
        raw = format_sse("turn_output", {"output": "hello"}).decode("utf-8")
        data_line = [l for l in raw.splitlines() if l.startswith("data: ")][0]
        payload = json.loads(data_line[len("data: "):])
        assert payload["output"] == "hello"

    def test_ends_with_double_newline(self):
        from io_iii.api._sse import format_sse
        raw = format_sse("turn_started", {}).decode("utf-8")
        assert raw.endswith("\n\n")

    def test_different_events_produce_different_headers(self):
        from io_iii.api._sse import format_sse
        a = format_sse("turn_started", {}).decode()
        b = format_sse("turn_completed", {}).decode()
        assert "turn_started" in a
        assert "turn_completed" in b
        assert "turn_started" not in b


# ---------------------------------------------------------------------------
# M9.2 — _SSE_SESSION_EVENTS taxonomy
# ---------------------------------------------------------------------------

class TestSSEEventTaxonomy:
    def test_taxonomy_is_frozenset(self):
        from io_iii.api._sse import _SSE_SESSION_EVENTS
        assert isinstance(_SSE_SESSION_EVENTS, frozenset)

    def test_taxonomy_has_exactly_five_events(self):
        from io_iii.api._sse import _SSE_SESSION_EVENTS
        assert len(_SSE_SESSION_EVENTS) == 5

    def test_required_events_present(self):
        from io_iii.api._sse import _SSE_SESSION_EVENTS
        required = {
            "turn_started",
            "turn_output",
            "turn_completed",
            "steward_gate_triggered",
            "turn_error",
        }
        assert _SSE_SESSION_EVENTS == required

    def test_taxonomy_is_immutable(self):
        from io_iii.api._sse import _SSE_SESSION_EVENTS
        with pytest.raises((AttributeError, TypeError)):
            _SSE_SESSION_EVENTS.add("new_event")


# ---------------------------------------------------------------------------
# M9.2 — stream_session_turn
# ---------------------------------------------------------------------------

class TestStreamSessionTurn:
    def _collect_events(self, raw: bytes) -> list[dict]:
        """Parse SSE bytes into list of {event, data} dicts."""
        events = []
        current = {}
        for line in raw.decode("utf-8").splitlines():
            if line.startswith("event: "):
                current["event"] = line[len("event: "):]
            elif line.startswith("data: "):
                current["data"] = json.loads(line[len("data: "):])
            elif line == "" and current:
                events.append(current)
                current = {}
        if current:
            events.append(current)
        return events

    def test_emits_turn_started_first(self, tmp_path):
        from io_iii.api._sse import stream_session_turn
        from io_iii.api._handlers import handle_session_start
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]

        buf = io.BytesIO()
        dtr = _make_dtr()
        with patch("io_iii.api._sse.execute_session_turn", return_value=(dtr, None)):
            stream_session_turn(session_id, "hello", _fake_cfg(tmp_path), buf)

        events = self._collect_events(buf.getvalue())
        assert events[0]["event"] == "turn_started"

    def test_emits_turn_output_with_model_text(self, tmp_path):
        from io_iii.api._sse import stream_session_turn
        from io_iii.api._handlers import handle_session_start
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]

        buf = io.BytesIO()
        dtr = _make_dtr(message="the model answer")
        with patch("io_iii.api._sse.execute_session_turn", return_value=(dtr, None)):
            stream_session_turn(session_id, "hello", _fake_cfg(tmp_path), buf)

        events = self._collect_events(buf.getvalue())
        output_events = [e for e in events if e["event"] == "turn_output"]
        assert len(output_events) == 1
        assert output_events[0]["data"]["output"] == "the model answer"

    def test_emits_turn_completed_on_success(self, tmp_path):
        from io_iii.api._sse import stream_session_turn
        from io_iii.api._handlers import handle_session_start
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]

        buf = io.BytesIO()
        dtr = _make_dtr()
        with patch("io_iii.api._sse.execute_session_turn", return_value=(dtr, None)):
            stream_session_turn(session_id, "hello", _fake_cfg(tmp_path), buf)

        events = self._collect_events(buf.getvalue())
        names = [e["event"] for e in events]
        assert "turn_completed" in names

    def test_emits_steward_gate_triggered_on_pause(self, tmp_path):
        from io_iii.api._sse import stream_session_turn
        from io_iii.api._handlers import handle_session_start
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]

        buf = io.BytesIO()
        dtr = _make_dtr(paused=True)
        with patch("io_iii.api._sse.execute_session_turn", return_value=(dtr, None)):
            stream_session_turn(session_id, "hello", _fake_cfg(tmp_path), buf)

        events = self._collect_events(buf.getvalue())
        names = [e["event"] for e in events]
        assert "steward_gate_triggered" in names
        assert "turn_completed" not in names

    def test_emits_turn_error_on_failure(self, tmp_path):
        from io_iii.api._sse import stream_session_turn

        buf = io.BytesIO()
        with patch("io_iii.api._sse.execute_session_turn", return_value=(None, "SESSION_NOT_FOUND")):
            stream_session_turn("no-such-id", "hello", _fake_cfg(tmp_path), buf)

        events = self._collect_events(buf.getvalue())
        names = [e["event"] for e in events]
        assert "turn_error" in names
        error_events = [e for e in events if e["event"] == "turn_error"]
        assert error_events[0]["data"]["error_code"] == "SESSION_NOT_FOUND"

    def test_event_sequence_on_success(self, tmp_path):
        """Sequence must be: turn_started → turn_output → turn_completed."""
        from io_iii.api._sse import stream_session_turn
        from io_iii.api._handlers import handle_session_start
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]

        buf = io.BytesIO()
        dtr = _make_dtr()
        with patch("io_iii.api._sse.execute_session_turn", return_value=(dtr, None)):
            stream_session_turn(session_id, "hello", _fake_cfg(tmp_path), buf)

        names = [e["event"] for e in self._collect_events(buf.getvalue())]
        assert names == ["turn_started", "turn_output", "turn_completed"]

    def test_turn_started_content_safe(self, tmp_path):
        """turn_started must not include prompt text (ADR-025 §5)."""
        from io_iii.api._sse import stream_session_turn
        from io_iii.api._handlers import handle_session_start
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]

        buf = io.BytesIO()
        dtr = _make_dtr()
        with patch("io_iii.api._sse.execute_session_turn", return_value=(dtr, None)):
            stream_session_turn(session_id, "my secret prompt", _fake_cfg(tmp_path), buf)

        raw = buf.getvalue().decode()
        # started event must not contain prompt text
        events = [e for e in self._collect_events(buf.getvalue()) if e["event"] == "turn_started"]
        event_str = json.dumps(events[0]["data"])
        assert "my secret prompt" not in event_str

    def test_turn_completed_content_safe(self, tmp_path):
        """turn_completed data must not include model output (ADR-025 §5)."""
        from io_iii.api._sse import stream_session_turn
        from io_iii.api._handlers import handle_session_start
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]

        buf = io.BytesIO()
        dtr = _make_dtr(message="secret model output")
        with patch("io_iii.api._sse.execute_session_turn", return_value=(dtr, None)):
            stream_session_turn(session_id, "hello", _fake_cfg(tmp_path), buf)

        events = [e for e in self._collect_events(buf.getvalue()) if e["event"] == "turn_completed"]
        completed_str = json.dumps(events[0]["data"])
        assert "secret model output" not in completed_str

    def test_no_prompt_text_in_non_output_events(self, tmp_path):
        from io_iii.api._sse import stream_session_turn
        from io_iii.api._handlers import handle_session_start
        _, start_resp = handle_session_start({}, _fake_cfg(tmp_path))
        session_id = start_resp["session_id"]

        buf = io.BytesIO()
        dtr = _make_dtr()
        with patch("io_iii.api._sse.execute_session_turn", return_value=(dtr, None)):
            stream_session_turn(session_id, "CANARY_PROMPT", _fake_cfg(tmp_path), buf)

        all_events = self._collect_events(buf.getvalue())
        non_output = [e for e in all_events if e["event"] != "turn_output"]
        for evt in non_output:
            assert "CANARY_PROMPT" not in json.dumps(evt["data"])


# ---------------------------------------------------------------------------
# M9.3 — WebhookDispatcher construction
# ---------------------------------------------------------------------------

class TestWebhookDispatcherConstruction:
    def test_empty_config_is_safe_default(self):
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher({})
        assert not d.is_configured("session_complete")

    def test_from_runtime_config_absent_key(self):
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher.from_runtime_config({})
        assert not d.is_configured("session_complete")

    def test_from_runtime_config_with_webhooks_block(self):
        from io_iii.api._webhooks import WebhookDispatcher
        cfg = {"webhooks": {"session_complete": {"url": "http://localhost:9999/hook"}}}
        d = WebhookDispatcher.from_runtime_config(cfg)
        assert d.is_configured("session_complete")

    def test_is_configured_false_for_absent_event(self):
        from io_iii.api._webhooks import WebhookDispatcher
        cfg = {"webhooks": {"session_complete": {"url": "http://localhost:9999/hook"}}}
        d = WebhookDispatcher.from_runtime_config(cfg)
        assert not d.is_configured("runbook_complete")

    def test_non_dict_webhooks_block_is_safe(self):
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher.from_runtime_config({"webhooks": "not-a-dict"})
        assert not d.is_configured("session_complete")


# ---------------------------------------------------------------------------
# M9.3 — WebhookDispatcher event taxonomy
# ---------------------------------------------------------------------------

class TestWebhookEventTaxonomy:
    def test_taxonomy_is_frozenset(self):
        from io_iii.api._webhooks import _WEBHOOK_EVENTS
        assert isinstance(_WEBHOOK_EVENTS, frozenset)

    def test_taxonomy_has_exactly_three_events(self):
        from io_iii.api._webhooks import _WEBHOOK_EVENTS
        assert len(_WEBHOOK_EVENTS) == 3

    def test_required_events_present(self):
        from io_iii.api._webhooks import _WEBHOOK_EVENTS
        required = {
            "session_complete",
            "runbook_complete",
            "steward_gate_triggered",
        }
        assert _WEBHOOK_EVENTS == required

    def test_constants_match_taxonomy(self):
        from io_iii.api._webhooks import (
            _WEBHOOK_EVENTS,
            WEBHOOK_SESSION_COMPLETE,
            WEBHOOK_RUNBOOK_COMPLETE,
            WEBHOOK_STEWARD_GATE_TRIGGERED,
        )
        assert WEBHOOK_SESSION_COMPLETE in _WEBHOOK_EVENTS
        assert WEBHOOK_RUNBOOK_COMPLETE in _WEBHOOK_EVENTS
        assert WEBHOOK_STEWARD_GATE_TRIGGERED in _WEBHOOK_EVENTS


# ---------------------------------------------------------------------------
# M9.3 — WebhookDispatcher.dispatch
# ---------------------------------------------------------------------------

class TestWebhookDispatch:
    def test_unknown_event_is_no_op(self):
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher({"unknown_event": {"url": "http://localhost:9999/hook"}})
        # Must not raise; just silently skip unknown events
        d.dispatch("unknown_event", {"x": 1})

    def test_absent_event_config_is_no_op(self):
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher({})
        d.dispatch("session_complete", {"session_id": "abc"})  # no-op, no raise

    def test_dispatch_calls_urlopen(self):
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher({"session_complete": {"url": "http://localhost:9999/hook"}})
        with patch("io_iii.api._webhooks.urllib.request.urlopen") as mock_open:
            d.dispatch("session_complete", {"session_id": "abc"})
        mock_open.assert_called_once()

    def test_dispatch_sends_json_body(self):
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher({"session_complete": {"url": "http://localhost:9999/hook"}})
        sent_data = {}
        def capture_request(req, timeout=None):
            sent_data["data"] = req.data
            return MagicMock()
        with patch("io_iii.api._webhooks.urllib.request.urlopen", side_effect=capture_request):
            d.dispatch("session_complete", {"session_id": "xyz", "turn_count": 3})
        body = json.loads(sent_data["data"].decode("utf-8"))
        assert body["session_id"] == "xyz"

    def test_dispatch_uses_x_io3_event_header(self):
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher({"session_complete": {"url": "http://localhost:9999/hook"}})
        captured = {}
        def capture_request(req, timeout=None):
            captured["headers"] = req.headers
            return MagicMock()
        with patch("io_iii.api._webhooks.urllib.request.urlopen", side_effect=capture_request):
            d.dispatch("session_complete", {"session_id": "abc"})
        # Headers dict keys are lowercased by urllib
        assert "x-io3-event" in {k.lower() for k in captured["headers"]}

    def test_delivery_failure_is_silent(self):
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher({"session_complete": {"url": "http://localhost:9999/hook"}})
        with patch("io_iii.api._webhooks.urllib.request.urlopen",
                   side_effect=Exception("connection refused")):
            d.dispatch("session_complete", {"session_id": "abc"})
        # Must not raise — best-effort delivery (ADR-025 §6)

    def test_dispatch_payload_is_content_safe(self):
        """Webhook payload must not contain model output or prompt text (ADR-025 §6)."""
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher({"session_complete": {"url": "http://localhost:9999/hook"}})
        sent_data = {}
        def capture_request(req, timeout=None):
            sent_data["data"] = req.data
            return MagicMock()
        # Payload must be content-safe — pass only structural metadata
        payload = {"session_id": "abc", "turn_count": 5}
        with patch("io_iii.api._webhooks.urllib.request.urlopen", side_effect=capture_request):
            d.dispatch("session_complete", payload)
        body = json.loads(sent_data["data"].decode())
        # Structural fields only
        assert "session_id" in body
        assert "turn_count" in body

    def test_missing_url_is_no_op(self):
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher({"session_complete": {}})  # no url key
        with patch("io_iii.api._webhooks.urllib.request.urlopen") as mock_open:
            d.dispatch("session_complete", {"session_id": "abc"})
        mock_open.assert_not_called()

    def test_dispatch_uses_configured_timeout(self):
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher({
            "session_complete": {"url": "http://localhost:9999/hook", "timeout_seconds": 10}
        })
        captured = {}
        def capture_request(req, timeout=None):
            captured["timeout"] = timeout
            return MagicMock()
        with patch("io_iii.api._webhooks.urllib.request.urlopen", side_effect=capture_request):
            d.dispatch("session_complete", {"session_id": "abc"})
        assert captured["timeout"] == 10

    def test_default_timeout_is_five(self):
        from io_iii.api._webhooks import WebhookDispatcher
        d = WebhookDispatcher({"session_complete": {"url": "http://localhost:9999/hook"}})
        captured = {}
        def capture_request(req, timeout=None):
            captured["timeout"] = timeout
            return MagicMock()
        with patch("io_iii.api._webhooks.urllib.request.urlopen", side_effect=capture_request):
            d.dispatch("session_complete", {"session_id": "abc"})
        assert captured["timeout"] == 5

    def test_runbook_complete_dispatches(self):
        from io_iii.api._webhooks import WebhookDispatcher, WEBHOOK_RUNBOOK_COMPLETE
        d = WebhookDispatcher({"runbook_complete": {"url": "http://localhost:9999/hook"}})
        with patch("io_iii.api._webhooks.urllib.request.urlopen") as mock_open:
            d.dispatch(WEBHOOK_RUNBOOK_COMPLETE, {"runbook_id": "rb-1"})
        mock_open.assert_called_once()

    def test_steward_gate_triggered_dispatches(self):
        from io_iii.api._webhooks import WebhookDispatcher, WEBHOOK_STEWARD_GATE_TRIGGERED
        d = WebhookDispatcher({
            "steward_gate_triggered": {"url": "http://localhost:9999/hook"}
        })
        with patch("io_iii.api._webhooks.urllib.request.urlopen") as mock_open:
            d.dispatch(WEBHOOK_STEWARD_GATE_TRIGGERED, {
                "session_id": "abc",
                "threshold_key": "step_count",
            })
        mock_open.assert_called_once()
