from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Failure categories (Phase 4 M4.6)
# ---------------------------------------------------------------------------

class RuntimeFailureKind(str, Enum):
    """
    Canonical failure categories for the IO-III runtime (Phase 4 M4.6).

    Categories:
      ROUTE_RESOLUTION   — routing table lookup failed; no valid route for declared mode
      PROVIDER_EXECUTION — provider raised during generation or inference
      AUDIT_CHALLENGER   — challenger or audit path failed, or bounded limit exceeded
      CAPABILITY         — capability invocation raised, timed out, or exceeded declared bounds
      CONTRACT_VIOLATION — invalid state, invariant breach, or structural contract violation
      INTERNAL           — unexpected runtime failure not covered by the above categories

    These categories are stable. New categories require a governed ADR update.
    """
    ROUTE_RESOLUTION   = "route_resolution"
    PROVIDER_EXECUTION = "provider_execution"
    AUDIT_CHALLENGER   = "audit_challenger"
    CAPABILITY         = "capability"
    CONTRACT_VIOLATION = "contract_violation"
    INTERNAL           = "internal"


# ---------------------------------------------------------------------------
# Failure envelope (Phase 4 M4.6)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuntimeFailure:
    """
    Typed, content-safe failure envelope (Phase 4 M4.6).

    Safe to propagate through all runtime surfaces without leaking prompt or response
    content. Attached to exceptions by the engine failure handler so that CLI and
    observability surfaces can access structured failure information.

    Fields:
        kind          — failure category (RuntimeFailureKind)
        code          — stable machine-readable identifier (e.g. "PROVIDER_UNAVAILABLE")
        summary       — short human-readable description; content-safe (no prompt/output)
        request_id    — session linkage (equals SessionState.request_id)
        task_spec_id  — upstream TaskSpec binding; None for CLI paths
        retryable     — True only for transient infrastructure failures (PROVIDER_UNAVAILABLE)
        causal_code   — stable code extracted from the causing exception; None if unavailable

    Content policy:
        summary must never contain user prompt text or model output text.
        causal_code carries only structured error codes, not exception messages or
        stack traces.
    """
    kind: RuntimeFailureKind
    code: str
    summary: str
    request_id: str
    task_spec_id: Optional[str]
    retryable: bool
    causal_code: Optional[str]


# ---------------------------------------------------------------------------
# Causal code extraction helper
# ---------------------------------------------------------------------------

def _extract_causal_code(exc: Exception) -> Optional[str]:
    """
    Extract a stable causal code from an exception without leaking message content.

    Priority:
    1. ProviderError: use .code attribute directly (already a structured code).
    2. Exception message starts with a known stable uppercase prefix: extract prefix
       before the first ':'.
    3. All others: None (no safe structural code available from this exception).

    The returned value is a stable machine-readable identifier only — never a
    free-form message string.
    """
    # Avoid circular import: local import at call time.
    from io_iii.providers.provider_contract import ProviderError

    if isinstance(exc, ProviderError):
        return exc.code

    _STABLE_PREFIXES = (
        "CAPABILITY_",
        "AUDIT_",
        "REVISION_",
        "TRACE_",
        "ORCHESTRATOR_",
        "PROVIDER_",
        "OBSERVABILITY_",
        "CONTRACT_",
    )

    def _try_extract(candidate: str) -> Optional[str]:
        for prefix in _STABLE_PREFIXES:
            if candidate.startswith(prefix):
                code_token = candidate.split(":", 1)[0].strip()
                if code_token.replace("_", "").isalnum() and code_token == code_token.upper():
                    return code_token
        return None

    # Try str() first (covers most exception types).
    result = _try_extract(str(exc))
    if result:
        return result

    # Fallback: some exceptions (e.g. KeyError) quote their str() output.
    # Check exc.args[0] directly when it is a plain string.
    if exc.args and isinstance(exc.args[0], str):
        result = _try_extract(exc.args[0])
        if result:
            return result

    return None


# ---------------------------------------------------------------------------
# Public classification entry point
# ---------------------------------------------------------------------------

