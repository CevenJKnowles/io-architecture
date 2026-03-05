from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Mapping

from io_iii.core.context_assembly import assemble_context
from io_iii.core.execution_context import ExecutionContext
from io_iii.core.session_state import (
    AuditGateState,
    SessionState,
    MAX_AUDIT_PASSES,
    MAX_REVISION_PASSES,
)

from io_iii.providers.null_provider import NullProvider
from io_iii.providers.ollama_provider import OllamaProvider
from io_iii.routing import resolve_route
from io_iii.persona_contract import EXECUTOR_PERSONA_CONTRACT, PERSONA_CONTRACT_VERSION

from io_iii.core.capabilities import CapabilityContext, CapabilityRegistry
from io_iii.core.content_safety import assert_no_forbidden_keys

from io_iii.core.execution_trace import TraceRecorder


def _capability_error_code_from_exc(exc: Exception) -> str:
    """Map exceptions to deterministic capability error codes.

    Rules:
    - If the exception message starts with "CAPABILITY_*", treat the prefix before ':' as the code.
    - Otherwise return a stable generic code.
    """
    msg = str(exc)
    if msg.startswith("CAPABILITY_"):
        return msg.split(":", 1)[0]
    return "CAPABILITY_EXCEPTION"


@dataclass(frozen=True)
class ExecutionResult:
    """
    Content-plane result returned to the CLI.

    Logging policy reminder:
    - Do NOT log 'message' (content).
    - 'prompt_hash' is safe to log (sha256 over canonical assembly messages).
    """
    message: str
    meta: Dict[str, Any]
    provider: str
    model: Optional[str]
    route_id: str
    audit_meta: Optional[Dict[str, Any]]
    prompt_hash: Optional[str]


def _run_challenger(
    cfg,
    user_prompt: str,
    draft_text: str,
    *,
    ollama_provider_factory,
) -> dict:
    """
    Challenger pass (ADR-008).

    Fail-open policy:
    - If challenger is unavailable or returns invalid JSON, auto-pass.
    """
    from io_iii.routing import _parse_target

    selection = resolve_route(
        routing_cfg=cfg.routing["routing_table"],
        mode="challenger",
        providers_cfg=cfg.providers,
        supported_providers={"null", "ollama"},
    )

    # Fail-safe: if challenger unavailable, auto-pass
    if selection.selected_provider != "ollama" or not selection.selected_target:
        return {
            "verdict": "pass",
            "issues": [],
            "high_risk_claims": [],
            "suggested_fixes": [],
        }

    _, model = _parse_target(selection.selected_target)
    provider = ollama_provider_factory(cfg.providers)

    system_prompt = (
        "You are IO-III Challenger.\n"
        "Audit the executor draft for:\n"
        "- policy compliance\n"
        "- factual risk or unverifiable claims\n"
        "- contradictions\n"
        "- missing verification steps\n\n"
        "You MUST NOT rewrite the draft.\n"
        "You MUST NOT introduce new facts.\n\n"
        "Respond in strict JSON with keys:\n"
        "{"
        "'verdict': 'pass'|'needs_work', "
        "'issues': [], "
        "'high_risk_claims': [], "
        "'suggested_fixes': []"
        "}"
    )

    audit_prompt = (
        f"{system_prompt}\n\n"
        f"USER_PROMPT:\n{user_prompt}\n\n"
        f"EXECUTOR_DRAFT:\n{draft_text}\n"
    )

    raw = provider.generate(model=model, prompt=audit_prompt).strip()

    try:
        parsed = json.loads(raw)
        # Minimal normalization: ensure required keys exist
        if not isinstance(parsed, dict):
            raise ValueError("Challenger output is not a JSON object")
        parsed.setdefault("verdict", "pass")
        parsed.setdefault("issues", [])
        parsed.setdefault("high_risk_claims", [])
        parsed.setdefault("suggested_fixes", [])
        return parsed
    except Exception:
        # Never block execution
        return {
            "verdict": "pass",
            "issues": [],
            "high_risk_claims": [],
            "suggested_fixes": [],
        }


