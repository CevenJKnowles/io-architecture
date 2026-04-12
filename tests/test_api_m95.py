"""
Tests for Phase 9 M9.5 (self-hosted web UI).

Coverage:
  - static/index.html exists and is valid HTML
  - content-safety: no raw config paths, no model names, no memory values
  - required UI surface elements present
  - session lifecycle operations referenced (start, turn/stream, status, close)
  - EventSource usage for SSE (ADR-025 §5 + §9)
  - no external JavaScript framework dependencies
  - no hard-coded model names or config paths
  - served at GET / by the HTTP server
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixture: load the web UI HTML
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ui_html() -> str:
    from io_iii.api.server import _UI_PATH
    assert _UI_PATH.exists(), f"Web UI not found at {_UI_PATH}"
    return _UI_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# M9.5 — file existence and basic validity
# ---------------------------------------------------------------------------

class TestUIFileExists:
    def test_index_html_exists(self):
        from io_iii.api.server import _UI_PATH
        assert _UI_PATH.exists()

    def test_index_html_is_file(self):
        from io_iii.api.server import _UI_PATH
        assert _UI_PATH.is_file()

    def test_index_html_is_nonempty(self, ui_html):
        assert len(ui_html) > 100

    def test_index_html_starts_with_doctype(self, ui_html):
        assert ui_html.strip().lower().startswith("<!doctype html")

    def test_index_html_has_html_tag(self, ui_html):
        assert "<html" in ui_html.lower()

    def test_index_html_has_head_tag(self, ui_html):
        assert "<head" in ui_html.lower()

    def test_index_html_has_body_tag(self, ui_html):
        assert "<body" in ui_html.lower()

    def test_index_html_has_script_tag(self, ui_html):
        assert "<script" in ui_html.lower()

    def test_index_html_has_title(self, ui_html):
        assert "<title>" in ui_html.lower() or "<title " in ui_html.lower()

    def test_static_dir_structure(self):
        from io_iii.api.server import _STATIC_DIR
        assert _STATIC_DIR.is_dir()


# ---------------------------------------------------------------------------
# M9.5 — session lifecycle API calls present
# ---------------------------------------------------------------------------

class TestUISessionLifecycle:
    def test_references_session_start(self, ui_html):
        """UI must call POST /session/start (ADR-025 §9)."""
        assert "/session/start" in ui_html

    def test_references_session_stream(self, ui_html):
        """UI must use the SSE stream endpoint for turn output (ADR-025 §9)."""
        assert "/stream" in ui_html

    def test_references_session_delete(self, ui_html):
        """UI must support session close via DELETE /session/{id} (ADR-025 §9)."""
        assert "DELETE" in ui_html

    def test_references_session_turn_action(self, ui_html):
        """UI must support steward pause actions via /session/{id}/turn (ADR-025 §9)."""
        assert "/turn" in ui_html

    def test_uses_eventsource(self, ui_html):
        """UI must use EventSource for SSE streaming (ADR-025 §9)."""
        assert "EventSource" in ui_html

    def test_handles_turn_output_event(self, ui_html):
        """UI must handle the turn_output SSE event (ADR-025 §5)."""
        assert "turn_output" in ui_html

    def test_handles_turn_completed_event(self, ui_html):
        assert "turn_completed" in ui_html

    def test_handles_turn_started_event(self, ui_html):
        assert "turn_started" in ui_html

    def test_handles_steward_gate_triggered_event(self, ui_html):
        """UI must surface steward gate pause (ADR-024 / ADR-025)."""
        assert "steward_gate_triggered" in ui_html

    def test_handles_turn_error_event(self, ui_html):
        assert "turn_error" in ui_html


# ---------------------------------------------------------------------------
# M9.5 — no external framework dependencies
# ---------------------------------------------------------------------------

class TestUINoExternalDeps:
    def test_no_cdn_script_tags(self, ui_html):
        """UI must not load scripts from external CDN (ADR-025 §9)."""
        import re
        # Find all script src attributes
        srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', ui_html, re.IGNORECASE)
        external = [s for s in srcs if s.startswith("http://") or s.startswith("https://")]
        assert external == [], f"External script sources found: {external}"

    def test_no_cdn_link_tags(self, ui_html):
        """UI must not load stylesheets from external CDN."""
        import re
        hrefs = re.findall(r'<link[^>]+href=["\']([^"\']+)["\']', ui_html, re.IGNORECASE)
        external = [h for h in hrefs if h.startswith("http://") or h.startswith("https://")]
        assert external == [], f"External stylesheet sources found: {external}"

    def test_no_import_from_cdn(self, ui_html):
        """UI must not use ES module imports from CDN."""
        assert "import(" not in ui_html or "unpkg.com" not in ui_html

    def test_no_react_reference(self, ui_html):
        assert "react" not in ui_html.lower()

    def test_no_vue_reference(self, ui_html):
        assert "vue.js" not in ui_html.lower()

    def test_no_angular_reference(self, ui_html):
        assert "angular.js" not in ui_html.lower()

    def test_no_jquery_reference(self, ui_html):
        assert "jquery" not in ui_html.lower()


# ---------------------------------------------------------------------------
# M9.5 — content safety: no hard-coded config values
# ---------------------------------------------------------------------------

class TestUIContentSafety:
    def test_no_hardcoded_model_names(self, ui_html):
        """UI must not contain hard-coded model names (ADR-025 §4 + §9)."""
        forbidden_model_patterns = ["llama", "mistral", "gemma", "phi3", "qwen"]
        lower = ui_html.lower()
        for pattern in forbidden_model_patterns:
            assert pattern not in lower, f"Model name '{pattern}' found in UI"

    def test_no_hardcoded_config_paths(self, ui_html):
        """UI must not contain hard-coded config file paths."""
        assert "routing_table.yaml" not in ui_html
        assert "memory_packs.yaml" not in ui_html
        assert "persona.yaml" not in ui_html

    def test_no_hardcoded_localhost_port_in_api_calls(self, ui_html):
        """UI must use window.location.origin for API base, not a hard-coded port."""
        # The UI should call window.location.origin or similar, not 'http://localhost:8080'
        assert "localhost:8080" not in ui_html
        assert "127.0.0.1:8080" not in ui_html

    def test_uses_window_location_origin(self, ui_html):
        """UI must derive API base from window.location.origin (ADR-025 §9)."""
        assert "window.location.origin" in ui_html

    def test_no_memory_values_in_html(self, ui_html):
        """UI must not contain static memory record values."""
        assert "memory_value" not in ui_html


# ---------------------------------------------------------------------------
# M9.5 — UI governance surface (steward mode, session controls)
# ---------------------------------------------------------------------------

class TestUIGovernanceSurface:
    def test_work_mode_option_present(self, ui_html):
        """UI must expose work/steward mode selection (ADR-024)."""
        assert "work" in ui_html

    def test_steward_mode_option_present(self, ui_html):
        assert "steward" in ui_html

    def test_approve_action_present(self, ui_html):
        """UI must surface approve action for steward pause (ADR-024 §6.3)."""
        assert "approve" in ui_html

    def test_redirect_action_present(self, ui_html):
        assert "redirect" in ui_html

    def test_close_action_present(self, ui_html):
        assert "close" in ui_html or "Close" in ui_html

    def test_persona_mode_selector_present(self, ui_html):
        """UI must allow persona mode selection."""
        assert "executor" in ui_html

    def test_session_id_display_present(self, ui_html):
        """UI must display session ID for governance tracking."""
        assert "session" in ui_html.lower()


# ---------------------------------------------------------------------------
# M9.5 — server serves UI at GET /
# ---------------------------------------------------------------------------

class TestServerServesUI:
    def test_ui_path_constant_points_to_existing_file(self):
        from io_iii.api.server import _UI_PATH
        assert _UI_PATH.exists()

    def test_static_dir_constant_is_correct(self):
        from io_iii.api.server import _STATIC_DIR, _UI_PATH
        assert _UI_PATH.parent == _STATIC_DIR
