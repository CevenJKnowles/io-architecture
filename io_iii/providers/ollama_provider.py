# io_iii/providers/ollama_provider.py
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class OllamaProvider:
    """
    Minimal Ollama provider for IO-III (deterministic, sequential).
    Uses Ollama HTTP API at OLLAMA_HOST or default 127.0.0.1:11434.

    - Non-streaming for deterministic handling (stream=False)
    - Uses /api/generate (stable, simple response shape)
    """
    host: str = "http://127.0.0.1:11434"

    @classmethod
    def from_config(cls, providers_cfg: Dict[str, Any]) -> "OllamaProvider":
        # providers.yaml may contain:
        # ollama:
        #   host: http://127.0.0.1:11434
        cfg = (providers_cfg or {}).get("ollama", {}) if isinstance(providers_cfg, dict) else {}
        host = cfg.get("host") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
        return cls(host=host)

    def generate(self, *, model: str, prompt: str, options: Optional[Dict[str, Any]] = None) -> str:
        url = f"{self.host}/api/generate"
        payload: Dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if options:
            payload["options"] = options

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
            raise RuntimeError(f"OllamaProvider error calling {url}: {e}") from e

        obj = json.loads(body)
        if "response" not in obj:
            raise RuntimeError(f"Unexpected Ollama response shape: keys={list(obj.keys())}")
        return obj["response"]
