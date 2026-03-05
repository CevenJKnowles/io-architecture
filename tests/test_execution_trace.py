from __future__ import annotations

import types

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


def _make_state(provider: str = "null") -> SessionState:
    route = RouteInfo(
        mode="executor",
        primary_target=None,
        secondary_target=None,
        selected_target=None,
        selected_provider=provider,
        fallback_used=False,
        fallback_reason=None,
        boundaries={"single_voice_output": True},
    )
    return SessionState(
        request_id="trace-test",
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
        persona_id=None,
        logging_policy={"content": "disabled"},
    )


def test_execution_trace_attached_and_ordered_for_null_route_with_capability():
    cfg = types.SimpleNamespace(
        providers={},
        routing={"routing_table": {}},
        logging={"schema": "test"},
        config_dir=".",
    )

    reg = CapabilityRegistry([EchoCapability()])
    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=reg,
    )

    state = _make_state(provider="null")
    _s2, res = engine.run(
        cfg=cfg,
        session_state=state,
        user_prompt="x",
        audit=False,
        deps=deps,
        capability_id="test.echo",
        capability_payload={"a": 1},
    )

    assert "trace" in res.meta
    trace = res.meta["trace"]
    assert trace["schema"] == "io-iii-execution-trace"
    assert trace["schema_version"] == "v1.0"
    assert trace["trace_id"] == "trace-test"

    steps = trace["steps"]
    assert isinstance(steps, list)
    assert [s["stage"] for s in steps] == ["capability_execution", "provider_run"]

    cap_step = steps[0]
    assert cap_step["meta"]["capability_id"] == "test.echo"
    assert cap_step["meta"]["success"] is True
    assert cap_step["meta"]["error_code"] is None

    for s in steps:
        assert isinstance(s.get("duration_ms"), int)
        assert s["duration_ms"] >= 0
        assert isinstance(s.get("started_at_ms"), int)

    # Content-safety guard (defensive): ensure no forbidden content keys appear in the trace.
    forbidden = {"prompt", "completion", "draft", "revision", "content", "message", "output"}

    def _walk_keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from _walk_keys(v)
        elif isinstance(obj, list):
            for it in obj:
                yield from _walk_keys(it)

    all_keys = set(_walk_keys(trace))
    assert not (forbidden & all_keys)
