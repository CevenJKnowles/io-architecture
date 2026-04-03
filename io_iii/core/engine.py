from __future__ import annotations

import json
import time
import concurrent.futures
from dataclasses import dataclass, replace as dataclasses_replace
from typing import Any, Dict, Optional, Tuple, Mapping

from io_iii.core.context_assembly import assemble_context
from io_iii.core.session_state import (
    AuditGateState,
    SessionState,
    MAX_AUDIT_PASSES,
    MAX_REVISION_PASSES,
)

from io_iii.providers.null_provider import NullProvider
from io_iii.providers.ollama_provider import OllamaProvider
from io_iii.routing import resolve_route
from io_iii.persona_contract import (
    EXECUTOR_PERSONA_CONTRACT,
    CHALLENGER_PERSONA_CONTRACT,
    PERSONA_CONTRACT_VERSION,
)

from io_iii.core.capabilities import CapabilityContext, CapabilityRegistry
from io_iii.core.content_safety import assert_no_forbidden_keys

from io_iii.core.execution_trace import TraceRecorder
from io_iii.core.engine_observability import EngineEventKind, EngineObservabilityLog
from io_iii.core.failure_model import classify_exception


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
    session_state: Optional[SessionState] = None,
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

    # Policy: challenger is fail-open (autopass) by design to prevent governance checks
    # from blocking execution when the challenger cannot run. This preserves bounded
    # deterministic execution and availability over strict challenger enforcement.
    if selection.selected_provider != "ollama" or not selection.selected_target:
        return {
            "verdict": "pass",
            "issues": [],
            "high_risk_claims": [],
            "suggested_fixes": [],
        }

    _, model = _parse_target(selection.selected_target)
    provider = ollama_provider_factory(cfg.providers)

    challenger_prompt = (
        "Audit the executor draft below for policy/compliance risk, factual risk, contradictions, "
        "or missing verification steps.\n\n"
        "You MUST NOT rewrite the draft.\n"
        "You MUST NOT introduce new facts.\n"
        "Respond in strict JSON with keys:\n"
        "{\n"
        "  \"verdict\": \"pass\"|\"needs_work\",\n"
        "  \"issues\": [],\n"
        "  \"high_risk_claims\": [],\n"
        "  \"suggested_fixes\": []\n"
        "}\n\n"
        f"USER_PROMPT:\n{user_prompt}\n\n"
        f"EXECUTOR_DRAFT:\n{draft_text}\n"
    )

    if session_state is None:
        session_state = SessionState(
            request_id="challenger-audit",
            started_at_ms=0,
            mode="challenger",
            config_dir=getattr(cfg, "config_dir", "./architecture/runtime/config"),
            route=None,
            audit=AuditGateState(audit_enabled=True),
            status="ok",
            provider="ollama",
            model=model,
            route_id="challenger",
            persona_contract_version=PERSONA_CONTRACT_VERSION,
            logging_policy={"content": "disabled"},
        )
    else:
        route = session_state.route
        if route is not None:
            route = dataclasses_replace(route, mode="challenger")
        session_state = _replace(
            session_state,
            mode="challenger",
            route=route,
            provider="ollama",
            model=model,
            route_id="challenger",
            audit=AuditGateState(audit_enabled=True),
        )

    assembled = assemble_context(
        session_state=session_state,
        user_prompt=challenger_prompt,
        persona_contract=CHALLENGER_PERSONA_CONTRACT,
        route_metadata={
            "selected_provider": selection.selected_provider,
            "selected_target": selection.selected_target,
            "fallback_used": selection.fallback_used,
            "route_id": "challenger",
        },
    )
    audit_prompt = f"{assembled.system_prompt}\n\nUser:\n{assembled.user_prompt}\n\nIO-III Challenger:"

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

    # Enforce timeout_ms deterministically (Phase 3 M3.15).
    # Note: thread-based timeout cannot forcibly kill arbitrary Python code,
    # but it does bound the control-plane waiting time and yields a stable error.
    timeout_s = max(0.001, float(spec.bounds.timeout_ms) / 1000.0)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(cap.invoke, ctx, payload)
        try:
            res = fut.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError as e:
            # Best-effort cancellation; capability code may still run to completion.
            fut.cancel()
            raise ValueError(
                f"CAPABILITY_TIMEOUT: exceeded timeout_ms={spec.bounds.timeout_ms}"
            ) from e

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

    Failure contract (Phase 4 M4.6):
    - On any exception, the execution trace always reaches terminal state ('failed').
    - A RUN_FAILED lifecycle event is always emitted on the failure path.
    - A RuntimeFailure envelope is attached to the exception as .runtime_failure before re-raise.
    - The original exception type is preserved (no wrapping) to maintain caller contracts.
    """
    # Variables declared before try so they are accessible in the except handler.
    capability_meta: Optional[Dict[str, Any]] = None
    trace = TraceRecorder(trace_id=session_state.request_id)

    # M4.5: Engine observability log — created alongside trace; engine-internal.
    # Stable run identifiers cached before any _replace() rebind (write-once on SessionState).
    _obs = EngineObservabilityLog()
    _rid: str = session_state.request_id
    _tsid: Optional[str] = session_state.task_spec_id

    # M4.6: Execution phase tracker for failure classification.
    # Updated at key phase boundaries; read by the except handler to classify failures.
    _phase: str = "setup"

    try:
        # Event 1: engine_run_started
        _obs.emit(
            EngineEventKind.RUN_STARTED,
            request_id=_rid,
            task_spec_id=_tsid,
            meta={
                "mode": session_state.mode,
                "provider": session_state.provider,
                "caller": "orchestrator" if _tsid is not None else "cli",
            },
        )

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
                _phase = "capability"
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

        # M4.6: Reset phase after deps/capability block; entering provider dispatch.
        _phase = "setup"

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
                        session_state=session_state,
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

        # Event 2: route_resolved — routing snapshot confirmed from finalized SessionState.
        _obs.emit(
            EngineEventKind.ROUTE_RESOLVED,
            request_id=_rid,
            task_spec_id=_tsid,
            meta={
                "selected_provider": session_state.provider,
                "route_id": session_state.route_id,
                "fallback_used": session_state.route.fallback_used if session_state.route else False,
            },
        )

        # Null route
        if session_state.provider != "ollama":
            provider = NullProvider()

            with trace.step("provider_run", meta={"provider": "null"}):
                result_obj = provider.run(mode=session_state.mode, route_id=session_state.route_id, meta={})
            message = getattr(result_obj, "message", "")
            meta = dict(getattr(result_obj, "meta", {}))

            # Event 3: provider_execution_complete (null path)
            _obs.emit(
                EngineEventKind.PROVIDER_EXECUTION_COMPLETE,
                request_id=_rid,
                task_spec_id=_tsid,
                meta={"provider": "null", "model": None},
            )

            # M4.3: explicit lifecycle terminal state before serialisation.
            trace.complete()
            trace_dict = trace.trace.to_dict()
            assert_no_forbidden_keys(trace_dict)
            meta["trace"] = trace_dict

            if capability_meta is not None:
                assert_no_forbidden_keys(capability_meta)
                meta["capability"] = capability_meta

            # Events 6–7: output_emitted → engine_run_complete (null path)
            _obs.emit(
                EngineEventKind.OUTPUT_EMITTED,
                request_id=_rid,
                task_spec_id=_tsid,
                meta={"provider": "null", "model": None},
            )
            _obs.emit(
                EngineEventKind.RUN_COMPLETE,
                request_id=_rid,
                task_spec_id=_tsid,
                meta={"trace_step_count": len(trace.trace.steps)},
            )
            meta["engine_events"] = _obs.to_list()

            latency_ms = max(0, int(time.time() * 1000) - session_state.started_at_ms)
            state2 = _replace(session_state, status="ok", provider="null", model=None, latency_ms=latency_ms)
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

        # Keep historical suffix while ADR-010 provides the canonical system prompt.
        final_prompt = f"{assembled.system_prompt}\n\nUser:\n{assembled.user_prompt}\n\nIO-III:"
        _phase = "provider"
        with trace.step(
            "provider_inference",
            meta={"provider": "ollama", "model": model},
        ):
            text = provider.generate(model=model, prompt=final_prompt).strip()

        # Event 3: provider_execution_complete (ollama path)
        _obs.emit(
            EngineEventKind.PROVIDER_EXECUTION_COMPLETE,
            request_id=_rid,
            task_spec_id=_tsid,
            meta={"provider": "ollama", "model": model},
        )

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

            _phase = "audit"
            with trace.step("challenger_audit", meta={"enabled": True}):
                audit_result = challenger_fn(cfg, user_prompt, text)
            audit_meta["audit_used"] = True
            audit_meta["audit_verdict"] = audit_result.get("verdict")

            # Event 4: challenger_audit_complete
            _obs.emit(
                EngineEventKind.CHALLENGER_AUDIT_COMPLETE,
                request_id=_rid,
                task_spec_id=_tsid,
                meta={"verdict": audit_result.get("verdict"), "audit_passes": audit_passes},
            )

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

                _phase = "revision"
                with trace.step("revision_inference", meta={"provider": "ollama", "model": model}):
                    text = provider.generate(model=model, prompt=revision_prompt).strip()
                audit_meta["revised"] = True

                # Event 5: revision_complete
                _obs.emit(
                    EngineEventKind.REVISION_COMPLETE,
                    request_id=_rid,
                    task_spec_id=_tsid,
                    meta={"revision_passes": revision_passes},
                )

        # M4.3: explicit lifecycle terminal state before serialisation.
        trace.complete()
        trace_dict = trace.trace.to_dict()
        assert_no_forbidden_keys(trace_dict)
        meta = {
            "persona_contract_version": PERSONA_CONTRACT_VERSION,
            "trace": trace_dict,
        }
        if capability_meta is not None:
            assert_no_forbidden_keys(capability_meta)
            meta["capability"] = capability_meta

        # Events 6–7: output_emitted → engine_run_complete (ollama path)
        _obs.emit(
            EngineEventKind.OUTPUT_EMITTED,
            request_id=_rid,
            task_spec_id=_tsid,
            meta={"provider": "ollama", "model": model},
        )
        _obs.emit(
            EngineEventKind.RUN_COMPLETE,
            request_id=_rid,
            task_spec_id=_tsid,
            meta={"trace_step_count": len(trace.trace.steps)},
        )
        meta["engine_events"] = _obs.to_list()

        latency_ms = max(0, int(time.time() * 1000) - session_state.started_at_ms)
        state2 = _replace(session_state, status="ok", provider="ollama", model=model, latency_ms=latency_ms)
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

    except Exception as exc:
        # M4.6: Deterministic failure terminal semantics.
        #
        # This handler ensures every failure path closes deterministically:
        #   1. Execution trace reaches terminal state ('failed').
        #   2. RUN_FAILED lifecycle event is emitted (content-safe).
        #   3. A typed RuntimeFailure envelope is attached to the exception.
        #   4. The original exception is re-raised (type preserved for caller contracts).
        #
        # All steps are fail-open: secondary failures in this handler are suppressed
        # to prevent exception cascade into the caller.

        # Step 1: Ensure trace reaches terminal 'failed' state.
        if trace.status not in ("completed", "failed"):
            try:
                trace.fail()
            except Exception:
                pass  # Guard: trace may already be terminal or transition itself may fail.

        # Step 2: Classify failure into a typed, content-safe RuntimeFailure envelope.
        failure = classify_exception(
            exc,
            request_id=_rid,
            task_spec_id=_tsid,
            phase_hint=_phase,
        )

        # Step 3: Emit RUN_FAILED lifecycle event (content-safe; fail-open).
        try:
            _obs.emit(
                EngineEventKind.RUN_FAILED,
                request_id=_rid,
                task_spec_id=_tsid,
                meta={
                    "failure_kind": failure.kind.value,
                    "failure_code": failure.code,
                    "phase": _phase,
                },
            )
        except Exception:
            pass  # Observability must not cascade into exception handling.

        # Step 4: Attach typed failure envelope to the exception for CLI/caller inspection.
        # Uses attribute assignment so the original exception type is preserved.
        try:
            exc.runtime_failure = failure  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            pass  # Some exception types do not allow attribute assignment.

        raise


def _replace(state: SessionState, **updates: Any) -> SessionState:
    """
    Replace fields on a frozen dataclass using explicit reconstruction.
    """
    data = state.__dict__.copy()
    data.update(updates)
    return SessionState(**data)
