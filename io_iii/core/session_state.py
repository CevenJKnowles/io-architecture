from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from io_iii.core.session_mode import SessionMode, DEFAULT_SESSION_MODE


# ----------------------------
# Route snapshot (control-plane)
# ----------------------------

@dataclass(frozen=True)
class RouteInfo:
    """
    Minimal route snapshot for SessionState v1.

    Content policy note:
    - This structure must not contain user prompt text or model output text.
    - It is intended to capture deterministic routing decisions and constraints.
    """
    mode: str
    primary_target: Optional[str]
    secondary_target: Optional[str]
    selected_target: Optional[str]
    selected_provider: str
    fallback_used: bool
    fallback_reason: Optional[str]
    boundaries: Dict[str, Any] = field(default_factory=dict)


# ----------------------------
# Audit gate snapshot (bounded)
# ----------------------------

@dataclass(frozen=True)
class AuditGateState:
    """
    Bounded audit gate counters (ADR-009).

    Hard limits are enforced by validation helpers:
    - MAX_AUDIT_PASSES = 1
    - MAX_REVISION_PASSES = 1
    """
    audit_enabled: bool
    audit_passes: int = 0
    revision_passes: int = 0
    audit_verdict: Optional[str] = None  # e.g. "pass", "needs_work"
    revised: bool = False


# ----------------------------
# SessionState v1 (definition)
# ----------------------------

@dataclass(frozen=True)
class SessionState:
    """
    SessionState v1 (Phase 4 M4.4).

    Design intent:
    - Pure structural snapshot aligned to current deterministic runtime outputs.
    - No persistence requirement (in-memory only).
    - No prompt/response content storage.
    - Bounded audit gate counters per ADR-009.
    - Explicit write-once vs engine-mutable field classification.

    Field classification
    -------------------
    Write-once (set at construction; must not be changed by engine or orchestrator):
        schema_version      — contract version sentinel; identifies this as v1
        request_id          — unique run identity
        started_at_ms       — epoch ms at run start; timing anchor
        mode                — selected execution mode
        config_dir          — runtime config root
        route               — deterministic routing snapshot (frozen RouteInfo)
        task_spec_id        — binding reference to the upstream TaskSpec (or None for CLI paths)
        persona_id          — persona binding reference (no payload stored)
        persona_contract_version — active persona contract version
        logging_policy      — logging configuration snapshot
        route_id            — resolved route identifier from routing table

    Engine-mutable (defaults set at construction; engine rebuilds these post-execution):
        latency_ms          — None at construction; set to computed value at completion
        status              — "ok" pre-execution; "ok" or "error" at completion
        provider            — routing selection; confirmed/updated by engine on result path
        model               — None until resolved by engine (ollama path)
        audit               — initial AuditGateState; rebuilt with pass counts and verdict
        error_code          — None unless status == "error"

    Notes:
    - 'request_id' format is intentionally left to the caller (CLI/engine) to generate.
    - 'logging_policy' is a snapshot of the active logging configuration/policy
      to explain what may be recorded (metadata-only posture).
    - 'task_spec_id' carries only the identifier, never the TaskSpec payload.
    - 'schema_version' == "v1" is a required invariant; any other value is invalid.
    """

    # Identity + timing
    request_id: str
    started_at_ms: int

    # Schema version sentinel (v1 contract; write-once)
    schema_version: str = "v1"

    # Timing (engine-mutable: None → computed at completion)
    latency_ms: Optional[int] = None

    # Invocation (write-once)
    mode: str = "executor"
    config_dir: str = "./architecture/runtime/config"

    # Route selection (deterministic snapshot; write-once)
    route: Optional[RouteInfo] = None

    # Audit gate (toggle-based, bounded; engine-mutable: rebuilt with actual pass counts)
    audit: AuditGateState = field(default_factory=lambda: AuditGateState(audit_enabled=False))

    # Result summary (single-voice output; no content stored; engine-mutable)
    status: str = "ok"  # "ok" | "error"
    provider: str = "null"
    model: Optional[str] = None
    route_id: str = "executor"

    # Binding references (write-once; identifier only, no payload stored)
    persona_contract_version: Optional[str] = None
    persona_id: Optional[str] = None
    task_spec_id: Optional[str] = None  # M4.4: binding reference to upstream TaskSpec

    # Error (engine-mutable: set when status == "error")
    error_code: Optional[str] = None

    # Logging policy snapshot (metadata-only posture; write-once)
    logging_policy: Dict[str, Any] = field(default_factory=dict)

    # Session operating mode (ADR-024, Phase 8 M8.1).
    # Governs whether execution proceeds without pause (WORK) or with
    # threshold-gated human-review pauses (STEWARD). Write-once at session
    # start; updated only by explicit user-initiated transition via StewardGate.
    # Never inferred from runtime observables. Default: WORK (ADR-024 §1.2).
    session_mode: SessionMode = DEFAULT_SESSION_MODE


