"""
Shared utilities for the io_iii CLI subpackage.

Private to the cli package — import via cli/__init__.py for external use.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from io_iii.config import default_config_dir

# ADR-009 hard limits
MAX_AUDIT_PASSES = 1
MAX_REVISION_PASSES = 1


def _to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return {k: _to_jsonable(v) for k, v in vars(obj).items()}
    return str(obj)


def _print(obj: Any) -> None:
    print(json.dumps(_to_jsonable(obj), indent=2))


def _get_cfg_dir(args) -> Path:
    if getattr(args, "config_dir", None):
        return Path(args.config_dir)
    return default_config_dir()


def _parse_capability_payload(raw: Optional[str]) -> Dict[str, Any]:
    """
    Parse a JSON object string into a dict for capability payload.

    Allowed: JSON object only.
    Default: {}.
    """
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except Exception as e:
        raise ValueError(f"CAPABILITY_PAYLOAD_INVALID_JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError("CAPABILITY_PAYLOAD_INVALID_SHAPE: payload must be a JSON object")
    return obj
