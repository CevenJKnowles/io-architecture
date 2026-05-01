"""
io_iii.core.dialogue_session — Bounded dialogue session loop (ADR-024, Phase 8 M8.2).

Implements the multi-turn session shell that sits above the frozen execution stack.
Each turn is a single orchestrator.run() call. The steward gate is evaluated at
each turn boundary. No content is stored in the session record.

Content policy (ADR-003):
    Session artefacts (TurnRecord, DialogueSession JSON) must never contain prompt
    text, model output, persona content, or memory values. Only structural identifiers,
    counts, modes, and timestamps are persisted.

ADR freeze boundary: engine.py, routing.py, telemetry.py are not touched.
All execution passes through orchestrator.run() as with all prior phases.
"""
from __future__ import annotations

import datetime
import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import io_iii.core.orchestrator as _orchestrator
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.file_store import FileRefExpiredError, FileRefNotFound, resolve as _fs_resolve
from io_iii.core.engine import ExecutionResult
from io_iii.memory.store import MemoryRecord
from io_iii.memory.session_continuity import SessionMemoryContext
from io_iii.core.session_mode import (
    DEFAULT_SESSION_MODE,
    PauseState,
    SessionMode,
    StewardGate,
    StewardThresholds,
)
from io_iii.core.session_state import SessionState
from io_iii.core.task_spec import TaskSpec


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DIALOGUE_SESSION_SCHEMA_VERSION: str = "v1"
DEFAULT_SESSION_STORAGE: Path = Path(".io_iii/sessions")

SESSION_MAX_TURNS: int = 50
"""
Hard ceiling on turns per dialogue session (ADR-024 M8.0 prerequisite).
Configurable via runtime.yaml ``session_max_turns`` key. Default: 50.
"""

SESSION_STATUS_ACTIVE: str = "active"


# ---------------------------------------------------------------------------
# Timestamp helper — declared here so dataclass field defaults can reference it
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")



SESSION_STATUS_PAUSED: str = "paused"
SESSION_STATUS_CLOSED: str = "closed"
SESSION_STATUS_AT_LIMIT: str = "at_limit"

VALID_SESSION_STATUSES: frozenset = frozenset({
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_PAUSED,
    SESSION_STATUS_CLOSED,
    SESSION_STATUS_AT_LIMIT,
})


# ---------------------------------------------------------------------------
# TurnRecord — content-safe per-turn record (ADR-003)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TurnRecord:
    """
    Content-safe record of a single dialogue turn (Phase 8 M8.2).

    Must NOT contain: prompt text, model output, persona content, memory values,
    capability payloads, or any free-form content strings.

    Fields:
        turn_index   — zero-based turn position within the session
        run_id       — engine run identity for this turn (ADR-018)
        status       — "ok" | "error"
        persona_mode — persona mode used for this turn (e.g. "executor")
        latency_ms   — wall-clock turn duration in milliseconds; None if unavailable
        error_code   — ADR-013 error code when status == "error"; else None
    """
    turn_index: int
    run_id: str
    status: str
    persona_mode: str
    latency_ms: Optional[int]
    error_code: Optional[str] = None
    memory_keys_loaded: int = 0
    """
    Count of memory records loaded for session continuity on this turn (M8.6).
    Content-safe: count only, never keys or values (ADR-003).
    """


# ---------------------------------------------------------------------------
# DialogueSession — mutable session state
# ---------------------------------------------------------------------------

@dataclass
class DialogueSession:
    """
    Mutable dialogue session state (Phase 8 M8.2).

    Owns the ordered turn history, session mode, and turn ceiling. Persisted
    to disk between CLI invocations as content-safe JSON.

    No prompt, output, persona content, or memory values may appear in any
    field (ADR-003).

    Fields:
        session_id    — unique session identifier
        session_mode  — current SessionMode (work | steward); ADR-024 §1
        turn_count    — number of turns executed so far
        max_turns     — hard ceiling; session is at_limit when reached
        status        — one of VALID_SESSION_STATUSES
        turns         — ordered list of TurnRecords (structural only)
        created_at    — ISO 8601 creation timestamp
        updated_at    — ISO 8601 last-update timestamp
    """
    session_id: str
    session_mode: SessionMode
    turn_count: int
    max_turns: int
    status: str
    turns: List[TurnRecord] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)

    def is_at_limit(self) -> bool:
        """True when no further turns may be executed."""
        return self.turn_count >= self.max_turns

    def is_active(self) -> bool:
        return self.status == SESSION_STATUS_ACTIVE

    def is_paused(self) -> bool:
        return self.status == SESSION_STATUS_PAUSED


