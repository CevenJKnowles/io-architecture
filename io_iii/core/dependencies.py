from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from io_iii.core.capabilities import CapabilityRegistry, default_registry


@dataclass(frozen=True)
class RuntimeDependencies:
    """
    Centralised dependency bundle for the engine.

    Phase 3 contract:
    - dependencies are explicit
    - no dynamic loading
    - defaults are deterministic
    """
    ollama_provider_factory: Callable[[Any], Any]
    challenger_fn: Optional[Callable[[Any, str, str], dict]] = None
    capability_registry: CapabilityRegistry = default_registry()
    