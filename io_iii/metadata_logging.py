from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _get_nested(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def metadata_enabled(logging_cfg: Dict[str, Any]) -> bool:
    # expects: logging.metadata.enabled (bool) in cfg.logging
    val = _get_nested(logging_cfg, "logging", "metadata", "enabled", default=True)
    return bool(val)


def metadata_log_path(logging_cfg: Dict[str, Any]) -> Path:
    # expects: storage.metadata_log_dir in cfg.logging
    log_dir = _get_nested(logging_cfg, "storage", "metadata_log_dir", default="./architecture/runtime/logs")
    return Path(log_dir) / "metadata.jsonl"


def make_request_id() -> str:
    return f"{time.time_ns()}-{os.getpid()}"


def append_metadata(logging_cfg: Dict[str, Any], record: Dict[str, Any]) -> Optional[Path]:
    """
    Appends one JSON object per line into metadata.jsonl (JSONL).

    Metadata-only observability channel.

    Never pass prompt/response content into `record`.
    """

    if not metadata_enabled(logging_cfg):
        return None

    path = metadata_log_path(logging_cfg)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = dict(record)

    # ---- Schema fields (stable contract) ----
    payload.setdefault("schema", "io-iii-metadata-jsonl")
    payload.setdefault("schema_version", "v1.0")

    # ---- Timestamp (milliseconds since epoch) ----
    payload.setdefault("timestamp_ms", int(time.time() * 1000))

    # ---- Ensure request_id exists ----
    payload.setdefault("request_id", make_request_id())

    # ---- Forbidden content keys guard ----
    forbidden = {
        "prompt",
        "user_prompt",
        "system_prompt",
        "assembled_prompt",
        "message",
        "output",
        "completion",
        "draft",
        "revision",
        "content",
    }

    overlap = forbidden.intersection(payload.keys())
    if overlap:
        raise ValueError(f"metadata log contains forbidden content keys: {sorted(overlap)}")

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return path