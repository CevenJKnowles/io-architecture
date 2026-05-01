"""
io_iii.core.file_store — Session-scoped in-memory file store (ADR-033 §5).

Storage is dict-backed and does not survive server restart.
A reloaded session may carry a file_ref that no longer resolves;
callers must handle FileRefNotFound and surface FILE_REF_EXPIRED.
"""
from __future__ import annotations

import uuid
from typing import Dict, Tuple

# { session_id: { file_ref: (filename, content) } }
_store: Dict[str, Dict[str, Tuple[str, str]]] = {}


class FileRefNotFound(Exception):
    """Raised when a file_ref cannot be resolved (expired or never stored)."""


class FileRefExpiredError(RuntimeError):
    """
    Raised by run_turn when file_ref is present but cannot be resolved.

    Signals a recoverable user error: the server was restarted and the
    in-memory file store was cleared. The session is NOT terminated.
    Surface the plain-language message to the user.
    """
    code = "FILE_REF_EXPIRED"
    user_message = (
        "File reference expired — the server was restarted since this file was uploaded. "
        "Please re-upload the file to continue."
    )


def store(session_id: str, content: str, filename: str) -> str:
    """Store extracted text for a session. Returns a UUID file_ref."""
    if session_id not in _store:
        _store[session_id] = {}
    ref = str(uuid.uuid4())
    _store[session_id][ref] = (filename, content)
    return ref


def resolve(session_id: str, file_ref: str) -> Tuple[str, str]:
    """
    Return (filename, content) for the given file_ref.
    Raises FileRefNotFound if absent.
    """
    session_files = _store.get(session_id, {})
    entry = session_files.get(file_ref)
    if entry is None:
        raise FileRefNotFound(file_ref)
    return entry  # (filename, content)


def delete(session_id: str) -> None:
    """Delete all files for a session. No-op if session has no files."""
    _store.pop(session_id, None)
