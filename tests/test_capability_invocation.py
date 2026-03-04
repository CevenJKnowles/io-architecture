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


class EchoCapability:
    @property
    def spec(self) -> CapabilitySpec:
        return CapabilitySpec(
            capability_id="test.echo",
            version="v0",
            category=CapabilityCategory.TRANSFORMATION,
            description="Test-only echo capability.",
            bounds=CapabilityBounds(max_calls=1, timeout_ms=100, max_input_chars=1000, max_output_chars=1000),
        )

    def invoke(self, ctx: CapabilityContext, payload):
        return CapabilityResult(ok=True, output={"echo": dict(payload)})


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


def test_capability_invocation_attaches_meta_for_ollama_route(monkeypatch):
    # Ensure parsing returns a model string
    import io_iii.routing as routing
    monkeypatch.setattr(routing, "_parse_target", lambda _t: ("local", "qwen3:8b"), raising=False)

    reg = CapabilityRegistry([EchoCapability()])
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
    _s2, res = engine.run(
        cfg=cfg,
        session_state=state,
        user_prompt="hello",
        audit=False,
        deps=deps,
        capability_id="test.echo",
        capability_payload={"a": 1},
    )

    assert "capability" in res.meta
    assert res.meta["capability"]["capability_id"] == "test.echo"
    assert res.meta["capability"]["output"] == {"echo": {"a": 1}}


def test_capability_rejects_nonexistent_id(monkeypatch):
    reg = CapabilityRegistry([])
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

    state = _make_state(provider="null")
    with pytest.raises(KeyError):
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="x",
            audit=False,
            deps=deps,
            capability_id="missing.cap",
            capability_payload={},
        )