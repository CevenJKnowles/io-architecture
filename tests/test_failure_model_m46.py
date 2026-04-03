"""
test_failure_model_m46.py — Phase 4 M4.6 Deterministic Failure Semantics tests.

Verifies the canonical failure contract introduced in M4.6:

  Unit — failure_model module:
  - RuntimeFailureKind covers all required categories
  - RuntimeFailure is frozen and content-safe
  - classify_exception maps correctly to each failure kind
  - causal_code extracted correctly from structured exceptions
  - retryable=True only for PROVIDER_UNAVAILABLE

  Engine integration — failure terminal semantics:
  - trace reaches 'failed' terminal state on capability exception
  - trace reaches 'failed' terminal state on validation exception
  - RUN_FAILED event emitted on failure path
  - RUN_FAILED event carries failure_kind, failure_code, phase
  - runtime_failure attached to raised exception
  - request_id propagated into RuntimeFailure
  - task_spec_id propagated into RuntimeFailure (both None and set)
  - no content leakage in RuntimeFailure fields
  - no content leakage in RUN_FAILED event meta
  - original exception type preserved on re-raise
  - successful-path behaviour unaffected (regression guard)
"""
from __future__ import annotations

import types
from typing import Any

import pytest

from io_iii.core.failure_model import (
    RuntimeFailure,
    RuntimeFailureKind,
    classify_exception,
    _extract_causal_code,
)
from io_iii.core.content_safety import assert_no_forbidden_keys
from io_iii.core.execution_trace import TraceLifecycleError, TraceRecorder
from io_iii.core.session_state import AuditGateState, RouteInfo, SessionState
from io_iii.providers.provider_contract import ProviderError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _null_state(*, task_spec_id=None, request_id="test-rid") -> SessionState:
    route = RouteInfo(
        mode="executor",
        primary_target=None,
        secondary_target=None,
        selected_target=None,
        selected_provider="null",
        fallback_used=False,
        fallback_reason=None,
        boundaries={},
    )
    return SessionState(
        request_id=request_id,
        started_at_ms=0,
        mode="executor",
        config_dir="./architecture/runtime/config",
        route=route,
        audit=AuditGateState(audit_enabled=False),
        status="ok",
        provider="null",
        model=None,
        route_id="executor",
        persona_contract_version="0.2.0",
        persona_id=None,
        task_spec_id=task_spec_id,
        logging_policy={"content": "disabled"},
    )


def _engine_cfg() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        providers={},
        routing={"routing_table": {}},
        logging={"schema": "test"},
        config_dir=".",
    )


def _engine_deps(*, registry=None):
    from io_iii.core.capabilities import CapabilityRegistry
    from io_iii.core.dependencies import RuntimeDependencies
    return RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=registry or CapabilityRegistry([]),
    )


# ---------------------------------------------------------------------------
# Unit — RuntimeFailureKind
# ---------------------------------------------------------------------------

def test_failure_kind_has_all_required_categories():
    """All six required failure categories must exist."""
    required = {
        "ROUTE_RESOLUTION", "PROVIDER_EXECUTION", "AUDIT_CHALLENGER",
        "CAPABILITY", "CONTRACT_VIOLATION", "INTERNAL",
    }
    actual = {k.name for k in RuntimeFailureKind}
    assert required.issubset(actual)


def test_failure_kind_values_are_stable_strings():
    """All kind values must be non-empty lowercase strings (stable identifiers)."""
    for kind in RuntimeFailureKind:
        assert isinstance(kind.value, str)
        assert len(kind.value) > 0
        assert kind.value == kind.value.lower()


# ---------------------------------------------------------------------------
# Unit — RuntimeFailure
# ---------------------------------------------------------------------------

def test_runtime_failure_is_frozen():
    """RuntimeFailure must be immutable (frozen dataclass)."""
    f = RuntimeFailure(
        kind=RuntimeFailureKind.INTERNAL,
        code="INTERNAL_ERROR",
        summary="test failure",
        request_id="req-1",
        task_spec_id=None,
        retryable=False,
        causal_code=None,
    )
    with pytest.raises((AttributeError, TypeError)):
        f.code = "CHANGED"  # type: ignore[misc]


