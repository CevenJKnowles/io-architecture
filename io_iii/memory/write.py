"""
io_iii.memory.write — Memory write contract (ADR-022 §7, Phase 6 M6.6).

All writes require explicit user confirmation.
Writes are atomic: single record, single operation.
No memory values are ever logged.

Content policy (ADR-003, ADR-022 §6):
    MemoryRecord.value is content-plane and must never appear in any log field.
    This module emits no logging; callers are responsible for content-safe logging.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Callable, Optional

from io_iii.memory.store import (
    SENSITIVITY_STANDARD,
    VALID_SENSITIVITY,
    MemoryRecord,
    MemoryStore,
)


def memory_write(
    *,
    scope: str,
    key: str,
    value: str,
    storage_root: str | Path,
    provenance: str = "human",
    sensitivity: str = SENSITIVITY_STANDARD,
    confirm_fn: Optional[Callable[[], bool]] = None,
) -> str:
    """
    Write a single memory record to the store (ADR-022 §7).

    Contracts:
    - Requires explicit user confirmation: confirm_fn() must return True.
    - Atomic: single record, single operation (temp file + rename).
    - Version auto-incremented when key already exists; starts at 1 for new records.
    - created_at preserved when updating an existing record.
    - Returns stable record identifier '<scope>/<key>' on success.
    - Raises ValueError('MEMORY_WRITE_FAILED: ...') on any failure including
      denied confirmation, invalid arguments, or store I/O errors.
    - No memory value appears in any log output from this module.

    Args:
        scope:        Record scope identifier (non-empty string).
        key:          Record key identifier (non-empty string).
        value:        Record content (content-plane — never logged).
        storage_root: Storage root directory path.
        provenance:   Provenance string (default: 'human').
        sensitivity:  Sensitivity tier (default: 'standard').
        confirm_fn:   Callable returning True if user confirms write.
                      Defaults to interactive stdin confirmation.

    Returns:
        str: Stable record identifier '<scope>/<key>'.

    Raises:
        ValueError: Prefixed 'MEMORY_WRITE_FAILED: ...' on any failure.
    """
    if not scope or not isinstance(scope, str):
        raise ValueError("MEMORY_WRITE_FAILED: scope must be a non-empty string")
    if not key or not isinstance(key, str):
        raise ValueError("MEMORY_WRITE_FAILED: key must be a non-empty string")
    if not isinstance(value, str):
        raise ValueError("MEMORY_WRITE_FAILED: value must be a string")
    if sensitivity not in VALID_SENSITIVITY:
        raise ValueError(
            f"MEMORY_WRITE_FAILED: sensitivity must be one of {sorted(VALID_SENSITIVITY)}"
        )

    if confirm_fn is None:
        confirm_fn = _default_confirm_fn(scope=scope, key=key)

    confirmed = confirm_fn()
    if not confirmed:
        raise ValueError(
            f"MEMORY_WRITE_FAILED: write aborted — confirmation denied for {scope}/{key}"
        )

    store = MemoryStore(storage_root)
    existing = store.get(scope, key)

    now = _utcnow_iso()

    if existing is None:
        version = 1
        created_at = now
    else:
        version = existing.version + 1
        created_at = existing.created_at

    try:
        record = MemoryRecord(
            key=key,
            scope=scope,
            value=value,
            version=version,
            provenance=provenance,
            created_at=created_at,
            updated_at=now,
            sensitivity=sensitivity,
        )
        store.put(record)
    except Exception as e:
        raise ValueError(f"MEMORY_WRITE_FAILED: {e}") from e

    return MemoryStore.record_identifier(scope, key)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    """Return current UTC time as ISO 8601 string (second precision)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_confirm_fn(*, scope: str, key: str) -> Callable[[], bool]:
    """Return an interactive stdin confirmation function (for CLI use)."""

    def _confirm() -> bool:
        try:
            answer = input(
                f"Confirm write to memory record '{scope}/{key}'? [y/N] "
            ).strip().lower()
            return answer in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    return _confirm
