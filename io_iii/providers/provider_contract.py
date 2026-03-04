from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class ProviderResult:
    """
    Provider result object.

    Content policy:
    - 'message' is content; do not log.
    - 'meta' must be content-safe metadata only.
    """
    message: str
    meta: Dict[str, Any]


class ProviderError(RuntimeError):
    """
    Provider execution failure.

    Must be raised for hard failures (network, model unavailable, invalid config).
    """
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.detail = message


@runtime_checkable
class Provider(Protocol):
    """
    Canonical provider contract.

    Providers are content-plane executors. The control plane remains responsible for:
    - routing
    - audit bounds
    - metadata logging policy
    """

    name: str

    def generate(self, *, model: str, prompt: str) -> str:
        """
        Generate a completion.

        Must return a string (may be empty but should not be None).
        Must raise ProviderError on failure.
        """
        ...

    def run(self, *, mode: str, route_id: str, meta: Mapping[str, Any]) -> ProviderResult:
        """
        Deterministic run helper for providers that implement non-LLM stubs.

        For LLM providers, this may be unused; it remains part of the contract
        for NullProvider style routes.
        """
        ...
        