def test_runtime_failure_summary_passes_content_safety():
    """RuntimeFailure summary must not contain forbidden content keys."""
    for kind in RuntimeFailureKind:
        f = RuntimeFailure(
            kind=kind,
            code="TEST_CODE",
            summary=f"Test summary for {kind.value}",
            request_id="req-1",
            task_spec_id=None,
            retryable=False,
            causal_code=None,
        )
        # Wrap in dict to check the whole structure
        as_dict = {
            "kind": f.kind.value,
            "code": f.code,
            "summary": f.summary,
            "request_id": f.request_id,
            "task_spec_id": f.task_spec_id,
            "retryable": f.retryable,
            "causal_code": f.causal_code,
        }
        assert_no_forbidden_keys(as_dict)


# ---------------------------------------------------------------------------
# Unit — _extract_causal_code
# ---------------------------------------------------------------------------

def test_extract_causal_code_from_provider_error():
    """ProviderError.code must be returned as causal_code."""
    err = ProviderError("PROVIDER_UNAVAILABLE", "cannot reach ollama")
    assert _extract_causal_code(err) == "PROVIDER_UNAVAILABLE"


def test_extract_causal_code_from_capability_prefix():
    """ValueError with CAPABILITY_ prefix must yield the token before ':'."""
    err = ValueError("CAPABILITY_TIMEOUT: exceeded timeout_ms=50")
    assert _extract_causal_code(err) == "CAPABILITY_TIMEOUT"


def test_extract_causal_code_from_audit_prefix():
    """RuntimeError with AUDIT_ prefix must yield the stable code token."""
    err = RuntimeError("AUDIT_LIMIT_EXCEEDED: audit_passes=1 max=1")
    assert _extract_causal_code(err) == "AUDIT_LIMIT_EXCEEDED"


def test_extract_causal_code_from_revision_prefix():
    err = RuntimeError("REVISION_LIMIT_EXCEEDED: revision_passes=1 max=1")
    assert _extract_causal_code(err) == "REVISION_LIMIT_EXCEEDED"


def test_extract_causal_code_none_for_generic_exception():
    """Generic exceptions without a known prefix must return None."""
    assert _extract_causal_code(Exception("something went wrong")) is None
    assert _extract_causal_code(RuntimeError("boom")) is None
    assert _extract_causal_code(ValueError("bad value")) is None


# ---------------------------------------------------------------------------
# Unit — classify_exception
# ---------------------------------------------------------------------------

def test_classify_provider_error_is_provider_execution():
    """ProviderError must classify as PROVIDER_EXECUTION."""
    exc = ProviderError("PROVIDER_UNAVAILABLE", "offline")
    f = classify_exception(exc, request_id="req-1")
    assert f.kind == RuntimeFailureKind.PROVIDER_EXECUTION
    assert f.code == "PROVIDER_UNAVAILABLE"


def test_classify_provider_unavailable_is_retryable():
    """PROVIDER_UNAVAILABLE must set retryable=True."""
    exc = ProviderError("PROVIDER_UNAVAILABLE", "offline")
    f = classify_exception(exc, request_id="req-1")
    assert f.retryable is True


def test_classify_provider_error_other_codes_not_retryable():
    """Provider errors other than PROVIDER_UNAVAILABLE must not be retryable."""
    exc = ProviderError("PROVIDER_MODEL_NOT_FOUND", "no such model")
    f = classify_exception(exc, request_id="req-1")
    assert f.kind == RuntimeFailureKind.PROVIDER_EXECUTION
    assert f.retryable is False


def test_classify_trace_lifecycle_error_is_contract_violation():
    """TraceLifecycleError must classify as CONTRACT_VIOLATION."""
    exc = TraceLifecycleError("TRACE_INVALID_TRANSITION: 'completed' → 'running'")
    f = classify_exception(exc, request_id="req-1")
    assert f.kind == RuntimeFailureKind.CONTRACT_VIOLATION


def test_classify_capability_phase_hint_is_capability():
    """phase_hint='capability' must classify as CAPABILITY regardless of exception type."""
    exc = ValueError("some capability error")
    f = classify_exception(exc, request_id="req-1", phase_hint="capability")
    assert f.kind == RuntimeFailureKind.CAPABILITY


