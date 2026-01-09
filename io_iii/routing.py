from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class RouteSelection:
    mode: str
    primary_target: Optional[str]
    secondary_target: Optional[str]
    selected_target: Optional[str]
    selected_provider: str
    fallback_used: bool
    fallback_reason: Optional[str]
    boundaries: Dict[str, Any]


def _require_mapping(obj: Any, *, where: str) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError(f"{where} must be a mapping/dict")
    return obj


def _parse_target(target: str) -> Tuple[str, str]:
    """Parse a routing target like 'local:ministral-3' -> ('local', 'ministral-3')."""
    if not isinstance(target, str) or ":" not in target:
        raise ValueError(f"Invalid target format: {target!r} (expected '<namespace>:<model>')")
    ns, model = target.split(":", 1)
    ns = ns.strip()
    model = model.strip()
    if not ns or not model:
        raise ValueError(f"Invalid target format: {target!r} (empty namespace/model)")
    return ns, model


def _namespace_to_provider(ns: str) -> str:
    # v0.2+ mapping: local targets use local runtime provider
    if ns == "local":
        return "ollama"
    return ns


def _is_provider_enabled(*, providers_cfg: Dict[str, Any], provider_name: str) -> bool:
    providers = providers_cfg.get("providers", {})
    if not isinstance(providers, dict):
        return False
    p = providers.get(provider_name, {})
    if not isinstance(p, dict):
        return False
    return bool(p.get("enabled", False))


def resolve_route(
    *,
    routing_cfg: Dict[str, Any],
    mode: str,
    providers_cfg: Optional[Dict[str, Any]] = None,
    supported_providers: Optional[set[str]] = None,
) -> RouteSelection:
    """
    Deterministic mode-driven route selection based on routing_table.yaml (canonical).

    Fallback policy (ADR-002):
      - Operational fallback only.
      - If provider is disabled or unsupported, treat as 'model_unavailable' and attempt secondary.
      - If neither primary nor secondary is usable, fall back to NullProvider.
    """
    providers_cfg = providers_cfg or {}
    supported_providers = supported_providers or {"null"}

    rt = _require_mapping(routing_cfg, where="routing_table.yaml root")

    rules = _require_mapping(rt.get("rules", {}), where="routing_table.yaml: rules")
    if rules.get("selection_method") not in (None, "mode"):
        raise ValueError("routing_table.yaml: rules.selection_method must be 'mode'")

    boundaries = _require_mapping(
        rules.get("boundaries", {}),
        where="routing_table.yaml: rules.boundaries",
    )

    modes = _require_mapping(rt.get("modes", {}), where="routing_table.yaml: modes")
    if mode not in modes:
        raise ValueError(f"routing_table.yaml: unknown mode: {mode!r}")

    spec = _require_mapping(modes[mode], where=f"routing_table.yaml: modes.{mode}")
    primary = spec.get("primary")
    secondary = spec.get("secondary")
    if not isinstance(primary, str) or not isinstance(secondary, str):
        raise ValueError(f"routing_table.yaml: modes.{mode} must define string primary/secondary targets")

    def usable(target: str) -> Tuple[bool, str]:
        ns, _ = _parse_target(target)
        provider = _namespace_to_provider(ns)
        if provider not in supported_providers:
            return False, provider
        if providers_cfg and not _is_provider_enabled(providers_cfg=providers_cfg, provider_name=provider):
            return False, provider
        return True, provider

    ok, provider = usable(primary)
    if ok:
        return RouteSelection(
            mode=mode,
            primary_target=primary,
            secondary_target=secondary,
            selected_target=primary,
            selected_provider=provider,
            fallback_used=False,
            fallback_reason=None,
            boundaries=boundaries,
        )

    ok2, provider2 = usable(secondary)
    if ok2:
        return RouteSelection(
            mode=mode,
            primary_target=primary,
            secondary_target=secondary,
            selected_target=secondary,
            selected_provider=provider2,
            fallback_used=True,
            fallback_reason="model_unavailable",
            boundaries=boundaries,
        )

    return RouteSelection(
        mode=mode,
        primary_target=primary,
        secondary_target=secondary,
        selected_target=None,
        selected_provider="null",
        fallback_used=True,
        fallback_reason="model_unavailable",
        boundaries=boundaries,
    )

