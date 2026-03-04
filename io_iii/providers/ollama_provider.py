# io_iii/providers/ollama_provider.py
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict

from io_iii.providers.provider_contract import ProviderError


@dataclass(frozen=True)
class OllamaProvider:
    """
    Minimal Ollama provider for IO-III (deterministic, sequential).
    Uses Ollama HTTP API at OLLAMA_HOST or default 127.0.0.1:11434.

    - Non-streaming for deterministic handling (stream=False)
    - Uses /api/generate (stable, simple response shape)
    """
    name: str = "ollama"
    host: str = "http://127.0.0.1:11434"

    @classmethod
    def from_config(cls, providers_cfg: Dict[str, Any]) -> "OllamaProvider":
        # providers.yaml may contain:
        # ollama:
        #   host: http://127.0.0.1:11434
        cfg = (providers_cfg or {}).get("ollama", {}) if isinstance(providers_cfg, dict) else {}
        host = cfg.get("host") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
        return cls(host=host)

    def generate(self, *, model: str, prompt: str) -> str:
        """
        Generate a completion via Ollama /api/generate.

        Contract:
        - returns a string (may be empty, never None)
        - raises ProviderError on failure
        """
        url = f"{self.host}/api/generate"

        # Keep implementation minimal and deterministic (no streaming).
        payload: Dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = resp.read().decode("utf-8")
        except Exception as e:
            raise ProviderError("PROVIDER_OLLAMA_FAILED", f"Error calling {url}: {e}") from e

        try:
            obj = json.loads(body)
        except Exception as e:
            raise ProviderError("PROVIDER_OLLAMA_BAD_JSON", f"Invalid JSON from {url}: {e}") from e

        if "response" not in obj:
            raise ProviderError(
                "PROVIDER_OLLAMA_BAD_SHAPE",
                f"Unexpected Ollama response shape: keys={list(obj.keys())}",
            )

        resp_text = obj.get("response")
        if not isinstance(resp_text, str):
            raise ProviderError(
                "PROVIDER_OLLAMA_BAD_SHAPE",
                f"Expected 'response' to be str, got {type(resp_text).__name__}",
            )

        return resp_text