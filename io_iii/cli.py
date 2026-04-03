import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from io_iii.metadata_logging import append_metadata, make_request_id

from io_iii.config import load_io3_config, default_config_dir
from io_iii.routing import resolve_route
from io_iii.providers.ollama_provider import OllamaProvider
from io_iii.persona_contract import PERSONA_CONTRACT_VERSION
from io_iii.core.engine import run as engine_run
from io_iii.core.session_state import SessionState, RouteInfo, AuditGateState, validate_session_state

# Phase 3 seams
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.capabilities.builtins import builtin_registry

# Phase 4 M4.9 — runbook CLI surface (ADR-016)
from io_iii.core.runbook import Runbook
import io_iii.core.runbook_runner as _runbook_runner

# -----------------------------
# Audit Gate Hard Limits (ADR-009)
# -----------------------------
MAX_AUDIT_PASSES = 1
MAX_REVISION_PASSES = 1


def _to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return {k: _to_jsonable(v) for k, v in vars(obj).items()}
    return str(obj)


def _print(obj: Any) -> None:
    print(json.dumps(_to_jsonable(obj), indent=2))


def _get_cfg_dir(args) -> Path:
    if getattr(args, "config_dir", None):
        return Path(args.config_dir)
    return default_config_dir()


def _parse_capability_payload(raw: Optional[str]) -> Dict[str, Any]:
    """
    Parse a JSON object string into a dict for capability payload.

    Allowed: JSON object only.
    Default: {}.
    """
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except Exception as e:
        raise ValueError(f"CAPABILITY_PAYLOAD_INVALID_JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError("CAPABILITY_PAYLOAD_INVALID_SHAPE: payload must be a JSON object")
    return obj


# -----------------------------
# CLI Commands
# -----------------------------
def cmd_capabilities(args) -> int:
    """
    List registered capabilities (content-safe introspection).

    This does not invoke capabilities and does not perform selection/planning.
    """
    registry = builtin_registry()

    # Stable introspection surface (provided by CapabilityRegistry)
    specs = registry.list_capabilities()

    caps = []
    for spec in specs:
        bounds = getattr(spec, "bounds", None)
        bounds_payload = None
        if bounds is not None:
            bounds_payload = {
                "max_calls": getattr(bounds, "max_calls", None),
                "timeout_ms": getattr(bounds, "timeout_ms", None),
                "max_input_chars": getattr(bounds, "max_input_chars", None),
                "max_output_chars": getattr(bounds, "max_output_chars", None),
                "side_effects_allowed": getattr(bounds, "side_effects_allowed", None),
            }

        caps.append(
            {
                "id": getattr(spec, "id", None),
                "version": getattr(spec, "version", None),
                "description": getattr(spec, "description", None),
                "category": getattr(
                    getattr(spec, "category", None),
                    "value",
                    str(getattr(spec, "category", None)),
                ),
                "bounds": bounds_payload,
            }
        )

    if getattr(args, "json", False):
        _print({"capabilities": caps})
        return 0

    print("Registered capabilities:")
    for c in caps:
        b = c.get("bounds") or {}
        print(
            f"- {c.get('id')} (v{c.get('version')}) — {c.get('description')} "
            f"[max_calls={b.get('max_calls')}, timeout_ms={b.get('timeout_ms')}, "
            f"max_input_chars={b.get('max_input_chars')}, max_output_chars={b.get('max_output_chars')}, "
            f"side_effects_allowed={b.get('side_effects_allowed')}]"
        )
    return 0


def cmd_config_show(args) -> int:
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)

    payload = {
        "config_dir": str(cfg.config_dir),
        "logging": cfg.logging,
        "providers": cfg.providers,
        "routing": cfg.routing,
    }
    _print(payload)
    return 0


def cmd_route(args) -> int:
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)

    selection = resolve_route(
        routing_cfg=cfg.routing["routing_table"],
        mode=args.mode,
        providers_cfg=cfg.providers,
        supported_providers={"null", "ollama"},
    )

    payload = {
        "mode": selection.mode,
        "route": {
            "primary_target": selection.primary_target,
            "secondary_target": selection.secondary_target,
            "selected_target": selection.selected_target,
            "selected_provider": selection.selected_provider,
            "fallback_used": selection.fallback_used,
            "fallback_reason": selection.fallback_reason,
            "boundaries": selection.boundaries,
        },
        "route_id": selection.mode,
    }

    _print(payload)
    return 0


def cmd_run(args) -> int:
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)
    request_id = make_request_id()
    t0 = time.perf_counter()

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
            },
        )

        _print(payload)
        return 0

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


def cmd_about(args) -> int:
    cfg_dir = _get_cfg_dir(args)
    cfg = load_io3_config(cfg_dir)

    identity = (
        "IO-III is a structured local AI execution engine designed for deterministic routing, "
        "verifiable reasoning boundaries, and disciplined output generation."
    )

    payload = {
        "identity": identity,
        "repo_root": str(Path.cwd()),
        "config_dir": str(cfg.config_dir),
        "execution_chain": [
            "CLI (io_iii/cli.py)",
            "Config loader (io_iii/config.py)",
            "Routing selection (io_iii/routing.py -> resolve_route)",
            "Provider instantiation (io_iii/providers/*)",
            "Model execution (OllamaProvider.generate)",
            "Structured JSON output + metadata logging policy",
        ],
        "commands": ["config show", "route <mode>", "run <mode> --prompt ...", "capabilities", "about"],
        "routing_contract": {
            "target_format": "<namespace>:<model>",
            "example": "local:qwen3:8b",
            "namespace_mapping": {"local": "ollama"},
        },
        "logging_policy": cfg.logging,
    }

    _print(payload)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="io-iii")
    parser.add_argument(
        "--config-dir",
        default=None,
        help="Path to IO-III runtime config directory",
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
    p_runbook.set_defaults(func=cmd_runbook)

    p_about = sub.add_parser("about")
    p_about.set_defaults(func=cmd_about)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())