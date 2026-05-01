"""
IO-III CLI subpackage.

cmd_run and cmd_capability are defined here (not in _run.py) so that
integration tests can monkeypatch their dependencies via:
    import io_iii.cli as cli
    monkeypatch.setattr(cli, "load_io3_config", fake)
Python resolves function globals from the module where the function is defined,
so patching io_iii.cli.X only works for functions whose __globals__ == cli.__dict__.

All other commands live in their domain submodules and are re-exported here.
"""
from __future__ import annotations

import argparse
import time

# ---- Dependencies imported here so monkeypatching cli.X works for cmd_run / cmd_capability ----
from io_iii.metadata_logging import append_metadata, make_request_id
from io_iii.config import load_io3_config, default_config_dir
from io_iii.routing import resolve_route
from io_iii.providers.ollama_provider import OllamaProvider
from io_iii.providers.provider_contract import ProviderError
from io_iii.persona_contract import PERSONA_CONTRACT_VERSION
from io_iii.core.engine import run as engine_run
from io_iii.core.session_state import SessionState, RouteInfo, AuditGateState, validate_session_state
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.capabilities.builtins import builtin_registry

# ---- Shared utilities ----
from ._shared import (
    _to_jsonable,
    _print,
    _get_cfg_dir,
    _parse_capability_payload,
    MAX_AUDIT_PASSES,
    MAX_REVISION_PASSES,
)

# ---- Domain submodules ----
from ._run import cmd_capabilities, cmd_config_show, cmd_route, cmd_about
from ._runbook import cmd_runbook
from ._replay import _emit_replay_resume_result
from io_iii.core.replay_resume import (
    replay as _replay,
    resume as _resume,
    DEFAULT_STORAGE_ROOT,
)
from ._memory import (
    cmd_memory_write,
    cmd_session_export,
    cmd_session_import,
    _build_minimal_session_state,
)
from ._init import cmd_validate, cmd_init
from ._session_shell import (
    cmd_session_start,
    cmd_session_continue,
    cmd_session_status,
    cmd_session_close,
)


__all__ = [
    "main",
    "cmd_run",
    "cmd_capability",
    "cmd_capabilities",
    "cmd_config_show",
    "cmd_route",
    "cmd_about",
    "cmd_runbook",
    "cmd_replay",
    "cmd_resume",
    "cmd_memory_write",
    "cmd_session_export",
    "cmd_session_import",
    "cmd_validate",
    "cmd_init",
    "cmd_session_start",
    "cmd_session_continue",
    "cmd_session_status",
    "cmd_session_close",
    "cmd_serve",
]


# -----------------------------
# Audit Gate Hard Limits (ADR-009)
# -----------------------------
# (also defined in _shared.py; re-declared here so patches to cli.MAX_* work)
MAX_AUDIT_PASSES = 1
MAX_REVISION_PASSES = 1


