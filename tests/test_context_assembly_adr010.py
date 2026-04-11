"""
test_context_assembly_adr010.py — ADR-010 Context Assembly Layer unit tests.

Verifies:

  _canonical_json
  - sorted keys produce stable output
  - compact separators (no extra whitespace)
  - nested structures serialised deterministically
  - stable across repeated calls with identical input

  _compute_prompt_hash
  - same messages → same sha256 digest (5 iterations)
  - different messages → different digest
  - digest is a 64-char hex string (sha256)

  _build_messages
  - returns exactly two entries
  - first entry has role == 'system'
  - second entry has role == 'user'
  - content fields match system_prompt / user_prompt

  _build_system_prompt
  - contains all four required sections (header, persona, boundaries, envelope)
  - section order is deterministic across repeated calls
  - mode and audit_enabled are reflected in envelope section
  - ends with a newline

  _format_boundaries_section
  - includes only the four safe keys (selected_provider, selected_target,
    fallback_used, route_id) from route_metadata
  - excludes unsafe keys (prompt, content, completion, etc.)
  - uses canonical JSON for route_metadata and boundaries

  _build_assembly_metadata
  - no content-plane keys present (prompt, completion, message)
  - system_prompt_chars and user_prompt_chars reflect input lengths
  - message_count matches _build_messages output
  - assembly_version matches ASSEMBLY_VERSION sentinel

  assemble_context (end-to-end)
  - same inputs → same prompt_hash (over 5 iterations)
  - prompt_hash is a 64-char hex string
  - assembly_version matches ASSEMBLY_VERSION
  - assembly_metadata contains no forbidden keys
"""
from __future__ import annotations

import hashlib
import json

import pytest

from io_iii.core.context_assembly import (
    ASSEMBLY_VERSION,
    AssembledContext,
    _build_assembly_metadata,
    _build_messages,
    _build_system_prompt,
    _canonical_json,
    _compute_prompt_hash,
    _format_boundaries_section,
    assemble_context,
)
from io_iii.core.content_safety import assert_no_forbidden_keys
from io_iii.core.session_state import AuditGateState, RouteInfo, SessionState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_state(
    *,
    mode: str = "executor",
    audit_enabled: bool = False,
    provider: str = "ollama",
    model: str = "test-model",
    route_id: str = "executor",
    boundaries: dict | None = None,
) -> SessionState:
    route = RouteInfo(
        mode=mode,
        primary_target="local:test-model",
        secondary_target=None,
        selected_target="local:test-model",
        selected_provider=provider,
        fallback_used=False,
        fallback_reason=None,
        boundaries=boundaries or {"single_voice_output": True},
    )
    return SessionState(
        request_id="test-req-001",
        started_at_ms=0,
        mode=mode,
        config_dir="./architecture/runtime/config",
        route=route,
        audit=AuditGateState(audit_enabled=audit_enabled),
        status="ok",
        provider=provider,
        model=model,
        route_id=route_id,
        persona_contract_version="v0.1",
        logging_policy={"content": "disabled"},
    )


# ---------------------------------------------------------------------------
# _canonical_json
# ---------------------------------------------------------------------------

class TestCanonicalJson:

    def test_sorted_keys(self):
        obj = {"z": 1, "a": 2, "m": 3}
        result = _canonical_json(obj)
        parsed = json.loads(result)
        assert list(parsed.keys()) == sorted(obj.keys())

    def test_compact_separators(self):
        obj = {"key": "value"}
        result = _canonical_json(obj)
        assert " " not in result, "canonical JSON must use compact separators (no spaces)"

    def test_nested_structure_deterministic(self):
        obj = {"outer": {"z": 99, "a": 1}, "first": True}
        r1 = _canonical_json(obj)
        r2 = _canonical_json(obj)
        assert r1 == r2

    def test_stable_across_repeated_calls(self):
        obj = {"selected_provider": "ollama", "fallback_used": False, "route_id": "executor"}
        results = [_canonical_json(obj) for _ in range(5)]
        assert len(set(results)) == 1, "canonical JSON must be identical across repeated calls"

    def test_empty_dict(self):
        assert _canonical_json({}) == "{}"

    def test_list_input(self):
        lst = [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]
        result = _canonical_json(lst)
        parsed = json.loads(result)
        assert parsed == lst


# ---------------------------------------------------------------------------
# _compute_prompt_hash
# ---------------------------------------------------------------------------

