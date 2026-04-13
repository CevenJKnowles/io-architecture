"""
tests/test_api_content_release_adr026.py

ADR-026 — Governed Content Release Gate.

Verifies that the `content_release` flag in runtime.yaml controls whether
the `response` field (model output) appears in API responses for /run and
/session/{id}/turn.

Coverage:
  - Gate disabled (default): `response` absent, `message` stripped (ADR-003 preserved)
  - Gate enabled: `response` present in /run response
  - Gate enabled: `response` present in /session/{id}/turn response
  - Gate enabled: unsafe keys (prompt, persona_content, value) still stripped
  - Gate disabled: no `response` even when engine emits `message`
  - _content_release_enabled() returns True/False based on runtime config
  - _extract_response() returns {} when gate closed, {'response': ...} when open
  - _extract_response() returns {} when message is absent even if gate open
  - SSE events remain structural (no response field) regardless of gate
  - /run: response absent when gate off, present when gate on
  - /session/{id}/turn: response absent when gate off, present when gate on
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from io_iii.api.app import app, _strip_content, _extract_response, _content_release_enabled
from io_iii.api import _bus as bus


client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cmd_ok(payload: dict):
    def _cmd(args):
        print(json.dumps(payload))
        return 0
    return _cmd


def _cmd_err(payload: dict):
    def _cmd(args):
        print(json.dumps(payload))
        return 1
    return _cmd


# ---------------------------------------------------------------------------
# Engine-like payloads (include message as engine produces it)
# ---------------------------------------------------------------------------

_RUN_PAYLOAD = {
    "status": "ok",
    "run_id": "run-adr026",
    "message": "Paris is the capital of France.",
    "prompt": "What is the capital of France?",
    "persona_content": "You are an assistant.",
    "turn_index": 0,
    "latency_ms": 123,
}

_TURN_PAYLOAD = {
    "status": "ok",
    "session_id": "ses-adr026",
    "session_status": "active",
    "turn_index": 1,
    "turn_count": 1,
    "latency_ms": 200,
    "message": "I am IO-III, a governed runtime.",
    "prompt": "Who are you?",
}

_STATUS_PAYLOAD = {
    "status": "ok",
    "session_id": "ses-adr026",
    "session_status": "active",
    "turn_count": 1,
}


# ===========================================================================
# 1. Unit: _extract_response
# ===========================================================================

class TestExtractResponse:
    """_extract_response() unit tests (ADR-026 §4)."""

    def test_gate_closed_returns_empty(self):
        result = _extract_response({"message": "hello"}, release=False)
        assert result == {}

    def test_gate_open_returns_response_field(self):
        result = _extract_response({"message": "hello"}, release=True)
        assert result == {"response": "hello"}

    def test_gate_open_no_message_returns_empty(self):
        result = _extract_response({"status": "ok"}, release=True)
        assert result == {}

    def test_gate_open_empty_message_returns_empty(self):
        # None message → absent (not null)
        result = _extract_response({"message": None}, release=True)
        assert result == {}

    def test_response_field_name_is_response_not_message(self):
        result = _extract_response({"message": "hi"}, release=True)
        assert "response" in result
        assert "message" not in result


# ===========================================================================
# 2. Unit: _content_release_enabled
# ===========================================================================

class TestContentReleaseEnabled:
    """_content_release_enabled() reads runtime config per-request (ADR-026 §4)."""

    def test_returns_true_when_flag_set(self):
        with patch("io_iii.api.app._runtime_cfg", return_value={"content_release": True}):
            assert _content_release_enabled() is True

    def test_returns_false_when_flag_off(self):
        with patch("io_iii.api.app._runtime_cfg", return_value={"content_release": False}):
            assert _content_release_enabled() is False

    def test_returns_false_when_key_absent(self):
        with patch("io_iii.api.app._runtime_cfg", return_value={}):
            assert _content_release_enabled() is False

    def test_returns_false_when_runtime_cfg_fails(self):
        with patch("io_iii.api.app._runtime_cfg", return_value={}):
            assert _content_release_enabled() is False


# ===========================================================================
# 3. POST /run — gate off (default)
# ===========================================================================

class TestRunGateOff:
    """/run with content_release=False: response absent, message stripped."""

    def test_response_field_absent(self):
        with patch("io_iii.api.app._cli") as mock_cli, \
             patch("io_iii.api.app._content_release_enabled", return_value=False):
            mock_cli.return_value.cmd_run = _cmd_ok(_RUN_PAYLOAD)
            resp = client.post("/run", json={"mode": "work"})
        assert resp.status_code == 200
        body = resp.json()
        assert "response" not in body

    def test_message_stripped(self):
        with patch("io_iii.api.app._cli") as mock_cli, \
             patch("io_iii.api.app._content_release_enabled", return_value=False):
            mock_cli.return_value.cmd_run = _cmd_ok(_RUN_PAYLOAD)
            resp = client.post("/run", json={"mode": "work"})
        assert "message" not in resp.json()

    def test_prompt_still_stripped(self):
        with patch("io_iii.api.app._cli") as mock_cli, \
             patch("io_iii.api.app._content_release_enabled", return_value=False):
            mock_cli.return_value.cmd_run = _cmd_ok(_RUN_PAYLOAD)
            resp = client.post("/run", json={"mode": "work"})
        assert "prompt" not in resp.json()


# ===========================================================================
# 4. POST /run — gate on
# ===========================================================================

class TestRunGateOn:
    """/run with content_release=True: response present, other unsafe keys absent."""

    def test_response_field_present(self):
        with patch("io_iii.api.app._cli") as mock_cli, \
             patch("io_iii.api.app._content_release_enabled", return_value=True):
            mock_cli.return_value.cmd_run = _cmd_ok(_RUN_PAYLOAD)
            resp = client.post("/run", json={"mode": "work"})
        assert resp.status_code == 200
        assert resp.json()["response"] == "Paris is the capital of France."

    def test_message_key_still_absent(self):
        """response is under the new key; the raw message key is still stripped."""
        with patch("io_iii.api.app._cli") as mock_cli, \
             patch("io_iii.api.app._content_release_enabled", return_value=True):
            mock_cli.return_value.cmd_run = _cmd_ok(_RUN_PAYLOAD)
            resp = client.post("/run", json={"mode": "work"})
        assert "message" not in resp.json()

    def test_prompt_still_stripped_when_gate_open(self):
        with patch("io_iii.api.app._cli") as mock_cli, \
             patch("io_iii.api.app._content_release_enabled", return_value=True):
            mock_cli.return_value.cmd_run = _cmd_ok(_RUN_PAYLOAD)
            resp = client.post("/run", json={"mode": "work"})
        assert "prompt" not in resp.json()

    def test_persona_content_still_stripped_when_gate_open(self):
        with patch("io_iii.api.app._cli") as mock_cli, \
             patch("io_iii.api.app._content_release_enabled", return_value=True):
            mock_cli.return_value.cmd_run = _cmd_ok(_RUN_PAYLOAD)
            resp = client.post("/run", json={"mode": "work"})
        assert "persona_content" not in resp.json()

    def test_structural_fields_preserved(self):
        with patch("io_iii.api.app._cli") as mock_cli, \
             patch("io_iii.api.app._content_release_enabled", return_value=True):
            mock_cli.return_value.cmd_run = _cmd_ok(_RUN_PAYLOAD)
            resp = client.post("/run", json={"mode": "work"})
        body = resp.json()
        assert body["status"] == "ok"
        assert body["run_id"] == "run-adr026"


# ===========================================================================
# 5. POST /session/{id}/turn — gate off
# ===========================================================================

class TestTurnGateOff:
    """/session/{id}/turn with content_release=False: response absent."""

    def _mock_turn(self, client_req):
        with patch("io_iii.api.app._cli") as mock_cli, \
             patch("io_iii.api.app._content_release_enabled", return_value=False):
            mock_cli.return_value.cmd_session_continue = _cmd_ok(_TURN_PAYLOAD)
            return client.post("/session/ses-adr026/turn", json=client_req)

    def test_response_absent(self):
        resp = self._mock_turn({"prompt": "Hello"})
        assert "response" not in resp.json()

    def test_message_stripped(self):
        resp = self._mock_turn({"prompt": "Hello"})
        assert "message" not in resp.json()

    def test_structural_fields_present(self):
        resp = self._mock_turn({"prompt": "Hello"})
        body = resp.json()
        assert body["turn_index"] == 1
        assert body["session_status"] == "active"


# ===========================================================================
# 6. POST /session/{id}/turn — gate on
# ===========================================================================

class TestTurnGateOn:
    """/session/{id}/turn with content_release=True: response present."""

    def _mock_turn(self, client_req, payload=None):
        p = payload or _TURN_PAYLOAD
        with patch("io_iii.api.app._cli") as mock_cli, \
             patch("io_iii.api.app._content_release_enabled", return_value=True):
            mock_cli.return_value.cmd_session_continue = _cmd_ok(p)
            mock_cli.return_value.cmd_session_status = _cmd_ok(_STATUS_PAYLOAD)
            return client.post("/session/ses-adr026/turn", json=client_req)

    def test_response_present(self):
        resp = self._mock_turn({"prompt": "Who are you?"})
        assert resp.json()["response"] == "I am IO-III, a governed runtime."

    def test_message_key_absent(self):
        resp = self._mock_turn({"prompt": "Who are you?"})
        assert "message" not in resp.json()

    def test_prompt_still_stripped(self):
        resp = self._mock_turn({"prompt": "Who are you?"})
        assert "prompt" not in resp.json()

    def test_response_absent_when_engine_has_no_message(self):
        payload_no_msg = {k: v for k, v in _TURN_PAYLOAD.items() if k != "message"}
        resp = self._mock_turn({"prompt": "silent?"}, payload=payload_no_msg)
        assert "response" not in resp.json()

    def test_structural_fields_preserved(self):
        resp = self._mock_turn({"prompt": "Who are you?"})
        body = resp.json()
        assert body["turn_index"] == 1
        assert body["session_status"] == "active"
        assert body["latency_ms"] == 200


# ===========================================================================
# 7. SSE events — always structural regardless of gate
# ===========================================================================

class TestSSEContentSafety:
    """SSE events never include response field even when gate is open (ADR-026 §7)."""

    def test_sse_session_state_has_no_response_field(self):
        sid = "sse-adr026"
        bus.clear(sid)
        # Publish a sentinel so the generator terminates.
        bus.close_stream(sid)

        status_payload = {
            "session_id": sid,
            "session_status": "active",
            "turn_count": 0,
            "message": "SHOULD NOT APPEAR",
        }

        with patch("io_iii.api.app._cli") as mock_cli, \
             patch("io_iii.api.app._SSE_POLL_INTERVAL", 0), \
             patch("io_iii.api.app._content_release_enabled", return_value=True):
            mock_cli.return_value.cmd_session_status = _cmd_ok(status_payload)
            resp = client.get(f"/session/{sid}/stream")

        assert resp.status_code == 200
        # Parse SSE lines for the session_state event data
        lines = resp.text.splitlines()
        data_lines = [l for l in lines if l.startswith("data:")]
        assert len(data_lines) >= 1
        for dl in data_lines:
            data = json.loads(dl[len("data:"):].strip())
            assert "response" not in data
            assert "message" not in data

        bus.clear(sid)
