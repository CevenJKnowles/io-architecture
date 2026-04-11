"""
test_engine_revision_paths.py — Engine revision inference and challenger fail-open tests.

Verifies:

  Revision path (engine.py lines 593–623)
  - audit=True + challenger returns needs_work → revision inference is called
  - provider.generate called twice (draft + revision)
  - audit_meta["revised"] == True after revision
  - audit_meta["audit_verdict"] == "needs_work"
  - revision_passes reflected in returned SessionState.audit
  - audit_passes == 1 in returned SessionState.audit
  - engine returns the revised text (second generate() call result)

  No-revision path
  - audit=True + challenger returns pass → generate called once only
  - audit_meta["revised"] == False
  - audit_meta["audit_verdict"] == "pass"

  audit=False path
  - challenger never called when audit=False
  - audit_meta is None in ExecutionResult when audit=False
  - generate called once only

  Challenger fail-open (engine.py _run_challenger lines 164–181)
  - _run_challenger returns auto-pass dict when JSON parse fails
  - auto-pass dict has verdict=="pass", empty issues/high_risk_claims/suggested_fixes
  - _run_challenger returns auto-pass dict when provider is unavailable (null route)
"""
from __future__ import annotations

import types
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

import io_iii.core.engine as engine
from io_iii.core.capabilities import CapabilityRegistry
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.session_state import AuditGateState, RouteInfo, SessionState
from io_iii.core.engine import _run_challenger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ollama_state(*, route_id: str = "executor") -> SessionState:
    route = RouteInfo(
        mode="executor",
        primary_target="local:test-model",
        secondary_target=None,
        selected_target="local:test-model",
        selected_provider="ollama",
        fallback_used=False,
        fallback_reason=None,
        boundaries={"single_voice_output": True},
    )
    return SessionState(
        request_id="engine-rev-test",
        started_at_ms=0,
        mode="executor",
        config_dir="./architecture/runtime/config",
        route=route,
        audit=AuditGateState(audit_enabled=False),
        status="ok",
        provider="ollama",
        model="test-model",
        route_id=route_id,
        persona_contract_version="v0.1",
        logging_policy={"content": "disabled"},
    )


def _make_null_state() -> SessionState:
    route = RouteInfo(
        mode="executor",
        primary_target=None,
        secondary_target=None,
        selected_target=None,
        selected_provider="null",
        fallback_used=False,
        fallback_reason=None,
        boundaries={},
    )
    return SessionState(
        request_id="engine-null-test",
        started_at_ms=0,
        mode="executor",
        config_dir="./architecture/runtime/config",
        route=route,
        audit=AuditGateState(audit_enabled=False),
        status="ok",
        provider="null",
        model=None,
        route_id="executor",
        persona_contract_version="v0.1",
        logging_policy={"content": "disabled"},
    )


class _CountingProvider:
    """Fake ollama provider. Tracks generate() calls and returns deterministic text."""

    def __init__(self, draft: str = "DRAFT", revision: str = "REVISED"):
        self._draft = draft
        self._revision = revision
        self.calls: list[dict] = []

    def generate(self, *, model: str, prompt: str) -> str:
        self.calls.append({"model": model, "prompt_len": len(prompt)})
        if len(self.calls) == 1:
            return self._draft
        return self._revision

    # M5.2 protocol: not present → engine falls back to generate()


def _make_cfg(*, context_limit: int = 0) -> types.SimpleNamespace:
    """Minimal cfg object accepted by engine.run()."""
    runtime: Dict[str, Any] = {}
    if context_limit > 0:
        runtime["context_limit_chars"] = context_limit
    return types.SimpleNamespace(
        config_dir=".",
        providers={},
        routing={"routing_table": {}},
        logging={"schema": "test"},
        runtime=runtime,
    )


def _make_deps(provider: _CountingProvider) -> RuntimeDependencies:
    return RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: provider,
        challenger_fn=None,
        capability_registry=CapabilityRegistry([]),
    )