def classify_exception(
    exc: Exception,
    *,
    request_id: str,
    task_spec_id: Optional[str] = None,
    phase_hint: Optional[str] = None,
) -> RuntimeFailure:
    """
    Map an exception to a typed RuntimeFailure envelope (Phase 4 M4.6).

    phase_hint — optional hint about which execution phase raised the exception.
      Accepted values: "capability", "provider", "audit", "revision", "route",
      "validation", "setup", None.
      Used to determine the failure kind when the exception type alone is ambiguous.

    Classification priority (first match wins):
      1. ProviderError (isinstance) — PROVIDER_EXECUTION.
      2. TraceLifecycleError (isinstance) — CONTRACT_VIOLATION.
      3. phase_hint == "capability" OR causal_code starts with CAPABILITY_ — CAPABILITY.
      4. phase_hint in ("audit", "revision") OR causal_code starts with AUDIT_/REVISION_
         — AUDIT_CHALLENGER.
      5. phase_hint == "route" OR causal_code starts with ORCHESTRATOR_ — ROUTE_RESOLUTION.
      6. phase_hint == "provider" — PROVIDER_EXECUTION.
      7. ValueError or TypeError or phase_hint == "validation" — CONTRACT_VIOLATION.
      8. Default — INTERNAL.

    Content policy:
        This function never reads exception message content into the summary field.
        All summary values are fixed category-level strings only.
    """
    # Avoid circular imports: local imports at call time.
    from io_iii.providers.provider_contract import ProviderError
    from io_iii.core.execution_trace import TraceLifecycleError

    causal_code = _extract_causal_code(exc)

    # 1. ProviderError: hard provider-side infrastructure failure.
    if isinstance(exc, ProviderError):
        retryable = exc.code in ("PROVIDER_UNAVAILABLE",)
        return RuntimeFailure(
            kind=RuntimeFailureKind.PROVIDER_EXECUTION,
            code=exc.code,
            summary="Provider execution failed",
            request_id=request_id,
            task_spec_id=task_spec_id,
            retryable=retryable,
            causal_code=exc.code,
        )

    # 2. TraceLifecycleError: invalid lifecycle transition — contract violation.
    if isinstance(exc, TraceLifecycleError):
        return RuntimeFailure(
            kind=RuntimeFailureKind.CONTRACT_VIOLATION,
            code=causal_code or "TRACE_CONTRACT_VIOLATION",
            summary="Execution trace lifecycle contract violated",
            request_id=request_id,
            task_spec_id=task_spec_id,
            retryable=False,
            causal_code=causal_code,
        )

    # 3. Capability phase or CAPABILITY_-prefixed code.
    if phase_hint == "capability" or (causal_code and causal_code.startswith("CAPABILITY_")):
        return RuntimeFailure(
            kind=RuntimeFailureKind.CAPABILITY,
            code=causal_code or "CAPABILITY_EXCEPTION",
            summary="Capability invocation failed",
            request_id=request_id,
            task_spec_id=task_spec_id,
            retryable=False,
            causal_code=causal_code,
        )

    # 4. Audit/revision phase or AUDIT_/REVISION_-prefixed code.
    if phase_hint in ("audit", "revision") or (
        causal_code and causal_code.startswith(("AUDIT_", "REVISION_"))
    ):
        return RuntimeFailure(
            kind=RuntimeFailureKind.AUDIT_CHALLENGER,
            code=causal_code or "AUDIT_FAILURE",
            summary="Audit or revision pass failed",
            request_id=request_id,
            task_spec_id=task_spec_id,
            retryable=False,
            causal_code=causal_code,
        )

    # 5. Route phase or ORCHESTRATOR_-prefixed code.
    if phase_hint == "route" or (causal_code and causal_code.startswith("ORCHESTRATOR_")):
        return RuntimeFailure(
            kind=RuntimeFailureKind.ROUTE_RESOLUTION,
            code=causal_code or "ROUTE_RESOLUTION_FAILED",
            summary="Route resolution failed for declared mode",
            request_id=request_id,
            task_spec_id=task_spec_id,
            retryable=False,
            causal_code=causal_code,
        )

    # 6. Provider phase (non-ProviderError exception in provider execution context).
    if phase_hint == "provider":
        retryable = causal_code == "PROVIDER_UNAVAILABLE"
        return RuntimeFailure(
            kind=RuntimeFailureKind.PROVIDER_EXECUTION,
            code=causal_code or "PROVIDER_EXECUTION_FAILED",
            summary="Provider execution failed",
            request_id=request_id,
            task_spec_id=task_spec_id,
            retryable=retryable,
            causal_code=causal_code,
        )

    # 7. Structural contract or validation errors.
    if isinstance(exc, (ValueError, TypeError)) or phase_hint == "validation":
        return RuntimeFailure(
            kind=RuntimeFailureKind.CONTRACT_VIOLATION,
            code=causal_code or "CONTRACT_VIOLATION",
            summary="Runtime contract or invariant violation",
            request_id=request_id,
            task_spec_id=task_spec_id,
            retryable=False,
            causal_code=causal_code,
        )

    # 8. Default: unexpected internal failure.
    return RuntimeFailure(
        kind=RuntimeFailureKind.INTERNAL,
        code=causal_code or "INTERNAL_ERROR",
        summary="Unexpected internal runtime failure",
        request_id=request_id,
        task_spec_id=task_spec_id,
        retryable=False,
        causal_code=causal_code,
    )
