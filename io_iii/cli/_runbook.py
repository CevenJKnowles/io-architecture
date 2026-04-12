"""
CLI command: runbook (Phase 4 M4.9 / ADR-016).
"""
from __future__ import annotations

import json
from pathlib import Path

from io_iii.config import load_io3_config
from io_iii.providers.ollama_provider import OllamaProvider
from io_iii.core.runbook import Runbook
import io_iii.core.runbook_runner as _runbook_runner
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.capabilities.builtins import builtin_registry

from ._shared import _get_cfg_dir, _print


def cmd_runbook(args) -> int:
    """
    Execute a Runbook from a JSON file (Phase 4 M4.9 / ADR-016).

    Command surface:
        python -m io_iii runbook <json-file>
        python -m io_iii runbook <json-file> --audit

    Validation order (ADR-016 §3 — contractual):
        1. file exists and is readable
        2. valid JSON
        3. valid runbook schema through existing contract (Runbook.from_dict)
        4. execute through existing runbook execution path (runbook_runner.run)
        5. emit stable structural result

    Thin veneer only (ADR-016 §4). Delegates entirely into runbook_runner.run().
    Does not call engine.run() directly. Does not own orchestration semantics.
    """
    json_path = Path(getattr(args, "json_file"))

    # 1. File exists and is readable.
    if not json_path.exists() or not json_path.is_file():
        _print({"status": "error", "error_code": "RUNBOOK_FILE_NOT_FOUND"})
        return 1

    # 2. Valid JSON.
    try:
        raw_text = json_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        _print({"status": "error", "error_code": "RUNBOOK_INVALID_JSON"})
        return 1

    # 3. Valid runbook schema through existing contract.
    try:
        runbook = Runbook.from_dict(data)
    except (ValueError, TypeError):
        _print({"status": "error", "error_code": "RUNBOOK_SCHEMA_ERROR"})
        return 1

    # 4. Execute through existing runbook execution path.
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)
    deps = RuntimeDependencies(
        ollama_provider_factory=OllamaProvider.from_config,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )

    result = _runbook_runner.run(
        runbook=runbook,
        cfg=cfg,
        deps=deps,
        audit=bool(getattr(args, "audit", False)),
    )

    # 5. Emit stable structural result (ADR-016 §6).
    # M4.8 metadata projection summary — structural, content-safe (ADR-016 §8).
    metadata_summary = None
    if result.metadata is not None:
        metadata_summary = {
            "runbook_id": result.metadata.runbook_id,
            "event_count": len(result.metadata.events),
        }

    if result.terminated_early:
        # Runbook failure: surface ADR-013 failure fields only (ADR-016 §7).
        failure_kind = None
        failure_code = None
        if result.failed_step_index is not None:
            idx = result.failed_step_index
            if 0 <= idx < len(result.step_outcomes):
                step_failure = result.step_outcomes[idx].failure
                if step_failure is not None:
                    failure_kind = step_failure.kind.value
                    failure_code = step_failure.code
        _print({
            "status": "error",
            "runbook_id": result.runbook_id,
            "steps_completed": result.steps_completed,
            "terminated_early": result.terminated_early,
            "failed_step_index": result.failed_step_index,
            "failure_kind": failure_kind,
            "failure_code": failure_code,
            "metadata_projection": metadata_summary,
        })
        return 1

    _print({
        "status": "ok",
        "runbook_id": result.runbook_id,
        "steps_completed": result.steps_completed,
        "terminated_early": result.terminated_early,
        "failed_step_index": result.failed_step_index,
        "metadata_projection": metadata_summary,
    })
    return 0
