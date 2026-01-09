from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from .config import load_io3_config, default_config_dir
from .routing import resolve_route
from .providers.null_provider import NullProvider


VALID_MODES = [
    "executor",
    "challenger",
    "synthesizer",
    "explorer",
    "visionary",
]


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def cmd_validate(_: argparse.Namespace) -> int:
    """
    Runs the invariant validator script.
    """
    validator = Path("/home/cjk/Dev/IO/io-persona-blueprint/IO-III/runtime/scripts/validate_invariants.py")
    if not validator.exists():
        print(f"ERROR: validator not found at: {validator}", file=sys.stderr)
        return 2

    p = subprocess.run([sys.executable, str(validator)])
    return p.returncode


def cmd_config_show(args: argparse.Namespace) -> int:
    cfg_dir = Path(args.config_dir) if args.config_dir else default_config_dir()
    cfg = load_io3_config(cfg_dir)
    _print_json(cfg.to_dict())
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    cfg_dir = Path(args.config_dir) if args.config_dir else default_config_dir()
    cfg = load_io3_config(cfg_dir)
    selection = resolve_route(routing_cfg=cfg.routing, mode=args.mode)
    _print_json(
        {
            "mode": selection.mode,
            "route_id": selection.route_id,
            "route": selection.route,
        }
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg_dir = Path(args.config_dir) if args.config_dir else default_config_dir()
    cfg = load_io3_config(cfg_dir)
    selection = resolve_route(routing_cfg=cfg.routing, mode=args.mode)

    # Provider resolution (v0.2: NullProvider only)
    provider_name = selection.route.get("provider", "null")
    if provider_name != "null":
        print(
            "ERROR: v0.2 runtime supports only provider='null'.\n"
            f"Got provider={provider_name!r} from route_id={selection.route_id!r}.",
            file=sys.stderr,
        )
        return 2

    provider = NullProvider()
    result = provider.run(mode=args.mode, route_id=selection.route_id, meta={"config_dir": str(cfg.config_dir)})

    _print_json(
        {
            "result": {
                "provider": result.provider,
                "mode": result.mode,
                "route_id": result.route_id,
                "message": result.message,
                "meta": result.meta,
            },
            "logging_policy": cfg.logging,
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="io-iii",
        description="IO-III runtime entrypoint (v0.2): config + routing + NullProvider",
    )
    p.add_argument(
        "--config-dir",
        dest="config_dir",
        default=None,
        help=f"Config directory (default: {default_config_dir()})",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("validate", help="Run invariant validator")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("config", help="Config operations")
    sub2 = sp.add_subparsers(dest="subcmd", required=True)
    sp_show = sub2.add_parser("show", help="Print merged IO-III runtime config as JSON")
    sp_show.set_defaults(func=cmd_config_show)

    sp = sub.add_parser("route", help="Resolve routing for a mode and print selection")
    sp.add_argument("mode", choices=VALID_MODES, help="Routing mode")
    sp.set_defaults(func=cmd_route)

    sp = sub.add_parser("run", help="Run IO-III (v0.2: NullProvider only)")
    sp.add_argument("mode", choices=VALID_MODES, help="Run mode")
    sp.set_defaults(func=cmd_run)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