def _safe_json_len(obj: Any) -> int:
    """
    Size estimator used for capability payload/output bounds.
    """
    try:
        return len(json.dumps(obj, ensure_ascii=False))
    except Exception:
        return len(str(obj))


def _validate_capability_payload(payload: Any) -> Dict[str, Any]:
    """Validate and normalize capability payload.

    Phase 3 (M3.14) requirement:
    - payload must be a JSON object (dict-like)
    - payload must be JSON-serializable (structural safety)

    Notes:
    - This does NOT enforce CapabilityBounds (that is handled in the invocation surface).
    - This is intentionally strict to preserve determinism and predictable error modes.
    """
    if payload is None:
        normalized: Dict[str, Any] = {}
    else:
        if not isinstance(payload, Mapping):
            raise ValueError(
                f"CAPABILITY_INVALID_PAYLOAD: payload must be a JSON object (mapping), got {type(payload).__name__}"
            )
        normalized = dict(payload)

    # JSON object keys must be strings for deterministic serialization.
    for k in normalized.keys():
        if not isinstance(k, str):
            raise ValueError(
                f"CAPABILITY_INVALID_PAYLOAD: payload keys must be strings, got {type(k).__name__}"
            )

    # Ensure it can be serialized deterministically (structural safety; no content logging).
    try:
        json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    except Exception as e:
        raise ValueError(f"CAPABILITY_INVALID_PAYLOAD: payload is not JSON-serializable ({e.__class__.__name__})")

    return normalized


def _invoke_capability_once(
    *,
    registry: CapabilityRegistry,
    capability_id: str,
    payload: Mapping[str, Any],
    ctx: CapabilityContext,
) -> Dict[str, Any]:
    """
    Single explicit capability invocation surface (Phase 3 M3.6).

    - explicit ID
    - single call max
    - bounded payload/output size checks
    - no recursion (capability cannot access registry from ctx)
    """
    cap = registry.get(capability_id)
    spec = cap.spec

    # Bounds sanity (contract hygiene)
    if spec.bounds.max_calls < 1:
        raise ValueError("CAPABILITY_BOUNDS_INVALID: max_calls must be >= 1")

    in_len = _safe_json_len(payload)
    if in_len > spec.bounds.max_input_chars:
        raise ValueError(
            f"CAPABILITY_INPUT_TOO_LARGE: {in_len} chars > max_input_chars={spec.bounds.max_input_chars}"
        )

    # Time the invocation (content-safe; structural observability only)
    t0 = time.perf_counter_ns()
    res = cap.invoke(ctx, payload)
    duration_ms = int((time.perf_counter_ns() - t0) / 1_000_000)

    out_len = _safe_json_len(res.output)
    if out_len > spec.bounds.max_output_chars:
        raise ValueError(
            f"CAPABILITY_OUTPUT_TOO_LARGE: {out_len} chars > max_output_chars={spec.bounds.max_output_chars}"
        )

    return {
        "capability_id": spec.capability_id,
        "version": spec.version,
        "category": spec.category.value,
        "ok": bool(res.ok),
        "error_code": res.error_code,
        "duration_ms": duration_ms,
        "output": res.output,
    }


