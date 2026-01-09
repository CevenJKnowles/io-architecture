import argparse
import json
from pathlib import Path
from typing import Any, Dict

from io_iii.config import load_io3_config, default_config_dir
from io_iii.routing import resolve_route
from io_iii.providers.null_provider import NullProvider


def _to_jsonable(obj: Any) -> Any:
    """
    Best-effort conversion to JSON-serializable structures.
    Handles dicts/lists/primitives and dataclass-like objects with __dict__.
    """
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
    """
    Portability rule:
    - If --config-dir is provided, use it.
    - Otherwise use default_config_dir() (portable resolver in io_iii/config.py).
    """
    if getattr(args, "config_dir", None):
        return Path(args.config_dir)
    return default_config_dir()


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
        routing_cfg=cfg.routing,
        mode=args.mode,
        providers_cfg=cfg.providers,
        supported_providers={"null"},  # v0.2 safety gate
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

    selection = resolve_route(
        routing_cfg=cfg.routing,
        mode=args.mode,
        providers_cfg=cfg.providers,
        supported_providers={"null"},  # v0.2 safety gate
    )

    provider = NullProvider()

    meta: Dict[str, Any] = {
        "config_dir": str(cfg.config_dir),
        "selected_primary": selection.primary_target,
        "selected_secondary": selection.secondary_target,
        "selected_target": selection.selected_target,
        "selected_provider": selection.selected_provider,
        "fallback_used": selection.fallback_used,
        "fallback_reason": selection.fallback_reason,
        "routing_source": "routing_table.yaml",
    }

    result = provider.run(
        mode=selection.mode,
        route_id=selection.mode,
        meta=meta,
    )

    payload = {
        "logging_policy": cfg.logging,
        "result": {
            "message": getattr(result, "message", "NullProvider executed (no model invocation)."),
            "meta": getattr(result, "meta", meta),
            "mode": selection.mode,
            "provider": "null",
            "route_id": selection.mode,
        },
    }

    _print(payload)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="io-iii")
    parser.add_argument(
        "--config-dir",
        default=None,
        help="Path to IO-III runtime config directory (optional; defaults to repo-relative IO-III/runtime/config).",
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
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
