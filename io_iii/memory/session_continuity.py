"""
io_iii.memory.session_continuity — Session continuity memory loading (Phase 8 M8.6).

Provides bounded, policy-gated memory loading for cross-turn session context.
The session continuity pack is auto-loaded by the session shell on `session continue`
if declared in memory_packs.yaml.

Contract (ADR-022):
    - Memory writes are NEVER triggered automatically (ADR-022 §7).
    - Absent pack → returns ([], None). Not a failure — safe default.
    - Retrieval policy is applied before records are returned (ADR-022 §4).
    - No record values appear in any structural or log field (ADR-003).

Default pack id: SESSION_CONTINUITY_PACK_ID ('pack.io_iii.session_resume').
Declared in architecture/runtime/config/memory_packs.yaml.

The returned MemoryRecord list is content-plane (values are present) and must
be handled by callers according to ADR-003. The SessionMemoryContext is
content-safe and may be logged or persisted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from io_iii.memory.packs import PackLoader
from io_iii.memory.policy import RetrievalPolicy
from io_iii.memory.store import MemoryRecord, MemoryStore


# ---------------------------------------------------------------------------
# Convention constant
# ---------------------------------------------------------------------------

SESSION_CONTINUITY_PACK_ID: str = "pack.io_iii.session_resume"
"""
Default pack identifier for session continuity (M8.6).

Declared in architecture/runtime/config/memory_packs.yaml.
Callers may pass a different pack_id to load_session_memory() to use a
custom pack — the absent-pack safe default applies regardless.
"""


# ---------------------------------------------------------------------------
# Content-safe context record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionMemoryContext:
    """
    Content-safe record of memory loaded for a session turn (Phase 8 M8.6).

    No record values, no record content. Safe to log, persist, or surface in
    CLI output (ADR-003).

    Fields:
        pack_id        — pack identifier used for loading
        scope          — record scope from the pack declaration
        keys_declared  — number of keys declared in the resolved pack
        keys_loaded    — number of records returned after policy filtering
        keys_missing   — declared keys with no record in the store (not a failure)
        policy_route   — route identifier used for retrieval policy evaluation
    """

    pack_id: str
    scope: str
    keys_declared: int
    keys_loaded: int
    keys_missing: int
    policy_route: str

    def to_log_safe(self) -> dict:
        """
        Return a content-safe dict projection (ADR-003).

        All fields are structural identifiers and counts — no values included.
        Safe for logging, CLI display, and session artefact embedding.
        """
        return {
            "pack_id": self.pack_id,
            "scope": self.scope,
            "keys_declared": self.keys_declared,
            "keys_loaded": self.keys_loaded,
            "keys_missing": self.keys_missing,
            "policy_route": self.policy_route,
        }


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_session_memory(
    *,
    pack_id: str = SESSION_CONTINUITY_PACK_ID,
    pack_loader: PackLoader,
    store: MemoryStore,
    policy: RetrievalPolicy,
    route: str = "executor",
) -> Tuple[List[MemoryRecord], Optional[SessionMemoryContext]]:
    """
    Load memory records for session continuity (Phase 8 M8.6).

    If pack_id is not declared in memory_packs.yaml, returns ([], None).
    This is not a failure — absent pack means no cross-turn memory (safe default).

    Contract:
    - Pack resolution is deterministic: keys resolved via PackLoader.resolve_keys()
      (max nesting depth 1, ADR-022 §3.2).
    - Records are loaded in pack declaration order via MemoryStore.list_by_keys().
    - Retrieval policy filtering is applied: records the route cannot access are
      dropped silently (ADR-022 §4).
    - Missing keys (declared in pack but absent from store) are counted in context
      but do not raise an error.
    - No memory values appear in the returned SessionMemoryContext.
    - Memory writes are NEVER triggered by this function (ADR-022 §7).

    Args:
        pack_id      — pack identifier to load (default: SESSION_CONTINUITY_PACK_ID)
        pack_loader  — PackLoader instance for the current config
        store        — MemoryStore instance for the current storage root
        policy       — RetrievalPolicy for access control (ADR-022 §4)
        route        — route identifier for policy evaluation (e.g. "executor")

    Returns:
        (records, context) where:
            records — policy-filtered MemoryRecord list (content-plane)
            context — SessionMemoryContext (content-safe) or None if pack absent
    """
    pack = pack_loader.get(pack_id)
    if pack is None:
        return [], None

    # Resolve full key list (max nesting depth 1; ADR-022 §3.2).
    keys = pack_loader.resolve_keys(pack_id)

    # Load records by declared key order; missing keys silently skipped.
    all_records = store.list_by_keys(scope=pack.scope, keys=keys)

    # Apply retrieval policy: drop records the route cannot access.
    filtered = policy.filter_records(route, all_records)

    ctx = SessionMemoryContext(
        pack_id=pack_id,
        scope=pack.scope,
        keys_declared=len(keys),
        keys_loaded=len(filtered),
        keys_missing=len(keys) - len(all_records),
        policy_route=route,
    )

    return filtered, ctx