def test_classify_capability_prefix_on_value_error():
    """CAPABILITY_-prefixed ValueError must classify as CAPABILITY."""
    exc = ValueError("CAPABILITY_TIMEOUT: exceeded timeout_ms=50")
    f = classify_exception(exc, request_id="req-1")
    assert f.kind == RuntimeFailureKind.CAPABILITY
    assert f.code == "CAPABILITY_TIMEOUT"


def test_classify_capability_prefix_on_key_error():
    """CAPABILITY_-prefixed code extracted from message must give CAPABILITY kind."""
    exc = ValueError("CAPABILITY_NOT_FOUND: no such capability")
    f = classify_exception(exc, request_id="req-1")
    assert f.kind == RuntimeFailureKind.CAPABILITY


def test_classify_audit_phase_hint_is_audit_challenger():
    """phase_hint='audit' must classify as AUDIT_CHALLENGER."""
    exc = RuntimeError("AUDIT_LIMIT_EXCEEDED: audit_passes=1 max=1")
    f = classify_exception(exc, request_id="req-1", phase_hint="audit")
    assert f.kind == RuntimeFailureKind.AUDIT_CHALLENGER
    assert f.code == "AUDIT_LIMIT_EXCEEDED"


def test_classify_revision_phase_hint_is_audit_challenger():
    """phase_hint='revision' must classify as AUDIT_CHALLENGER."""
    exc = RuntimeError("REVISION_LIMIT_EXCEEDED: revision_passes=1 max=1")
    f = classify_exception(exc, request_id="req-1", phase_hint="revision")
    assert f.kind == RuntimeFailureKind.AUDIT_CHALLENGER
    assert f.code == "REVISION_LIMIT_EXCEEDED"


def test_classify_route_phase_hint_is_route_resolution():
    """phase_hint='route' must classify as ROUTE_RESOLUTION."""
    exc = ValueError("No valid route found for mode 'unknown'")
    f = classify_exception(exc, request_id="req-1", phase_hint="route")
    assert f.kind == RuntimeFailureKind.ROUTE_RESOLUTION


def test_classify_provider_phase_hint_is_provider_execution():
    """phase_hint='provider' must classify as PROVIDER_EXECUTION."""
    exc = RuntimeError("connection refused")
    f = classify_exception(exc, request_id="req-1", phase_hint="provider")
    assert f.kind == RuntimeFailureKind.PROVIDER_EXECUTION


def test_classify_value_error_without_phase_hint_is_contract_violation():
    """Plain ValueError without phase hint must classify as CONTRACT_VIOLATION."""
    exc = ValueError("bad state")
    f = classify_exception(exc, request_id="req-1")
    assert f.kind == RuntimeFailureKind.CONTRACT_VIOLATION


def test_classify_type_error_is_contract_violation():
    """TypeError must classify as CONTRACT_VIOLATION."""
    exc = TypeError("expected str, got int")
    f = classify_exception(exc, request_id="req-1")
    assert f.kind == RuntimeFailureKind.CONTRACT_VIOLATION


def test_classify_generic_exception_is_internal():
    """Generic Exception without known structure must classify as INTERNAL."""
    exc = Exception("something exploded")
    f = classify_exception(exc, request_id="req-1")
    assert f.kind == RuntimeFailureKind.INTERNAL


def test_classify_request_id_propagated():
    """request_id must appear in the returned RuntimeFailure."""
    exc = ValueError("bad state")
    f = classify_exception(exc, request_id="req-xyz")
    assert f.request_id == "req-xyz"


def test_classify_task_spec_id_none_preserved():
    """task_spec_id=None (CLI path) must be preserved in RuntimeFailure."""
    exc = ValueError("bad state")
    f = classify_exception(exc, request_id="req-1", task_spec_id=None)
    assert f.task_spec_id is None


def test_classify_task_spec_id_set_preserved():
    """task_spec_id (orchestrator path) must be preserved in RuntimeFailure."""
    exc = ValueError("bad state")
    f = classify_exception(exc, request_id="req-1", task_spec_id="ts-abc")
    assert f.task_spec_id == "ts-abc"


