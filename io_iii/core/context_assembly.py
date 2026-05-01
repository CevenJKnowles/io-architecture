from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from io_iii.core.session_state import SessionState
from io_iii.memory.store import MemoryRecord
from io_iii.persona_contract import load_identity, load_user_profile


ASSEMBLY_VERSION = "adr-010/v1"

# Memory injection budget (ADR-022 §5).
# Records are included in declaration order until cumulative value chars
# exceed this ceiling. Overflow records are dropped silently.
_DEFAULT_MEMORY_BUDGET_CHARS: int = 4_000

# Runtime attribution — injected as the final section of every system prompt.
# Non-configurable. Preserves authorship across all deployments.
_RUNTIME_ATTRIBUTION: str = (
    "=== Runtime ===\n"
    "I0\u00b3 io-architecture \u00b7 https://github.com/CevenJKnowles/io-architecture"
    " \u00b7 \u00a9 Ceven Knowles\n"
)


@dataclass(frozen=True)
class AssembledContext:
    """
    Content-plane output of the Context Assembly Layer (ADR-010).

    Logging policy:
    - DO NOT log system_prompt, user_prompt, or messages.
    - It is safe to log prompt_hash and assembly_metadata (non-content metrics only).
    """
    system_prompt: str
    user_prompt: str
    messages: List[Dict[str, str]]
    prompt_hash: str
    assembly_version: str = ASSEMBLY_VERSION
    assembly_metadata: Dict[str, Any] = field(default_factory=dict)


def assemble_context(
    *,
    session_state: SessionState,
    user_prompt: str,
    persona_contract: str,
    route_metadata: Mapping[str, Any] | None = None,
    memory: Sequence[MemoryRecord] | None = None,
    memory_budget_chars: int = _DEFAULT_MEMORY_BUDGET_CHARS,
) -> AssembledContext:
    """
    Deterministically assemble the provider-neutral prompt/messages.

    Inputs:
    - session_state: control-plane only (must not contain prompt/output content)
    - user_prompt: explicit user content (content-plane)
    - persona_contract: persona contract text (content-plane)
    - route_metadata: non-content routing/provider metadata (control-plane-ish)
    - memory: policy-filtered MemoryRecord list (content-plane); injected as
      a '=== Memory ===' section in the system prompt when non-empty (ADR-022 §5)
    - memory_budget_chars: maximum chars of record values to inject; overflow
      records are dropped silently in declaration order

    Output:
    - AssembledContext (content-plane)
    """
    if route_metadata is None:
        route_metadata = {}

    injected = _select_bounded_memory(memory or [], budget_chars=memory_budget_chars)

    system_prompt = _build_system_prompt(
        session_state=session_state,
        persona_contract=persona_contract,
        route_metadata=route_metadata,
        injected_memory=injected,
    )

    messages = _build_messages(system_prompt=system_prompt, user_prompt=user_prompt)

    prompt_hash = _compute_prompt_hash(messages=messages)

    assembly_metadata = _build_assembly_metadata(
        session_state=session_state,
        route_metadata=route_metadata,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        messages=messages,
        injected_memory=injected,
    )

    return AssembledContext(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        messages=messages,
        prompt_hash=prompt_hash,
        assembly_version=ASSEMBLY_VERSION,
        assembly_metadata=assembly_metadata,
    )


# ----------------------------
# Deterministic construction
# ----------------------------

def _build_system_prompt(
    *,
    session_state: SessionState,
    persona_contract: str,
    route_metadata: Mapping[str, Any],
    injected_memory: List[MemoryRecord],
) -> str:
    """
    Canonical system prompt layout (stable ordering, no randomness).

    Sections:
    1) System header (IO-III governance posture)
    2) Persona contract
    3) User profile (omitted when empty) — user_profile.yaml
    4) Runtime boundaries summary (non-content)
    5) Execution envelope (mode, audit toggle)
    6) Memory context (omitted when empty) — ADR-022 §5
    7) Runtime attribution (always present, non-configurable)
    """
    identity = load_identity()
    _name = (identity.get("name") or "IO-III").strip()
    _desc = (identity.get("description") or "").strip()
    _style = (identity.get("style") or "").strip()

    _identity_lines = [f"Your name is {_name}."]
    if _desc:
        _identity_lines.append(_desc)
    if _style:
        _identity_lines.append(f"Communication style: {_style}")

    header = (
        f"You are IO-III. {' '.join(_identity_lines)}\n"
        "When asked your name, respond with your name only.\n"
        "Operate under governance-first constraints.\n"
        "Follow deterministic, bounded execution.\n"
        "Output must be a single unified final response.\n"
    )

    persona_section = (
        "=== Persona Contract ===\n"
        f"{persona_contract.strip()}\n"
    )

    boundaries_section = _format_boundaries_section(session_state=session_state, route_metadata=route_metadata)

    envelope_section = (
        "=== Execution Envelope ===\n"
        f"mode: {session_state.mode}\n"
        f"audit_enabled: {bool(session_state.audit.audit_enabled)}\n"
        f"max_audit_passes: 1\n"
        f"max_revision_passes: 1\n"
    )

    sections = [header.strip(), persona_section.strip()]

    user = load_user_profile()
    _u_name     = (user.get("name") or "").strip()
    _u_role     = (user.get("role") or "").strip()
    _u_expertise = [e.strip() for e in (user.get("expertise") or []) if str(e).strip()]
    _u_prefs    = user.get("preferences") or {}
    _u_notes    = (user.get("notes") or "").strip()

    _user_lines = []
    if _u_name:     _user_lines.append(f"Name: {_u_name}")
    if _u_role:     _user_lines.append(f"Role: {_u_role}")
    if _u_expertise:_user_lines.append(f"Expertise: {', '.join(_u_expertise)}")
    if _u_prefs:
        for k, v in _u_prefs.items():
            if v: _user_lines.append(f"{k.capitalize()}: {v}")
    if _u_notes:    _user_lines.append(f"Notes: {_u_notes}")

    if _user_lines:
        user_section = "=== User Profile ===\n" + "\n".join(_user_lines) + "\n"
        sections.append(user_section.strip())

    sections += [boundaries_section.strip(), envelope_section.strip()]

    if injected_memory:
        sections.append(_format_memory_section(injected_memory).strip())

    # Stable join with explicit separators; attribution is always last.
    return "\n".join(sections).strip() + "\n" + _RUNTIME_ATTRIBUTION.strip() + "\n"


