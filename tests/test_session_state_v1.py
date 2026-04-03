"""
test_session_state_v1.py — Phase 4 M4.4 SessionState v1 contract tests.

Verifies the M4.4 additions to SessionState:
- schema_version sentinel ("v1" required)
- task_spec_id linkage (Optional[str]; None valid for CLI path; empty string invalid)
- write-once field pass-through across engine _replace() rebuilds
- orchestrator propagates task_spec_id from TaskSpec to SessionState
- full invariant check (validate_session_state) covers all new fields
"""
from __future__ import annotations

import time
import types

import pytest

from io_iii.core.session_state import (
    AuditGateState,
    RouteInfo,
    SessionState,
    validate_session_state,
    MAX_AUDIT_PASSES,
    MAX_REVISION_PASSES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_state(**overrides) -> SessionState:
    """Construct a minimal valid SessionState v1 for testing."""
    defaults = dict(
        request_id="req-test",
        started_at_ms=0,
    )
    defaults.update(overrides)
    return SessionState(**defaults)


# ---------------------------------------------------------------------------
# schema_version sentinel
# ---------------------------------------------------------------------------

def test_schema_version_default_is_v1():
    """Default schema_version must be 'v1'."""
    s = _minimal_state()
    assert s.schema_version == "v1"


def test_schema_version_validates_as_v1():
    """validate_session_state must pass for schema_version == 'v1'."""
    s = _minimal_state()
    validate_session_state(s)  # must not raise


def test_schema_version_wrong_value_raises():
    """validate_session_state must reject schema_version != 'v1'."""
    s = _minimal_state(schema_version="v0")
    with pytest.raises(ValueError, match="schema_version"):
        validate_session_state(s)


def test_schema_version_empty_string_raises():
    """Empty schema_version must fail validation."""
    s = _minimal_state(schema_version="")
    with pytest.raises(ValueError, match="schema_version"):
        validate_session_state(s)


# ---------------------------------------------------------------------------
# task_spec_id field
# ---------------------------------------------------------------------------

def test_task_spec_id_default_is_none():
    """task_spec_id must default to None (CLI paths do not supply a TaskSpec)."""
    s = _minimal_state()
    assert s.task_spec_id is None


def test_task_spec_id_none_passes_validation():
    """None task_spec_id must pass validate_session_state — valid for CLI path."""
    s = _minimal_state(task_spec_id=None)
    validate_session_state(s)  # must not raise


def test_task_spec_id_set_passes_validation():
    """A non-empty task_spec_id must pass validate_session_state."""
    s = _minimal_state(task_spec_id="ts-abc123def456")
    validate_session_state(s)  # must not raise
    assert s.task_spec_id == "ts-abc123def456"


def test_task_spec_id_empty_string_raises():
    """Empty string task_spec_id must be rejected — empty identifier is invalid."""
    s = _minimal_state(task_spec_id="")
    with pytest.raises(ValueError, match="task_spec_id"):
        validate_session_state(s)


def test_task_spec_id_whitespace_only_raises():
    """Whitespace-only task_spec_id must be rejected."""
    s = _minimal_state(task_spec_id="   ")
    with pytest.raises(ValueError, match="task_spec_id"):
        validate_session_state(s)


# ---------------------------------------------------------------------------
# Write-once field pass-through via engine _replace()
# ---------------------------------------------------------------------------

def test_write_once_fields_survive_engine_replace():
    """
    Write-once fields (request_id, started_at_ms, task_spec_id, schema_version)
    must be preserved unchanged across engine _replace() rebuilds.

    This verifies that the _replace() implementation in engine.py (using __dict__.copy())
    copies the new v1 fields through without dropping or altering them.
    """
    # Import the private engine helper directly to test the copy semantics.
    from io_iii.core.engine import _replace

    original = SessionState(
        request_id="req-write-once",
        started_at_ms=1_000_000,
        task_spec_id="ts-deadbeef0000",
        schema_version="v1",
    )

    # Simulate what the engine does post-execution: only mutable fields change.
    rebuilt = _replace(original, latency_ms=42, status="ok", provider="null", model=None)

    # Write-once fields must be identical.
    assert rebuilt.request_id == "req-write-once"
    assert rebuilt.started_at_ms == 1_000_000
    assert rebuilt.task_spec_id == "ts-deadbeef0000"
    assert rebuilt.schema_version == "v1"

    # Engine-mutable fields updated as expected.
    assert rebuilt.latency_ms == 42
    assert rebuilt.status == "ok"


def test_rebuilt_state_still_passes_validation():
    """
    A state rebuilt via engine _replace() with valid mutable fields
    must still pass validate_session_state.
    """
    from io_iii.core.engine import _replace

    original = SessionState(
        request_id="req-rebuild-valid",
        started_at_ms=0,
        task_spec_id="ts-rebuildtest00",
    )
    rebuilt = _replace(original, latency_ms=10, status="ok")
    validate_session_state(rebuilt)  # must not raise


# ---------------------------------------------------------------------------
# Orchestrator propagates task_spec_id
# ---------------------------------------------------------------------------

def test_orchestrator_propagates_task_spec_id():
    """
    orchestrator.run must propagate task_spec.task_spec_id into the returned
    SessionState. This is the core M4.4 linkage contract.
    """
    import io_iii.core.orchestrator as orchestrator
    from io_iii.core.task_spec import TaskSpec
    from io_iii.core.dependencies import RuntimeDependencies

    cfg = types.SimpleNamespace(
        config_dir=".",
        providers={"providers": {"ollama": {"enabled": False}}},
        routing={
            "routing_table": {
                "rules": {"boundaries": {}},
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
    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
    )

    spec = TaskSpec.create(mode="executor", prompt="M4.4 linkage test.")
    state2, _ = orchestrator.run(task_spec=spec, cfg=cfg, deps=deps)

    # The returned state must carry the TaskSpec's identifier.
    assert state2.task_spec_id == spec.task_spec_id
    assert state2.task_spec_id is not None
    assert state2.task_spec_id.startswith("ts-")


def test_orchestrator_returned_state_passes_v1_validation():
    """
    The state returned by orchestrator.run must satisfy all v1 invariants
    including schema_version == 'v1' and valid task_spec_id.
    """
    import io_iii.core.orchestrator as orchestrator
    from io_iii.core.task_spec import TaskSpec
    from io_iii.core.dependencies import RuntimeDependencies

    cfg = types.SimpleNamespace(
        config_dir=".",
        providers={"providers": {"ollama": {"enabled": False}}},
        routing={
            "routing_table": {
                "rules": {"boundaries": {}},
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
    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
    )

    spec = TaskSpec.create(mode="executor", prompt="v1 validation test.")
    state2, _ = orchestrator.run(task_spec=spec, cfg=cfg, deps=deps)

    validate_session_state(state2)  # must not raise


# ---------------------------------------------------------------------------
# CLI construction path: task_spec_id=None is valid
# ---------------------------------------------------------------------------

def test_cli_construction_without_task_spec_id_is_valid():
    """
    CLI paths that construct SessionState directly (without TaskSpec) must
    remain valid. task_spec_id=None is the correct value for this path.
    """
    # Reproduce the pattern used in cli.py cmd_run and cmd_capability.
    route = RouteInfo(
        mode="executor",
        primary_target=None,
        secondary_target=None,
        selected_target=None,
        selected_provider="null",
        fallback_used=False,
        fallback_reason=None,
    )
    state = SessionState(
        request_id="req-cli-direct",
        started_at_ms=int(time.time() * 1000),
        mode="executor",
        config_dir="./architecture/runtime/config",
        route=route,
        audit=AuditGateState(audit_enabled=False),
        status="ok",
        provider="null",
        model=None,
        route_id="executor",
        logging_policy={"content": "disabled"},
        # task_spec_id intentionally omitted (defaults to None)
    )
    validate_session_state(state)  # must not raise
    assert state.task_spec_id is None
    assert state.schema_version == "v1"
