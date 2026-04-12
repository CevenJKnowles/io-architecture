"""
CLI commands: memory write, session export, session import (Phase 6 M6.6–M6.7 / ADR-022).
"""
from __future__ import annotations

from io_iii.config import load_io3_config
from io_iii.persona_contract import PERSONA_CONTRACT_VERSION
from io_iii.memory.write import memory_write as _memory_write
from io_iii.core.snapshot import export_snapshot as _export_snapshot, import_snapshot as _import_snapshot

from ._shared import _get_cfg_dir, _print


def _build_minimal_session_state(
    *,
    request_id: str,
    mode: str,
    route_id: str,
    cfg,
):
    """Build a minimal SessionState for snapshot export (no execution performed)."""
    from io_iii.core.session_state import AuditGateState, RouteInfo, SessionState

    route = RouteInfo(
        mode=mode,
        primary_target=None,
        secondary_target=None,
        selected_target=None,
        selected_provider="null",
        fallback_used=False,
        fallback_reason=None,
        boundaries={},
    )
    return SessionState(
        request_id=request_id,
        started_at_ms=0,
        mode=mode,
        config_dir=str(cfg.config_dir),
        route=route,
        audit=AuditGateState(audit_enabled=False),
        status="ok",
        provider="null",
        model=None,
        route_id=route_id,
        persona_contract_version=PERSONA_CONTRACT_VERSION,
        persona_id=None,
        logging_policy=cfg.logging,
    )


def cmd_memory_write(args) -> int:
    """
    Write a single memory record to the store (Phase 6 M6.6 / ADR-022 §7).

    Command surface:
        python -m io_iii memory write --scope <scope> --key <key> --value <value>
        [--sensitivity standard|elevated|restricted] [--provenance human|mixed|llm:<slug>]

    Properties:
    - Requires explicit user confirmation before writing.
    - Atomic: single record, single operation.
    - Version auto-incremented when key already exists.
    - No memory value logged.
    """
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)

    # Resolve storage_root from memory_packs config if available.
    try:
        from io_iii.memory.packs import load_memory_packs_config
        packs_cfg = load_memory_packs_config(cfg_dir)
        storage_root = packs_cfg.storage_root
    except Exception:
        storage_root = "./memory_store"

    scope = args.scope
    key = args.key
    value = args.value
    sensitivity = getattr(args, "sensitivity", "standard")
    provenance = getattr(args, "provenance", "human")

    try:
        identifier = _memory_write(
            scope=scope,
            key=key,
            value=value,
            storage_root=storage_root,
            provenance=provenance,
            sensitivity=sensitivity,
            # confirm_fn=None → uses interactive stdin confirmation
        )
        _print({"status": "ok", "identifier": identifier})
        return 0
    except ValueError as e:
        _print({"status": "error", "error_code": str(e).split(":")[0].strip()})
        return 1


def cmd_session_export(args) -> int:
    """
    Export a portable session snapshot (Phase 6 M6.7 / ADR-022 §8).

    Command surface:
        python -m io_iii session export --run-id <id> --mode <mode>
            [--workflow-position <pos>] [--output <path>] [--pack <id>]...

    Properties:
    - User-initiated only; no automatic exports.
    - Snapshot contains control-plane fields only; no content.
    - Default path: <storage_root>/<run_id>.snapshot.json
    """
    run_id = args.run_id
    mode = args.mode
    workflow_position = getattr(args, "workflow_position", None) or mode
    packs = getattr(args, "pack", []) or []
    output = getattr(args, "output", None)

    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)

    try:
        from io_iii.memory.packs import load_memory_packs_config
        packs_cfg = load_memory_packs_config(cfg_dir)
        storage_root = packs_cfg.storage_root
    except Exception:
        storage_root = "./memory_store"

    # Build a minimal SessionState for snapshot export (control-plane only).
    state = _build_minimal_session_state(
        request_id=run_id,
        mode=mode,
        route_id=workflow_position,
        cfg=cfg,
    )

    try:
        snap = _export_snapshot(
            state,
            active_memory_pack_ids=packs,
            output_path=output,
            storage_root=None if output else storage_root,
        )
        _print({
            "status": "ok",
            "schema_version": snap.schema_version,
            "run_id": snap.run_id,
            "workflow_position": snap.workflow_position,
            "active_memory_pack_ids": snap.active_memory_pack_ids,
            "governance_mode": snap.governance_mode,
            "exported_at": snap.exported_at,
        })
        return 0
    except ValueError as e:
        _print({"status": "error", "error_code": str(e).split(":")[0].strip()})
        return 1


def cmd_session_import(args) -> int:
    """
    Import and validate a session snapshot from disk (Phase 6 M6.7 / ADR-022 §8).

    Command surface:
        python -m io_iii session import --snapshot <path>
    """
    snapshot_path = args.snapshot

    try:
        snap = _import_snapshot(snapshot_path)
        _print({
            "status": "ok",
            "schema_version": snap.schema_version,
            "run_id": snap.run_id,
            "workflow_position": snap.workflow_position,
            "active_memory_pack_ids": snap.active_memory_pack_ids,
            "governance_mode": snap.governance_mode,
            "exported_at": snap.exported_at,
        })
        return 0
    except ValueError as e:
        _print({"status": "error", "error_code": str(e).split(":")[0].strip()})
        return 1
