"""
test_orchestrator_bounds.py — Phase 4 M4.2 orchestration boundary tests.

Verifies the single-run orchestration contract defined in ADR-012:
- exactly one route resolution
- exactly one engine delegation
- at most one capability
- no planner/branching/loop semantics
- audit flag pass-through (not invoked by orchestrator itself)
- invariant preservation on returned SessionState

All tests use a null-provider path (empty providers_cfg forces ollama fallback to null).
Monkeypatching targets the orchestrator module namespace, never the engine namespace directly.
"""
from __future__ import annotations

import types
from typing import Any, Dict

import pytest

from io_iii.capabilities.builtins import builtin_registry
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.task_spec import TaskSpec
import io_iii.core.orchestrator as orchestrator


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

def _null_cfg() -> types.SimpleNamespace:
    """
    Minimal cfg that forces a null provider.

    resolve_route checks `if providers_cfg:` before calling _is_provider_enabled,
    so an empty dict is treated as "no check" (ollama would be selected). We must
    explicitly disable ollama to guarantee the null fallback path.

    resolve_route will:
    - parse "local:test-model" → provider="ollama"
    - find ollama disabled in providers_cfg
    - fall back to null (selected_provider="null", selected_target=None)
    """
    return types.SimpleNamespace(
        config_dir=".",
        providers={"providers": {"ollama": {"enabled": False}}},
        routing={
            "routing_table": {
                "rules": {
                    "boundaries": {},
                },
                "modes": {
                    "executor": {
                        "primary": "local:test-model",
                        "secondary": "local:fallback-model",
                    }
                },
            }
        },
        logging={"schema": "test"},
    )


def _null_deps() -> RuntimeDependencies:
    """Minimal deps bundle with no live provider and builtin capability registry."""
    return RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_orchestrator_basic_null_route_returns_valid_result():
    """
    Core contract: orchestrator.run returns (SessionState, ExecutionResult) for a
    well-formed TaskSpec on a null provider route.
    """
    spec = TaskSpec.create(mode="executor", prompt="Hello world.")

    state2, result = orchestrator.run(
        task_spec=spec,
        cfg=_null_cfg(),
        deps=_null_deps(),
    )

    assert state2 is not None
    assert result is not None
    assert state2.mode == "executor"
    assert state2.provider == "null"
    assert state2.status == "ok"
    assert state2.request_id is not None
    assert state2.latency_ms is not None
    assert state2.latency_ms >= 0


def test_orchestrator_request_id_injected():
    """Caller-supplied request_id must be propagated to SessionState."""
    spec = TaskSpec.create(mode="executor", prompt="ID test.")
    rid = "test-request-id-42"

    state2, _ = orchestrator.run(
        task_spec=spec,
        cfg=_null_cfg(),
        deps=_null_deps(),
        request_id=rid,
    )

    assert state2.request_id == rid


def test_orchestrator_generates_request_id_when_not_supplied():
    """Orchestrator must generate a stable non-empty request_id when none is provided."""
    spec = TaskSpec.create(mode="executor", prompt="Auto-ID test.")

    state2, _ = orchestrator.run(task_spec=spec, cfg=_null_cfg(), deps=_null_deps())

    assert isinstance(state2.request_id, str)
    assert len(state2.request_id) > 0


# ---------------------------------------------------------------------------
# Invariant preservation
# ---------------------------------------------------------------------------

def test_orchestrator_returned_state_passes_invariants():
    """
    Returned SessionState must satisfy all SessionState v0 invariants.
    validate_session_state is called internally; this test confirms no bypass.
    """
    from io_iii.core.session_state import validate_session_state

    spec = TaskSpec.create(mode="executor", prompt="Invariant check.")

    state2, _ = orchestrator.run(task_spec=spec, cfg=_null_cfg(), deps=_null_deps())

    validate_session_state(state2)  # must not raise


# ---------------------------------------------------------------------------
# Single-run constraint: capability bounds
# ---------------------------------------------------------------------------

def test_orchestrator_rejects_multi_capability_task_spec():
    """
    M4.2 single-run: TaskSpec with >1 capability must be rejected before engine call.
    This preserves the explicit-only, one-capability-per-run contract.
    """
    spec = TaskSpec.create(
        mode="executor",
        prompt="Multi-cap.",
        capabilities=["cap.echo_json", "cap.json_pretty"],
    )

    with pytest.raises(ValueError, match="ORCHESTRATOR_SINGLE_RUN"):
        orchestrator.run(task_spec=spec, cfg=_null_cfg(), deps=_null_deps())


def test_orchestrator_single_capability_forwarded_to_engine(monkeypatch):
    """
    Single capability in task_spec.capabilities must be forwarded as capability_id
    to engine.run. Orchestrator must not suppress or alter the capability ID.
    """
    captured: Dict[str, Any] = {"capability_id": "NOT_SET"}
    real_engine_run = orchestrator._engine_run

    def capturing_engine_run(**kwargs):
        captured["capability_id"] = kwargs.get("capability_id")
        return real_engine_run(**kwargs)

    monkeypatch.setattr(orchestrator, "_engine_run", capturing_engine_run)

    spec = TaskSpec.create(
        mode="executor",
        prompt="Cap forward.",
        capabilities=["cap.echo_json"],
    )
    orchestrator.run(task_spec=spec, cfg=_null_cfg(), deps=_null_deps())

    assert captured["capability_id"] == "cap.echo_json"


