from __future__ import annotations

import io_iii.core.engine as engine
from io_iii.capabilities.builtins import builtin_registry
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.session_state import AuditGateState, RouteInfo, SessionState


def _make_state() -> SessionState:
    return SessionState(
        request_id="req-demo",
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


def test_demo_capability_json_pretty_formats_deterministically() -> None:
    deps = RuntimeDependencies(
        ollama_provider_factory=None,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )

    payload = {"name": "Ada", "skills": ["math", "logic", "programming"], "year": 1843}

    _state, res = engine.run(
        cfg=None,
        session_state=_make_state(),
        user_prompt="x",
        audit=False,
        deps=deps,
        capability_id="cap.json_pretty",
        capability_payload=payload,
    )

    pretty = res.meta["capability"]["output"]["pretty"]
    assert pretty == (
        "{\n"
        "  \"name\": \"Ada\",\n"
        "  \"skills\": [\n"
        "    \"math\",\n"
        "    \"logic\",\n"
        "    \"programming\"\n"
        "  ],\n"
        "  \"year\": 1843\n"
        "}"
    )


def test_demo_capability_validate_json_schema_valid() -> None:
    deps = RuntimeDependencies(
        ollama_provider_factory=None,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )

    payload = {
        "schema": {
            "type": "object",
            "required": ["name", "age"],
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
        "data": {"name": "Ada", "age": 36},
    }

    _state, res = engine.run(
        cfg=None,
        session_state=_make_state(),
        user_prompt="x",
        audit=False,
        deps=deps,
        capability_id="cap.validate_json_schema",
        capability_payload=payload,
    )

    out = res.meta["capability"]["output"]
    assert out["valid"] is True
    assert out["error_count"] == 0
    assert out["errors"] == []


def test_demo_capability_validate_json_schema_type_mismatch() -> None:
    deps = RuntimeDependencies(
        ollama_provider_factory=None,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )

    payload = {
        "schema": {
            "type": "object",
            "required": ["name", "age"],
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
        "data": {"name": "Ada", "age": "36"},
    }

    _state, res = engine.run(
        cfg=None,
        session_state=_make_state(),
        user_prompt="x",
        audit=False,
        deps=deps,
        capability_id="cap.validate_json_schema",
        capability_payload=payload,
    )

    out = res.meta["capability"]["output"]
    assert out["valid"] is False
    assert out["error_count"] >= 1
    assert any(e["path"] == "/age" and e["code"] == "TYPE_MISMATCH" for e in out["errors"])
