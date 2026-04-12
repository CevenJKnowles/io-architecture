"""
io_iii.core.snapshot — SessionState snapshot export/import (ADR-022 §8, Phase 6 M6.7).

Provides a governed export/import contract for a portable session artefact.
Export is user-initiated only; no automatic exports.

Content policy (ADR-003, ADR-022 §6):
    Snapshots must never contain memory values, model output, or prompt content.
    All fields are control-plane identifiers and metadata only.
"""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from io_iii.core.session_state import SessionState

SNAPSHOT_SCHEMA_VERSION = "v1"

REQUIRED_SNAPSHOT_FIELDS = frozenset({
    "schema_version",
    "run_id",
    "workflow_position",
    "active_memory_pack_ids",
    "governance_mode",
    "exported_at",
})


@dataclass(frozen=True)
class SessionSnapshot:
    """
    Portable, content-safe session artefact (ADR-022 §8).

    Fields:
        schema_version          — snapshot schema version; must be 'v1'
        run_id                  — source run identifier (= SessionState.request_id)
        workflow_position       — route/mode identifier at export time
        active_memory_pack_ids  — list of active memory pack IDs at export time
        governance_mode         — execution mode at export time
        exported_at             — ISO 8601 export timestamp

    Content policy:
        Must never contain memory values, model output, or prompt content.
        All fields are control-plane identifiers and metadata only.
    """
    schema_version: str
    run_id: str
    workflow_position: str
    active_memory_pack_ids: List[str]
    governance_mode: str
    exported_at: str


def export_snapshot(
    session_state: SessionState,
    *,
    active_memory_pack_ids: Optional[List[str]] = None,
    output_path: Optional[str | Path] = None,
    storage_root: Optional[str | Path] = None,
) -> SessionSnapshot:
    """
    Export a portable snapshot from a SessionState (ADR-022 §8).

    The snapshot captures control-plane fields only. No prompt, output, or
    memory values are included.

    Args:
        session_state:           Source session state (control-plane only).
        active_memory_pack_ids:  Active pack IDs at export time (default: []).
        output_path:             Explicit output path (overrides default path).
        storage_root:            Root for default path; required if output_path
                                 not set.

    Returns:
        SessionSnapshot written to disk.

    Raises:
        ValueError('SNAPSHOT_SCHEMA_INVALID: ...') on structural failure.
    """
    if active_memory_pack_ids is None:
        active_memory_pack_ids = []

    now = _utcnow_iso()

    snapshot = SessionSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        run_id=session_state.request_id,
        workflow_position=session_state.route_id,
        active_memory_pack_ids=list(active_memory_pack_ids),
        governance_mode=session_state.mode,
        exported_at=now,
    )

    resolved_path = _resolve_output_path(
        output_path=output_path,
        storage_root=storage_root,
        run_id=session_state.request_id,
    )

    _write_snapshot(snapshot, resolved_path)
    return snapshot


def import_snapshot(path: str | Path) -> SessionSnapshot:
    """
    Import and validate a session snapshot from disk (ADR-022 §8).

    Validates:
    - File exists and is readable JSON
    - All required fields present
    - schema_version == 'v1'
    - active_memory_pack_ids is a list
    - String fields are non-empty strings

    Returns:
        SessionSnapshot on success.

    Raises:
        ValueError('SNAPSHOT_SCHEMA_INVALID: ...') on any validation failure.
    """
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"SNAPSHOT_SCHEMA_INVALID: file not found: {path}")

    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        raise ValueError(
            f"SNAPSHOT_SCHEMA_INVALID: could not read or parse snapshot file: {e}"
        ) from e

    if not isinstance(data, dict):
        raise ValueError("SNAPSHOT_SCHEMA_INVALID: snapshot must be a JSON object")

    _validate_snapshot_dict(data)

    return SessionSnapshot(
        schema_version=data["schema_version"],
        run_id=data["run_id"],
        workflow_position=data["workflow_position"],
        active_memory_pack_ids=list(data["active_memory_pack_ids"]),
        governance_mode=data["governance_mode"],
        exported_at=data["exported_at"],
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_snapshot_dict(data: Dict[str, Any]) -> None:
    """Validate a raw snapshot dict against all ADR-022 §8 constraints."""
    missing = [f for f in sorted(REQUIRED_SNAPSHOT_FIELDS) if f not in data]
    if missing:
        raise ValueError(
            f"SNAPSHOT_SCHEMA_INVALID: missing required fields: {missing}"
        )

    if data["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            f"SNAPSHOT_SCHEMA_INVALID: schema_version must be "
            f"'{SNAPSHOT_SCHEMA_VERSION}', got '{data['schema_version']}'"
        )

    if not isinstance(data["active_memory_pack_ids"], list):
        raise ValueError(
            "SNAPSHOT_SCHEMA_INVALID: active_memory_pack_ids must be a list"
        )

    for field in ("run_id", "workflow_position", "governance_mode", "exported_at"):
        if not isinstance(data[field], str) or not data[field].strip():
            raise ValueError(
                f"SNAPSHOT_SCHEMA_INVALID: field '{field}' must be a non-empty string"
            )


def _resolve_output_path(
    *,
    output_path: Optional[str | Path],
    storage_root: Optional[str | Path],
    run_id: str,
) -> Path:
    if output_path is not None:
        return Path(output_path)
    if storage_root is not None:
        return Path(storage_root) / f"{run_id}.snapshot.json"
    raise ValueError(
        "SNAPSHOT_SCHEMA_INVALID: either output_path or storage_root must be provided"
    )


def _write_snapshot(snapshot: SessionSnapshot, path: Path) -> None:
    """Write snapshot to disk as JSON (atomic via temp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": snapshot.schema_version,
        "run_id": snapshot.run_id,
        "workflow_position": snapshot.workflow_position,
        "active_memory_pack_ids": snapshot.active_memory_pack_ids,
        "governance_mode": snapshot.governance_mode,
        "exported_at": snapshot.exported_at,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _utcnow_iso() -> str:
    """Return current UTC time as ISO 8601 string (second precision)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