# ---------------------------------------------------------------------------
# DialogueSessionResult — bounded result of a single turn
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DialogueTurnResult:
    """
    Bounded, content-safe result of a single dialogue turn (Phase 8 M8.2).

    Fields:
        session      — updated DialogueSession after the turn
        turn_record  — TurnRecord for this turn (structural only)
        state        — SessionState from the engine execution (control-plane only)
        result       — ExecutionResult (content-plane in result.message — callers
                       are responsible for handling message according to ADR-003)
        pause_state  — PauseState if the steward gate fired; else None (ADR-024 §6)
    """
    session: DialogueSession
    turn_record: TurnRecord
    state: SessionState
    result: ExecutionResult
    pause_state: Optional[PauseState]
    memory_context: Optional[SessionMemoryContext] = None
    """
    Content-safe session continuity context for this turn (M8.6).
    None when no session memory pack was loaded.
    """


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

def new_session(
    *,
    session_mode: SessionMode = DEFAULT_SESSION_MODE,
    max_turns: Optional[int] = None,
    runtime_config: Optional[Dict[str, Any]] = None,
) -> DialogueSession:
    """
    Create a new DialogueSession with a fresh session_id (Phase 8 M8.2).

    Args:
        session_mode:   initial SessionMode (default: WORK per ADR-024 §1.2)
        max_turns:      hard turn ceiling; if None, loaded from runtime_config
                        or falls back to SESSION_MAX_TURNS
        runtime_config: runtime.yaml dict for ``session_max_turns`` loading

    Returns:
        DialogueSession with status=active and turn_count=0.
    """
    if max_turns is None:
        max_turns = _load_max_turns(runtime_config or {})

    return DialogueSession(
        session_id=str(uuid.uuid4()),
        session_mode=session_mode,
        turn_count=0,
        max_turns=max_turns,
        status=SESSION_STATUS_ACTIVE,
        turns=[],
        created_at=_utcnow_iso(),
        updated_at=_utcnow_iso(),
    )


# ---------------------------------------------------------------------------
# Turn execution (M8.2 bounded loop)
# ---------------------------------------------------------------------------

