"""
io_iii.cli._session_shell — Session shell CLI commands (Phase 8 M8.3).

Provides four bounded session management commands:
    session start    — initialise a new dialogue session (optionally run first turn)
    session continue — load an existing session and run one turn
    session status   — print content-safe session status summary
    session close    — terminate a session and print a content-safe summary

All output is content-safe (ADR-003): no prompt text, model output, persona content,
or memory values appear in any printed field.

Storage root: configurable via runtime.yaml ``session_storage_root``; defaults to
DEFAULT_SESSION_STORAGE (.io_iii/sessions).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

from io_iii.capabilities.builtins import builtin_registry
from io_iii.config import load_io3_config
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.dialogue_session import (
    DEFAULT_SESSION_STORAGE,
    SESSION_STATUS_CLOSED,
    DialogueSession,
    DialogueTurnResult,
    load_session,
    new_session,
    run_turn,
    save_session,
    session_status_summary,
)
from io_iii.core.session_mode import (
    DEFAULT_SESSION_MODE,
    SessionMode,
    StewardGate,
    StewardThresholds,
    load_steward_thresholds,
)
from io_iii.memory.packs import PackLoader
from io_iii.memory.policy import load_retrieval_policy
from io_iii.memory.session_continuity import (
    SESSION_CONTINUITY_PACK_ID,
    SessionMemoryContext,
    load_session_memory,
)
from io_iii.memory.store import MemoryRecord, MemoryStore
from io_iii.metadata_logging import append_metadata
from io_iii.providers.ollama_provider import OllamaProvider

from ._shared import _get_cfg_dir, _print


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session_storage(cfg_runtime: dict) -> Path:
    """Resolve session storage root from runtime config or fall back to default."""
    raw = cfg_runtime.get("session_storage_root")
    if raw and isinstance(raw, str):
        return Path(raw)
    return DEFAULT_SESSION_STORAGE


def _build_gate(cfg_runtime: dict, session: DialogueSession) -> StewardGate:
    """Build a StewardGate wired to the session's current mode and runtime thresholds."""
    thresholds: StewardThresholds = load_steward_thresholds(cfg_runtime)
    return StewardGate(
        session_mode=session.session_mode,
        thresholds=thresholds,
    )


def _emit_turn_result(turn_result: DialogueTurnResult, cfg_runtime: dict | None = None) -> None:
    """
    Print turn result summary.

    When content_release is enabled in runtime.yaml (ADR-026), the model
    response text is included as ``message``. Otherwise only structural
    metadata is emitted (ADR-003 content-safe default).
    """
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
        "memory_context": (
            turn_result.memory_context.to_log_safe()
            if turn_result.memory_context is not None
            else None
        ),
        "pause": _pause_summary(turn_result) if turn_result.pause_state else None,
    }
    # ADR-026: include message when operator has opened the content release gate.
    if cfg_runtime and cfg_runtime.get("content_release"):
        msg = getattr(turn_result.result, "message", None)
        if msg:
            payload["message"] = msg
    _print(payload)


def _pause_summary(turn_result: DialogueTurnResult) -> dict:
    """Content-safe pause state summary (ADR-024 §6.2)."""
    p = turn_result.pause_state
    return {
        "threshold_key": p.threshold_key,
        "step_index": p.step_index,
        "steps_total": p.steps_total,
        "session_mode": p.session_mode.value,
        "run_id": p.run_id,
        "valid_actions": sorted(p.VALID_ACTIONS),
    }


def _build_deps(cfg) -> RuntimeDependencies:
    return RuntimeDependencies(
        ollama_provider_factory=OllamaProvider.from_config,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )


def _load_continuity_memory(
    cfg,
    *,
    pack_id: str = SESSION_CONTINUITY_PACK_ID,
    route: str = "executor",
) -> tuple:
    """
    Load session continuity memory for the current turn (M8.6).

    Returns (records, context) — records is a list of MemoryRecord (content-plane);
    context is a SessionMemoryContext (content-safe) or None if pack is absent.

    Absent pack and absent store are both safe defaults — ([], None) is returned.
    No memory writes are triggered (ADR-022 §7).
    """
    cfg_dir = cfg.config_dir

    pack_loader = PackLoader(cfg_dir / "memory_packs.yaml")
    policy = load_retrieval_policy(cfg_dir / "memory_retrieval_policy.yaml")
    storage_root = pack_loader.storage_root
    store = MemoryStore(storage_root)

    return load_session_memory(
        pack_id=pack_id,
        pack_loader=pack_loader,
        store=store,
        policy=policy,
        route=route,
    )


# ---------------------------------------------------------------------------
# session start (M8.3)
# ---------------------------------------------------------------------------

def cmd_session_start(args) -> int:
    """
    Initialise a new dialogue session (Phase 8 M8.3).

    Optionally runs the first turn if --prompt is supplied.

    CLI:
        python -m io_iii session start [--mode work|steward]
            [--persona-mode executor] [--prompt TEXT] [--audit]
    """
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)

    # Resolve session mode from --mode flag (defaults to work; ADR-024 §1.2)
    raw_mode = getattr(args, "mode", "work") or "work"
    try:
        session_mode = SessionMode(raw_mode)
    except ValueError:
        print(
            f"SESSION_MODE_INVALID: --mode must be 'work' or 'steward', got {raw_mode!r}",
            file=sys.stderr,
        )
        return 1

    session = new_session(
        session_mode=session_mode,
        runtime_config=cfg.runtime,
    )

    storage_root = _session_storage(cfg.runtime)

    prompt = getattr(args, "prompt", None)
    if prompt:
        persona_mode = getattr(args, "persona_mode", "executor") or "executor"
        gate = _build_gate(cfg.runtime, session)
        deps = _build_deps(cfg)
        audit = bool(getattr(args, "audit", False))

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
            print(f"SESSION_TURN_FAILED: {type(e).__name__}", file=sys.stderr)
            save_session(session, storage_root)
            return 1

        save_session(session, storage_root)
        _emit_turn_result(turn_result, cfg_runtime=cfg.runtime)
        return 0

    # No prompt — just initialise and save
    save_session(session, storage_root)
    _print({
        "session_id": session.session_id,
        "session_mode": session.session_mode.value,
        "status": session.status,
        "turn_count": session.turn_count,
        "max_turns": session.max_turns,
        "created_at": session.created_at,
    })
    return 0


