# io_iii/core/telemetry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ExecutionMetrics:
    """
    Content-safe execution telemetry for a single governed run (ADR-021 §3).

    All fields are counts, durations, or stable identifier strings.
    No prompt text, model output, context content, or memory values are stored.

    Fields:
        call_count      number of provider calls in the execution
        input_tokens    estimated input token count (from M5.1 heuristic, or
                        provider-confirmed value where available)
        output_tokens   token count of provider response; None if unavailable
        latency_ms      total execution duration in milliseconds
        model_used      resolved model identifier from routing; None for null route
    """
    call_count: int
    input_tokens: int
    output_tokens: Optional[int]
    latency_ms: int
    model_used: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Content-safe projection for metadata.jsonl (ADR-003)."""
        return {
            "call_count": self.call_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "model_used": self.model_used,
        }
