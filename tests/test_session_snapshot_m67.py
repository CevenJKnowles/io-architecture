"""
test_session_snapshot_m67.py — Phase 6 M6.7 session snapshot export/import tests (ADR-022 §8).

Verifies:

  Unit — SessionSnapshot construction
  - SessionSnapshot can be constructed with all required fields
  - SessionSnapshot is frozen (fields cannot be reassigned)

  Unit — export_snapshot
  - writes a JSON file to storage_root/<run_id>.snapshot.json by default
  - explicit output_path overrides default path
  - exported fields match source SessionState
  - active_memory_pack_ids are preserved in export
  - no output_path and no storage_root raises SNAPSHOT_SCHEMA_INVALID

  Unit — import_snapshot
  - round-trip: export then import returns equivalent snapshot
  - file not found raises SNAPSHOT_SCHEMA_INVALID
  - invalid JSON raises SNAPSHOT_SCHEMA_INVALID
  - missing required field raises SNAPSHOT_SCHEMA_INVALID
  - wrong schema_version raises SNAPSHOT_SCHEMA_INVALID

  Content safety
  - snapshot dict contains no value/prompt/output/content fields
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from io_iii.core.snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    SessionSnapshot,
    export_snapshot,
    import_snapshot,
)
from io_iii.core.session_state import AuditGateState, RouteInfo, SessionState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(
    request_id: str = "20260412T000000Z-test",
    mode: str = "executor",
    route_id: str = "executor",
) -> SessionState:
    return SessionState(
        request_id=request_id,
        started_at_ms=0,
        mode=mode,
        config_dir="./architecture/runtime/config",
        route=RouteInfo(
            mode=mode,
            primary_target=mode,
            secondary_target=None,
            selected_target=mode,
            selected_provider="null",
            fallback_used=False,
            fallback_reason=None,
            boundaries={"single_voice_output": True},
        ),
        audit=AuditGateState(audit_enabled=False),
        status="ok",
        provider="null",
        model=None,
        route_id=route_id,
        persona_contract_version="0.2.0",
        persona_id="io-ii:v1.4.2",
        logging_policy={"content": "disabled"},
    )


# ---------------------------------------------------------------------------
# SessionSnapshot construction
# ---------------------------------------------------------------------------

def test_session_snapshot_can_be_constructed() -> None:
    snap = SessionSnapshot(
        schema_version="v1",
        run_id="run-001",
        workflow_position="executor",
        active_memory_pack_ids=["pack-a"],
        governance_mode="executor",
        exported_at="2026-04-12T00:00:00Z",
    )
    assert snap.schema_version == "v1"
    assert snap.run_id == "run-001"
    assert snap.active_memory_pack_ids == ["pack-a"]


def test_session_snapshot_is_frozen() -> None:
    snap = SessionSnapshot(
        schema_version="v1",
        run_id="run-001",
        workflow_position="executor",
        active_memory_pack_ids=[],
        governance_mode="executor",
        exported_at="2026-04-12T00:00:00Z",
    )
    with pytest.raises((AttributeError, TypeError)):
        snap.run_id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# export_snapshot
# ---------------------------------------------------------------------------

def test_export_writes_to_default_path(tmp_path: Path) -> None:
    state = _make_state(request_id="run-abc")
    export_snapshot(state, storage_root=tmp_path)
    expected = tmp_path / "run-abc.snapshot.json"
    assert expected.is_file()


def test_export_explicit_output_path(tmp_path: Path) -> None:
    state = _make_state(request_id="run-xyz")
    out = tmp_path / "custom" / "snap.json"
    snap = export_snapshot(state, output_path=out)
    assert out.is_file()
    assert snap.run_id == "run-xyz"


def test_export_fields_match_session_state(tmp_path: Path) -> None:
    state = _make_state(request_id="run-001", mode="executor", route_id="executor")
    snap = export_snapshot(state, storage_root=tmp_path)
    assert snap.schema_version == SNAPSHOT_SCHEMA_VERSION
    assert snap.run_id == "run-001"
    assert snap.workflow_position == "executor"
    assert snap.governance_mode == "executor"
    assert isinstance(snap.exported_at, str) and snap.exported_at


def test_export_active_memory_pack_ids_preserved(tmp_path: Path) -> None:
    state = _make_state()
    packs = ["core-context", "project-notes"]
    snap = export_snapshot(state, active_memory_pack_ids=packs, storage_root=tmp_path)
    assert snap.active_memory_pack_ids == packs


def test_export_no_path_or_root_raises(tmp_path: Path) -> None:
    state = _make_state()
    with pytest.raises(ValueError, match="SNAPSHOT_SCHEMA_INVALID"):
        export_snapshot(state)


# ---------------------------------------------------------------------------
# import_snapshot
# ---------------------------------------------------------------------------

def test_import_round_trip(tmp_path: Path) -> None:
    state = _make_state(request_id="run-rt", mode="executor")
    export_snapshot(state, storage_root=tmp_path)
    snap_path = tmp_path / "run-rt.snapshot.json"
    imported = import_snapshot(snap_path)
    assert imported.run_id == "run-rt"
    assert imported.governance_mode == "executor"
    assert imported.schema_version == SNAPSHOT_SCHEMA_VERSION


def test_import_file_not_found_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SNAPSHOT_SCHEMA_INVALID"):
        import_snapshot(tmp_path / "nonexistent.snapshot.json")


def test_import_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.snapshot.json"
    bad.write_text("NOT JSON {{{{", encoding="utf-8")
    with pytest.raises(ValueError, match="SNAPSHOT_SCHEMA_INVALID"):
        import_snapshot(bad)


def test_import_missing_required_field_raises(tmp_path: Path) -> None:
    data = {
        "schema_version": "v1",
        "run_id": "run-001",
        # workflow_position intentionally omitted
        "active_memory_pack_ids": [],
        "governance_mode": "executor",
        "exported_at": "2026-04-12T00:00:00Z",
    }
    bad = tmp_path / "missing.snapshot.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="SNAPSHOT_SCHEMA_INVALID"):
        import_snapshot(bad)


def test_import_wrong_schema_version_raises(tmp_path: Path) -> None:
    data = {
        "schema_version": "v99",
        "run_id": "run-001",
        "workflow_position": "executor",
        "active_memory_pack_ids": [],
        "governance_mode": "executor",
        "exported_at": "2026-04-12T00:00:00Z",
    }
    bad = tmp_path / "bad_ver.snapshot.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="SNAPSHOT_SCHEMA_INVALID"):
        import_snapshot(bad)


# ---------------------------------------------------------------------------
# Content safety
# ---------------------------------------------------------------------------

def test_snapshot_dict_contains_no_content_fields(tmp_path: Path) -> None:
    state = _make_state(request_id="run-safe")
    export_snapshot(state, storage_root=tmp_path)
    snap_path = tmp_path / "run-safe.snapshot.json"
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    forbidden_keys = {"value", "prompt", "output", "content", "completion", "draft", "revision"}
    present = forbidden_keys & data.keys()
    assert not present, f"Snapshot contains forbidden content fields: {present}"
