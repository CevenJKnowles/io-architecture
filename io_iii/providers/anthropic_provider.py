from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from io_iii.providers.provider_contract import Provider, ProviderResult


@dataclass(frozen=True)
class AnthropicProvider(Provider):
    """
    Stub adapter for Anthropic.

    Cloud provider adapters are not implemented in this release.
    This module exists to satisfy the provider protocol interface
    and to surface a clear error if the provider is enabled.

    Phase 11 replaces this stub with a real implementation.
    See ADR-028 §1.
    """

    name: str = "anthropic"

    @classmethod
    def from_config(cls, providers_cfg: Any) -> "AnthropicProvider":
        raise NotImplementedError(
            "PROVIDER_NOT_IMPLEMENTED: anthropic — cloud provider adapters are not yet "
            "available in this release. See ROADMAP.md for Phase 11 timeline."
        )

    def generate(self, *, model: str, prompt: str) -> str:
        raise NotImplementedError(
            "PROVIDER_NOT_IMPLEMENTED: anthropic — cloud provider adapters are not yet "
            "available in this release. See ROADMAP.md for Phase 11 timeline."
        )

    def run(self, *, mode: str, route_id: str, meta: Mapping[str, Any]) -> ProviderResult:
        raise NotImplementedError(
            "PROVIDER_NOT_IMPLEMENTED: anthropic — cloud provider adapters are not yet "
            "available in this release. See ROADMAP.md for Phase 11 timeline."
        )