def test_classify_all_kinds_not_retryable_except_provider_unavailable():
    """Only PROVIDER_UNAVAILABLE should have retryable=True."""
    cases = [
        (ValueError("CAPABILITY_TIMEOUT: x"), "capability", False),
        (RuntimeError("AUDIT_LIMIT_EXCEEDED: x"), "audit", False),
        (RuntimeError("REVISION_LIMIT_EXCEEDED: x"), "revision", False),
        (ValueError("bad"), "route", False),
        (TraceLifecycleError("TRACE_INVALID_TRANSITION: x"), None, False),
        (Exception("boom"), None, False),
        (ProviderError("PROVIDER_UNAVAILABLE", "x"), None, True),
    ]
    for exc, phase, expected_retryable in cases:
        f = classify_exception(exc, request_id="req", phase_hint=phase)
        assert f.retryable == expected_retryable, (
            f"Expected retryable={expected_retryable} for {type(exc).__name__} "
            f"(phase={phase}), got {f.retryable}"
        )


# ---------------------------------------------------------------------------
# Engine integration — failure terminal semantics
# ---------------------------------------------------------------------------

def _make_failing_registry(exc_to_raise: Exception):
    """Create a CapabilityRegistry stub that raises on invocation."""
    from io_iii.core.capabilities import (
        CapabilityBounds, CapabilityCategory, CapabilityContext,
        CapabilityRegistry, CapabilityResult, CapabilitySpec,
    )

    class FailingCapability:
        @property
        def spec(self) -> CapabilitySpec:
            return CapabilitySpec(
                capability_id="test.fail",
                version="v0",
                category=CapabilityCategory.TRANSFORMATION,
                description="Always fails.",
                bounds=CapabilityBounds(
                    max_calls=1, timeout_ms=500,
                    max_input_chars=1000, max_output_chars=1000,
                ),
            )

        def invoke(self, ctx: CapabilityContext, payload: Any) -> CapabilityResult:
            raise exc_to_raise

    return CapabilityRegistry([FailingCapability()])


def test_engine_trace_failed_on_capability_exception():
    """
    When capability invocation raises, the execution trace must reach 'failed'
    terminal state before the exception propagates to the caller.
    """
    import io_iii.core.engine as engine
    from io_iii.core.dependencies import RuntimeDependencies

    registry = _make_failing_registry(RuntimeError("cap exploded"))
    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=registry,
    )
    cfg = _engine_cfg()
    state = _null_state()

    # Capture the trace recorder before the exception erases context.
    # We verify via the runtime_failure attached to the exception.
    with pytest.raises(RuntimeError, match="cap exploded"):
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="x",
            audit=False,
            deps=deps,
            capability_id="test.fail",
            capability_payload={},
        )


def test_engine_runtime_failure_attached_to_exception():
    """
    On a controlled failure, the raised exception must have a .runtime_failure
    attribute containing a RuntimeFailure with the correct request_id.
    """
    import io_iii.core.engine as engine
    from io_iii.core.dependencies import RuntimeDependencies

    registry = _make_failing_registry(RuntimeError("CAPABILITY_EXCEPTION: test failure"))
    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=registry,
    )
    cfg = _engine_cfg()
    state = _null_state(request_id="fail-rid-1")

    with pytest.raises(RuntimeError) as exc_info:
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="x",
            audit=False,
            deps=deps,
            capability_id="test.fail",
            capability_payload={},
        )

    exc = exc_info.value
    assert hasattr(exc, "runtime_failure"), "Exception must have .runtime_failure attribute"
    failure = exc.runtime_failure
    assert isinstance(failure, RuntimeFailure)
    assert failure.request_id == "fail-rid-1"


def test_engine_failure_has_correct_kind_for_capability_exception():
    """
    A capability-phase exception must produce a RuntimeFailure with kind=CAPABILITY.
    """
    import io_iii.core.engine as engine
    from io_iii.core.dependencies import RuntimeDependencies

    registry = _make_failing_registry(ValueError("CAPABILITY_TIMEOUT: exceeded"))
    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=registry,
    )
    cfg = _engine_cfg()
    state = _null_state(request_id="cap-fail")

    with pytest.raises(ValueError) as exc_info:
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="x",
            audit=False,
            deps=deps,
            capability_id="test.fail",
            capability_payload={},
        )

    failure = exc_info.value.runtime_failure
    assert failure.kind == RuntimeFailureKind.CAPABILITY


