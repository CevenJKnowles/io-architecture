# io_iii/providers/ollama_provider.py
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

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
        # providers.yaml canonical key: ollama.base_url
        cfg = (providers_cfg or {}).get("ollama", {}) if isinstance(providers_cfg, dict) else {}
        host = cfg.get("base_url") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
        return cls(host=host)

    def check_reachable(self, *, timeout_ms: int = 1000) -> None:
        """
        Pre-flight reachability check (ADR-011).

        Performs a lightweight GET to the Ollama root endpoint.
        Raises RuntimeError("PROVIDER_UNAVAILABLE: ollama") if unreachable.

        This is a CLI-boundary concern — do not call from the engine or routing layer.
        """
        url = f"{self.host}/"
        timeout_s = max(0.1, timeout_ms / 1000.0)
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout_s):
                pass
        except Exception as e:
            raise RuntimeError(f"PROVIDER_UNAVAILABLE: ollama — {e}") from e

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

    def generate_with_metrics(
        self, *, model: str, prompt: str
    ) -> Tuple[str, Optional[int], Optional[int]]:
        """
        Generate a completion and return Ollama's native token counts (M5.2).

        Returns:
            (text, input_tokens, output_tokens)

        Token fields:
            input_tokens  — from Ollama's prompt_eval_count (tokens consumed
                            to process the prompt); None if absent in response
            output_tokens — from Ollama's eval_count (tokens generated in the
                            response); None if absent in response

        Contract:
        - Provider Protocol `generate()` remains unchanged (returns str only).
        - This method is the M5.2 metrics-aware variant for the engine's executor path.
        - Raises ProviderError on failure (identical to generate()).
        """
        url = f"{self.host}/api/generate"

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

        # ADR-021 §3.3: surface Ollama's native token counts where present.
        # prompt_eval_count = tokens consumed processing the input prompt.
        # eval_count        = tokens generated in the output response.
        raw_input = obj.get("prompt_eval_count")
        raw_output = obj.get("eval_count")
        input_tokens: Optional[int] = int(raw_input) if isinstance(raw_input, int) else None
        output_tokens: Optional[int] = int(raw_output) if isinstance(raw_output, int) else None

        return resp_text, input_tokens, output_tokens