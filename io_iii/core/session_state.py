from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ----------------------------
# Route snapshot (control-plane)
# ----------------------------

@dataclass(frozen=True)
class RouteInfo:
    """
    Minimal route snapshot for SessionState v0.

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
# SessionState v0 (definition)
# ----------------------------

@dataclass(frozen=True)
class SessionState:
    """
    SessionState v0 (definition only).

    Design intent:
    - Pure structural snapshot aligned to current deterministic runtime outputs.
    - No persistence requirement (in-memory only).
    - No prompt/response content storage.
    - Bounded audit gate counters per ADR-009.

    Notes:
    - 'request_id' format is intentionally left to the caller (CLI/engine) to generate.
    - 'logging_policy' is a snapshot of the active logging configuration/policy
      to explain what may be recorded (metadata-only posture).
    """
    # Identity + timing
    request_id: str
    started_at_ms: int
    latency_ms: Optional[int] = None

    # Invocation
    mode: str = "executor"
    config_dir: str = "./architecture/runtime/config"

    # Route selection (deterministic snapshot)
    route: Optional[RouteInfo] = None

    # Audit gate (toggle-based, bounded)
    audit: AuditGateState = field(default_factory=lambda: AuditGateState(audit_enabled=False))

    # Result summary (single-voice output; no content stored)
    status: str = "ok"  # "ok" | "error"
    provider: str = "null"
    model: Optional[str] = None
    route_id: str = "executor"
    persona_contract_version: Optional[str] = None
    persona_id: Optional[str] = None  # optional reference only (no payload)

    # Error (when status == "error")
    error_code: Optional[str] = None

    # Logging policy snapshot (metadata-only posture)
    logging_policy: Dict[str, Any] = field(default_factory=dict)


# ----------------------------
# Validation helpers (non-wiring)
# ----------------------------

MAX_AUDIT_PASSES = 1
MAX_REVISION_PASSES = 1


def validate_session_state(state: SessionState) -> None:
    """
    Validate SessionState v0 invariants.

    This is a pure helper (not wired into CLI yet).
    Raises ValueError on invalid state.
    """
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

    a = state.audit
    if not isinstance(a.audit_passes, int) or a.audit_passes < 0:
        raise ValueError("AuditGateState.audit_passes must be a non-negative integer")
    if not isinstance(a.revision_passes, int) or a.revision_passes < 0:
        raise ValueError("AuditGateState.revision_passes must be a non-negative integer")

    if a.audit_passes > MAX_AUDIT_PASSES:
        raise ValueError(f"AuditGateState.audit_passes exceeds MAX_AUDIT_PASSES={MAX_AUDIT_PASSES}")
    if a.revision_passes > MAX_REVISION_PASSES:
        raise ValueError(f"AuditGateState.revision_passes exceeds MAX_REVISION_PASSES={MAX_REVISION_PASSES}")

    # Route snapshot sanity (if present)
    if state.route is not None:
        r = state.route
        if r.mode != state.mode:
            raise ValueError("RouteInfo.mode must match SessionState.mode")
        if not r.selected_provider:
            raise ValueError("RouteInfo.selected_provider must be a non-empty string")