def cmd_replay(args) -> int:
    """
    Re-execute a prior runbook run from step 0 (Phase 4 M4.11 / ADR-020 §8.1).

    Defined here (not in _replay.py) so that integration tests can patch
    io_iii.cli._replay and have the patch take effect.
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
    Continue a prior runbook run from the first incomplete step (ADR-020 §8.1).

    Defined here (not in _replay.py) so that integration tests can patch
    io_iii.cli._resume and have the patch take effect.
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


def cmd_run(args) -> int:
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)
    request_id = make_request_id()
    t0 = time.perf_counter()

    # M5.3: Constellation integrity guard (ADR-021 §4).
    # Runs after config load, before routing resolution.
    if getattr(args, "no_constellation_check", False):
        import sys as _sys
        print(
            "WARN: constellation integrity check bypassed via --no-constellation-check",
            file=_sys.stderr,
        )
    else:
        from io_iii.core.constellation import check_constellation
        check_constellation(cfg.routing)

    selection = resolve_route(
        routing_cfg=cfg.routing["routing_table"],
        mode=args.mode,
        providers_cfg=cfg.providers,
        supported_providers={"null", "ollama"},
    )

    # Provider health check (ADR-011): pre-flight, before SessionState creation.
    # Skipped for null provider and when --no-health-check is passed.
    if selection.selected_provider == "ollama" and not getattr(args, "no_health_check", False):
        try:
            OllamaProvider.from_config(cfg.providers).check_reachable()
        except RuntimeError as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            append_metadata(
                cfg.logging,
                {
                    "request_id": request_id,
                    "mode": getattr(selection, "mode", None),
                    "provider": "ollama",
                    "model": None,
                    "status": "error",
                    "latency_ms": latency_ms,
                    "error_code": "PROVIDER_UNAVAILABLE",
                    "fallback_used": False,
                    "fallback_reason": None,
                    "selected_primary": getattr(selection, "primary_target", None),
                },
            )
            raise

    # Prompt source (CLI concern)
    prompt = getattr(args, "prompt", None)
    if not prompt:
        import sys

        prompt = sys.stdin.read().strip() or "Say hello in one short sentence."

    cap_id = getattr(args, "capability_id", None)
    cap_payload = (
        _parse_capability_payload(getattr(args, "capability_payload_json", None)) if cap_id else None
    )

    # Build SessionState (control-plane; no prompt text stored)
    route = RouteInfo(
        mode=selection.mode,
        primary_target=selection.primary_target,
        secondary_target=selection.secondary_target,
        selected_target=selection.selected_target,
        selected_provider=selection.selected_provider,
        fallback_used=selection.fallback_used,
        fallback_reason=selection.fallback_reason,
        boundaries=selection.boundaries,
    )

    state = SessionState(
        request_id=request_id,
        started_at_ms=int(time.time() * 1000),
        mode=selection.mode,
        config_dir=str(cfg.config_dir),
        route=route,
        audit=AuditGateState(audit_enabled=bool(getattr(args, "audit", False))),
        status="ok",
        provider=selection.selected_provider,
        model=None,
        route_id=selection.mode,
        persona_contract_version=PERSONA_CONTRACT_VERSION,
        persona_id=None,
        logging_policy=cfg.logging,
    )

    # Defensive invariant enforcement (SessionState v0)
    validate_session_state(state)

    # Phase 3: explicit dependency bundle (injection seams)
    deps = RuntimeDependencies(
        ollama_provider_factory=OllamaProvider.from_config,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )

    try:
        state2, result = engine_run(
            cfg=cfg,
            session_state=state,
            user_prompt=prompt,
            audit=bool(getattr(args, "audit", False)),
            deps=deps,
            capability_id=cap_id,
            capability_payload=cap_payload,
        )

        # Defensive invariant enforcement (SessionState v0)
        validate_session_state(state2)

        payload = {
            "logging_policy": cfg.logging,
            "result": {
                "message": result.message,
                "meta": result.meta,
                "mode": state2.mode,
                "provider": result.provider,
                "model": result.model,
                "route_id": state2.route_id,
            },
            "audit_meta": result.audit_meta,
        }

        # Trace summary (content-safe)
        trace_obj = result.meta.get("trace") if isinstance(result.meta, dict) else None
        trace_steps = None
        trace_total_ms = None
        if isinstance(trace_obj, dict) and isinstance(trace_obj.get("steps"), list):
            trace_steps = len(trace_obj["steps"])
            trace_total_ms = sum(
                int(s.get("duration_ms", 0)) for s in trace_obj["steps"] if isinstance(s, dict)
            )

        # Engine observability summary (M4.5; structural count only — no event content)
        engine_events_raw = result.meta.get("engine_events") if isinstance(result.meta, dict) else None
        engine_event_count = len(engine_events_raw) if isinstance(engine_events_raw, list) else None

        # Capability summary (content-safe; MUST NOT include output)
        cap_meta = result.meta.get("capability") if isinstance(result.meta, dict) else None

        capability_ok = None
        capability_version = None
        capability_duration_ms = None
        capability_error_code = None
        if isinstance(cap_meta, dict):
            capability_ok = cap_meta.get("ok")
            capability_version = cap_meta.get("version")
            capability_duration_ms = cap_meta.get("duration_ms")
            capability_error_code = cap_meta.get("error_code")

        # Telemetry projection (M5.2; content-safe counts only)
        telemetry_raw = result.meta.get("telemetry") if isinstance(result.meta, dict) else None

        # Metadata logging (NO prompt/response content; prompt_hash is safe)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        append_metadata(
            cfg.logging,
            {
                "request_id": request_id,
                "mode": state2.mode,
                "provider": result.provider,
                "model": result.model,
                "status": "ok",
                "latency_ms": latency_ms,
                "prompt_hash": result.prompt_hash,
                "fallback_used": getattr(selection, "fallback_used", None),
                "fallback_reason": getattr(selection, "fallback_reason", None),
                "selected_primary": getattr(selection, "primary_target", None),
                "capability_id": cap_id,
                "capability_ok": capability_ok,
                "capability_version": capability_version,
                "capability_duration_ms": capability_duration_ms,
                "capability_error_code": capability_error_code,
                "trace_steps": trace_steps,
                "trace_total_ms": trace_total_ms,
                "engine_event_count": engine_event_count,
                "telemetry": telemetry_raw,
            },
        )

        if getattr(args, "raw", False):
            print(result.message)
        else:
            _print(payload)
        return 0

    except ProviderError as e:
        # M10.2: intercept before generic handler to emit plain-language hint on 404.
        import sys as _sys
        _is_404 = "404" in e.detail
        _error_code = "PROVIDER_MODEL_NOT_FOUND" if _is_404 else e.code
        latency_ms = int((time.perf_counter() - t0) * 1000)
        append_metadata(
            cfg.logging,
            {
                "request_id": request_id,
                "mode": getattr(selection, "mode", None),
                "provider": getattr(selection, "selected_provider", None),
                "model": None,
                "status": "error",
                "latency_ms": latency_ms,
                "error_code": _error_code,
                "failure_kind": None,
                "fallback_used": getattr(selection, "fallback_used", None),
                "fallback_reason": getattr(selection, "fallback_reason", None),
                "selected_primary": getattr(selection, "primary_target", None),
                "capability_id": cap_id,
                "capability_ok": False if cap_id else None,
                "capability_error_code": _error_code if cap_id else None,
            },
        )
        if _is_404:
            print(
                f"\nModel not found in Ollama: {e.detail}\n\n"
                "Check which models are available:\n"
                "  ollama list\n\n"
                "Then update architecture/runtime/config/routing_table.yaml "
                "to use a model name that appears in that list.\n",
                file=_sys.stderr,
            )
            _sys.exit(1)
        raise

    except Exception as e:
        # Metadata logging (error case; NO prompt/response content)
        # M4.6: use typed failure envelope when available for stable error codes.
        _failure = getattr(e, "runtime_failure", None)
        _error_code = _failure.code if _failure is not None else type(e).__name__
        _failure_kind = _failure.kind.value if _failure is not None else None
        latency_ms = int((time.perf_counter() - t0) * 1000)
        append_metadata(
            cfg.logging,
            {
                "request_id": request_id,
                "mode": getattr(selection, "mode", None),
                "provider": getattr(selection, "selected_provider", None),
                "model": None,
                "status": "error",
                "latency_ms": latency_ms,
                "error_code": _error_code,
                "failure_kind": _failure_kind,
                "fallback_used": getattr(selection, "fallback_used", None),
                "fallback_reason": getattr(selection, "fallback_reason", None),
                "selected_primary": getattr(selection, "primary_target", None),
                "capability_id": cap_id,
                "capability_ok": False if cap_id else None,
                "capability_error_code": _error_code if cap_id else None,
            },
        )
        raise


def cmd_capability(args) -> int:
    """Invoke a capability explicitly (Phase 3).

    Command surface (DOC-OVW-003 M3.16):
        python -m io_iii capability <capability_id> '{"x":1}'

    Notes:
    - Deterministic: explicit-only invocation; no selection/planning.
    - Content-safe logging: metadata only; never logs payload/output.
    """
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)
    request_id = make_request_id()
    t0 = time.perf_counter()

    cap_id = getattr(args, "capability_id", None)
    if not cap_id:
        raise ValueError("CAPABILITY_ID_REQUIRED: capability_id is required")

    cap_payload = _parse_capability_payload(getattr(args, "payload_json", None))

    # Capability-only execution uses the null provider path.
    route = RouteInfo(
        mode="capability",
        primary_target=None,
        secondary_target=None,
        selected_target=None,
        selected_provider="null",
        fallback_used=False,
        fallback_reason=None,
        boundaries={},
    )

    state = SessionState(
        request_id=request_id,
        started_at_ms=int(time.time() * 1000),
        mode="capability",
        config_dir=str(cfg.config_dir),
        route=route,
        audit=AuditGateState(audit_enabled=False),
        status="ok",
        provider="null",
        model=None,
        route_id="capability",
        persona_contract_version=PERSONA_CONTRACT_VERSION,
        persona_id=None,
        logging_policy=cfg.logging,
    )

    # Defensive invariant enforcement (SessionState v0)
    validate_session_state(state)

    deps = RuntimeDependencies(
        ollama_provider_factory=OllamaProvider.from_config,
        challenger_fn=None,
        capability_registry=builtin_registry(),
    )

    try:
        state2, result = engine_run(
            cfg=cfg,
            session_state=state,
            user_prompt="",  # not used by null provider path
            audit=False,
            deps=deps,
            capability_id=cap_id,
            capability_payload=cap_payload,
        )

        # Defensive invariant enforcement (SessionState v0)
        validate_session_state(state2)

        # Capability summary (content-safe; MUST NOT include output)
        cap_meta = result.meta.get("capability") if isinstance(result.meta, dict) else None
        capability_ok = None
        capability_version = None
        capability_duration_ms = None
        capability_error_code = None
        if isinstance(cap_meta, dict):
            capability_ok = cap_meta.get("ok")
            capability_version = cap_meta.get("version")
            capability_duration_ms = cap_meta.get("duration_ms")
            capability_error_code = cap_meta.get("error_code")

        # Engine observability summary (M4.5; structural count only)
        cap_engine_events = result.meta.get("engine_events") if isinstance(result.meta, dict) else None
        cap_engine_event_count = len(cap_engine_events) if isinstance(cap_engine_events, list) else None

        latency_ms = int((time.perf_counter() - t0) * 1000)
        append_metadata(
            cfg.logging,
            {
                "request_id": request_id,
                "mode": state2.mode,
                "provider": result.provider,
                "model": result.model,
                "status": "ok",
                "latency_ms": latency_ms,
                "prompt_hash": result.prompt_hash,
                "fallback_used": False,
                "fallback_reason": None,
                "selected_primary": None,
                "capability_id": cap_id,
                "capability_ok": capability_ok,
                "capability_version": capability_version,
                "capability_duration_ms": capability_duration_ms,
                "capability_error_code": capability_error_code,
                "engine_event_count": cap_engine_event_count,
            },
        )

        payload = {
            "result": {
                "message": result.message,
                "meta": result.meta,
                "mode": state2.mode,
                "provider": result.provider,
                "model": result.model,
                "route_id": state2.route_id,
            },
        }

        _print(payload)
        return 0

    except Exception as e:
        # M4.6: use typed failure envelope when available for stable error codes.
        _failure = getattr(e, "runtime_failure", None)
        _error_code = _failure.code if _failure is not None else type(e).__name__
        _failure_kind = _failure.kind.value if _failure is not None else None
        latency_ms = int((time.perf_counter() - t0) * 1000)
        append_metadata(
            cfg.logging,
            {
                "request_id": request_id,
                "mode": "capability",
                "provider": "null",
                "model": None,
                "status": "error",
                "latency_ms": latency_ms,
                "error_code": _error_code,
                "failure_kind": _failure_kind,
                "fallback_used": False,
                "fallback_reason": None,
                "selected_primary": None,
                "capability_id": cap_id,
                "capability_ok": False,
                "capability_error_code": _error_code,
            },
        )
        raise


def cmd_serve(args) -> int:
    """
    Start the IO-III HTTP API server (Phase 9 M9.1 / ADR-025 §7).

    CLI:
        python -m io_iii serve [--host HOST] [--port PORT]

    Starts a uvicorn server hosting the FastAPI transport adapter.
    All requests route through the existing session/engine layer.
    Zero new execution semantics (ADR-025 §1).
    """
    import uvicorn
    from io_iii.api import app

    host = getattr(args, "host", "0.0.0.0")
    port = int(getattr(args, "port", 8080))
    uvicorn.run(app, host=host, port=port)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="io-iii")
    parser.add_argument(
        "--config-dir",
        default=None,
        help="Path to IO-III runtime config directory",
    )
    parser.add_argument(
        "--output",
        choices=["json"],
        default="json",
        dest="output_format",
        help="Output format (default: json; all output is JSON — M9.4 / ADR-025 §7)",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_cfg = sub.add_parser("config")
    p_cfg.add_argument("show", nargs="?")
    p_cfg.set_defaults(func=cmd_config_show)

    p_route = sub.add_parser("route")
    p_route.add_argument("mode")
    p_route.set_defaults(func=cmd_route)

    p_run = sub.add_parser("run")
    p_run.add_argument("mode")
    p_run.add_argument("--prompt", type=str, default=None, help="Prompt text (or pipe via stdin)")
    p_run.add_argument("--raw", action="store_true", help="Print only the model response, no metadata")
    p_run.add_argument("--audit", action="store_true", help="Enable challenger audit pass")
    p_run.add_argument(
        "--capability-id",
        type=str,
        default=None,
        help="Explicit capability ID to invoke once (Phase 3; bounded; no autonomy).",
    )
    p_run.add_argument(
        "--capability-payload-json",
        type=str,
        default=None,
        help="JSON object payload for capability invocation (must be a JSON object).",
    )
    p_run.add_argument(
        "--no-health-check",
        action="store_true",
        dest="no_health_check",
        help="Skip provider reachability check (for offline/CI use; ADR-011).",
    )
    p_run.add_argument(
        "--no-constellation-check",
        action="store_true",
        dest="no_constellation_check",
        help="Skip constellation integrity guard (for offline/CI use; ADR-021).",
    )
    p_run.add_argument(
        "--output",
        choices=["json"],
        default="json",
        help="Output format (default: json; M9.4 — formalises machine-readable contract).",
    )
    p_run.set_defaults(func=cmd_run)

    p_caps = sub.add_parser("capabilities")
    p_caps.add_argument("--json", action="store_true", help="Output JSON format")
    p_caps.set_defaults(func=cmd_capabilities)

    p_cap = sub.add_parser("capability")
    p_cap.add_argument("capability_id", type=str, help="Capability ID to invoke")
    p_cap.add_argument(
        "payload_json",
        nargs="?",
        default=None,
        help="Optional JSON object payload (must be a JSON object)",
    )
    p_cap.set_defaults(func=cmd_capability)

    p_runbook = sub.add_parser("runbook")
    p_runbook.add_argument("json_file", type=str, help="Path to a JSON file containing a Runbook definition")
    p_runbook.add_argument("--audit", action="store_true", help="Enable challenger audit pass per step")
    p_runbook.add_argument(
        "--output", choices=["json"], default="json",
        help="Output format (default: json; M9.4).",
    )
    p_runbook.set_defaults(func=cmd_runbook)

    p_replay = sub.add_parser("replay")
    p_replay.add_argument("run_id", type=str, help="Source run_id to replay from checkpoint")
    p_replay.add_argument("--audit", action="store_true", help="Enable challenger audit pass per step")
    p_replay.set_defaults(func=cmd_replay)

    p_resume = sub.add_parser("resume")
    p_resume.add_argument("run_id", type=str, help="Source run_id to resume from checkpoint")
    p_resume.add_argument("--audit", action="store_true", help="Enable challenger audit pass per step")
    p_resume.set_defaults(func=cmd_resume)

    p_about = sub.add_parser("about")
    p_about.set_defaults(func=cmd_about)

    # Phase 6 M6.6 — memory write command (ADR-022 §7)
    p_memory = sub.add_parser("memory")
    p_memory_sub = p_memory.add_subparsers(dest="memory_subcmd", required=True)
    p_memory_write = p_memory_sub.add_parser("write")
    p_memory_write.add_argument("--scope", required=True, help="Memory record scope")
    p_memory_write.add_argument("--key", required=True, help="Memory record key")
    p_memory_write.add_argument("--value", required=True, help="Memory record value (content-plane)")
    p_memory_write.add_argument(
        "--sensitivity", default="standard",
        choices=["standard", "elevated", "restricted"],
        help="Sensitivity tier (default: standard)",
    )
    p_memory_write.add_argument(
        "--provenance", default="human",
        help="Provenance string (default: human)",
    )
    p_memory_write.set_defaults(func=cmd_memory_write)

    # Phase 7 M7.4 — portability validation (ADR-023 §6)
    p_validate = sub.add_parser("validate")
    p_validate.set_defaults(func=cmd_validate)

    # Phase 7 M7.2 — init command (ADR-023 §4)
    p_init = sub.add_parser("init")
    p_init.set_defaults(func=cmd_init)

    # Phase 6 M6.7 — session export/import commands (ADR-022 §8)
    p_session = sub.add_parser("session")
    p_session_sub = p_session.add_subparsers(dest="session_subcmd", required=True)

    p_session_export = p_session_sub.add_parser("export")
    p_session_export.add_argument("--run-id", required=True, dest="run_id", help="Source run identifier")
    p_session_export.add_argument("--mode", required=True, help="Governance mode (e.g. executor)")
    p_session_export.add_argument(
        "--workflow-position", dest="workflow_position", default=None,
        help="Workflow position identifier (defaults to --mode)",
    )
    p_session_export.add_argument(
        "--pack", action="append", dest="pack", default=[], metavar="PACK_ID",
        help="Active memory pack ID (repeatable)",
    )
    p_session_export.add_argument("--output", default=None, help="Output path (overrides default)")
    p_session_export.set_defaults(func=cmd_session_export)

    p_session_import = p_session_sub.add_parser("import")
    p_session_import.add_argument("--snapshot", required=True, help="Path to snapshot file")
    p_session_import.set_defaults(func=cmd_session_import)

    # Phase 8 M8.3 — session shell commands (ADR-024)
    p_session_start = p_session_sub.add_parser("start")
    p_session_start.add_argument(
        "--mode", default="work", choices=["work", "steward"],
        help="Session operating mode: work (default) or steward (ADR-024)",
    )
    p_session_start.add_argument(
        "--persona-mode", dest="persona_mode", default="executor",
        help="Persona execution mode for turns (default: executor)",
    )
    p_session_start.add_argument("--prompt", default=None, help="Optional first-turn prompt")
    p_session_start.add_argument("--audit", action="store_true", help="Enable challenger audit pass")
    p_session_start.add_argument(
        "--output", choices=["json"], default="json",
        help="Output format (default: json; M9.4).",
    )
    p_session_start.set_defaults(func=cmd_session_start)

    p_session_continue = p_session_sub.add_parser("continue")
    p_session_continue.add_argument("--session-id", required=True, dest="session_id", help="Session ID to continue")
    p_session_continue.add_argument("--prompt", default=None, help="Prompt for this turn")
    p_session_continue.add_argument(
        "--persona-mode", dest="persona_mode", default="executor",
        help="Persona execution mode (default: executor)",
    )
    p_session_continue.add_argument("--audit", action="store_true", help="Enable challenger audit pass")
    p_session_continue.add_argument(
        "--action", default=None, choices=["approve", "redirect", "close"],
        help="Steward pause action (ADR-024 §6.3)",
    )
    p_session_continue.add_argument(
        "--output", choices=["json"], default="json",
        help="Output format (default: json; M9.4).",
    )
    p_session_continue.set_defaults(func=cmd_session_continue)

    p_session_status = p_session_sub.add_parser("status")
    p_session_status.add_argument("--session-id", required=True, dest="session_id", help="Session ID to query")
    p_session_status.add_argument(
        "--output", choices=["json"], default="json",
        help="Output format (default: json; M9.4).",
    )
    p_session_status.set_defaults(func=cmd_session_status)

    p_session_close = p_session_sub.add_parser("close")
    p_session_close.add_argument("--session-id", required=True, dest="session_id", help="Session ID to close")
    p_session_close.add_argument(
        "--output", choices=["json"], default="json",
        help="Output format (default: json; M9.4).",
    )
    p_session_close.set_defaults(func=cmd_session_close)

    # Phase 9 M9.1 — HTTP server (ADR-025 §7)
    p_serve = sub.add_parser("serve", help="Start the IO-III HTTP API server (Phase 9)")
    p_serve.add_argument(
        "--host", default="0.0.0.0",
        help="Bind host (default: 0.0.0.0)",
    )
    p_serve.add_argument(
        "--port", type=int, default=8080,
        help="Bind port (default: 8080)",
    )
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return int(args.func(args))