# ---------------------------------------------------------------------------
# session continue (M8.3)
# ---------------------------------------------------------------------------

def cmd_session_continue(args) -> int:
    """
    Load an existing session and run one turn (Phase 8 M8.3).

    Evaluates the steward gate after the turn. If the session is paused,
    prints the pause state and takes no further action until the user
    provides an action (approve / redirect / close).

    CLI:
        python -m io_iii session continue --session-id ID --prompt TEXT
            [--persona-mode executor] [--audit] [--action approve|redirect|close]
    """
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)
    storage_root = _session_storage(cfg.runtime)

    session_id = getattr(args, "session_id", None)
    if not session_id:
        print("SESSION_ID_REQUIRED: --session-id is required", file=sys.stderr)
        return 1

    try:
        session = load_session(session_id, storage_root)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    # Handle steward pause actions before running a new turn (ADR-024 §6.3).
    action = getattr(args, "action", None)
    if session.is_paused():
        if action == "close":
            return _close_session(session, storage_root)
        elif action in ("approve", "redirect"):
            session.status = "active"
            save_session(session, storage_root)
            if action == "approve" and not getattr(args, "prompt", None):
                _print({
                    "session_id": session.session_id,
                    "status": "active",
                    "message": "session_approved_awaiting_prompt",
                })
                return 0
        else:
            # Paused with no valid action — surface pause state.
            # Exit code 3: steward gate pause requires human action (ADR-025 §7).
            _print({
                "session_id": session.session_id,
                "status": session.status,
                "message": "session_paused_awaiting_action",
                "valid_actions": ["approve", "redirect", "close"],
            })
            return 3

    prompt = getattr(args, "prompt", None)
    if not prompt:
        print("PROMPT_REQUIRED: --prompt is required for session continue", file=sys.stderr)
        return 1

    persona_mode = getattr(args, "persona_mode", "executor") or "executor"
    gate = _build_gate(cfg.runtime, session)
    deps = _build_deps(cfg)
    audit = bool(getattr(args, "audit", False))

    # Auto-load session continuity memory (M8.6).
    # Absent pack is the safe default → ([], None). No writes triggered.
    sm_records, sm_context = _load_continuity_memory(cfg, route=persona_mode)

    try:
        turn_result = run_turn(
            session=session,
            user_prompt=prompt,
            cfg=cfg,
            deps=deps,
            gate=gate,
            persona_mode=persona_mode,
            audit=audit,
            session_memory=sm_records if sm_records else None,
            memory_context=sm_context,
        )
    except ValueError as e:
        code = str(e).split(":")[0]
        print(str(e), file=sys.stderr)
        save_session(session, storage_root)
        return 1
    except Exception as e:
        print(f"SESSION_TURN_FAILED: {type(e).__name__}", file=sys.stderr)
        save_session(session, storage_root)
        return 1

    save_session(session, storage_root)
    _emit_turn_result(turn_result, cfg_runtime=cfg.runtime)
    return 0


# ---------------------------------------------------------------------------
# session status (M8.3)
# ---------------------------------------------------------------------------

def cmd_session_status(args) -> int:
    """
    Print content-safe status summary for a session (Phase 8 M8.3).

    CLI:
        python -m io_iii session status --session-id ID
    """
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)
    storage_root = _session_storage(cfg.runtime)

    session_id = getattr(args, "session_id", None)
    if not session_id:
        print("SESSION_ID_REQUIRED: --session-id is required", file=sys.stderr)
        return 1

    try:
        session = load_session(session_id, storage_root)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    _print(session_status_summary(session))
    return 0


# ---------------------------------------------------------------------------
# session close (M8.3)
# ---------------------------------------------------------------------------

def cmd_session_close(args) -> int:
    """
    Terminate a session and print a content-safe summary (Phase 8 M8.3).

    Marks the session as closed. Closed sessions cannot run further turns.
    The session file is retained for audit purposes.

    CLI:
        python -m io_iii session close --session-id ID
    """
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)
    storage_root = _session_storage(cfg.runtime)

    session_id = getattr(args, "session_id", None)
    if not session_id:
        print("SESSION_ID_REQUIRED: --session-id is required", file=sys.stderr)
        return 1

    try:
        session = load_session(session_id, storage_root)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    return _close_session(session, storage_root)


def _close_session(session: DialogueSession, storage_root: Path) -> int:
    """Mark session closed, persist, and emit content-safe summary."""
    session.status = SESSION_STATUS_CLOSED
    import datetime as _dt
    session.updated_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_session(session, storage_root)
    _print({
        "session_id": session.session_id,
        "status": SESSION_STATUS_CLOSED,
        "session_mode": session.session_mode.value,
        "turn_count": session.turn_count,
        "max_turns": session.max_turns,
        "updated_at": session.updated_at,
    })
    return 0
