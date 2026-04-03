from __future__ import annotations

import time
from typing import Any, Mapping, Optional, Tuple

from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.engine import ExecutionResult
from io_iii.core.engine import run as _engine_run
from io_iii.core.session_state import (
    AuditGateState,
    RouteInfo,
    SessionState,
    validate_session_state,
)
from io_iii.core.task_spec import TaskSpec
from io_iii.metadata_logging import make_request_id
from io_iii.persona_contract import PERSONA_CONTRACT_VERSION
from io_iii.routing import resolve_route


def run(
    *,
    task_spec: TaskSpec,
    cfg,
    deps: RuntimeDependencies,
    audit: bool = False,
    capability_payload: Optional[Mapping[str, Any]] = None,
    request_id: Optional[str] = None,
) -> Tuple[SessionState, ExecutionResult]:
    """
    Bounded single-run orchestration layer (Phase 4 M4.2 / ADR-012).

    Contract:
    - Exactly one route resolution from task_spec.mode (table-driven, deterministic).
    - Exactly one delegated engine execution.
    - One optional challenger pass via audit=True (ADR-009 bounds enforced by engine).
    - At most one declared capability (Phase 4 M4.2 single-run constraint).
    - No recursion, no planner logic, no output-driven branching, no loops.

    This is a coordination layer only. It does not:
    - load config
    - perform health checks (ADR-011; CLI concern)
    - log metadata (CLI concern)
    - create execution traces (engine concern)
    - invoke the challenger directly (engine concern)

    Returns:
        (SessionState, ExecutionResult) from the single engine execution.

    Raises:
        TypeError: if task_spec or deps are not the expected types.
        ValueError: if task_spec.capabilities declares more than one capability.
    """
    if not isinstance(task_spec, TaskSpec):
        raise TypeError(
            f"task_spec must be an instance of TaskSpec, got {type(task_spec).__name__}"
        )

    if not isinstance(deps, RuntimeDependencies):
        raise TypeError(
            f"deps must be an instance of RuntimeDependencies, got {type(deps).__name__}"
        )

    # M4.2 single-run constraint: at most one capability per execution.
    # Multi-capability composition is not supported until a later Phase 4 milestone.
    if len(task_spec.capabilities) > 1:
        raise ValueError(
            f"ORCHESTRATOR_SINGLE_RUN: TaskSpec declares {len(task_spec.capabilities)} "
            "capabilities; Phase 4 M4.2 single-run orchestration supports at most one."
        )

    # Deterministic route resolution (ADR-002 / ADR-012).
    # Exactly one call; result is never re-evaluated from engine output.
    selection = resolve_route(
        routing_cfg=cfg.routing["routing_table"],
        mode=task_spec.mode,
        providers_cfg=cfg.providers,
        supported_providers={"null", "ollama"},
    )

    # Build frozen SessionState (control-plane snapshot; no prompt content stored).
    rid = request_id or make_request_id()
    route = RouteInfo(
        mode=selection.mode,
        primary_target=selection.primary_target,
        secondary_target=selection.secondary_target,
        selected_target=selection.selected_target,
        selected_provider=selection.selected_provider,
        fallback_used=selection.fallback_used,
        fallback_reason=selection.fallback_reason,
        boundaries=selection.boundaries,
    )

    state = SessionState(
        request_id=rid,
        started_at_ms=int(time.time() * 1000),
        mode=selection.mode,
        config_dir=str(cfg.config_dir),
        route=route,
        audit=AuditGateState(audit_enabled=bool(audit)),
        status="ok",
        provider=selection.selected_provider,
        model=None,
        route_id=selection.mode,
        persona_contract_version=PERSONA_CONTRACT_VERSION,
        persona_id=None,
        logging_policy=cfg.logging,
    )

    # Defensive invariant guard (SessionState v0) — pre-execution.
    validate_session_state(state)

    # Derive capability_id from task_spec (at most one; explicit-only per Phase 3 contract).
    capability_id: Optional[str] = (
        task_spec.capabilities[0] if task_spec.capabilities else None
    )

    # Single delegated engine execution — exactly once, no retry, no loop.
    state2, result = _engine_run(
        cfg=cfg,
        session_state=state,
        user_prompt=task_spec.prompt,
        audit=bool(audit),
        deps=deps,
        capability_id=capability_id,
        capability_payload=capability_payload if capability_id else None,
    )

    # Defensive invariant guard (SessionState v0) — post-execution.
    validate_session_state(state2)

    return state2, result
