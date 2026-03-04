from __future__ import annotations

import types

import pytest

import io_iii.core.engine as engine
from io_iii.core.capabilities import (
    CapabilityBounds,
    CapabilityCategory,
    CapabilityContext,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
)
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.session_state import AuditGateState, RouteInfo, SessionState
from io_iii.metadata_logging import append_metadata


class LeakyCapability:
    """A deliberately unsafe capability used to verify content-safety guards."""

    @property
    def spec(self) -> CapabilitySpec:
        return CapabilitySpec(
            capability_id="test.leaky",
            version="v0",
            category=CapabilityCategory.TRANSFORMATION,
            description="Test-only leaky capability.",
            bounds=CapabilityBounds(max_calls=1, timeout_ms=100, max_input_chars=1000, max_output_chars=1000),
        )

    def invoke(self, ctx: CapabilityContext, payload):
        # Forbidden key must be rejected even if nested.
        return CapabilityResult(ok=True, output={"safe": {"content": "should_not_pass"}})


class FakeProvider:
    def generate(self, *, model: str, prompt: str) -> str:
        return "ok"


def _make_state(provider: str = "ollama") -> SessionState:
    route = RouteInfo(
        mode="executor",
        primary_target="local:qwen3:8b",
        secondary_target=None,
        selected_target="local:qwen3:8b",
        selected_provider=provider,
        fallback_used=False,
        fallback_reason=None,
        boundaries={"single_voice_output": True},
    )
    return SessionState(
        request_id="test",
        started_at_ms=0,
        mode="executor",
        config_dir="./architecture/runtime/config",
        route=route,
        audit=AuditGateState(audit_enabled=False, audit_passes=0, revision_passes=0),
        status="ok",
        provider=provider,
        model=None,
        route_id="executor",
        persona_contract_version="0.2.0",
        persona_id="io-ii:v1.4.2",
        logging_policy={"content": "disabled"},
    )


def test_engine_rejects_capability_meta_with_forbidden_keys(monkeypatch):
    # Ensure parsing returns a model string
    import io_iii.routing as routing

    monkeypatch.setattr(routing, "_parse_target", lambda _t: ("local", "qwen3:8b"), raising=False)

    reg = CapabilityRegistry([LeakyCapability()])
    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: FakeProvider(),
        challenger_fn=None,
        capability_registry=reg,
    )

    cfg = types.SimpleNamespace(
        providers={},
        routing={"routing_table": {}},
        logging={"schema": "test"},
        config_dir=".",
    )

    state = _make_state(provider="ollama")
    with pytest.raises(ValueError):
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="hello",
            audit=False,
            deps=deps,
            capability_id="test.leaky",
            capability_payload={"a": 1},
        )


def test_metadata_logger_rejects_nested_forbidden_keys(tmp_path):
    logging_cfg = {
        "logging": {"metadata": {"enabled": True}},
        "storage": {"metadata_log_dir": str(tmp_path)},
    }

    with pytest.raises(ValueError):
        append_metadata(logging_cfg, {"ok": True, "nested": {"content": "nope"}})


def test_metadata_logger_allows_safe_nested_structures(tmp_path):
    logging_cfg = {
        "logging": {"metadata": {"enabled": True}},
        "storage": {"metadata_log_dir": str(tmp_path)},
    }

    p = append_metadata(logging_cfg, {"ok": True, "nested": {"trace_steps": 3}})
    assert p is not None