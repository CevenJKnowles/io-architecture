from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from io_iii.providers.ollama_provider import OllamaProvider


def test_check_reachable_succeeds_when_endpoint_responds(monkeypatch):
    """Health check passes when the Ollama root endpoint returns any response."""

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: _FakeResponse())

    provider = OllamaProvider(host="http://localhost:11434")
    # Must not raise
    provider.check_reachable(timeout_ms=500)


def test_check_reachable_raises_provider_unavailable_on_connection_error(monkeypatch):
    """Health check raises PROVIDER_UNAVAILABLE when the endpoint is unreachable."""

    def _fail(req, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _fail)

    provider = OllamaProvider(host="http://localhost:11434")
    with pytest.raises(RuntimeError, match="PROVIDER_UNAVAILABLE: ollama"):
        provider.check_reachable(timeout_ms=500)


def test_check_reachable_raises_provider_unavailable_on_timeout(monkeypatch):
    """Health check raises PROVIDER_UNAVAILABLE on timeout."""

    def _timeout(req, timeout):
        import socket
        raise socket.timeout("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", _timeout)

    provider = OllamaProvider(host="http://localhost:11434")
    with pytest.raises(RuntimeError, match="PROVIDER_UNAVAILABLE: ollama"):
        provider.check_reachable(timeout_ms=100)
