from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

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


def _run_challenger(cfg, user_prompt: str, draft_text: str) -> dict:
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


def run(
    *,
    cfg,
    session_state: SessionState,
    user_prompt: str,
    audit: bool,
    challenger_fn=None,
    ollama_provider_factory=None,
) -> Tuple[SessionState, ExecutionResult]:
    """
    Deterministic execution engine (Phase 2 extraction).

    Integrations:
    - ADR-010 Context Assembly (assemble_context)
    - ADR-009 bounded audit/revision limits

    Constraints:
    - SessionState remains control-plane only (no prompt/response content stored).
    - Audit toggle is explicit ('audit') and mirrored into SessionState.audit for traceability.
    """
    # Allow dependency injection for tests (keeps CLI monkeypatch compatibility)
    if challenger_fn is None:
        challenger_fn = _run_challenger
    if challenger_fn is None:
        def challenger_fn(cfg_, prompt_, draft_):
            return _run_challenger(
                cfg_,
                prompt_,
                draft_,
                provider_factory=ollama_provider_factory,
            )

    if ollama_provider_factory is None:
        ollama_provider_factory = OllamaProvider.from_config

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

        result_obj = provider.run(mode=session_state.mode, route_id=session_state.route_id, meta={})
        message = getattr(result_obj, "message", "")
        meta = getattr(result_obj, "meta", {})

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

            text = provider.generate(model=model, prompt=revision_prompt).strip()
            audit_meta["revised"] = True

    meta = {"persona_contract_version": PERSONA_CONTRACT_VERSION}

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
