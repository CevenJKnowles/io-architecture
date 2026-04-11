"""
test_telemetry_m52.py — Phase 5 M5.2 execution telemetry metrics tests.

Verifies:

  Unit — ExecutionMetrics
  - all fields stored correctly
  - to_dict() produces content-safe projection
  - to_dict() keys match ADR-021 §3.2 field names
  - output_tokens may be None (best-effort)
  - model_used may be None (null route)

  Unit — OllamaProvider.generate_with_metrics()
  - returns (str, int, int) when Ollama supplies token counts
  - returns (str, None, None) when token counts absent in response
  - prompt_eval_count maps to input_tokens
  - eval_count maps to output_tokens
  - raises ProviderError on network failure (same as generate())

  Integration — engine Ollama path
  - meta["telemetry"] present in ExecutionResult after Ollama run
  - telemetry["call_count"] == 1 for a single-pass run
  - telemetry["model_used"] matches the route model
  - telemetry["latency_ms"] is a non-negative integer
  - telemetry["input_tokens"] is positive (heuristic fallback when provider silent)
  - telemetry["output_tokens"] is None when provider does not supply it
  - provider-confirmed input_tokens takes precedence over heuristic
  - no telemetry key on null route (null route never assembles a prompt)
  - telemetry is content-safe (assert_no_forbidden_keys passes)
"""
from __future__ import annotations

import time
import types
from typing import Optional
from unittest.mock import patch

import pytest

from io_iii.core.telemetry import ExecutionMetrics
from io_iii.core.content_safety import assert_no_forbidden_keys


# ---------------------------------------------------------------------------
# Unit: ExecutionMetrics dataclass
# ---------------------------------------------------------------------------

def test_execution_metrics_stores_fields():
    m = ExecutionMetrics(
        call_count=1,
        input_tokens=512,
        output_tokens=128,
        latency_ms=300,
        model_used="llama3.2",
    )
    assert m.call_count == 1
    assert m.input_tokens == 512
    assert m.output_tokens == 128
    assert m.latency_ms == 300
    assert m.model_used == "llama3.2"


def test_execution_metrics_output_tokens_none():
    m = ExecutionMetrics(
        call_count=1,
        input_tokens=400,
        output_tokens=None,
        latency_ms=200,
        model_used="llama3.2",
    )
    assert m.output_tokens is None


def test_execution_metrics_model_used_none():
    m = ExecutionMetrics(
        call_count=0,
        input_tokens=0,
        output_tokens=None,
        latency_ms=5,
        model_used=None,
    )
    assert m.model_used is None


def test_execution_metrics_to_dict_keys():
    m = ExecutionMetrics(
        call_count=2,
        input_tokens=300,
        output_tokens=50,
        latency_ms=150,
        model_used="phi3",
    )
    d = m.to_dict()
    assert set(d.keys()) == {"call_count", "input_tokens", "output_tokens", "latency_ms", "model_used"}


def test_execution_metrics_to_dict_values():
    m = ExecutionMetrics(
        call_count=1,
        input_tokens=200,
        output_tokens=75,
        latency_ms=100,
        model_used="mistral",
    )
    d = m.to_dict()
    assert d["call_count"] == 1
    assert d["input_tokens"] == 200
    assert d["output_tokens"] == 75
    assert d["latency_ms"] == 100
    assert d["model_used"] == "mistral"


def test_execution_metrics_to_dict_content_safe():
    """to_dict() output must pass assert_no_forbidden_keys."""
    m = ExecutionMetrics(
        call_count=1,
        input_tokens=100,
        output_tokens=50,
        latency_ms=80,
        model_used="llama3.2",
    )
    assert_no_forbidden_keys(m.to_dict())


# ---------------------------------------------------------------------------
# Unit: OllamaProvider.generate_with_metrics()
# ---------------------------------------------------------------------------

def _make_ollama_response_body(
    response_text: str,
    prompt_eval_count: Optional[int] = None,
    eval_count: Optional[int] = None,
) -> bytes:
    import json
    obj = {"response": response_text}
    if prompt_eval_count is not None:
        obj["prompt_eval_count"] = prompt_eval_count
    if eval_count is not None:
        obj["eval_count"] = eval_count
    return json.dumps(obj).encode("utf-8")


