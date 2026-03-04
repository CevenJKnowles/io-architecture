from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from io_iii.core.context_assembly import AssembledContext
from io_iii.core.session_state import RouteInfo, SessionState


@dataclass(frozen=True)
class ExecutionContext:
    """
    Engine-local container for runtime execution inputs and derived values.

    Design intent:
    - Unify engine inputs + derived values for a single deterministic run.
    - Reduce CLI→engine coupling by centralising runtime wiring.
    - Explicitly exclude raw prompt text to keep SessionState content-free.

    Notes:
    - 'prompt_hash' is safe to log.
    - 'assembled_context' is content-plane and MUST NOT be logged.
    """

    cfg: Any
    session_state: SessionState
    provider: Any
    route: Optional[RouteInfo]
    prompt_hash: Optional[str]
    assembled_context: Optional[AssembledContext]
    