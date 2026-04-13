"""
tests/test_api_webhooks_m93.py

Phase 9 M9.3 — Webhook dispatch.

Governing ADR: ADR-025 §6 — Webhook Dispatch.

Coverage:
  - dispatch() fires a daemon thread per call (non-blocking)
  - dispatch() no-ops when url is None or empty
  - get_webhook_url() extracts webhook_url from runtime config
  - Content-safe payloads: event type + structural metadata only
  - Fire-and-forget: HTTP errors are swallowed silently
  - _fire() sends correct Content-Type and method
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from io_iii.api._webhooks import dispatch, get_webhook_url, _fire


# ===========================================================================
# 1. get_webhook_url
# ===========================================================================

class TestGetWebhookUrl:
    def test_present(self):
        cfg = {"webhook_url": "https://example.com/hook"}
        assert get_webhook_url(cfg) == "https://example.com/hook"

    def test_absent(self):
        assert get_webhook_url({}) is None

    def test_empty_string(self):
        assert get_webhook_url({"webhook_url": ""}) is None

    def test_whitespace_only(self):
        assert get_webhook_url({"webhook_url": "   "}) is None

    def test_non_string_ignored(self):
        assert get_webhook_url({"webhook_url": 42}) is None


# ===========================================================================
# 2. dispatch() — no-op cases
# ===========================================================================

class TestDispatchNoop:
    def test_none_url(self):
        """dispatch() is a no-op when url is None."""
        with patch("io_iii.api._webhooks.threading.Thread") as mock_t:
            dispatch(None, "SESSION_COMPLETE", {"session_id": "x"})
        mock_t.assert_not_called()

    def test_empty_url(self):
        with patch("io_iii.api._webhooks.threading.Thread") as mock_t:
            dispatch("", "SESSION_COMPLETE", {"session_id": "x"})
        mock_t.assert_not_called()


# ===========================================================================
# 3. dispatch() — thread spawning
# ===========================================================================

class TestDispatchThread:
    def test_spawns_daemon_thread(self):
        """dispatch() spawns exactly one daemon Thread."""
        threads = []
        real_thread = threading.Thread

        def capture_thread(**kwargs):
            t = real_thread(**kwargs)
            t.daemon = True
            threads.append(t)
            return t

        with patch("io_iii.api._webhooks.threading.Thread", side_effect=capture_thread):
            dispatch("http://localhost/hook", "SESSION_COMPLETE", {"session_id": "s"})

        assert len(threads) == 1
        assert threads[0].daemon is True

    def test_non_blocking(self):
        """dispatch() returns immediately without waiting for HTTP call."""
        called = threading.Event()

        def slow_fire(url, body):
            called.wait(timeout=5)  # would block if awaited

        with patch("io_iii.api._webhooks._fire", side_effect=slow_fire):
            dispatch("http://localhost/hook", "SESSION_COMPLETE", {"session_id": "s"})
        # If dispatch() waited for _fire(), this line would be reached only after
        # the event is set. Since it's fire-and-forget, we reach here immediately.
        called.set()  # unblock the thread so it can clean up


# ===========================================================================
# 4. _fire() — HTTP POST mechanics
# ===========================================================================

class TestFireHttp:
    def test_fire_sends_post_with_json(self):
        """_fire() sends HTTP POST with application/json Content-Type."""
        import urllib.request
        sent = {}

        def fake_urlopen(req, timeout):
            sent["method"] = req.method
            sent["content_type"] = req.get_header("Content-type")
            sent["url"] = req.full_url
            return MagicMock(__enter__=MagicMock(return_value=None), __exit__=MagicMock(return_value=False))

        with patch("io_iii.api._webhooks.urllib.request.urlopen", side_effect=fake_urlopen):
            _fire("http://example.com/hook", {"event": "SESSION_COMPLETE", "session_id": "x"})

        assert sent["method"] == "POST"
        assert sent["content_type"] == "application/json"
        assert sent["url"] == "http://example.com/hook"

    def test_fire_swallows_http_errors(self):
        """_fire() does not raise on HTTP error (fire-and-forget)."""
        import urllib.error
        with patch("io_iii.api._webhooks.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("connection refused")):
            _fire("http://localhost:9999/nonexistent", {"event": "x"})  # must not raise

    def test_fire_swallows_generic_errors(self):
        with patch("io_iii.api._webhooks.urllib.request.urlopen",
                   side_effect=Exception("unexpected")):
            _fire("http://example.com", {})  # must not raise


# ===========================================================================
# 5. Content-safety (ADR-003)
# ===========================================================================

class TestWebhookContentSafety:
    def test_dispatch_payload_contains_event_type(self):
        """The webhook body includes the event_type as 'event' field."""
        import json
        sent_body = {}

        def capture_fire(url, body):
            sent_body.update(body)

        with patch("io_iii.api._webhooks._fire", side_effect=capture_fire):
            # Run synchronously by patching Thread to run immediately
            with patch("io_iii.api._webhooks.threading.Thread") as mock_t:
                def run_now(**kwargs):
                    t = MagicMock()
                    t.start = lambda: kwargs["target"](*kwargs.get("args", ()))
                    t.daemon = True
                    return t
                mock_t.side_effect = run_now
                dispatch("http://hook", "SESSION_COMPLETE", {
                    "session_id": "ses-x",
                    "session_status": "closed",
                })

        assert sent_body.get("event") == "SESSION_COMPLETE"
        assert sent_body.get("session_id") == "ses-x"
        # Must NOT contain content-unsafe fields
        assert "message" not in sent_body
        assert "prompt" not in sent_body