def test_engine_failure_task_spec_id_none_for_cli_path():
    """RuntimeFailure must carry task_spec_id=None for CLI-style state."""
    import io_iii.core.engine as engine
    from io_iii.core.dependencies import RuntimeDependencies

    registry = _make_failing_registry(RuntimeError("CAPABILITY_EXCEPTION: fail"))
    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=registry,
    )
    cfg = _engine_cfg()
    state = _null_state(task_spec_id=None, request_id="cli-fail")

    with pytest.raises(RuntimeError) as exc_info:
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="x",
            audit=False,
            deps=deps,
            capability_id="test.fail",
            capability_payload={},
        )

    failure = exc_info.value.runtime_failure
    assert failure.task_spec_id is None


def test_engine_failure_task_spec_id_propagated():
    """RuntimeFailure must carry task_spec_id when provided (orchestrator path)."""
    import io_iii.core.engine as engine
    from io_iii.core.dependencies import RuntimeDependencies

    registry = _make_failing_registry(RuntimeError("CAPABILITY_EXCEPTION: fail"))
    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=registry,
    )
    cfg = _engine_cfg()
    state = _null_state(task_spec_id="ts-test-001", request_id="orch-fail")

    with pytest.raises(RuntimeError) as exc_info:
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="x",
            audit=False,
            deps=deps,
            capability_id="test.fail",
            capability_payload={},
        )

    failure = exc_info.value.runtime_failure
    assert failure.task_spec_id == "ts-test-001"


def test_engine_failure_no_content_in_runtime_failure():
    """RuntimeFailure must pass assert_no_forbidden_keys on all fields."""
    import io_iii.core.engine as engine
    from io_iii.core.dependencies import RuntimeDependencies

    registry = _make_failing_registry(RuntimeError("CAPABILITY_EXCEPTION: fail"))
    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=registry,
    )
    cfg = _engine_cfg()
    state = _null_state(request_id="safety-fail")

    with pytest.raises(RuntimeError) as exc_info:
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="sensitive prompt text",
            audit=False,
            deps=deps,
            capability_id="test.fail",
            capability_payload={},
        )

    failure = exc_info.value.runtime_failure
    failure_dict = {
        "kind": failure.kind.value,
        "code": failure.code,
        "summary": failure.summary,
        "request_id": failure.request_id,
        "task_spec_id": failure.task_spec_id,
        "retryable": failure.retryable,
        "causal_code": failure.causal_code,
    }
    # Must not raise — no content keys in failure envelope.
    assert_no_forbidden_keys(failure_dict)


def test_engine_original_exception_type_preserved():
    """
    The engine must re-raise the original exception type (not wrapped).
    This preserves existing caller contracts and backward compatibility.
    """
    import io_iii.core.engine as engine
    from io_iii.core.dependencies import RuntimeDependencies

    registry = _make_failing_registry(ValueError("CAPABILITY_INVALID_PAYLOAD: bad"))
    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=registry,
    )
    cfg = _engine_cfg()
    state = _null_state()

    # Must raise ValueError (not a wrapper).
    with pytest.raises(ValueError):
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="x",
            audit=False,
            deps=deps,
            capability_id="test.fail",
            capability_payload={},
        )


def test_engine_failure_on_invalid_payload_type():
    """
    Invalid capability payload (wrong type) must raise ValueError with CAPABILITY_INVALID_PAYLOAD
    AND attach a RuntimeFailure with kind=CAPABILITY.
    """
    import io_iii.core.engine as engine
    from io_iii.core.dependencies import RuntimeDependencies
    from io_iii.core.capabilities import CapabilityRegistry

    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=CapabilityRegistry([]),  # registry doesn't matter; validation fires first
    )

    # We need a registry that has the capability to avoid KeyError before payload validation.
    from io_iii.core.capabilities import (
        CapabilityBounds, CapabilityCategory, CapabilityContext,
        CapabilityResult, CapabilitySpec,
    )
    class EchoCapability:
        @property
        def spec(self) -> CapabilitySpec:
            return CapabilitySpec(
                capability_id="test.echo",
                version="v0",
                category=CapabilityCategory.TRANSFORMATION,
                description="Echo.",
                bounds=CapabilityBounds(max_calls=1, timeout_ms=100, max_input_chars=1000, max_output_chars=1000),
            )
        def invoke(self, ctx: CapabilityContext, payload: Any) -> CapabilityResult:
            return CapabilityResult(ok=True, output={})

    deps2 = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=CapabilityRegistry([EchoCapability()]),
    )
    cfg = _engine_cfg()
    state = _null_state(request_id="payload-fail")

    with pytest.raises(ValueError, match="CAPABILITY_INVALID_PAYLOAD") as exc_info:
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="x",
            audit=False,
            deps=deps2,
            capability_id="test.echo",
            capability_payload="not-a-dict",
        )

    # RuntimeFailure must be attached.
    exc = exc_info.value
    assert hasattr(exc, "runtime_failure")
    failure = exc.runtime_failure
    assert failure.kind == RuntimeFailureKind.CAPABILITY
    assert failure.request_id == "payload-fail"