def test_orchestrator_no_capabilities_passes_none_to_engine(monkeypatch):
    """
    Empty capabilities list must result in capability_id=None being passed to engine.
    Orchestrator must not fabricate a capability_id.
    """
    captured: Dict[str, Any] = {"capability_id": "NOT_SET"}
    real_engine_run = orchestrator._engine_run

    def capturing_engine_run(**kwargs):
        captured["capability_id"] = kwargs.get("capability_id")
        return real_engine_run(**kwargs)

    monkeypatch.setattr(orchestrator, "_engine_run", capturing_engine_run)

    spec = TaskSpec.create(mode="executor", prompt="No cap.")
    orchestrator.run(task_spec=spec, cfg=_null_cfg(), deps=_null_deps())

    assert captured["capability_id"] is None


# ---------------------------------------------------------------------------
# Engine delegation: exactly once
# ---------------------------------------------------------------------------

def test_orchestrator_engine_delegated_exactly_once(monkeypatch):
    """
    Core ADR-012 constraint: engine.run must be called exactly once per
    orchestrator.run call. Any loop, retry, or recursive delegation is a violation.
    """
    call_count: Dict[str, int] = {"n": 0}
    real_engine_run = orchestrator._engine_run

    def counting_engine_run(**kwargs):
        call_count["n"] += 1
        return real_engine_run(**kwargs)

    monkeypatch.setattr(orchestrator, "_engine_run", counting_engine_run)

    spec = TaskSpec.create(mode="executor", prompt="Count engine calls.")
    orchestrator.run(task_spec=spec, cfg=_null_cfg(), deps=_null_deps())

    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# Route resolution: exactly once, from task_spec.mode
# ---------------------------------------------------------------------------

def test_orchestrator_route_resolved_once_from_task_spec_mode(monkeypatch):
    """
    ADR-012: route must be resolved exactly once from task_spec.mode.
    No re-resolution based on engine output is permitted.
    """
    resolve_calls: Dict[str, list] = {"modes": []}
    real_resolve = orchestrator.resolve_route

    def counting_resolve(*, routing_cfg, mode, **kwargs):
        resolve_calls["modes"].append(mode)
        return real_resolve(routing_cfg=routing_cfg, mode=mode, **kwargs)

    monkeypatch.setattr(orchestrator, "resolve_route", counting_resolve)

    spec = TaskSpec.create(mode="executor", prompt="Route test.")
    orchestrator.run(task_spec=spec, cfg=_null_cfg(), deps=_null_deps())

    assert resolve_calls["modes"] == ["executor"]


# ---------------------------------------------------------------------------
# Audit flag pass-through
# ---------------------------------------------------------------------------

def test_orchestrator_audit_defaults_to_false():
    """
    Audit must default to False. The returned state must reflect this.
    Challenger must not be invoked when audit is not explicitly enabled.
    """
    spec = TaskSpec.create(mode="executor", prompt="No audit.")

    state2, result = orchestrator.run(task_spec=spec, cfg=_null_cfg(), deps=_null_deps())

    assert state2.audit.audit_enabled is False
    assert result.audit_meta is None


def test_orchestrator_audit_true_reflected_in_state():
    """
    When audit=True is passed, the returned SessionState must reflect audit_enabled=True.
    The engine owns challenger execution; orchestrator only sets the flag.
    (Challenger is not exercised here since null provider skips the ollama path.)
    """
    spec = TaskSpec.create(mode="executor", prompt="Audit flag.")

    state2, _ = orchestrator.run(
        task_spec=spec,
        cfg=_null_cfg(),
        deps=_null_deps(),
        audit=True,
    )

    assert state2.audit.audit_enabled is True


# ---------------------------------------------------------------------------
# Type guards
# ---------------------------------------------------------------------------

def test_orchestrator_rejects_non_taskspec():
    """Type guard: non-TaskSpec input must raise TypeError before any execution."""
    with pytest.raises(TypeError, match="TaskSpec"):
        orchestrator.run(
            task_spec={"mode": "executor", "prompt": "Bad"},  # type: ignore[arg-type]
            cfg=_null_cfg(),
            deps=_null_deps(),
        )


def test_orchestrator_rejects_non_runtime_dependencies():
    """Type guard: non-RuntimeDependencies deps must raise TypeError before any execution."""
    spec = TaskSpec.create(mode="executor", prompt="Bad deps.")

    with pytest.raises(TypeError, match="RuntimeDependencies"):
        orchestrator.run(
            task_spec=spec,
            cfg=_null_cfg(),
            deps=object(),  # type: ignore[arg-type]
        )