# ---------------------------------------------------------------------------
# Revision path
# ---------------------------------------------------------------------------

class TestRevisionPath:

    def _run_with_needs_work(self) -> tuple:
        """Run engine with a challenger that always returns needs_work."""
        provider = _CountingProvider(draft="DRAFT TEXT", revision="REVISED TEXT")
        cfg = _make_cfg()
        state = _make_ollama_state()
        deps = _make_deps(provider)

        challenger_calls: list = []

        def fake_challenger(_cfg, _prompt, _draft):
            challenger_calls.append(True)
            return {
                "verdict": "needs_work",
                "issues": ["needs improvement"],
                "high_risk_claims": [],
                "suggested_fixes": ["fix it"],
            }

        state2, result = engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="test query",
            audit=True,
            deps=deps,
            challenger_fn=fake_challenger,
        )
        return state2, result, provider, challenger_calls

    def test_revision_inference_called(self):
        """When challenger returns needs_work, provider.generate must be called twice."""
        _state2, _result, provider, _challenger_calls = self._run_with_needs_work()
        assert len(provider.calls) == 2, "generate must be called twice: draft + revision"

    def test_audit_meta_revised_true(self):
        _state2, result, _provider, _challenger_calls = self._run_with_needs_work()
        assert result.audit_meta is not None
        assert result.audit_meta["revised"] is True

    def test_audit_meta_verdict_needs_work(self):
        _state2, result, _provider, _challenger_calls = self._run_with_needs_work()
        assert result.audit_meta["audit_verdict"] == "needs_work"

    def test_result_message_is_revised_text(self):
        """The returned message must be the revision (second generate() call)."""
        _state2, result, _provider, _challenger_calls = self._run_with_needs_work()
        assert result.message == "REVISED TEXT"

    def test_session_state_revision_passes_incremented(self):
        state2, _result, _provider, _challenger_calls = self._run_with_needs_work()
        assert state2.audit.revision_passes == 1

    def test_session_state_audit_passes_incremented(self):
        state2, _result, _provider, _challenger_calls = self._run_with_needs_work()
        assert state2.audit.audit_passes == 1

    def test_challenger_called_once(self):
        _state2, _result, _provider, challenger_calls = self._run_with_needs_work()
        assert len(challenger_calls) == 1


# ---------------------------------------------------------------------------
# No-revision path (challenger returns pass)
# ---------------------------------------------------------------------------

class TestNoRevisionPath:

    def _run_with_pass(self) -> tuple:
        provider = _CountingProvider(draft="GOOD DRAFT")
        cfg = _make_cfg()
        state = _make_ollama_state()
        deps = _make_deps(provider)

        def fake_challenger(_cfg, _prompt, _draft):
            return {"verdict": "pass", "issues": [], "high_risk_claims": [], "suggested_fixes": []}

        state2, result = engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="test query",
            audit=True,
            deps=deps,
            challenger_fn=fake_challenger,
        )
        return state2, result, provider

    def test_generate_called_once(self):
        _state2, _result, provider = self._run_with_pass()
        assert len(provider.calls) == 1, "no revision → generate called only once"

    def test_audit_meta_revised_false(self):
        _state2, result, _provider = self._run_with_pass()
        assert result.audit_meta is not None
        assert result.audit_meta["revised"] is False

    def test_audit_meta_verdict_pass(self):
        _state2, result, _provider = self._run_with_pass()
        assert result.audit_meta["audit_verdict"] == "pass"

    def test_result_message_is_draft(self):
        _state2, result, _provider = self._run_with_pass()
        assert result.message == "GOOD DRAFT"

    def test_session_state_revision_passes_zero(self):
        state2, _result, _provider = self._run_with_pass()
        assert state2.audit.revision_passes == 0


# ---------------------------------------------------------------------------
# audit=False path
# ---------------------------------------------------------------------------