def _format_boundaries_section(*, session_state: SessionState, route_metadata: Mapping[str, Any]) -> str:
    """
    Non-content summary of relevant boundaries/policy.
    Must remain deterministic and safe to include in system prompt.
    """
    provider = session_state.provider
    route_id = session_state.route_id

    # Only include safe, non-content keys from route_metadata
    safe_keys = ("selected_provider", "selected_target", "fallback_used", "route_id")
    safe_meta: Dict[str, Any] = {}
    for k in safe_keys:
        if k in route_metadata:
            safe_meta[k] = route_metadata[k]

    # Include routing boundaries if present (already non-content policy)
    boundaries = {}
    if session_state.route is not None:
        boundaries = dict(session_state.route.boundaries or {})

    # Canonical JSON for deterministic ordering
    safe_meta_json = _canonical_json(safe_meta)
    boundaries_json = _canonical_json(boundaries)

    return (
        "=== Runtime Boundaries ===\n"
        f"provider: {provider}\n"
        f"route_id: {route_id}\n"
        f"route_metadata: {safe_meta_json}\n"
        f"boundaries: {boundaries_json}\n"
    )


def _build_messages(*, system_prompt: str, user_prompt: str) -> List[Dict[str, str]]:
    """
    Provider-neutral message format.
    Deterministic ordering.
    """
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _compute_prompt_hash(*, messages: Sequence[Mapping[str, str]]) -> str:
    """
    Compute sha256 hash of canonical serialisation of messages.
    Safe to log.
    """
    payload = _canonical_json(list(messages))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest


def _build_assembly_metadata(
    *,
    session_state: SessionState,
    route_metadata: Mapping[str, Any],
    system_prompt: str,
    user_prompt: str,
    messages: Sequence[Mapping[str, str]],
    injected_memory: List[MemoryRecord],
) -> Dict[str, Any]:
    """
    Non-content metrics only.

    Memory fields (ADR-022 §6 allowed log fields):
    - memory_keys_released: list of scope/key identifiers — safe to log
    - memory_records_count: integer count
    - memory_total_chars: total chars of injected values
    Memory values are never included.
    """
    # Char counts only (no content)
    sys_len = len(system_prompt)
    user_len = len(user_prompt)
    msg_count = len(messages)

    # Safe memory log fields — identifiers and counts only, never values
    memory_keys_released = [r.identifier() for r in injected_memory]
    memory_total_chars = sum(len(r.value) for r in injected_memory)

    return {
        "assembly_version": ASSEMBLY_VERSION,
        "mode": session_state.mode,
        "provider": session_state.provider,
        "model": session_state.model,
        "route_id": session_state.route_id,
        "audit_enabled": bool(session_state.audit.audit_enabled),
        "system_prompt_chars": sys_len,
        "user_prompt_chars": user_len,
        "message_count": msg_count,
        # Include only safe keys; never include full route_metadata blob
        "route_metadata_safe": {
            k: route_metadata.get(k)
            for k in ("selected_provider", "selected_target", "fallback_used", "route_id")
            if k in route_metadata
        },
        # Memory safe log fields (ADR-022 §6)
        "memory_keys_released": memory_keys_released,
        "memory_records_count": len(injected_memory),
        "memory_total_chars": memory_total_chars,
    }


def _select_bounded_memory(
    records: Sequence[MemoryRecord],
    *,
    budget_chars: int,
) -> List[MemoryRecord]:
    """
    Return the largest prefix of records whose cumulative value length ≤ budget_chars.

    Records are evaluated in declaration order. The first record that would push
    the total over budget — and all subsequent records — are dropped silently.
    A budget of 0 drops all records.
    """
    selected: List[MemoryRecord] = []
    total = 0
    for record in records:
        cost = len(record.value)
        if total + cost > budget_chars:
            break
        selected.append(record)
        total += cost
    return selected


def _format_memory_section(records: List[MemoryRecord]) -> str:
    """
    Render injected memory records as a system-prompt section (ADR-022 §5).

    Format (content-plane — never logged):
        === Memory ===
        [scope/key]
        <value>

        [scope/key]
        <value>

    Keys identify the record; values are the injected context.
    """
    lines = ["=== Memory ==="]
    for record in records:
        lines.append(f"[{record.identifier()}]")
        lines.append(record.value)
        lines.append("")  # blank line between records
    return "\n".join(lines)


def _canonical_json(obj: Any) -> str:
    """
    Stable JSON serialisation:
    - sorted keys
    - compact separators
    - no non-deterministic whitespace
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)