class TestComputePromptHash:

    def test_same_messages_same_hash(self):
        messages = [
            {"role": "system", "content": "You are IO-III."},
            {"role": "user", "content": "Hello."},
        ]
        hashes = [_compute_prompt_hash(messages=messages) for _ in range(5)]
        assert len(set(hashes)) == 1, "identical messages must always produce identical hash"

    def test_different_messages_different_hash(self):
        m1 = [{"role": "user", "content": "Hello."}]
        m2 = [{"role": "user", "content": "Goodbye."}]
        assert _compute_prompt_hash(messages=m1) != _compute_prompt_hash(messages=m2)

    def test_hash_is_sha256_hex_string(self):
        messages = [{"role": "user", "content": "test"}]
        digest = _compute_prompt_hash(messages=messages)
        assert isinstance(digest, str)
        assert len(digest) == 64, "sha256 hex digest must be 64 characters"
        assert all(c in "0123456789abcdef" for c in digest)

    def test_hash_matches_manual_sha256(self):
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
        payload = _canonical_json(list(messages))
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        assert _compute_prompt_hash(messages=messages) == expected

    def test_order_sensitive(self):
        """Swapping system/user order must change the hash."""
        m1 = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
        m2 = [{"role": "user", "content": "U"}, {"role": "system", "content": "S"}]
        assert _compute_prompt_hash(messages=m1) != _compute_prompt_hash(messages=m2)


# ---------------------------------------------------------------------------
# _build_messages
# ---------------------------------------------------------------------------

class TestBuildMessages:

    def test_returns_two_entries(self):
        msgs = _build_messages(system_prompt="SYS", user_prompt="USR")
        assert len(msgs) == 2

    def test_first_role_is_system(self):
        msgs = _build_messages(system_prompt="SYS", user_prompt="USR")
        assert msgs[0]["role"] == "system"

    def test_second_role_is_user(self):
        msgs = _build_messages(system_prompt="SYS", user_prompt="USR")
        assert msgs[1]["role"] == "user"

    def test_system_content_matches(self):
        msgs = _build_messages(system_prompt="governance-first", user_prompt="hello")
        assert msgs[0]["content"] == "governance-first"

    def test_user_content_matches(self):
        msgs = _build_messages(system_prompt="SYS", user_prompt="the user query")
        assert msgs[1]["content"] == "the user query"

    def test_deterministic_ordering(self):
        for _ in range(5):
            msgs = _build_messages(system_prompt="S", user_prompt="U")
            assert msgs[0]["role"] == "system"
            assert msgs[1]["role"] == "user"


# ---------------------------------------------------------------------------
# _build_system_prompt
# ---------------------------------------------------------------------------

class TestBuildSystemPrompt:

    def test_contains_persona_section(self):
        state = _make_session_state()
        result = _build_system_prompt(
            session_state=state,
            persona_contract="Persona: be accurate.",
            route_metadata={},
        )
        assert "=== Persona Contract ===" in result

    def test_contains_runtime_boundaries_section(self):
        state = _make_session_state()
        result = _build_system_prompt(
            session_state=state,
            persona_contract="Test persona",
            route_metadata={},
        )
        assert "=== Runtime Boundaries ===" in result

    def test_contains_execution_envelope_section(self):
        state = _make_session_state()
        result = _build_system_prompt(
            session_state=state,
            persona_contract="Test persona",
            route_metadata={},
        )
        assert "=== Execution Envelope ===" in result

    def test_contains_io_iii_header(self):
        state = _make_session_state()
        result = _build_system_prompt(
            session_state=state,
            persona_contract="Test persona",
            route_metadata={},
        )
        assert "You are IO-III." in result

    def test_envelope_reflects_mode(self):
        state = _make_session_state(mode="challenger")
        result = _build_system_prompt(
            session_state=state,
            persona_contract="challenger persona",
            route_metadata={},
        )
        assert "mode: challenger" in result

    def test_envelope_reflects_audit_enabled(self):
        state = _make_session_state(audit_enabled=True)
        result = _build_system_prompt(
            session_state=state,
            persona_contract="Test persona",
            route_metadata={},
        )
        assert "audit_enabled: True" in result

    def test_ends_with_newline(self):
        state = _make_session_state()
        result = _build_system_prompt(
            session_state=state,
            persona_contract="Test persona",
            route_metadata={},
        )
        assert result.endswith("\n")

    def test_section_order_is_stable(self):
        """Persona section must precede boundaries, which precede envelope."""
        state = _make_session_state()
        result = _build_system_prompt(
            session_state=state,
            persona_contract="Test persona",
            route_metadata={},
        )
        idx_persona = result.index("=== Persona Contract ===")
        idx_boundaries = result.index("=== Runtime Boundaries ===")
        idx_envelope = result.index("=== Execution Envelope ===")
        assert idx_persona < idx_boundaries < idx_envelope

    def test_deterministic_across_repeated_calls(self):
        state = _make_session_state()
        results = [
            _build_system_prompt(
                session_state=state,
                persona_contract="Determinism persona",
                route_metadata={"selected_provider": "ollama"},
            )
            for _ in range(5)
        ]
        assert len(set(results)) == 1


