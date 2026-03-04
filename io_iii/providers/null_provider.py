from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from io_iii.providers.provider_contract import Provider, ProviderResult


@dataclass(frozen=True)
class NullProvider(Provider):
    """
    Deterministic stub provider.

    Used when provider routing selects 'null'.
    """
    name: str = "null"

    def generate(self, *, model: str, prompt: str) -> str:
        # Deterministic, content-free stub. Caller controls actual behaviour.
        return ""

    def run(self, *, mode: str, route_id: str, meta: Mapping[str, Any]) -> ProviderResult:
        # Deterministic placeholder response.
        return ProviderResult(
            message="",
            meta={"provider": self.name, "mode": mode, "route_id": route_id, "stub": True},
        )