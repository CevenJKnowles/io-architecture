"""
io_iii.api._handlers — Request handlers for the HTTP API (Phase 9 M9.1, ADR-025).

Each handler maps one HTTP endpoint to an existing session-layer or execution-layer
operation. Handlers are the only place where IO-III execution is invoked from the
API. They must not call engine.run() directly — all execution goes through the
session layer or orchestrator (ADR-025 §1).

Content policy (ADR-003 / ADR-025 §4):
    POST /run and POST /runbook include model output (primary output surfaces).
    Session endpoints return content-safe governance metadata only.
    No prompt text, memory values, or model names in session endpoint responses.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from io_iii.capabilities.builtins import builtin_registry
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.dialogue_session import (
    DEFAULT_SESSION_STORAGE,
    DialogueTurnResult,
    SESSION_STATUS_CLOSED,
    load_session,
    new_session,
    run_turn,
    save_session,
    session_status_summary,
)
from io_iii.core.engine import ExecutionResult
from io_iii.core.runbook import Runbook
from io_iii.core.runbook_runner import run as runbook_runner_run
from io_iii.core.session_mode import (
    DEFAULT_SESSION_MODE,
    SessionMode,
    StewardGate,
    load_steward_thresholds,
)
from io_iii.core.session_state import SessionState
from io_iii.core.task_spec import TaskSpec
from io_iii.providers.ollama_provider import OllamaProvider
import io_iii.core.orchestrator as _orchestrator

import datetime


# ---------------------------------------------------------------------------
# Error schema
# ---------------------------------------------------------------------------

def _err(code: str, detail: Optional[str] = None) -> dict:
    """Content-safe error response body."""
    r: dict = {"status": "error", "error_code": code}
    if detail:
        r["detail"] = detail
    return r


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _build_deps() -> RuntimeDependencies:
    return RuntimeDependencies(
        ollama_provider_factory=OllamaProvider.from_config,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )


def _session_storage(cfg_runtime: dict) -> Path:
    raw = cfg_runtime.get("session_storage_root")
    if raw and isinstance(raw, str):
        return Path(raw)
    return DEFAULT_SESSION_STORAGE


def _build_gate(cfg_runtime: dict, session) -> StewardGate:
    thresholds = load_steward_thresholds(cfg_runtime)
    return StewardGate(
        session_mode=session.session_mode,
        thresholds=thresholds,
    )


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# POST /run — single-turn execution (primary output surface; includes message)
# ---------------------------------------------------------------------------

def handle_run(body: dict, cfg) -> Tuple[int, dict]:
    """
    Execute a single governed run (Phase 9 M9.1, ADR-025 §3).

    Maps to: python -m io_iii run {mode} --prompt TEXT

    Request body:
        mode        — persona route (e.g. "executor")
        prompt      — user prompt text (required)
        audit       — bool (optional; default False)

    Response includes model output (primary output surface — ADR-025 §4).
    """
    mode = body.get("mode")
    prompt = body.get("prompt")
    audit = bool(body.get("audit", False))

    if not mode or not isinstance(mode, str):
        return 400, _err("INVALID_REQUEST_BODY", "mode is required")
    if not prompt or not isinstance(prompt, str):
        return 400, _err("INVALID_REQUEST_BODY", "prompt is required")

    deps = _build_deps()
    task_spec = TaskSpec.create(mode=mode, prompt=prompt)

    try:
        state, result = _orchestrator.run(
            task_spec=task_spec,
            cfg=cfg,
            deps=deps,
            audit=audit,
        )
    except Exception as e:
        failure = getattr(e, "runtime_failure", None)
        code = failure.code if failure else type(e).__name__
        return 500, _err(code)

    return 200, {
        "status": "ok",
        "mode": state.mode,
        "route_id": state.route_id,
        "provider": result.provider,
        "model": result.model,
        "message": result.message,
        "prompt_hash": result.prompt_hash,
        "meta": {k: v for k, v in (result.meta or {}).items()
                 if k not in ("engine_events",)},
    }


# ---------------------------------------------------------------------------
# POST /runbook — runbook execution (primary output surface; includes outputs)
# ---------------------------------------------------------------------------

def handle_runbook(body: dict, cfg) -> Tuple[int, dict]:
    """
    Execute a Runbook passed as a JSON dict in the request body (M9.1, ADR-025 §3).

    Request body:
        runbook     — Runbook definition dict (required)
        audit       — bool (optional; default False)

    Response includes step-level execution results (primary output surface).
    """
    runbook_data = body.get("runbook")
    audit = bool(body.get("audit", False))

    if not isinstance(runbook_data, dict):
        return 400, _err("INVALID_REQUEST_BODY", "runbook must be an object")

    try:
        runbook = Runbook.from_dict(runbook_data)
    except (ValueError, TypeError) as e:
        return 400, _err("RUNBOOK_SCHEMA_ERROR", str(e))

    deps = _build_deps()

    try:
        result = runbook_runner_run(runbook=runbook, cfg=cfg, deps=deps, audit=audit)
    except Exception as e:
        failure = getattr(e, "runtime_failure", None)
        code = failure.code if failure else type(e).__name__
        return 500, _err(code)

    # Build response: include step outputs (primary output surface — ADR-025 §4)
    steps = []
    for outcome in (result.step_outcomes or []):
        steps.append({
            "step_index": outcome.step_index,
            "task_spec_id": outcome.task_spec_id,
            "status": "ok" if outcome.success else "error",
            "run_id": outcome.state.request_id if outcome.state else None,
            "message": outcome.result.message if outcome.result else None,
            "error_code": outcome.failure.code if outcome.failure else None,
        })

    return 200, {
        "status": "ok",
        "runbook_id": result.runbook_id,
        "steps_total": len(result.step_outcomes),
        "steps_completed": result.steps_completed,
        "steps_skipped": result.steps_skipped,
        "failed_step_index": result.failed_step_index,
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# POST /session/start
# ---------------------------------------------------------------------------

def handle_session_start(body: dict, cfg) -> Tuple[int, dict]:
    """
    Start a new dialogue session (M9.1, ADR-025 §3).

    Maps to: python -m io_iii session start

    Request body:
        mode         — "work" | "steward" (optional; default "work")
        persona_mode — persona route (optional; default "executor")
        prompt       — first-turn prompt (optional)
        audit        — bool (optional; default False)

    Response: content-safe session metadata (no model output).
    """
    raw_mode = body.get("mode", "work")
    try:
        session_mode = SessionMode(raw_mode)
    except ValueError:
        return 400, _err("SESSION_MODE_INVALID", f"mode must be 'work' or 'steward'")

    session = new_session(session_mode=session_mode, runtime_config=cfg.runtime)
    storage_root = _session_storage(cfg.runtime)

    prompt = body.get("prompt")
    if prompt and isinstance(prompt, str):
        persona_mode = body.get("persona_mode", "executor") or "executor"
        audit = bool(body.get("audit", False))
        gate = _build_gate(cfg.runtime, session)
        deps = _build_deps()

        try:
            turn_result = run_turn(
                session=session,
                user_prompt=prompt,
                cfg=cfg,
                deps=deps,
                gate=gate,
                persona_mode=persona_mode,
                audit=audit,
            )
        except Exception as e:
            save_session(session, storage_root)
            failure = getattr(e, "runtime_failure", None)
            code = failure.code if failure else type(e).__name__
            return 500, _err(code)

        save_session(session, storage_root)
        return 200, _turn_result_payload(turn_result)

    save_session(session, storage_root)
    return 201, {
        "session_id": session.session_id,
        "session_mode": session.session_mode.value,
        "status": session.status,
        "turn_count": session.turn_count,
        "max_turns": session.max_turns,
        "created_at": session.created_at,
    }


# ---------------------------------------------------------------------------
# POST /session/{id}/turn — one content-safe turn (no model output in response)
# ---------------------------------------------------------------------------

def handle_session_turn(session_id: str, body: dict, cfg) -> Tuple[int, dict]:
    """
    Run one bounded turn on an existing session (M9.1, ADR-025 §3 + §4).

    Maps to: python -m io_iii session continue

    Request body:
        prompt       — user prompt (required)
        persona_mode — persona route (optional; default "executor")
        audit        — bool (optional; default False)
        action       — "approve"|"redirect"|"close" (optional; for paused sessions)

    Response: content-safe governance metadata. Model output is not included.
    Use GET /session/{id}/stream for model output delivery (M9.2).
    """
    storage_root = _session_storage(cfg.runtime)

    try:
        session = load_session(session_id, storage_root)
    except ValueError as e:
        code = str(e).split(":")[0]
        return 404, _err(code)

    action = body.get("action")
    if session.is_paused():
        if action == "close":
            return _do_close(session, storage_root)
        elif action in ("approve", "redirect"):
            session.status = "active"
            save_session(session, storage_root)
            if action == "approve" and not body.get("prompt"):
                return 200, {
                    "session_id": session.session_id,
                    "status": "active",
                    "message": "session_approved_awaiting_prompt",
                }
        else:
            return 200, {
                "session_id": session.session_id,
                "status": session.status,
                "message": "session_paused_awaiting_action",
                "valid_actions": ["approve", "redirect", "close"],
            }

    prompt = body.get("prompt")
    if not prompt or not isinstance(prompt, str):
        return 400, _err("PROMPT_REQUIRED", "prompt is required for a session turn")

    persona_mode = body.get("persona_mode", "executor") or "executor"
    audit = bool(body.get("audit", False))
    gate = _build_gate(cfg.runtime, session)
    deps = _build_deps()

    try:
        turn_result = run_turn(
            session=session,
            user_prompt=prompt,
            cfg=cfg,
            deps=deps,
            gate=gate,
            persona_mode=persona_mode,
            audit=audit,
        )
    except ValueError as e:
        save_session(session, storage_root)
        code = str(e).split(":")[0]
        return 409, _err(code)
    except Exception as e:
        save_session(session, storage_root)
        failure = getattr(e, "runtime_failure", None)
        code = failure.code if failure else type(e).__name__
        return 500, _err(code)

    save_session(session, storage_root)
    status_code = 202 if turn_result.session.is_paused() else 200
    return status_code, _turn_result_payload(turn_result)


# ---------------------------------------------------------------------------
# GET /session/{id}/state
# ---------------------------------------------------------------------------

def handle_session_state(session_id: str, cfg) -> Tuple[int, dict]:
    """
    Return content-safe session status summary (M9.1, ADR-025 §3).

    Maps to: python -m io_iii session status --session-id ID
    """
    storage_root = _session_storage(cfg.runtime)
    try:
        session = load_session(session_id, storage_root)
    except ValueError as e:
        code = str(e).split(":")[0]
        return 404, _err(code)

    return 200, session_status_summary(session)


# ---------------------------------------------------------------------------
# DELETE /session/{id}
# ---------------------------------------------------------------------------

def handle_session_delete(session_id: str, cfg) -> Tuple[int, dict]:
    """
    Close a session (M9.1, ADR-025 §3).

    Maps to: python -m io_iii session close --session-id ID
    """
    storage_root = _session_storage(cfg.runtime)
    try:
        session = load_session(session_id, storage_root)
    except ValueError as e:
        code = str(e).split(":")[0]
        return 404, _err(code)

    return _do_close(session, storage_root)


# ---------------------------------------------------------------------------
# Shared helpers for session responses
# ---------------------------------------------------------------------------

def _turn_result_payload(turn_result: DialogueTurnResult) -> dict:
    """Content-safe turn result for API session endpoints (ADR-025 §4)."""
    payload: dict = {
        "session_id": turn_result.session.session_id,
        "session_mode": turn_result.session.session_mode.value,
        "turn_index": turn_result.turn_record.turn_index,
        "status": turn_result.turn_record.status,
        "persona_mode": turn_result.turn_record.persona_mode,
        "latency_ms": turn_result.turn_record.latency_ms,
        "error_code": turn_result.turn_record.error_code,
        "session_status": turn_result.session.status,
        "turn_count": turn_result.session.turn_count,
        "turns_remaining": max(
            0, turn_result.session.max_turns - turn_result.session.turn_count
        ),
        "memory_keys_loaded": turn_result.turn_record.memory_keys_loaded,
    }
    if turn_result.pause_state:
        payload["pause"] = {
            "threshold_key": turn_result.pause_state.threshold_key,
            "step_index": turn_result.pause_state.step_index,
            "steps_total": turn_result.pause_state.steps_total,
            "session_mode": turn_result.pause_state.session_mode.value,
            "run_id": turn_result.pause_state.run_id,
            "valid_actions": sorted(turn_result.pause_state.VALID_ACTIONS),
        }
    return payload


def _do_close(session, storage_root: Path) -> Tuple[int, dict]:
    """Mark session closed, persist, return content-safe summary."""
    session.status = SESSION_STATUS_CLOSED
    session.updated_at = _utcnow()
    save_session(session, storage_root)
    return 200, {
        "session_id": session.session_id,
        "status": SESSION_STATUS_CLOSED,
        "session_mode": session.session_mode.value,
        "turn_count": session.turn_count,
        "max_turns": session.max_turns,
        "updated_at": session.updated_at,
    }


# ---------------------------------------------------------------------------
# Core turn executor shared with SSE handler (M9.2)
# ---------------------------------------------------------------------------

def execute_session_turn(
    session_id: str,
    prompt: str,
    cfg,
    *,
    persona_mode: str = "executor",
    audit: bool = False,
) -> Tuple[Optional[DialogueTurnResult], Optional[str]]:
    """
    Load a session, execute one turn, save, and return the result.

    Used by both the M9.1 turn endpoint and the M9.2 SSE stream handler.

    Returns:
        (DialogueTurnResult, None)  on success
        (None, error_code_str)      on failure
    """
    storage_root = _session_storage(cfg.runtime)

    try:
        session = load_session(session_id, storage_root)
    except ValueError as e:
        return None, str(e).split(":")[0]

    if not session.is_active():
        return None, "SESSION_NOT_ACTIVE"

    gate = _build_gate(cfg.runtime, session)
    deps = _build_deps()

    try:
        turn_result = run_turn(
            session=session,
            user_prompt=prompt,
            cfg=cfg,
            deps=deps,
            gate=gate,
            persona_mode=persona_mode,
            audit=audit,
        )
    except ValueError as e:
        save_session(session, storage_root)
        return None, str(e).split(":")[0]
    except Exception as e:
        save_session(session, storage_root)
        failure = getattr(e, "runtime_failure", None)
        return None, failure.code if failure else type(e).__name__

    save_session(session, storage_root)
    return turn_result, None
