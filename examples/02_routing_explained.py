"""
examples/02_routing_explained.py: Deterministic routing, no model call

Calls resolve_route() for each configured mode and prints the result.
No Ollama instance required; routing resolution is a pure config operation.

This example shows what happens before any model is invoked: the routing
layer reads routing_table.yaml and produces exactly one provider + model
selection for each mode. There is no dynamic selection or fallback chain.

Run from repo root:
  python examples/02_routing_explained.py
"""

from io_iii.config import load_io3_config, default_config_dir
from io_iii.routing import resolve_route

# Load runtime configuration from architecture/runtime/config/
cfg = load_io3_config(default_config_dir())

# The modes available in a default Io³ install.
modes = ["executor", "challenger", "drafter", "fast", "data"]

print(f"{'Mode':<14} {'Provider':<12} {'Model':<40} {'Fallback'}")
print("-" * 80)

for mode in modes:
    try:
        route = resolve_route(
            routing_cfg=cfg.routing["routing_table"],
            mode=mode,
            providers_cfg=cfg.providers,
            supported_providers={"null", "ollama"},
        )
        model = route.selected_target or "(none)"
        fallback = "yes" if route.fallback_used else "no"
        print(f"{mode:<14} {route.selected_provider:<12} {model:<40} {fallback}")
    except Exception as exc:
        # A missing mode entry in routing_table.yaml produces a clear error here.
        print(f"{mode:<14} ERROR: {exc}")

# RouteSelection fields available for inspection:
#   route.mode              : the mode that was resolved
#   route.selected_provider : which provider adapter was chosen (e.g. "ollama")
#   route.selected_target   : the full target string (e.g. "local:qwen2.5:14b-instruct")
#   route.fallback_used     : True if the primary target was unavailable
#   route.boundaries        : the execution limits that apply to this route
