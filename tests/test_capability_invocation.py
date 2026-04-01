from __future__ import annotations

import types
import time

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
    assert isinstance(res.meta["capability"].get("duration_ms"), int)
    assert res.meta["capability"]["duration_ms"] >= 0


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


class SlowCapability:
    @property
    def spec(self) -> CapabilitySpec:
        return CapabilitySpec(
            capability_id="test.slow",
            version="v0",
            category=CapabilityCategory.COMPUTATION,
            description="Test-only slow capability.",
            bounds=CapabilityBounds(max_calls=1, timeout_ms=50, max_input_chars=1000, max_output_chars=1000),
        )

    def invoke(self, ctx: CapabilityContext, payload):
        time.sleep(0.5)  # 500ms > 50ms timeout
        return CapabilityResult(ok=True, output={"done": True})


class BigOutputCapability:
    @property
    def spec(self) -> CapabilitySpec:
        return CapabilitySpec(
            capability_id="test.bigout",
            version="v0",
            category=CapabilityCategory.TRANSFORMATION,
            description="Test-only large-output capability.",
            bounds=CapabilityBounds(max_calls=1, timeout_ms=500, max_input_chars=1000, max_output_chars=10),
        )

    def invoke(self, ctx: CapabilityContext, payload):
        return CapabilityResult(ok=True, output={"data": "x" * 1000})


def test_capability_enforces_timeout(monkeypatch):
    reg = CapabilityRegistry([SlowCapability()])
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
    with pytest.raises(ValueError, match="CAPABILITY_TIMEOUT"):
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="x",
            audit=False,
            deps=deps,
            capability_id="test.slow",
            capability_payload={},
        )


def test_capability_enforces_output_size(monkeypatch):
    reg = CapabilityRegistry([BigOutputCapability()])
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
    with pytest.raises(ValueError, match="CAPABILITY_OUTPUT_TOO_LARGE"):
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="x",
            audit=False,
            deps=deps,
            capability_id="test.bigout",
            capability_payload={},
        )


@pytest.mark.parametrize(
    "bad_payload",
    [
        "not-a-dict",
        123,
        [1, 2, 3],
        [("a", 1)],  # list is not allowed even if dict() would accept it
        {1: "x"},  # non-string key
    ],
)
def test_capability_rejects_invalid_payload_types(monkeypatch, bad_payload):
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
    with pytest.raises(ValueError) as ei:
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="x",
            audit=False,
            deps=deps,
            capability_id="test.echo",
            capability_payload=bad_payload,
        )

    assert str(ei.value).startswith("CAPABILITY_INVALID_PAYLOAD")


def test_engine_sets_latency_ms_on_returned_state():
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
    started_at_ms = int(time.time() * 1000)
    state = SessionState(
        request_id="test-latency",
        started_at_ms=started_at_ms,
        mode="executor",
        config_dir=".",
        route=RouteInfo(
            mode="executor",
            primary_target=None,
            secondary_target=None,
            selected_target=None,
            selected_provider="null",
            fallback_used=False,
            fallback_reason=None,
            boundaries={},
        ),
        audit=AuditGateState(audit_enabled=False),
        status="ok",
        provider="null",
        model=None,
        route_id="executor",
        persona_contract_version="1.0",
        logging_policy={},
    )
    state2, _res = engine.run(
        cfg=cfg,
        session_state=state,
        user_prompt="x",
        audit=False,
        deps=deps,
        capability_id="test.echo",
        capability_payload={"a": 1},
    )
    assert state2.latency_ms is not None
    assert isinstance(state2.latency_ms, int)
    assert state2.latency_ms >= 0
