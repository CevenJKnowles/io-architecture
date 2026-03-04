from __future__ import annotations

import types

import io_iii.core.engine as engine
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.session_state import AuditGateState, RouteInfo, SessionState


class FakeProvider:
    def __init__(self):
        self.calls = []

    def generate(self, model: str, prompt: str) -> str:
        self.calls.append({"model": model, "prompt": prompt})
        return "ok"


def test_engine_prefers_dependency_bundle_provider_factory(monkeypatch):
    fake_provider = FakeProvider()

    def injected_factory(_providers_cfg):
        return fake_provider

    # Force resolve_route usage already present in engine paths.
    import io_iii.routing as routing
    monkeypatch.setattr(routing, "_parse_target", lambda _t: ("local", "qwen3:8b"), raising=False)

    cfg = types.SimpleNamespace(
        config_dir=".",
        providers={},
        routing={"routing_table": {}},
        logging={"schema": "test"},
    )

    # Minimal route snapshot for ollama path
    state = SessionState(
        request_id="test",
        started_at_ms=0,
        mode="executor",
        config_dir="./architecture/runtime/config",
        route=RouteInfo(
            mode="executor",
            primary_target="local:qwen3:8b",
            secondary_target=None,
            selected_target="local:qwen3:8b",
            selected_provider="ollama",
            fallback_used=False,
            fallback_reason=None,
            boundaries={"single_voice_output": True},
        ),
        audit=AuditGateState(audit_enabled=False, audit_passes=0, revision_passes=0),
        status="ok",
        provider="ollama",
        model=None,
        route_id="executor",
        persona_contract_version="0.2.0",
        persona_id="io-ii:v1.4.2",
        logging_policy={"content": "disabled"},
    )

    deps = RuntimeDependencies(ollama_provider_factory=injected_factory)

    _state2, result = engine.run(cfg=cfg, session_state=state, user_prompt="x", audit=False, deps=deps)

    assert result.message == "ok"
    assert len(fake_provider.calls) == 1
    