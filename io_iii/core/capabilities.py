from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Protocol, runtime_checkable


class CapabilityCategory(str, Enum):
    """
    Conceptual categories for capability classification.

    Categories are guidance for architecture and governance. They must not imply
    dynamic selection or arbitration.
    """
    COMPUTATION = "computation"
    VALIDATION = "validation"
    TRANSFORMATION = "transformation"
    EXTERNAL_INTERACTION = "external_interaction"


@dataclass(frozen=True)
class CapabilityBounds:
    """
    Hard bounds for capability execution.

    All bounds are enforced at invocation time by the engine's capability runner
    (_invoke_capability_once in engine.py):
    - max_input_chars: checked before invocation (CAPABILITY_INPUT_TOO_LARGE)
    - timeout_ms: enforced via ThreadPoolExecutor timeout (CAPABILITY_TIMEOUT)
    - max_output_chars: checked after invocation (CAPABILITY_OUTPUT_TOO_LARGE)
    - max_calls: architectural constraint — one invocation per engine.run() call
    """
    max_calls: int = 1
    timeout_ms: int = 2_000
    max_input_chars: int = 20_000
    max_output_chars: int = 20_000
    side_effects_allowed: bool = False


@dataclass(frozen=True)
class CapabilitySpec:
    """
    Static contract describing a capability.

    This spec is designed to be:
    - deterministic
    - inspectable
    - testable
    - safe to log (no content)
    """
    capability_id: str
    version: str
    category: CapabilityCategory
    description: str
    bounds: CapabilityBounds = CapabilityBounds()

    # Schema fields are intentionally generic at v0.
    # They document intent without forcing an implementation framework.
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None

    @property
    def id(self) -> str:
        """Alias for capability_id (stable external name)."""
        return self.capability_id


@dataclass(frozen=True)
class CapabilityResult:
    """
    Result of one capability invocation.

    Output must be structured data only.
    """
    ok: bool
    output: Dict[str, Any]
    error_code: Optional[str] = None


@dataclass(frozen=True)
class CapabilityContext:
    """
    Context provided to capability invocations.

    This is control-plane safe: it carries references to runtime state objects
    but must not expose prompt/output content surfaces.

    Note:
    - Use of these fields is capability-specific and must respect non-goals.
    """
    cfg: Any
    session_state: Any
    execution_context: Any = None


@runtime_checkable
class Capability(Protocol):
    """
    Capability interface contract.

    Capabilities are invoked explicitly by the control plane.
    They must not self-invoke other capabilities.
    """

    @property
    def spec(self) -> CapabilitySpec:
        ...

    def invoke(self, ctx: CapabilityContext, payload: Mapping[str, Any]) -> CapabilityResult:
        ...


class CapabilityRegistry:
    """
    Static registry for declared capabilities.

    Phase 3 guarantee:
    - registry is explicit, not discoverable
    - lookup is deterministic
    - no dynamic loading
    """

    def __init__(self, capabilities: Optional[Iterable[Capability]] = None) -> None:
        self._by_id: Dict[str, Capability] = {}
        if capabilities:
            for cap in capabilities:
                self.register(cap)

    def register(self, cap: Capability) -> None:
        cid = cap.spec.capability_id.strip()
        if not cid:
            raise ValueError("CAPABILITY_ID_EMPTY: capability_id must be a non-empty string")
        if cid in self._by_id:
            raise ValueError(f"CAPABILITY_ID_DUPLICATE: '{cid}' is already registered")

        # Minimal bounds validation (contract hygiene).
        b = cap.spec.bounds
        if b.max_calls < 1:
            raise ValueError("CAPABILITY_BOUNDS_INVALID: max_calls must be >= 1")
        if b.timeout_ms < 1:
            raise ValueError("CAPABILITY_BOUNDS_INVALID: timeout_ms must be >= 1")
        if b.max_input_chars < 1 or b.max_output_chars < 1:
            raise ValueError("CAPABILITY_BOUNDS_INVALID: max_input_chars/max_output_chars must be >= 1")

        self._by_id[cid] = cap

    def get(self, capability_id: str) -> Capability:
        cid = capability_id.strip()
        if cid not in self._by_id:
            raise KeyError(f"CAPABILITY_NOT_FOUND: '{cid}' is not registered")
        return self._by_id[cid]

    def has(self, capability_id: str) -> bool:
        return capability_id.strip() in self._by_id

    def specs(self) -> Dict[str, CapabilitySpec]:
        return {cid: cap.spec for cid, cap in self._by_id.items()}

    def ids(self) -> list[str]:
        return sorted(self._by_id.keys())

    def list_capabilities(self) -> list[CapabilitySpec]:
        """Return registered CapabilitySpec objects in deterministic (id-sorted) order."""
        return [self._by_id[cid].spec for cid in self.ids()]

    # Compatibility alias (some call sites prefer list_specs)
    def list_specs(self) -> list[CapabilitySpec]:
        return self.list_capabilities()


def default_registry() -> CapabilityRegistry:
    """
    Default registry for Phase 3.

    Intentionally empty: Phase 3 introduces the boundary contracts first.
    """
    return CapabilityRegistry()
