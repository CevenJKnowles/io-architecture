from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Set


DEFAULT_FORBIDDEN_KEYS: Set[str] = {
    "prompt",
    "user_prompt",
    "system_prompt",
    "assembled_prompt",
    "message",
    "completion",
    "draft",
    "revision",
    "content",
}


# Metadata channel is stricter: reject common "output"-named payloads as well.
METADATA_FORBIDDEN_KEYS: Set[str] = set(DEFAULT_FORBIDDEN_KEYS) | {"output"}


def assert_no_forbidden_keys(obj: Any, forbidden: Set[str] | None = None) -> None:
    """Raise ValueError if any forbidden key appears anywhere in a nested structure.

    This is a structural guardrail to prevent accidental content leakage into
    metadata channels or ExecutionResult.meta.
    """

    if forbidden is None:
        forbidden = DEFAULT_FORBIDDEN_KEYS

    stack: list[Any] = [obj]
    while stack:
        cur = stack.pop()

        if isinstance(cur, dict):
            for k, v in cur.items():
                if isinstance(k, str) and k in forbidden:
                    raise ValueError(f"forbidden key present in structure: {k}")
                stack.append(v)
            continue

        if isinstance(cur, (list, tuple, set)):
            stack.extend(list(cur))
            continue

        # Ignore scalars / unknown types