class _MockHTTPResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def _patch_urlopen(body: bytes):
    """Return a context manager that patches urllib.request.urlopen."""
    import unittest.mock as mock
    return mock.patch(
        "urllib.request.urlopen",
        return_value=_MockHTTPResponse(body),
    )


def test_generate_with_metrics_returns_text():
    from io_iii.providers.ollama_provider import OllamaProvider
    body = _make_ollama_response_body("Hello", prompt_eval_count=10, eval_count=5)
    with _patch_urlopen(body):
        p = OllamaProvider()
        text, _, _ = p.generate_with_metrics(model="llama3.2", prompt="Hi")
    assert text == "Hello"


def test_generate_with_metrics_returns_input_tokens():
    from io_iii.providers.ollama_provider import OllamaProvider
    body = _make_ollama_response_body("Hi", prompt_eval_count=42, eval_count=7)
    with _patch_urlopen(body):
        _, input_tokens, _ = OllamaProvider().generate_with_metrics(model="x", prompt="y")
    assert input_tokens == 42


def test_generate_with_metrics_returns_output_tokens():
    from io_iii.providers.ollama_provider import OllamaProvider
    body = _make_ollama_response_body("Hi", prompt_eval_count=42, eval_count=7)
    with _patch_urlopen(body):
        _, _, output_tokens = OllamaProvider().generate_with_metrics(model="x", prompt="y")
    assert output_tokens == 7


def test_generate_with_metrics_none_when_absent():
    """Token counts are None when Ollama does not include them in the response."""
    from io_iii.providers.ollama_provider import OllamaProvider
    body = _make_ollama_response_body("Hello")  # no token fields
    with _patch_urlopen(body):
        _, input_tokens, output_tokens = OllamaProvider().generate_with_metrics(model="x", prompt="y")
    assert input_tokens is None
    assert output_tokens is None


def test_generate_with_metrics_raises_provider_error_on_network_failure():
    """generate_with_metrics must raise ProviderError on network failure."""
    from io_iii.providers.ollama_provider import OllamaProvider
    from io_iii.providers.provider_contract import ProviderError
    import unittest.mock as mock

    with mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        with pytest.raises(ProviderError):
            OllamaProvider().generate_with_metrics(model="x", prompt="y")


# ---------------------------------------------------------------------------
# Integration: engine attaches telemetry on Ollama path
# ---------------------------------------------------------------------------

def _make_ollama_state(request_id: str = "test-telemetry"):
    from io_iii.core.session_state import SessionState, AuditGateState, RouteInfo
    return SessionState(
        request_id=request_id,
        started_at_ms=int(time.time() * 1000),
        mode="executor",
        config_dir="./architecture/runtime/config",
        route=RouteInfo(
            mode="executor",
            primary_target="ollama:llama3.2",
            secondary_target=None,
            selected_target="ollama:llama3.2",
            selected_provider="ollama",
            fallback_used=False,
            fallback_reason=None,
        ),
        audit=AuditGateState(audit_enabled=False),
        status="ok",
        provider="ollama",
        model="llama3.2",
        route_id="executor",
        persona_contract_version="v1.0",
        logging_policy={"content": "disabled"},
    )


def _make_cfg(context_limit_chars=32000):
    return types.SimpleNamespace(
        providers={"ollama": {"base_url": "http://127.0.0.1:11434"}},
        logging={},
        routing={"routing_table": {}},
        runtime={"context_limit_chars": context_limit_chars},
    )


class _MockOllamaProvider:
    """Test double that returns controlled text and token counts."""
    def __init__(self, text="ok", input_tokens=None, output_tokens=None):
        self._text = text
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens

    def generate_with_metrics(self, *, model, prompt):
        return self._text, self._input_tokens, self._output_tokens

    def generate(self, *, model, prompt):
        return self._text


def test_engine_ollama_meta_has_telemetry_key():
    from io_iii.core.engine import run
    state = _make_ollama_state("t-telemetry-key")
    _, result = run(
        cfg=_make_cfg(),
        session_state=state,
        user_prompt="hello",
        audit=False,
        ollama_provider_factory=lambda _: _MockOllamaProvider("response"),
    )
    assert "telemetry" in result.meta