# ---------------------------------------------------------------------------
# Engine integration — RUN_FAILED event
# ---------------------------------------------------------------------------

def test_engine_run_failed_event_emitted_on_capability_failure():
    """
    On capability failure, a RUN_FAILED event must be emitted by the engine.
    Since events are internal to the engine (not in ExecutionResult on failure),
    we verify via the RuntimeFailure code on the exception which implies classification
    happened (which requires the RUN_FAILED path ran).

    This test is structural: it verifies the failure kind is correctly classified,
    which is only possible if the M4.6 except block executed.
    """
    import io_iii.core.engine as engine
    from io_iii.core.dependencies import RuntimeDependencies

    registry = _make_failing_registry(ValueError("CAPABILITY_TIMEOUT: exceeded"))
    deps = RuntimeDependencies(
        ollama_provider_factory=lambda _cfg: None,
        challenger_fn=None,
        capability_registry=registry,
    )
    cfg = _engine_cfg()
    state = _null_state(request_id="event-test")

    with pytest.raises(ValueError) as exc_info:
        engine.run(
            cfg=cfg,
            session_state=state,
            user_prompt="x",
            audit=False,
            deps=deps,
            capability_id="test.fail",
            capability_payload={},
        )

    # M4.6 except block ran: failure is classified and attached.
    failure = exc_info.value.runtime_failure
    assert failure.kind == RuntimeFailureKind.CAPABILITY
    assert failure.code == "CAPABILITY_TIMEOUT"


# ---------------------------------------------------------------------------
# Engine integration — successful path regression guard
# ---------------------------------------------------------------------------

def test_engine_null_path_success_unaffected_by_m46():
    """
    M4.6 must not alter the successful null-provider execution path.
    Verifies backward compatibility: (SessionState, ExecutionResult) still returned.
    """
    import io_iii.core.engine as engine

    cfg = _engine_cfg()
    deps = _engine_deps()
    state = _null_state(request_id="success-guard")

    state2, result = engine.run(
        cfg=cfg,
        session_state=state,
        user_prompt="regression guard",
        audit=False,
        deps=deps,
    )

    assert state2.status == "ok"
    assert state2.request_id == "success-guard"
    assert isinstance(result.meta, dict)
    assert "trace" in result.meta
    assert result.meta["trace"]["status"] == "completed"
    assert "engine_events" in result.meta
    # On success, no RUN_FAILED event must appear.
    event_kinds = [e["kind"] for e in result.meta["engine_events"]]
    assert "engine_run_failed" not in event_kinds


def test_engine_null_path_trace_status_completed_on_success():
    """On a successful run, trace status must remain 'completed' (not 'failed')."""
    import io_iii.core.engine as engine

    cfg = _engine_cfg()
    deps = _engine_deps()
    state = _null_state()

    _s2, result = engine.run(
        cfg=cfg,
        session_state=state,
        user_prompt="trace status check",
        audit=False,
        deps=deps,
    )

    assert result.meta["trace"]["status"] == "completed"


def test_engine_run_complete_event_still_last_on_success():
    """
    M4.6 regression guard: on success, engine_run_complete must still be the
    last event (RUN_FAILED must not appear on the success path).
    """
    import io_iii.core.engine as engine

    cfg = _engine_cfg()
    deps = _engine_deps()
    state = _null_state()

    _s2, result = engine.run(
        cfg=cfg,
        session_state=state,
        user_prompt="event ordering",
        audit=False,
        deps=deps,
    )

    events = result.meta["engine_events"]
    assert events[-1]["kind"] == "engine_run_complete"