# ---------------------------------------------------------------------------
# _format_boundaries_section
# ---------------------------------------------------------------------------

class TestFormatBoundariesSection:

    def test_includes_safe_key_selected_provider(self):
        state = _make_session_state()
        result = _format_boundaries_section(
            session_state=state,
            route_metadata={"selected_provider": "ollama", "prompt": "SHOULD NOT APPEAR"},
        )
        assert "ollama" in result

    def test_excludes_unsafe_key_prompt(self):
        state = _make_session_state()
        result = _format_boundaries_section(
            session_state=state,
            route_metadata={"prompt": "secret prompt text"},
        )
        assert "secret prompt text" not in result

    def test_excludes_unsafe_key_completion(self):
        state = _make_session_state()
        result = _format_boundaries_section(
            session_state=state,
            route_metadata={"completion": "model output here", "selected_provider": "ollama"},
        )
        assert "model output here" not in result

    def test_includes_fallback_used(self):
        state = _make_session_state()
        result = _format_boundaries_section(
            session_state=state,
            route_metadata={"fallback_used": True},
        )
        assert "fallback_used" in result

    def test_includes_route_id(self):
        state = _make_session_state()
        result = _format_boundaries_section(
            session_state=state,
            route_metadata={"route_id": "executor"},
        )
        assert "executor" in result

    def test_empty_route_metadata(self):
        state = _make_session_state()
        result = _format_boundaries_section(session_state=state, route_metadata={})
        assert "=== Runtime Boundaries ===" in result


# ---------------------------------------------------------------------------
# _build_assembly_metadata
# ---------------------------------------------------------------------------

class TestBuildAssemblyMetadata:

    def _make(self, system_prompt: str = "SYS", user_prompt: str = "USR"):
        state = _make_session_state()
        messages = _build_messages(system_prompt=system_prompt, user_prompt=user_prompt)
        return _build_assembly_metadata(
            session_state=state,
            route_metadata={},
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            messages=messages,
        )

    def test_no_forbidden_keys(self):
        meta = self._make()
        assert_no_forbidden_keys(meta)  # must not raise

    def test_system_prompt_chars_correct(self):
        meta = self._make(system_prompt="hello world")
        assert meta["system_prompt_chars"] == len("hello world")

    def test_user_prompt_chars_correct(self):
        meta = self._make(user_prompt="query text")
        assert meta["user_prompt_chars"] == len("query text")

    def test_message_count_is_two(self):
        meta = self._make()
        assert meta["message_count"] == 2

    def test_assembly_version_matches_sentinel(self):
        meta = self._make()
        assert meta["assembly_version"] == ASSEMBLY_VERSION

    def test_mode_field_present(self):
        meta = self._make()
        assert "mode" in meta

    def test_provider_field_present(self):
        meta = self._make()
        assert "provider" in meta


# ---------------------------------------------------------------------------
# assemble_context (end-to-end)
# ---------------------------------------------------------------------------

class TestAssembleContext:

    def _make_ctx(self, user_prompt: str = "What is governance?") -> AssembledContext:
        state = _make_session_state()
        return assemble_context(
            session_state=state,
            user_prompt=user_prompt,
            persona_contract="Governance-first persona contract.",
            route_metadata={"selected_provider": "ollama", "route_id": "executor"},
        )

    def test_same_inputs_same_hash(self):
        """Identical inputs must produce identical prompt_hash across 5 calls."""
        hashes = [self._make_ctx().prompt_hash for _ in range(5)]
        assert len(set(hashes)) == 1

    def test_prompt_hash_is_sha256_hex(self):
        ctx = self._make_ctx()
        assert isinstance(ctx.prompt_hash, str)
        assert len(ctx.prompt_hash) == 64
        assert all(c in "0123456789abcdef" for c in ctx.prompt_hash)

    def test_assembly_version_matches_sentinel(self):
        ctx = self._make_ctx()
        assert ctx.assembly_version == ASSEMBLY_VERSION

    def test_assembly_metadata_no_forbidden_keys(self):
        ctx = self._make_ctx()
        assert_no_forbidden_keys(ctx.assembly_metadata)

    def test_different_user_prompt_different_hash(self):
        ctx1 = self._make_ctx(user_prompt="first query")
        ctx2 = self._make_ctx(user_prompt="entirely different query")
        assert ctx1.prompt_hash != ctx2.prompt_hash

    def test_messages_structure(self):
        ctx = self._make_ctx()
        assert len(ctx.messages) == 2
        assert ctx.messages[0]["role"] == "system"
        assert ctx.messages[1]["role"] == "user"

    def test_user_prompt_preserved(self):
        ctx = self._make_ctx(user_prompt="preserved query text")
        assert ctx.user_prompt == "preserved query text"