def test_engine_telemetry_call_count_is_one():
    from io_iii.core.engine import run
    state = _make_ollama_state("t-call-count")
    _, result = run(
        cfg=_make_cfg(),
        session_state=state,
        user_prompt="hello",
        audit=False,
        ollama_provider_factory=lambda _: _MockOllamaProvider("response"),
    )
    assert result.meta["telemetry"]["call_count"] == 1


def test_engine_telemetry_model_used_matches_route():
    from io_iii.core.engine import run
    state = _make_ollama_state("t-model-used")
    _, result = run(
        cfg=_make_cfg(),
        session_state=state,
        user_prompt="hello",
        audit=False,
        ollama_provider_factory=lambda _: _MockOllamaProvider("response"),
    )
    assert result.meta["telemetry"]["model_used"] == "llama3.2"


def test_engine_telemetry_latency_ms_non_negative():
    from io_iii.core.engine import run
    state = _make_ollama_state("t-latency")
    _, result = run(
        cfg=_make_cfg(),
        session_state=state,
        user_prompt="hello",
        audit=False,
        ollama_provider_factory=lambda _: _MockOllamaProvider("response"),
    )
    assert isinstance(result.meta["telemetry"]["latency_ms"], int)
    assert result.meta["telemetry"]["latency_ms"] >= 0


def test_engine_telemetry_input_tokens_positive_heuristic_fallback():
    """input_tokens must be positive even when provider returns None."""
    from io_iii.core.engine import run
    state = _make_ollama_state("t-input-heuristic")
    _, result = run(
        cfg=_make_cfg(),
        session_state=state,
        user_prompt="hello world",
        audit=False,
        ollama_provider_factory=lambda _: _MockOllamaProvider("response", input_tokens=None),
    )
    assert result.meta["telemetry"]["input_tokens"] > 0


def test_engine_telemetry_output_tokens_none_when_provider_silent():
    from io_iii.core.engine import run
    state = _make_ollama_state("t-output-none")
    _, result = run(
        cfg=_make_cfg(),
        session_state=state,
        user_prompt="hello",
        audit=False,
        ollama_provider_factory=lambda _: _MockOllamaProvider("response", output_tokens=None),
    )
    assert result.meta["telemetry"]["output_tokens"] is None


def test_engine_telemetry_provider_confirmed_input_tokens_take_precedence():
    """Provider-confirmed input_tokens must override the heuristic estimate."""
    from io_iii.core.engine import run
    state = _make_ollama_state("t-confirmed-tokens")
    # Provider returns a very specific count that would differ from heuristic
    _, result = run(
        cfg=_make_cfg(),
        session_state=state,
        user_prompt="hello",
        audit=False,
        ollama_provider_factory=lambda _: _MockOllamaProvider("response", input_tokens=9999),
    )
    assert result.meta["telemetry"]["input_tokens"] == 9999


def test_engine_null_route_has_no_telemetry():
    """Null route does not assemble a prompt — telemetry key must be absent."""
    from io_iii.core.engine import run
    from io_iii.core.session_state import SessionState, AuditGateState

    state = SessionState(
        request_id="t-null-telemetry",
        started_at_ms=int(time.time() * 1000),
        mode="executor",
        config_dir="./architecture/runtime/config",
        route=None,
        audit=AuditGateState(audit_enabled=False),
        status="ok",
        provider="null",
        model=None,
        route_id="null",
        persona_contract_version="v1.0",
        logging_policy={"content": "disabled"},
    )
    _, result = run(
        cfg=_make_cfg(),
        session_state=state,
        user_prompt="hello",
        audit=False,
    )
    assert "telemetry" not in result.meta


def test_engine_telemetry_content_safe():
    """Telemetry dict must pass assert_no_forbidden_keys."""
    from io_iii.core.engine import run
    state = _make_ollama_state("t-content-safe")
    _, result = run(
        cfg=_make_cfg(),
        session_state=state,
        user_prompt="hello",
        audit=False,
        ollama_provider_factory=lambda _: _MockOllamaProvider("response", input_tokens=100, output_tokens=50),
    )
    assert_no_forbidden_keys(result.meta["telemetry"])