def run_turn(
    *,
    session: DialogueSession,
    user_prompt: str,
    cfg: Any,
    deps: RuntimeDependencies,
    gate: StewardGate,
    persona_mode: str = "executor",
    audit: bool = False,
    session_memory: Optional[List[MemoryRecord]] = None,
    memory_context: Optional[SessionMemoryContext] = None,
    file_ref: Optional[str] = None,
) -> DialogueTurnResult:
    """
    Execute one bounded turn of the dialogue session loop (Phase 8 M8.2).

    Turn loop:
        validate bounds → build TaskSpec → orchestrator.run() →
        steward gate check → update session → return result

    Contract (ADR-024 / ADR-012 / ADR-014):
    - Exactly one orchestrator.run() call per turn.
    - Execution bounded by SESSION_MAX_TURNS ceiling.
    - Steward gate evaluated at each turn boundary (ADR-024 §5.3).
    - No prompt or output content stored in the session record.
    - Memory writes are never triggered automatically (ADR-022 §7).
    - No output-driven control flow.

    Args:
        session:     current DialogueSession (must be active and below limit)
        user_prompt: user input for this turn (content-plane; not stored)
        cfg:         IO3Config
        deps:        RuntimeDependencies
        gate:        StewardGate (carries current SessionMode + thresholds)
        persona_mode:     persona execution mode (e.g. "executor", "explorer")
        audit:            whether to enable challenger audit pass (ADR-009)
        session_memory:   memory records for cross-turn context (M8.6); content-plane.
                          Loaded by the session shell; count stored in TurnRecord.
                          Never written automatically (ADR-022 §7).
        memory_context:   content-safe context record from load_session_memory() (M8.6).
                          Threaded through to DialogueTurnResult unchanged.

    Returns:
        DialogueTurnResult with updated session, optional PauseState, and
        optional SessionMemoryContext (M8.6).

    Raises:
        ValueError('SESSION_AT_LIMIT: ...')  if session has reached max_turns
        ValueError('SESSION_NOT_ACTIVE: ...') if session is not active
        TypeError if session or deps have incorrect types
    """
    if not isinstance(session, DialogueSession):
        raise TypeError(
            f"session must be a DialogueSession instance, got {type(session).__name__}"
        )

    if not session.is_active():
        raise ValueError(
            f"SESSION_NOT_ACTIVE: session {session.session_id!r} "
            f"has status {session.status!r}; only active sessions may run turns"
        )

    if session.is_at_limit():
        session.status = SESSION_STATUS_AT_LIMIT
        raise ValueError(
            f"SESSION_AT_LIMIT: session {session.session_id!r} has reached "
            f"max_turns={session.max_turns}; no further turns permitted"
        )

    turn_index = session.turn_count
    import time as _time
    turn_start_ns = _time.monotonic_ns()

    # File content injection (ADR-029/ADR-033).
    # Resolve file_ref to text and prepend to user_prompt before TaskSpec.
    # engine.py is frozen and cannot receive file_ref directly; injecting here
    # is semantically equivalent to the ADR-033 formal lane model.
    if file_ref is not None:
        try:
            _filename, _file_text = _fs_resolve(session.session_id, file_ref)
        except FileRefNotFound:
            raise FileRefExpiredError()
        # Apply budget from cfg.runtime; fall back to 16000.
        _budget = int((getattr(cfg, "runtime", {}) or {}).get("file_content_limit_chars", 16000))
        _file_truncated = False
        if len(_file_text) > _budget:
            _truncated = _file_text[:_budget]
            # Seek last sentence boundary in the second half of the budget.
            for _punct in (".", "\n", "!", "?"):
                _idx = _truncated.rfind(_punct, _budget // 2)
                if _idx > 0:
                    _truncated = _truncated[: _idx + 1]
                    break
            _file_text = (
                _truncated
                + f"\n[File content truncated at context limit — "
                f"{len(_truncated)} characters shown of {len(_file_text)}]"
            )
            _file_truncated = True
        user_prompt = (
            f"[Attached file: {_filename}]\n---\n{_file_text}\n---\n\n{user_prompt}"
        )

    # Build a TaskSpec for this turn (content-plane: user_prompt is not stored
    # in TurnRecord or DialogueSession — it is consumed by the engine only).
    task_spec = TaskSpec(
        task_spec_id=f"{session.session_id}:turn:{turn_index}",
        mode=persona_mode,
        prompt=user_prompt,
        capabilities=[],
        metadata={
            "session_id": session.session_id,
            "turn_index": turn_index,
        },
    )

    # Execute through orchestrator (ADR-012 bounded contract; never engine directly).
    state, result = _orchestrator.run(
        task_spec=task_spec,
        cfg=cfg,
        deps=deps,
        audit=audit,
    )

    turn_latency_ms = (_time.monotonic_ns() - turn_start_ns) // 1_000_000

    turn_record = TurnRecord(
        turn_index=turn_index,
        run_id=state.request_id,
        status=state.status,
        persona_mode=persona_mode,
        latency_ms=turn_latency_ms,
        error_code=state.error_code,
        memory_keys_loaded=len(session_memory) if session_memory else 0,
    )

    # Update session (mutable: turn appended, count incremented, timestamp refreshed)
    session.turns.append(turn_record)
    session.turn_count += 1
    session.updated_at = _utcnow_iso()

    # Steward gate evaluation at turn boundary (ADR-024 §5.3).
    # In work mode the gate always returns None (ADR-024 §2.2).
    pause_state = gate.check(
        step_index=turn_index,
        steps_total=session.max_turns,
        run_id=state.request_id,
    )

    if pause_state is not None:
        session.status = SESSION_STATUS_PAUSED

    if session.is_at_limit():
        session.status = SESSION_STATUS_AT_LIMIT

    return DialogueTurnResult(
        session=session,
        turn_record=turn_record,
        state=state,
        result=result,
        pause_state=pause_state,
        memory_context=memory_context,
    )


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------

def save_session(
    session: DialogueSession,
    storage_root: Path | str = DEFAULT_SESSION_STORAGE,
) -> Path:
    """
    Persist a DialogueSession to disk as JSON (Phase 8 M8.2).

    File: <storage_root>/<session_id>.session.json

    Content policy: no prompt, output, or memory values are written.
    All fields are structural identifiers and control-plane metadata.

    Returns:
        Path to the written file.

    Raises:
        ValueError('SESSION_PERSIST_FAILED: ...') on write failure.
    """
    root = Path(storage_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{session.session_id}.session.json"

    data: Dict[str, Any] = {
        "schema_version": DIALOGUE_SESSION_SCHEMA_VERSION,
        "session_id": session.session_id,
        "session_mode": session.session_mode.value,
        "turn_count": session.turn_count,
        "max_turns": session.max_turns,
        "status": session.status,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "turns": [
            {
                "turn_index": t.turn_index,
                "run_id": t.run_id,
                "status": t.status,
                "persona_mode": t.persona_mode,
                "latency_ms": t.latency_ms,
                "error_code": t.error_code,
                "memory_keys_loaded": t.memory_keys_loaded,
            }
            for t in session.turns
        ],
    }

    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(path)
    except OSError as e:
        raise ValueError(f"SESSION_PERSIST_FAILED: {e}") from e

    return path


def load_session(
    session_id: str,
    storage_root: Path | str = DEFAULT_SESSION_STORAGE,
) -> DialogueSession:
    """
    Load a DialogueSession from disk (Phase 8 M8.2).

    Raises:
        ValueError('SESSION_NOT_FOUND: ...')  if no file for session_id
        ValueError('SESSION_SCHEMA_INVALID: ...') on parse or validation failure
    """
    root = Path(storage_root)
    path = root / f"{session_id}.session.json"

    if not path.is_file():
        raise ValueError(
            f"SESSION_NOT_FOUND: no session file for session_id={session_id!r}"
        )

    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(
            f"SESSION_SCHEMA_INVALID: could not read session file: {e}"
        ) from e

    return _deserialise_session(data)


def list_sessions(
    storage_root: Path | str = DEFAULT_SESSION_STORAGE,
) -> List[str]:
    """
    Return sorted list of session IDs found in storage_root.

    Returns empty list if storage_root does not exist.
    """
    root = Path(storage_root)
    if not root.is_dir():
        return []
    return sorted(
        p.stem.replace(".session", "")
        for p in root.glob("*.session.json")
    )


# ---------------------------------------------------------------------------
# Content-safe session summary (CLI surface)
# ---------------------------------------------------------------------------

def session_status_summary(session: DialogueSession) -> Dict[str, Any]:
    """
    Build a content-safe session status summary for CLI display (ADR-024 §6.2).

    Contains only structural identifiers, counts, modes, and timestamps.
    No prompt, output, persona content, or memory values.
    """
    return {
        "session_id": session.session_id,
        "session_mode": session.session_mode.value,
        "status": session.status,
        "turn_count": session.turn_count,
        "max_turns": session.max_turns,
        "turns_remaining": max(0, session.max_turns - session.turn_count),
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _load_max_turns(runtime_config: Dict[str, Any]) -> int:
    """Load session_max_turns from runtime config; fall back to SESSION_MAX_TURNS."""
    raw = runtime_config.get("session_max_turns")
    if raw is None:
        return SESSION_MAX_TURNS
    if not isinstance(raw, int) or raw <= 0:
        raise ValueError(
            f"SESSION_MAX_TURNS_INVALID: session_max_turns must be a positive integer, got {raw!r}"
        )
    return raw


def _deserialise_session(data: Any) -> DialogueSession:
    """Validate and reconstruct a DialogueSession from a raw JSON dict."""
    if not isinstance(data, dict):
        raise ValueError("SESSION_SCHEMA_INVALID: session file must be a JSON object")

    required = {"schema_version", "session_id", "session_mode", "turn_count",
                "max_turns", "status", "created_at", "updated_at", "turns"}
    missing = required - data.keys()
    if missing:
        raise ValueError(
            f"SESSION_SCHEMA_INVALID: missing required fields: {sorted(missing)}"
        )

    if data["schema_version"] != DIALOGUE_SESSION_SCHEMA_VERSION:
        raise ValueError(
            f"SESSION_SCHEMA_INVALID: schema_version must be "
            f"'{DIALOGUE_SESSION_SCHEMA_VERSION}', got {data['schema_version']!r}"
        )

    try:
        session_mode = SessionMode(data["session_mode"])
    except ValueError:
        raise ValueError(
            f"SESSION_SCHEMA_INVALID: invalid session_mode: {data['session_mode']!r}"
        )

    if data["status"] not in VALID_SESSION_STATUSES:
        raise ValueError(
            f"SESSION_SCHEMA_INVALID: invalid status: {data['status']!r}"
        )

    if not isinstance(data["turns"], list):
        raise ValueError("SESSION_SCHEMA_INVALID: turns must be a list")

    turns: List[TurnRecord] = []
    for i, t in enumerate(data["turns"]):
        if not isinstance(t, dict):
            raise ValueError(f"SESSION_SCHEMA_INVALID: turn[{i}] must be an object")
        turns.append(TurnRecord(
            turn_index=t.get("turn_index", i),
            run_id=t.get("run_id", ""),
            status=t.get("status", "ok"),
            persona_mode=t.get("persona_mode", "executor"),
            latency_ms=t.get("latency_ms"),
            error_code=t.get("error_code"),
            memory_keys_loaded=t.get("memory_keys_loaded", 0),
        ))

    return DialogueSession(
        session_id=data["session_id"],
        session_mode=session_mode,
        turn_count=data["turn_count"],
        max_turns=data["max_turns"],
        status=data["status"],
        turns=turns,
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )
