"""
CLI commands: replay, resume (Phase 4 M4.11 / ADR-020).
"""
from __future__ import annotations

from io_iii.config import load_io3_config
from io_iii.providers.ollama_provider import OllamaProvider
from io_iii.core.replay_resume import (
    replay as _replay,
    resume as _resume,
    DEFAULT_STORAGE_ROOT,
    ReplayResumeResult,
)
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.capabilities.builtins import builtin_registry

from ._shared import _get_cfg_dir, _print


def _emit_replay_resume_result(result: "ReplayResumeResult") -> int:
    """Emit ADR-020 §8.2 output contract and return exit code."""
    if result.status == "error":
        _print({
            "status": "error",
            "mode": result.mode,
            "run_id": result.run_id,
            "source_run_id": result.source_run_id,
            "runbook_id": result.runbook_id,
            "failure_kind": result.failure_kind,
            "failure_code": result.failure_code,
            "failed_step_index": result.failed_step_index,
            "terminated_early": result.terminated_early,
        })
        return 1
    _print({
        "status": "success",
        "mode": result.mode,
        "run_id": result.run_id,
        "source_run_id": result.source_run_id,
        "runbook_id": result.runbook_id,
        "steps_completed": result.steps_completed,
        "total_steps": result.total_steps,
        "metadata": result.metadata_summary,
    })
    return 0


def cmd_replay(args) -> int:
    """
    Re-execute a prior runbook run from step 0 (Phase 4 M4.11 / ADR-020 §8.1).

    Command surface:
        python -m io_iii replay <run_id>
        python -m io_iii replay <run_id> --audit
    """
    source_run_id = getattr(args, "run_id")
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)
    deps = RuntimeDependencies(
        ollama_provider_factory=OllamaProvider.from_config,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )
    result = _replay(
        source_run_id,
        cfg=cfg,
        deps=deps,
        audit=bool(getattr(args, "audit", False)),
        storage_root=DEFAULT_STORAGE_ROOT,
    )
    return _emit_replay_resume_result(result)


def cmd_resume(args) -> int:
    """
    Continue a prior runbook run from the first incomplete step (Phase 4 M4.11 / ADR-020 §8.1).

    Command surface:
        python -m io_iii resume <run_id>
        python -m io_iii resume <run_id> --audit
    """
    source_run_id = getattr(args, "run_id")
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)
    deps = RuntimeDependencies(
        ollama_provider_factory=OllamaProvider.from_config,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )
    result = _resume(
        source_run_id,
        cfg=cfg,
        deps=deps,
        audit=bool(getattr(args, "audit", False)),
        storage_root=DEFAULT_STORAGE_ROOT,
    )
    return _emit_replay_resume_result(result)