def run(
    *,
    cfg,
    session_state: SessionState,
    user_prompt: str,
    audit: bool,
    deps=None,
    challenger_fn=None,
    ollama_provider_factory=None,
    capability_id: Optional[str] = None,
    capability_payload: Optional[Mapping[str, Any]] = None,
) -> Tuple[SessionState, ExecutionResult]:
    """
    Deterministic execution engine (Phase 2 extraction).

    Integrations:
    - ADR-010 Context Assembly (assemble_context)
    - ADR-009 bounded audit/revision limits

    Constraints:
    - SessionState remains control-plane only (no prompt/response content stored).
    - Audit toggle is explicit ('audit') and mirrored into SessionState.audit for traceability.
    - Capability invocation is explicit-only and bounded (Phase 3 M3.6).
    """
    capability_meta: Optional[Dict[str, Any]] = None
    trace = TraceRecorder(trace_id=session_state.request_id)

    # Phase 3 injection seam: prefer explicit dependency bundle when provided.
    if deps is not None:
        from io_iii.core.dependencies import RuntimeDependencies  # local import to avoid cycles

        if not isinstance(deps, RuntimeDependencies):
            raise TypeError("deps must be an instance of io_iii.core.dependencies.RuntimeDependencies")

        if ollama_provider_factory is None:
            ollama_provider_factory = deps.ollama_provider_factory
        if challenger_fn is None and deps.challenger_fn is not None:
            challenger_fn = deps.challenger_fn

        # Capability invocation surface (explicit-only)
        if capability_id:
            payload = _validate_capability_payload(capability_payload)
            ctx = CapabilityContext(cfg=cfg, session_state=session_state, execution_context=None)
            cap_trace_meta: Dict[str, Any] = {
                "capability_id": capability_id,
                "success": None,
                "error_code": None,
            }
            with trace.step("capability_execution", meta=cap_trace_meta):
                try:
                    capability_meta = _invoke_capability_once(
                        registry=deps.capability_registry,
                        capability_id=capability_id,
                        payload=payload,
                        ctx=ctx,
                    )
                    cap_trace_meta["success"] = bool(capability_meta.get("ok"))
                    cap_trace_meta["error_code"] = capability_meta.get("error_code")
                except Exception as e:
                    cap_trace_meta["success"] = False
                    cap_trace_meta["error_code"] = _capability_error_code_from_exc(e)
                    raise

    if ollama_provider_factory is None:
        ollama_provider_factory = OllamaProvider.from_config

    # Allow dependency injection for tests (keeps CLI monkeypatch compatibility)
    # Default challenger binds the provider factory explicitly to avoid scope leakage.
    if challenger_fn is None:
        def challenger_fn(cfg_, prompt_, draft_):
            # Backwards-compatibility: some tests monkeypatch _run_challenger with a
            # 3-arg callable. Prefer the explicit provider factory when supported.
            try:
                return _run_challenger(
                    cfg_,
                    prompt_,
                    draft_,
                    ollama_provider_factory=ollama_provider_factory,
                )
            except TypeError:
                return _run_challenger(cfg_, prompt_, draft_)

    # Mirror audit flag into state (frozen dataclass => rebuild audit field only)
    audit_state = AuditGateState(
        audit_enabled=bool(audit),
        audit_passes=session_state.audit.audit_passes,
        revision_passes=session_state.audit.revision_passes,
        audit_verdict=session_state.audit.audit_verdict,
        revised=session_state.audit.revised,
    )
    session_state = _replace(session_state, audit=audit_state)

    # Null route
    if session_state.provider != "ollama":
        provider = NullProvider()

        # Engine-local execution context (no content; no assembly for null route)
        _exec_ctx = ExecutionContext(
            cfg=cfg,
            session_state=session_state,
            provider=provider,
            route=session_state.route,
            prompt_hash=None,
            assembled_context=None,
        )

        with trace.step("provider_run", meta={"provider": "null"}):
            result_obj = provider.run(mode=session_state.mode, route_id=session_state.route_id, meta={})
        message = getattr(result_obj, "message", "")
        meta = dict(getattr(result_obj, "meta", {}))

        trace_dict = trace.trace.to_dict()
        assert_no_forbidden_keys(trace_dict)
        meta["trace"] = trace_dict

        if capability_meta is not None:
            assert_no_forbidden_keys(capability_meta)
            meta["capability"] = capability_meta

        state2 = _replace(session_state, status="ok", provider="null", model=None)
        return state2, ExecutionResult(
            message=message,
            meta=meta,
            provider="null",
            model=None,
            route_id=state2.route_id,
            audit_meta=None,
            prompt_hash=None,
        )

    # Ollama route
    from io_iii.routing import _parse_target

    if session_state.route is None or not session_state.route.selected_target:
        raise ValueError("No selected_target available for ollama route")

    _, model = _parse_target(session_state.route.selected_target)
    provider = ollama_provider_factory(cfg.providers)

    with trace.step(
        "context_assembly",
        meta={
            "persona_contract_version": PERSONA_CONTRACT_VERSION,
            "route_id": session_state.route_id,
        },
    ):
        assembled = assemble_context(
            session_state=session_state,
            user_prompt=user_prompt,
            persona_contract=EXECUTOR_PERSONA_CONTRACT,
            route_metadata={
                "selected_provider": session_state.provider,
                "selected_target": session_state.route.selected_target,
                "fallback_used": session_state.route.fallback_used,
                "route_id": session_state.route_id,
            },
        )

    # Engine-local execution context (content-safe: stores hash, not prompt text)
    _exec_ctx = ExecutionContext(
        cfg=cfg,
        session_state=session_state,
        provider=provider,
        route=session_state.route,
        prompt_hash=assembled.prompt_hash,
        assembled_context=assembled,
    )

    # Keep historical suffix while ADR-010 provides the canonical system prompt.
    final_prompt = f"{assembled.system_prompt}\n\nUser:\n{assembled.user_prompt}\n\nIO-III:"
    with trace.step(
        "provider_inference",
        meta={"provider": "ollama", "model": model},
    ):
        text = provider.generate(model=model, prompt=final_prompt).strip()

    audit_meta = {
        "audit_used": False,
        "audit_verdict": None,
        "revised": False,
    }

    # Hard-limit counters (ADR-009)
    audit_passes = 0
    revision_passes = 0

    # Challenger pass (optional)
    if audit:
        if audit_passes >= MAX_AUDIT_PASSES:
            raise RuntimeError(
                f"AUDIT_LIMIT_EXCEEDED: audit_passes={audit_passes} max={MAX_AUDIT_PASSES}"
            )
        audit_passes += 1

        with trace.step("challenger_audit", meta={"enabled": True}):
            audit_result = challenger_fn(cfg, user_prompt, text)
        audit_meta["audit_used"] = True
        audit_meta["audit_verdict"] = audit_result.get("verdict")

        # Single bounded revision
        if audit_result.get("verdict") == "needs_work":
            if revision_passes >= MAX_REVISION_PASSES:
                raise RuntimeError(
                    f"REVISION_LIMIT_EXCEEDED: revision_passes={revision_passes} max={MAX_REVISION_PASSES}"
                )
            revision_passes += 1

            revision_prompt = (
                "You are IO-III Executor performing a single controlled revision.\n"
                "Address the challenger feedback below.\n"
                "You MUST NOT introduce new facts.\n"
                "Preserve user intent.\n\n"
                f"USER_PROMPT:\n{user_prompt}\n\n"
                f"ORIGINAL_DRAFT:\n{text}\n\n"
                f"CHALLENGER_FEEDBACK:\n{json.dumps(audit_result, indent=2)}\n\n"
                "Produce the improved final answer only."
            )

            with trace.step("revision_inference", meta={"provider": "ollama", "model": model}):
                text = provider.generate(model=model, prompt=revision_prompt).strip()
            audit_meta["revised"] = True

    trace_dict = trace.trace.to_dict()
    assert_no_forbidden_keys(trace_dict)
    meta = {
        "persona_contract_version": PERSONA_CONTRACT_VERSION,
        "trace": trace_dict,
    }
    if capability_meta is not None:
        assert_no_forbidden_keys(capability_meta)
        meta["capability"] = capability_meta

    state2 = _replace(session_state, status="ok", provider="ollama", model=model)
    # Also reflect audit verdict/revised into state.audit (control-plane)
    state2 = _replace(
        state2,
        audit=AuditGateState(
            audit_enabled=bool(audit),
            audit_passes=audit_passes,
            revision_passes=revision_passes,
            audit_verdict=audit_meta["audit_verdict"],
            revised=bool(audit_meta["revised"]),
        ),
    )

    return state2, ExecutionResult(
        message=text,
        meta=meta,
        provider="ollama",
        model=model,
        route_id=state2.route_id,
        audit_meta=audit_meta if audit else None,
        prompt_hash=assembled.prompt_hash,
    )


def _replace(state: SessionState, **updates: Any) -> SessionState:
    """
    Replace fields on a frozen dataclass using explicit reconstruction.
    """
    data = state.__dict__.copy()
    data.update(updates)
    return SessionState(**data)