import argparse
import json
from pathlib import Path
from typing import Any

from io_iii.config import load_io3_config, default_config_dir
from io_iii.routing import resolve_route
from io_iii.providers.null_provider import NullProvider
from io_iii.providers.ollama_provider import OllamaProvider


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


# -----------------------------
# Challenger Enforcement (ADR-008)
# -----------------------------

def _run_challenger(cfg, user_prompt: str, draft_text: str):
    from io_iii.routing import _parse_target

    selection = resolve_route(
        routing_cfg=cfg.routing["routing_table"],
        mode="challenger",
        providers_cfg=cfg.providers,
        supported_providers={"null", "ollama"},
    )

    # Fail-safe: if challenger unavailable, auto-pass
    if selection.selected_provider != "ollama" or not selection.selected_target:
        return {"verdict": "pass", "issues": [], "high_risk_claims": [], "suggested_fixes": []}

    _, model = _parse_target(selection.selected_target)
    provider = OllamaProvider.from_config(cfg.providers)

    system_prompt = (
        "You are IO-III Challenger.\n"
        "Audit the executor draft for:\n"
        "- policy compliance\n"
        "- factual risk or unverifiable claims\n"
        "- contradictions\n"
        "- missing verification steps\n\n"
        "You MUST NOT rewrite the draft.\n"
        "You MUST NOT introduce new facts.\n\n"
        "Respond in strict JSON with keys:\n"
        "{"
        "'verdict': 'pass'|'needs_work', "
        "'issues': [], "
        "'high_risk_claims': [], "
        "'suggested_fixes': []"
        "}"
    )

    audit_prompt = (
        f"{system_prompt}\n\n"
        f"USER_PROMPT:\n{user_prompt}\n\n"
        f"EXECUTOR_DRAFT:\n{draft_text}\n"
    )

    raw = provider.generate(model=model, prompt=audit_prompt).strip()

    try:
        return json.loads(raw)
    except Exception:
        # Never block execution
        return {"verdict": "pass", "issues": [], "high_risk_claims": [], "suggested_fixes": []}


# -----------------------------
# CLI Commands
# -----------------------------

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

    selection = resolve_route(
        routing_cfg=cfg.routing["routing_table"],
        mode=args.mode,
        providers_cfg=cfg.providers,
        supported_providers={"null", "ollama"},
    )

    if selection.selected_provider == "ollama":
        from io_iii.routing import _parse_target

        provider = OllamaProvider.from_config(cfg.providers)

        if not selection.selected_target:
            raise ValueError("No selected_target available for ollama route")

        _, model = _parse_target(selection.selected_target)

        prompt = getattr(args, "prompt", None)
        if not prompt:
            import sys
            prompt = sys.stdin.read().strip() or "Say hello in one short sentence."

        # Executor pass
        system_identity = (
            "You are IO-III, a structured local AI execution engine designed "
            "for deterministic routing, verifiable reasoning boundaries, "
            "and disciplined output generation. "
            "Respond concisely and with technical precision."
        )

        final_prompt = f"{system_identity}\n\nUser:\n{prompt}\n\nIO-III:"
        text = provider.generate(model=model, prompt=final_prompt).strip()

        audit_meta = {
            "audit_used": False,
            "audit_verdict": None,
            "revised": False,
        }

        # Challenger pass (optional)
        if getattr(args, "audit", False):
            audit = _run_challenger(cfg, prompt, text)
            audit_meta["audit_used"] = True
            audit_meta["audit_verdict"] = audit.get("verdict")

            if audit.get("verdict") == "needs_work":
                revision_prompt = (
                    "You are IO-III Executor performing a single controlled revision.\n"
                    "Address the challenger feedback below.\n"
                    "You MUST NOT introduce new facts.\n"
                    "Preserve user intent.\n\n"
                    f"USER_PROMPT:\n{prompt}\n\n"
                    f"ORIGINAL_DRAFT:\n{text}\n\n"
                    f"CHALLENGER_FEEDBACK:\n{json.dumps(audit, indent=2)}\n\n"
                    "Produce the improved final answer only."
                )

                text = provider.generate(model=model, prompt=revision_prompt).strip()
                audit_meta["revised"] = True

        result = {
            "message": text,
            "meta": {},
            "provider": "ollama",
            "model": model,
        }

    else:
        provider = NullProvider()
        result_obj = provider.run(
            mode=selection.mode,
            route_id=selection.mode,
            meta={},
        )
        result = {
            "message": getattr(result_obj, "message", ""),
            "meta": getattr(result_obj, "meta", {}),
            "provider": "null",
        }
        audit_meta = None

    payload = {
        "logging_policy": cfg.logging,
        "result": {
            "message": result["message"],
            "meta": result["meta"],
            "mode": selection.mode,
            "provider": result["provider"],
            "model": result.get("model"),
            "route_id": selection.mode,
        },
        "audit_meta": audit_meta,
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
        "commands": ["config show", "route <mode>", "run <mode> --prompt ...", "about"],
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
    p_run.set_defaults(func=cmd_run)

    p_about = sub.add_parser("about")
    p_about.set_defaults(func=cmd_about)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
