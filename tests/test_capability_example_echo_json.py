from __future__ import annotations

import pytest

import io_iii.core.engine as engine
from io_iii.capabilities.builtins import builtin_registry
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.session_state import AuditGateState, RouteInfo, SessionState


def _make_state() -> SessionState:
    return SessionState(
        request_id="req-1",
        started_at_ms=0,
        mode="executor",
        config_dir=".",
        route=RouteInfo(
            mode="executor",
            primary_target="local",
            secondary_target=None,
            selected_target="local",
            selected_provider="null",
            fallback_used=False,
            fallback_reason=None,
            boundaries={"provider": "null"},
        ),
        audit=AuditGateState(audit_enabled=False),
        status="ok",
        provider="null",
        model=None,
        route_id="executor",
        persona_contract_version="1.0",
        persona_id=None,
        logging_policy={"metadata_enabled": True, "content_enabled": False},
    )


def test_builtin_capability_echo_json_is_invokable() -> None:
    deps = RuntimeDependencies(
        ollama_provider_factory=None,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )

    state, res = engine.run(
        cfg=None,
        session_state=_make_state(),
        user_prompt="Return one word.",
        audit=False,
        deps=deps,
        capability_id="cap.echo_json",
        capability_payload={"a": 1, "b": 2},
    )

    assert res.meta["capability"]["capability_id"] == "cap.echo_json"
    assert res.meta["capability"]["ok"] is True
    out = res.meta["capability"]["output"]
    assert "summary" in out
    assert out["summary"]["top_level_keys"] == 2
    assert isinstance(out["summary"]["payload_bytes"], int)


def test_builtin_capability_enforces_payload_bounds() -> None:
    deps = RuntimeDependencies(
        ollama_provider_factory=None,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )

    # Exceed max_input_chars (4096) by constructing a large string value
    big = "x" * 5000

    with pytest.raises(ValueError, match="CAPABILITY_INPUT_TOO_LARGE"):
        engine.run(
            cfg=None,
            session_state=_make_state(),
            user_prompt="Return one word.",
            audit=False,
            deps=deps,
            capability_id="cap.echo_json",
            capability_payload={"big": big},
        )
