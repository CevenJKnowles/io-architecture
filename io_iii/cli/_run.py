"""
CLI commands: capabilities, config show, route, about.

Note: cmd_run and cmd_capability live in __init__.py so that monkeypatching
via `import io_iii.cli as cli; monkeypatch.setattr(cli, ...)` works correctly
in integration tests (functions resolve globals from their defining module).
"""
from __future__ import annotations

from pathlib import Path

from io_iii.config import load_io3_config
from io_iii.routing import resolve_route
from io_iii.capabilities.builtins import builtin_registry

from ._shared import _get_cfg_dir, _print


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
