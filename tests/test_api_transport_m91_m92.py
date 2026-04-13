"""
tests/test_api_transport_m91_m92.py

Phase 9 M9.1 + M9.2 — HTTP API transport adapter + SSE streaming.

Governing ADR: ADR-025 — API-as-Transport-Adapter Contract.

Coverage:
  M9.1 — HTTP API routes:
    - POST /run → cmd_run (transport-adapter pattern)
    - POST /runbook → cmd_runbook
    - POST /session/start → cmd_session_start
    - POST /session/{id}/turn → cmd_session_continue
    - GET  /session/{id}/state → cmd_session_status
    - DELETE /session/{id} → cmd_session_close
    - GET  /health → liveness probe (no exec)

  M9.2 — SSE event stream:
    - GET /session/{id}/stream → yields session_state on connect
    - Event bus publish/get_events_since round-trip

  Content-safety (ADR-025 §1 + ADR-003):
    - 'message' field stripped from all API responses
    - 'prompt' field stripped from all API responses
    - 'logging_policy' stripped

  Transport-adapter rule (ADR-025 §1):
    - Every route captures stdout from the corresponding cmd_* function
    - No new execution semantics introduced in the API layer

  M9.4 — --output json flag:
    - Flag accepted on run, runbook, session start/continue/status/close
    - Behaviour unchanged (already JSON; flag is a contract declaration)

  M9.5 — Web UI:
    - GET / returns HTML
    - GET / returns 200 with text/html content-type
"""
from __future__ import annotations

import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from io_iii.api.app import app, _strip_content
from io_iii.api import _bus as bus


# ---------------------------------------------------------------------------
# Test client
# ---------------------------------------------------------------------------

client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cmd_ok(payload: dict):
    """Return a function that prints JSON and returns 0 (simulates cmd_*)."""
    def _cmd(args):
        print(json.dumps(payload))
        return 0
    return _cmd


def _make_cmd_err(payload: dict):
    """Return a function that prints JSON and returns 1 (simulates cmd_* error)."""
    def _cmd(args):
        print(json.dumps(payload))
        return 1
    return _cmd


# ===========================================================================
# 1. POST /run (M9.1)
# ===========================================================================

class TestRunRoute:
    def test_run_ok(self):
        """POST /run wraps cmd_run; returns 200 with structured output."""
        payload = {
            "result": {"meta": {}, "mode": "executor", "provider": "null",
                       "model": None, "route_id": "executor"},
            "audit_meta": None,
            "message": "CONTENT_UNSAFE_SHOULD_BE_STRIPPED",
        }
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_run = _make_cmd_ok(payload)
            resp = client.post("/run", json={"mode": "executor"})
        assert resp.status_code == 200
        body = resp.json()
        # Content-safe: 'message' must not appear in response
        assert "message" not in body
        assert "result" in body

    def test_run_error_returns_422(self):
        """POST /run returns 422 when cmd_run exits with code 1."""
        err_payload = {"status": "error", "error_code": "PROVIDER_UNAVAILABLE"}
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_run = _make_cmd_err(err_payload)
            resp = client.post("/run", json={"mode": "executor"})
        assert resp.status_code == 422
        body = resp.json()
        assert body.get("error_code") == "PROVIDER_UNAVAILABLE"

    def test_run_passes_mode(self):
        """The mode from the request body is forwarded to cmd_run via Namespace."""
        received = {}
        def _cmd(args):
            received["mode"] = args.mode
            print(json.dumps({"status": "ok"}))
            return 0
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_run = _cmd
            client.post("/run", json={"mode": "research"})
        assert received["mode"] == "research"

    def test_run_passes_optional_fields(self):
        """Optional fields (audit, no_health_check, etc.) are forwarded."""
        received = {}
        def _cmd(args):
            received.update(vars(args))
            print(json.dumps({"status": "ok"}))
            return 0
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_run = _cmd
            client.post("/run", json={
                "mode": "executor",
                "audit": True,
                "no_health_check": True,
                "no_constellation_check": True,
            })
        assert received["audit"] is True
        assert received["no_health_check"] is True
        assert received["no_constellation_check"] is True


