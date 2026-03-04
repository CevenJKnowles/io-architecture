from __future__ import annotations

import types

import io_iii.core.engine as engine
from io_iii.core.session_state import AuditGateState, RouteInfo, SessionState


class FakeProvider:
    """Deterministic provider stub used to exercise the challenger path."""

    def __init__(self):
        self.calls: list[dict[str, str]] = []

    def generate(self, model: str, prompt: str) -> str:
        self.calls.append({"model": model, "prompt": prompt})

        # Challenger prompt should return strict JSON.
        if "You are IO-III Challenger" in prompt or "Respond in strict JSON" in prompt:
            return '{"verdict": "pass", "issues": [], "high_risk_claims": [], "suggested_fixes": []}'

        # Executor draft.
        return "DRAFT: ok"


def test_engine_challenger_uses_injected_provider_factory(monkeypatch):
    """
    Regression test:

    Ensures that when audit is enabled, the default challenger path does not
    reference an out-of-scope provider factory (previously a NameError).

    The test keeps everything deterministic by injecting:
    - a fake provider factory
    - a deterministic route snapshot
    - deterministic challenger route resolution
    """

    fake_provider = FakeProvider()

    def fake_ollama_provider_factory(_providers_cfg):
        return fake_provider

    # Patch parse_target for both executor and challenger paths.
    def fake_parse_target(_target: str):
        return ("local", "qwen3:8b")

    monkeypatch.setattr(engine, "resolve_route", lambda **_kwargs: types.SimpleNamespace(
        selected_provider="ollama",
        selected_target="local:qwen3:8b",
    ))

    import io_iii.routing as routing
    monkeypatch.setattr(routing, "_parse_target", fake_parse_target, raising=False)

    cfg = types.SimpleNamespace(
        config_dir=".",
        providers={},
        routing={"routing_table": {}},
        logging={"schema": "test"},
    )

    state = SessionState(
        request_id="20260304T000000Z-test",
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
        audit=AuditGateState(audit_enabled=True, audit_passes=0, revision_passes=0),
        status="ok",
        provider="ollama",
        model=None,
        route_id="executor",
        persona_contract_version="0.2.0",
        persona_id="io-ii:v1.4.2",
        logging_policy={"content": "disabled"},
    )

    state2, result = engine.run(
        cfg=cfg,
        session_state=state,
        user_prompt="Return one word.",
        audit=True,
        ollama_provider_factory=fake_ollama_provider_factory,
    )

    assert state2.status == "ok"
    assert result.message == "DRAFT: ok"

    # One executor call + one challenger call.
    assert len(fake_provider.calls) == 2
    assert any("IO-III Challenger" in c["prompt"] for c in fake_provider.calls)
    