# ----------------------------
# Validation helpers (non-wiring)
# ----------------------------

MAX_AUDIT_PASSES = 1
MAX_REVISION_PASSES = 1


def validate_session_state(state: SessionState) -> None:
    """
    Validate SessionState v1 invariants.

    This is a pure helper (wired into CLI and orchestrator execution paths).
    Raises ValueError on invalid state.
    """
    # v1 contract sentinel
    if state.schema_version != "v1":
        raise ValueError(
            f"SessionState.schema_version must be 'v1', got '{state.schema_version}'"
        )

    if not state.request_id or not isinstance(state.request_id, str):
        raise ValueError("SessionState.request_id must be a non-empty string")

    if not isinstance(state.started_at_ms, int) or state.started_at_ms < 0:
        raise ValueError("SessionState.started_at_ms must be a non-negative integer (epoch ms)")

    if state.latency_ms is not None:
        if not isinstance(state.latency_ms, int) or state.latency_ms < 0:
            raise ValueError("SessionState.latency_ms must be a non-negative integer when set")

    if state.status not in ("ok", "error"):
        raise ValueError("SessionState.status must be 'ok' or 'error'")

    if state.status == "error" and not state.error_code:
        raise ValueError("SessionState.error_code must be set when status == 'error'")

    # task_spec_id: None is valid (CLI path); non-None must be a non-empty string
    if state.task_spec_id is not None:
        if not isinstance(state.task_spec_id, str) or not state.task_spec_id.strip():
            raise ValueError(
                "SessionState.task_spec_id must be a non-empty string when set"
            )

    a = state.audit
    if not isinstance(a.audit_passes, int) or a.audit_passes < 0:
        raise ValueError("AuditGateState.audit_passes must be a non-negative integer")
    if not isinstance(a.revision_passes, int) or a.revision_passes < 0:
        raise ValueError("AuditGateState.revision_passes must be a non-negative integer")

    if a.audit_passes > MAX_AUDIT_PASSES:
        raise ValueError(f"AuditGateState.audit_passes exceeds MAX_AUDIT_PASSES={MAX_AUDIT_PASSES}")
    if a.revision_passes > MAX_REVISION_PASSES:
        raise ValueError(f"AuditGateState.revision_passes exceeds MAX_REVISION_PASSES={MAX_REVISION_PASSES}")

    # session_mode (ADR-024 §1): must be a valid SessionMode value
    if not isinstance(state.session_mode, SessionMode):
        raise ValueError(
            f"SessionState.session_mode must be a SessionMode instance, "
            f"got {type(state.session_mode).__name__}"
        )

    # Route snapshot sanity (if present)
    if state.route is not None:
        r = state.route
        if r.mode != state.mode:
            raise ValueError("RouteInfo.mode must match SessionState.mode")
        if not r.selected_provider:
            raise ValueError("RouteInfo.selected_provider must be a non-empty string")