# ===========================================================================
# 2. POST /runbook (M9.1)
# ===========================================================================

class TestRunbookRoute:
    def test_runbook_ok(self):
        payload = {
            "status": "ok",
            "runbook_id": "rb-001",
            "steps_completed": 2,
        }
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_runbook = _make_cmd_ok(payload)
            resp = client.post("/runbook", json={"json_file": "/tmp/fake.json"})
        assert resp.status_code == 200
        assert resp.json()["runbook_id"] == "rb-001"

    def test_runbook_passes_json_file(self):
        received = {}
        def _cmd(args):
            received["json_file"] = args.json_file
            print(json.dumps({"status": "ok"}))
            return 0
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_runbook = _cmd
            client.post("/runbook", json={"json_file": "/path/to/rb.json"})
        assert received["json_file"] == "/path/to/rb.json"

    def test_runbook_fires_webhook(self):
        """POST /runbook dispatches RUNBOOK_COMPLETE webhook (M9.3)."""
        payload = {"status": "ok", "runbook_id": "rb-x", "steps_completed": 1}
        dispatched = []
        with patch("io_iii.api.app._cli") as m, \
             patch("io_iii.api.app.webhooks.dispatch") as mock_dispatch, \
             patch("io_iii.api.app._runtime_cfg", return_value={"webhook_url": "http://hook"}):
            m.return_value.cmd_runbook = _make_cmd_ok(payload)
            mock_dispatch.side_effect = lambda url, evt, pl: dispatched.append((evt, pl))
            client.post("/runbook", json={"json_file": "/f.json"})
        assert any(e == "RUNBOOK_COMPLETE" for e, _ in dispatched)


# ===========================================================================
# 3. POST /session/start (M9.1)
# ===========================================================================