class TestAuditDisabled:

    def _run_no_audit(self) -> tuple:
        provider = _CountingProvider(draft="DRAFT NO AUDIT")
        cfg = _make_cfg()
        state = _make_ollama_state()
        deps = _make_deps(provider)

        challenger_calls: list = []

        def fake_challenger(_cfg, _prompt, _draft):
            challenger_calls.append(True)
            return {"verdict": "needs_work", "issues": [], "high_risk_claims": [], "suggested_fixes": []}

        state2, result = engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="no-audit query",
            audit=False,
            deps=deps,
            challenger_fn=fake_challenger,
        )
        return state2, result, provider, challenger_calls

    def test_challenger_not_called(self):
        _state2, _result, _provider, challenger_calls = self._run_no_audit()
        assert len(challenger_calls) == 0

    def test_audit_meta_is_none(self):
        _state2, result, _provider, _challenger_calls = self._run_no_audit()
        assert result.audit_meta is None

    def test_generate_called_once(self):
        _state2, _result, provider, _challenger_calls = self._run_no_audit()
        assert len(provider.calls) == 1


# ---------------------------------------------------------------------------
# Challenger fail-open — _run_challenger internal behaviour
# ---------------------------------------------------------------------------

class TestChallengerFailOpen:

    def test_fail_open_on_invalid_json(self):
        """When the provider returns non-JSON, _run_challenger must auto-pass."""
        cfg = types.SimpleNamespace(
            config_dir=".",
            providers={"providers": {"ollama": {"enabled": True}}},
            routing={
                "routing_table": {
                    "modes": {
                        "challenger": {
                            "primary": "local:test-model",
                            "secondary": "local:test-model",
                        }
                    },
                    "rules": {},
                }
            },
            logging={"schema": "test"},
        )

        class _BadJsonProvider:
            def generate(self, *, model, prompt):
                return "this is not JSON at all!!!"

        result = _run_challenger(
            cfg,
            "user prompt",
            "executor draft",
            ollama_provider_factory=lambda _cfg: _BadJsonProvider(),
        )

        assert result["verdict"] == "pass"
        assert result["issues"] == []
        assert result["high_risk_claims"] == []
        assert result["suggested_fixes"] == []

    def test_fail_open_when_provider_unavailable(self):
        """When no ollama route is available, _run_challenger must auto-pass."""
        cfg = types.SimpleNamespace(
            config_dir=".",
            providers={"providers": {"ollama": {"enabled": False}}},
            routing={
                "routing_table": {
                    "modes": {
                        "challenger": {
                            "primary": "local:test-model",
                            "secondary": "local:test-model",
                        }
                    },
                    "rules": {},
                }
            },
            logging={"schema": "test"},
        )

        class _UnreachableProvider:
            def generate(self, *, model, prompt):
                raise ConnectionError("ollama is down")

        result = _run_challenger(
            cfg,
            "user prompt",
            "executor draft",
            ollama_provider_factory=lambda _cfg: _UnreachableProvider(),
        )
        # Null route → fail-open auto-pass (provider != ollama)
        assert result["verdict"] == "pass"

    def test_fail_open_returns_required_keys(self):
        """Auto-pass dict must always contain all required audit keys."""
        cfg = types.SimpleNamespace(
            config_dir=".",
            providers={"providers": {"ollama": {"enabled": True}}},
            routing={
                "routing_table": {
                    "modes": {
                        "challenger": {
                            "primary": "local:test-model",
                            "secondary": "local:test-model",
                        }
                    },
                    "rules": {},
                }
            },
            logging={"schema": "test"},
        )

        class _BadJsonProvider:
            def generate(self, *, model, prompt):
                return "not json"

        result = _run_challenger(
            cfg,
            "prompt",
            "draft",
            ollama_provider_factory=lambda _cfg: _BadJsonProvider(),
        )
        required = {"verdict", "issues", "high_risk_claims", "suggested_fixes"}
        assert required <= set(result.keys())
