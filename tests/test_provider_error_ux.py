from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from io_iii.providers.provider_contract import ProviderError


def _args(**overrides):
    a = MagicMock()
    a.mode = "fast"
    a.prompt = "hello"
    a.audit = False
    a.raw = False
    a.capability_id = None
    a.capability_payload_json = None
    a.no_health_check = True
    a.no_constellation_check = True
    for k, v in overrides.items():
        setattr(a, k, v)
    return a


def _selection():
    s = MagicMock()
    s.mode = "fast"
    s.selected_provider = "ollama"
    s.primary_target = "local:mistral:latest"
    s.selected_target = "local:mistral:latest"
    s.secondary_target = None
    s.fallback_used = False
    s.fallback_reason = None
    s.boundaries = {}
    return s


def _cfg(tmp_path):
    c = MagicMock()
    c.logging = {}
    c.providers = {}
    c.routing = {"routing_table": {}}
    c.config_dir = tmp_path
    return c


def _raise(exc):
    def _engine(**_):
        raise exc
    return _engine


class TestProviderErrorUX:
    """M10.2 — plain-language hint on ProviderError 404 (ADR-028)."""

    def test_404_exits_1(self, tmp_path, monkeypatch, capsys):
        import io_iii.cli as cli
        monkeypatch.setattr(cli, "load_io3_config", lambda _: _cfg(tmp_path))
        monkeypatch.setattr(cli, "resolve_route", lambda **_: _selection())
        monkeypatch.setattr(cli, "append_metadata", lambda *a, **k: None)
        monkeypatch.setattr(cli, "engine_run", _raise(
            ProviderError("PROVIDER_OLLAMA_FAILED", "HTTP Error 404: Not Found")
        ))
        with pytest.raises(SystemExit) as exc:
            cli.cmd_run(_args())
        assert exc.value.code == 1

    def test_404_hint_content(self, tmp_path, monkeypatch, capsys):
        import io_iii.cli as cli
        monkeypatch.setattr(cli, "load_io3_config", lambda _: _cfg(tmp_path))
        monkeypatch.setattr(cli, "resolve_route", lambda **_: _selection())
        monkeypatch.setattr(cli, "append_metadata", lambda *a, **k: None)
        monkeypatch.setattr(cli, "engine_run", _raise(
            ProviderError("PROVIDER_OLLAMA_FAILED", "HTTP Error 404: Not Found")
        ))
        with pytest.raises(SystemExit):
            cli.cmd_run(_args())
        err = capsys.readouterr().err
        assert "ollama list" in err
        assert "routing_table.yaml" in err

    def test_404_logs_correct_error_code(self, tmp_path, monkeypatch):
        import io_iii.cli as cli
        logged = {}
        monkeypatch.setattr(cli, "load_io3_config", lambda _: _cfg(tmp_path))
        monkeypatch.setattr(cli, "resolve_route", lambda **_: _selection())
        monkeypatch.setattr(cli, "append_metadata", lambda _, r: logged.update(r))
        monkeypatch.setattr(cli, "engine_run", _raise(
            ProviderError("PROVIDER_OLLAMA_FAILED", "HTTP Error 404: Not Found")
        ))
        with pytest.raises(SystemExit):
            cli.cmd_run(_args())
        assert logged.get("error_code") == "PROVIDER_MODEL_NOT_FOUND"

    def test_non_404_reraises(self, tmp_path, monkeypatch):
        import io_iii.cli as cli
        monkeypatch.setattr(cli, "load_io3_config", lambda _: _cfg(tmp_path))
        monkeypatch.setattr(cli, "resolve_route", lambda **_: _selection())
        monkeypatch.setattr(cli, "append_metadata", lambda *a, **k: None)
        monkeypatch.setattr(cli, "engine_run", _raise(
            ProviderError("PROVIDER_OLLAMA_BAD_JSON", "Invalid JSON response")
        ))
        with pytest.raises(ProviderError):
            cli.cmd_run(_args())

    def test_non_404_logs_original_code(self, tmp_path, monkeypatch):
        import io_iii.cli as cli
        logged = {}
        monkeypatch.setattr(cli, "load_io3_config", lambda _: _cfg(tmp_path))
        monkeypatch.setattr(cli, "resolve_route", lambda **_: _selection())
        monkeypatch.setattr(cli, "append_metadata", lambda _, r: logged.update(r))
        monkeypatch.setattr(cli, "engine_run", _raise(
            ProviderError("PROVIDER_OLLAMA_BAD_JSON", "Invalid JSON response")
        ))
        with pytest.raises(ProviderError):
            cli.cmd_run(_args())
        assert logged.get("error_code") == "PROVIDER_OLLAMA_BAD_JSON"