class TestSessionStartRoute:
    def test_start_ok(self):
        payload = {
            "session_id": "ses-abc",
            "session_mode": "work",
            "status": "active",
            "turn_count": 0,
            "max_turns": 20,
        }
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_session_start = _make_cmd_ok(payload)
            resp = client.post("/session/start", json={"mode": "work"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "ses-abc"

    def test_start_publishes_bus_event(self):
        """session_state event is published to the event bus on start."""
        sid = "ses-bus-test"
        payload = {"session_id": sid, "status": "active", "turn_count": 0, "session_mode": "work"}
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_session_start = _make_cmd_ok(payload)
            client.post("/session/start", json={"mode": "work"})
        events = bus.get_events_since(sid, 0)
        assert len(events) >= 1
        assert events[0]["event"] == "session_state"

    def test_start_error(self):
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_session_start = _make_cmd_err({"status": "error"})
            resp = client.post("/session/start", json={"mode": "bad"})
        assert resp.status_code == 422


# ===========================================================================
# 4. POST /session/{id}/turn (M9.1)
# ===========================================================================

class TestSessionTurnRoute:
    def test_turn_ok(self):
        payload = {
            "session_id": "ses-t",
            "turn_index": 0,
            "status": "ok",
            "session_status": "active",
            "turn_count": 1,
            "latency_ms": 55,
        }
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_session_continue = _make_cmd_ok(payload)
            resp = client.post("/session/ses-t/turn", json={"prompt": "hello"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["turn_index"] == 0

    def test_turn_publishes_events(self):
        """turn_started and turn_completed events are published to bus."""
        sid = "ses-turn-events"
        payload = {
            "session_id": sid, "turn_index": 0,
            "status": "ok", "session_status": "active", "turn_count": 1,
        }
        # Clear any prior events for this session
        bus.clear(sid)
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_session_continue = _make_cmd_ok(payload)
            client.post(f"/session/{sid}/turn", json={"prompt": "p"})
        events = bus.get_events_since(sid, 0)
        event_types = [e["event"] for e in events]
        assert "turn_started" in event_types
        assert "turn_completed" in event_types

    def test_turn_steward_gate_publishes_event(self):
        """steward_gate_triggered event published when session_status = paused."""
        sid = "ses-paused"
        bus.clear(sid)
        payload = {
            "session_id": sid, "turn_index": 0,
            "status": "ok", "session_status": "paused", "turn_count": 1,
            "pause": {"threshold_key": "step_count", "step_index": 0, "steps_total": 1},
        }
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_session_continue = _make_cmd_ok(payload)
            client.post(f"/session/{sid}/turn", json={"prompt": "p"})
        events = bus.get_events_since(sid, 0)
        event_types = [e["event"] for e in events]
        assert "steward_gate_triggered" in event_types

    def test_turn_session_close_fires_webhook(self):
        """SESSION_COMPLETE webhook fires when session reaches closed/at_limit."""
        sid = "ses-done"
        bus.clear(sid)
        payload = {
            "session_id": sid, "turn_index": 5,
            "status": "ok", "session_status": "at_limit", "turn_count": 20,
        }
        dispatched = []
        with patch("io_iii.api.app._cli") as m, \
             patch("io_iii.api.app.webhooks.dispatch") as mock_d, \
             patch("io_iii.api.app._runtime_cfg", return_value={"webhook_url": "http://hook"}):
            m.return_value.cmd_session_continue = _make_cmd_ok(payload)
            mock_d.side_effect = lambda url, evt, pl: dispatched.append(evt)
            client.post(f"/session/{sid}/turn", json={"prompt": "last"})
        assert "SESSION_COMPLETE" in dispatched

    def test_turn_passes_session_id(self):
        received = {}
        def _cmd(args):
            received["session_id"] = args.session_id
            print(json.dumps({"status": "ok", "session_status": "active"}))
            return 0
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_session_continue = _cmd
            client.post("/session/MY-SES-ID/turn", json={"prompt": "x"})
        assert received["session_id"] == "MY-SES-ID"


# ===========================================================================
# 5. GET /session/{id}/state (M9.1)
# ===========================================================================

class TestSessionStateRoute:
    def test_state_ok(self):
        payload = {
            "session_id": "ses-s",
            "status": "active",
            "turn_count": 3,
            "max_turns": 20,
        }
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_session_status = _make_cmd_ok(payload)
            resp = client.get("/session/ses-s/state")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "ses-s"

    def test_state_not_found(self):
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_session_status = _make_cmd_err(
                {"status": "error", "error_code": "SESSION_NOT_FOUND"}
            )
            resp = client.get("/session/no-such/state")
        assert resp.status_code == 422


# ===========================================================================
# 6. DELETE /session/{id} (M9.1)
# ===========================================================================

class TestSessionCloseRoute:
    def test_close_ok(self):
        payload = {"session_id": "ses-cl", "status": "closed", "turn_count": 2}
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_session_close = _make_cmd_ok(payload)
            resp = client.delete("/session/ses-cl")
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"

    def test_close_publishes_session_closed_event(self):
        sid = "ses-cl-event"
        bus.clear(sid)
        payload = {"session_id": sid, "status": "closed", "turn_count": 1}
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_session_close = _make_cmd_ok(payload)
            client.delete(f"/session/{sid}")
        events = bus.get_events_since(sid, 0)
        assert any(e["event"] == "session_closed" for e in events)

    def test_close_fires_webhook(self):
        sid = "ses-cl-wh"
        bus.clear(sid)
        payload = {"session_id": sid, "status": "closed", "turn_count": 1}
        dispatched = []
        with patch("io_iii.api.app._cli") as m, \
             patch("io_iii.api.app.webhooks.dispatch") as mock_d, \
             patch("io_iii.api.app._runtime_cfg", return_value={"webhook_url": "http://hook"}):
            m.return_value.cmd_session_close = _make_cmd_ok(payload)
            mock_d.side_effect = lambda url, evt, pl: dispatched.append(evt)
            client.delete(f"/session/{sid}")
        assert "SESSION_COMPLETE" in dispatched


# ===========================================================================
# 7. GET /health (M9.1)
# ===========================================================================

class TestHealthRoute:
    def test_health_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["runtime"] == "io-iii"

    def test_health_no_exec(self):
        """Health endpoint must not call any CLI command."""
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_run = MagicMock(side_effect=Exception("must not run"))
            resp = client.get("/health")
        assert resp.status_code == 200


# ===========================================================================
# 8. GET /session/{id}/stream — SSE (M9.2)
# ===========================================================================

class TestSSEStream:
    """
    SSE stream tests.

    Each test pre-publishes a STREAM_CLOSE_EVENT sentinel so the async generator
    terminates after its first poll (1 s sleep).  The poll interval is patched to
    near-zero to keep tests fast.
    """

    def _run_sse(self, sid, state_payload, extra_events=None):
        """
        Shared helper: set up bus, run SSE request, return raw bytes.
        Patches _SSE_POLL_INTERVAL to 0 so the first sleep is instant.
        """
        bus.clear(sid)
        if extra_events:
            for evt_type, evt_data in extra_events:
                bus.publish(sid, evt_type, evt_data)
        bus.close_stream(sid)

        with patch("io_iii.api.app._cli") as m, \
             patch("io_iii.api.app._SSE_POLL_INTERVAL", 0):
            m.return_value.cmd_session_status = _make_cmd_ok(state_payload)
            with client.stream("GET", f"/session/{sid}/stream") as resp:
                return resp, b"".join(resp.iter_raw())

    def test_stream_returns_streaming_response(self):
        """GET /session/{id}/stream returns StreamingResponse (text/event-stream)."""
        sid = "ses-sse-resp"
        state_payload = {"session_id": sid, "status": "active", "turn_count": 0}
        resp, chunks = self._run_sse(sid, state_payload)
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        # session_state event is emitted before the poll loop starts
        assert b"session_state" in chunks

    def test_stream_headers_no_cache(self):
        """SSE stream sets Cache-Control: no-cache."""
        sid = "ses-sse-hdr"
        resp, _ = self._run_sse(sid, {"session_id": sid, "status": "active"})
        assert resp.headers.get("cache-control", "").lower() == "no-cache"

    def test_stream_emits_queued_bus_events(self):
        """Events published before connecting are served to the SSE client."""
        sid = "ses-sse-bus"
        state_payload = {"session_id": sid, "status": "closed"}
        extra = [
            ("turn_completed", {"turn_index": 0}),
            ("session_closed", {"session_status": "closed"}),
        ]
        _, chunks = self._run_sse(sid, state_payload, extra_events=extra)
        assert b"turn_completed" in chunks
        assert b"session_closed" in chunks

    def test_stream_close_sentinel_not_emitted(self):
        """The __stream_close__ sentinel event is never emitted to the client."""
        sid = "ses-sse-sentinel"
        state_payload = {"session_id": sid, "status": "active"}
        extra = [("turn_completed", {"turn_index": 0})]
        _, chunks = self._run_sse(sid, state_payload, extra_events=extra)
        # Sentinel must never appear in the SSE output
        assert b"__stream_close__" not in chunks


# ===========================================================================
# 9. Event bus — _bus module (M9.2)
# ===========================================================================

class TestEventBus:
    def test_publish_and_get(self):
        sid = "bus-test-1"
        bus.clear(sid)
        bus.publish(sid, "turn_completed", {"turn_index": 0})
        events = bus.get_events_since(sid, 0)
        assert len(events) == 1
        assert events[0]["event"] == "turn_completed"
        assert events[0]["data"]["turn_index"] == 0

    def test_cursor_based_read(self):
        sid = "bus-test-2"
        bus.clear(sid)
        bus.publish(sid, "turn_started", {})
        bus.publish(sid, "turn_completed", {"turn_index": 0})
        bus.publish(sid, "session_closed", {})
        # Read from cursor=1 — should skip first event
        events = bus.get_events_since(sid, 1)
        assert len(events) == 2
        assert events[0]["event"] == "turn_completed"
        assert events[1]["event"] == "session_closed"

    def test_unknown_session_returns_empty(self):
        events = bus.get_events_since("no-such-session", 0)
        assert events == []

    def test_clear_removes_events(self):
        sid = "bus-test-clear"
        bus.publish(sid, "turn_completed", {})
        bus.clear(sid)
        assert bus.get_events_since(sid, 0) == []

    def test_publish_is_thread_safe(self):
        """Concurrent publishes do not corrupt the event log."""
        import threading
        sid = "bus-thread-safe"
        bus.clear(sid)
        threads = [
            threading.Thread(target=bus.publish, args=(sid, "ev", {"i": i}))
            for i in range(50)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        events = bus.get_events_since(sid, 0)
        assert len(events) == 50


# ===========================================================================
# 10. Content-safety (ADR-003 / ADR-025 §1)
# ===========================================================================

class TestContentSafety:
    def test_strip_content_removes_message(self):
        obj = {"session_id": "x", "message": "MODEL OUTPUT", "result": {"model": "llama"}}
        stripped = _strip_content(obj)
        assert "message" not in stripped
        assert stripped["session_id"] == "x"

    def test_strip_content_removes_prompt(self):
        obj = {"status": "ok", "prompt": "USER INPUT", "mode": "executor"}
        stripped = _strip_content(obj)
        assert "prompt" not in stripped
        assert stripped["mode"] == "executor"

    def test_strip_content_removes_logging_policy(self):
        obj = {"status": "ok", "logging_policy": {"path": "/logs"}}
        stripped = _strip_content(obj)
        assert "logging_policy" not in stripped

    def test_strip_content_nested(self):
        obj = {"result": {"message": "SECRET", "mode": "x"}, "ok": True}
        stripped = _strip_content(obj)
        assert "message" not in stripped["result"]
        assert stripped["result"]["mode"] == "x"

    def test_strip_content_list(self):
        obj = [{"message": "A"}, {"message": "B", "id": 1}]
        stripped = _strip_content(obj)
        for item in stripped:
            assert "message" not in item

    def test_run_response_strips_message(self):
        """POST /run response never contains 'message' even if cmd_run outputs it."""
        payload = {
            "result": {"message": "model says hello", "mode": "executor"},
            "message": "top-level message",
        }
        with patch("io_iii.api.app._cli") as m:
            m.return_value.cmd_run = _make_cmd_ok(payload)
            resp = client.post("/run", json={"mode": "executor"})
        body = resp.json()
        assert "message" not in body
        assert "message" not in body.get("result", {})


# ===========================================================================
# 11. Web UI (M9.5)
# ===========================================================================

class TestWebUI:
    def test_get_root_returns_html(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_ui_contains_io_iii_branding(self):
        resp = client.get("/")
        assert "IO-III" in resp.text

    def test_ui_references_session_start_endpoint(self):
        """UI must use the /session/start API endpoint (not bypass it)."""
        resp = client.get("/")
        assert "/session/start" in resp.text

    def test_ui_references_session_turn_endpoint(self):
        """UI must reference the session turn endpoint."""
        resp = client.get("/")
        assert "/turn" in resp.text

    def test_ui_no_prompt_in_html(self):
        """Static HTML must not embed any prompt or model output content."""
        resp = client.get("/")
        # The HTML itself may contain the word 'prompt' as a UI label — that's fine.
        # Ensure no hardcoded model output or content-plane data.
        body = resp.text
        assert "MODEL OUTPUT" not in body
        assert "USER_PROMPT_VALUE" not in body


# ===========================================================================
# 12. CLI --output json flag (M9.4)
# ===========================================================================

class TestCLIOutputJsonFlag:
    """Verify --output json is accepted without altering existing behaviour."""

    def _run_cli(self, argv):
        import io
        import contextlib
        import io_iii.cli as cli_mod
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                rc = cli_mod.main(argv)
            except SystemExit as e:
                rc = e.code
        return rc, buf.getvalue()

    def test_run_accepts_output_json(self):
        """python -m io_iii run executor --output json --no-health-check parses without error."""
        # We just want argparse to accept the flag; mock the actual execution.
        with patch("io_iii.cli.cmd_run") as mock_cmd:
            mock_cmd.return_value = 0
            rc, _ = self._run_cli(
                ["run", "executor", "--output", "json",
                 "--no-health-check", "--no-constellation-check"]
            )
        mock_cmd.assert_called_once()
        args = mock_cmd.call_args[0][0]
        assert args.output == "json"

    def test_runbook_accepts_output_json(self):
        with patch("io_iii.cli.cmd_runbook") as mock_cmd:
            mock_cmd.return_value = 0
            rc, _ = self._run_cli(["runbook", "/tmp/rb.json", "--output", "json"])
        mock_cmd.assert_called_once()
        assert mock_cmd.call_args[0][0].output == "json"

    def test_session_start_accepts_output_json(self):
        with patch("io_iii.cli.cmd_session_start") as mock_cmd:
            mock_cmd.return_value = 0
            rc, _ = self._run_cli(["session", "start", "--output", "json"])
        mock_cmd.assert_called_once()
        assert mock_cmd.call_args[0][0].output == "json"

    def test_session_continue_accepts_output_json(self):
        with patch("io_iii.cli.cmd_session_continue") as mock_cmd:
            mock_cmd.return_value = 0
            rc, _ = self._run_cli([
                "session", "continue",
                "--session-id", "ses-x",
                "--output", "json",
            ])
        mock_cmd.assert_called_once()
        assert mock_cmd.call_args[0][0].output == "json"

    def test_session_status_accepts_output_json(self):
        with patch("io_iii.cli.cmd_session_status") as mock_cmd:
            mock_cmd.return_value = 0
            rc, _ = self._run_cli([
                "session", "status", "--session-id", "ses-x", "--output", "json"
            ])
        mock_cmd.assert_called_once()
        assert mock_cmd.call_args[0][0].output == "json"

    def test_session_close_accepts_output_json(self):
        with patch("io_iii.cli.cmd_session_close") as mock_cmd:
            mock_cmd.return_value = 0
            rc, _ = self._run_cli([
                "session", "close", "--session-id", "ses-x", "--output", "json"
            ])
        mock_cmd.assert_called_once()
        assert mock_cmd.call_args[0][0].output == "json"

    def test_output_default_is_json(self):
        """--output defaults to 'json' even when not specified."""
        with patch("io_iii.cli.cmd_session_status") as mock_cmd:
            mock_cmd.return_value = 0
            self._run_cli(["session", "status", "--session-id", "ses-x"])
        assert mock_cmd.call_args[0][0].output == "json"


# ===========================================================================
# 13. CLI serve command (M9.1 / ADR-025 §7)
# ===========================================================================

class TestCLIServeCommand:
    def test_serve_registered(self):
        """'serve' subcommand is registered in the CLI parser."""
        import io
        import contextlib
        import io_iii.cli as cli_mod

        with patch("io_iii.cli.cmd_serve") as mock_serve:
            mock_serve.return_value = 0
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cli_mod.main(["serve", "--host", "127.0.0.1", "--port", "9999"])
        mock_serve.assert_called_once()
        args = mock_serve.call_args[0][0]
        assert args.host == "127.0.0.1"
        assert args.port == 9999

    def test_serve_default_host_port(self):
        import io_iii.cli as cli_mod
        with patch("io_iii.cli.cmd_serve") as mock_serve:
            mock_serve.return_value = 0
            cli_mod.main(["serve"])
        args = mock_serve.call_args[0][0]
        assert args.host == "0.0.0.0"
        assert args.port == 8080
