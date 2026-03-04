from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from io_iii.core.capabilities import (
    Capability,
    CapabilityBounds,
    CapabilityCategory,
    CapabilityContext,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySpec,
)


@dataclass(frozen=True)
class EchoJsonSummaryCapability:
    """
    Reference capability: cap.echo_json

    Purpose:
    - Demonstrate end-to-end capability invocation (Phase 3 M3.9)
    - Stay content-safe by returning ONLY structural summary (not payload content)

    Output:
    {
      "summary": {
        "payload_bytes": int,
        "payload_type": str,
        "top_level_keys": int | None,
        "top_level_len": int | None
      }
    }
    """

    _spec: CapabilitySpec

    @property
    def spec(self) -> CapabilitySpec:
        return self._spec

    def invoke(self, ctx: CapabilityContext, payload: Mapping[str, Any]) -> CapabilityResult:
        # Structural summary only (no payload echo)
        try:
            payload_bytes = len(json.dumps(payload, ensure_ascii=False))
        except Exception:
            payload_bytes = len(str(payload))

        payload_type = type(payload).__name__
        top_level_keys = None
        top_level_len = None

        if isinstance(payload, Mapping):
            top_level_keys = len(payload.keys())
        elif isinstance(payload, (list, tuple, set)):
            top_level_len = len(payload)

        return CapabilityResult(
            ok=True,
            output={
                "summary": {
                    "payload_bytes": payload_bytes,
                    "payload_type": payload_type,
                    "top_level_keys": top_level_keys,
                    "top_level_len": top_level_len,
                }
            },
        )


def builtin_capabilities() -> list[Capability]:
    """Declared built-in capabilities shipped with the reference runtime."""
    echo_spec = CapabilitySpec(
        capability_id="cap.echo_json",
        version="1.0",
        category=CapabilityCategory.VALIDATION,
        bounds=CapabilityBounds(
            max_calls=1,
            timeout_ms=50,
            max_input_chars=4096,
            max_output_chars=1024,
        ),
        description="Return a content-safe structural summary of the provided JSON payload.",
    )
    return [EchoJsonSummaryCapability(_spec=echo_spec)]


def builtin_registry() -> CapabilityRegistry:
    """Deterministic registry of built-in capabilities."""
    return CapabilityRegistry(builtin_capabilities())
