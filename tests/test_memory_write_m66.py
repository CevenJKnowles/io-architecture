"""
test_memory_write_m66.py — Phase 6 M6.6 memory write contract tests (ADR-022 §7).

Verifies:

  Unit — argument validation
  - empty scope raises MEMORY_WRITE_FAILED
  - empty key raises MEMORY_WRITE_FAILED
  - invalid sensitivity raises MEMORY_WRITE_FAILED

  Unit — confirmation gate
  - denied confirmation raises MEMORY_WRITE_FAILED
  - confirmed write succeeds and returns identifier

  Unit — version management
  - new key starts at version 1
  - existing key gets version incremented
  - created_at preserved when updating an existing record

  Unit — return value and storage
  - returns scope/key identifier on success
  - written record is retrievable by get()

  Content safety
  - written record value absent from to_log_safe() projection
  - no value field in to_log_safe() dict

  Integration — sensitivity tier
  - custom sensitivity tier is persisted
"""
from __future__ import annotations

import pytest
from pathlib import Path

from io_iii.memory.write import memory_write
from io_iii.memory.store import MemoryStore, SENSITIVITY_STANDARD, SENSITIVITY_ELEVATED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _confirm_yes() -> bool:
    return True


def _confirm_no() -> bool:
    return False


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

def test_empty_scope_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MEMORY_WRITE_FAILED"):
        memory_write(scope="", key="k", value="v", storage_root=tmp_path, confirm_fn=_confirm_yes)


def test_empty_key_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MEMORY_WRITE_FAILED"):
        memory_write(scope="s", key="", value="v", storage_root=tmp_path, confirm_fn=_confirm_yes)


def test_invalid_sensitivity_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MEMORY_WRITE_FAILED"):
        memory_write(
            scope="s", key="k", value="v",
            storage_root=tmp_path,
            sensitivity="ultra-secret",
            confirm_fn=_confirm_yes,
        )


# ---------------------------------------------------------------------------
# Confirmation gate
# ---------------------------------------------------------------------------

def test_denied_confirmation_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MEMORY_WRITE_FAILED"):
        memory_write(scope="s", key="k", value="v", storage_root=tmp_path, confirm_fn=_confirm_no)


def test_confirmed_write_succeeds(tmp_path: Path) -> None:
    identifier = memory_write(
        scope="test", key="note", value="hello",
        storage_root=tmp_path,
        confirm_fn=_confirm_yes,
    )
    assert identifier == "test/note"


# ---------------------------------------------------------------------------
# Version management
# ---------------------------------------------------------------------------

def test_new_key_starts_at_version_1(tmp_path: Path) -> None:
    memory_write(scope="s", key="k", value="v", storage_root=tmp_path, confirm_fn=_confirm_yes)
    store = MemoryStore(tmp_path)
    record = store.get("s", "k")
    assert record is not None
    assert record.version == 1


def test_existing_key_increments_version(tmp_path: Path) -> None:
    memory_write(scope="s", key="k", value="v1", storage_root=tmp_path, confirm_fn=_confirm_yes)
    memory_write(scope="s", key="k", value="v2", storage_root=tmp_path, confirm_fn=_confirm_yes)
    store = MemoryStore(tmp_path)
    record = store.get("s", "k")
    assert record is not None
    assert record.version == 2


def test_created_at_preserved_on_update(tmp_path: Path) -> None:
    memory_write(scope="s", key="k", value="v1", storage_root=tmp_path, confirm_fn=_confirm_yes)
    store = MemoryStore(tmp_path)
    original = store.get("s", "k")
    assert original is not None
    original_created_at = original.created_at

    memory_write(scope="s", key="k", value="v2", storage_root=tmp_path, confirm_fn=_confirm_yes)
    updated = store.get("s", "k")
    assert updated is not None
    assert updated.created_at == original_created_at


# ---------------------------------------------------------------------------
# Return value and storage
# ---------------------------------------------------------------------------

def test_returns_scope_key_identifier(tmp_path: Path) -> None:
    result = memory_write(scope="io_iii", key="context", value="abc", storage_root=tmp_path, confirm_fn=_confirm_yes)
    assert result == "io_iii/context"


def test_written_record_is_retrievable(tmp_path: Path) -> None:
    memory_write(scope="s", key="k", value="content here", storage_root=tmp_path, confirm_fn=_confirm_yes)
    store = MemoryStore(tmp_path)
    record = store.get("s", "k")
    assert record is not None
    assert record.value == "content here"


# ---------------------------------------------------------------------------
# Content safety
# ---------------------------------------------------------------------------

def test_value_absent_from_to_log_safe(tmp_path: Path) -> None:
    memory_write(scope="s", key="k", value="SECRET", storage_root=tmp_path, confirm_fn=_confirm_yes)
    store = MemoryStore(tmp_path)
    record = store.get("s", "k")
    assert record is not None
    log_safe = record.to_log_safe()
    assert "SECRET" not in str(log_safe)


def test_no_value_key_in_to_log_safe(tmp_path: Path) -> None:
    memory_write(scope="s", key="k", value="v", storage_root=tmp_path, confirm_fn=_confirm_yes)
    store = MemoryStore(tmp_path)
    record = store.get("s", "k")
    assert record is not None
    log_safe = record.to_log_safe()
    assert "value" not in log_safe


# ---------------------------------------------------------------------------
# Sensitivity tier
# ---------------------------------------------------------------------------

def test_custom_sensitivity_persisted(tmp_path: Path) -> None:
    memory_write(
        scope="s", key="k", value="v",
        storage_root=tmp_path,
        sensitivity=SENSITIVITY_ELEVATED,
        confirm_fn=_confirm_yes,
    )
    store = MemoryStore(tmp_path)
    record = store.get("s", "k")
    assert record is not None
    assert record.sensitivity == SENSITIVITY_ELEVATED
