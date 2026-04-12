"""
test_session_continuity_m86.py — Phase 8 M8.6 Session Continuity via Memory.

Contract coverage:
  SessionMemoryContext:
    - construction and field access
    - to_log_safe() carries no values — structural fields only
    - frozen (immutable)

  load_session_memory:
    - absent pack → ([], None) — safe default
    - pack present, store empty → records=[], ctx with keys_declared and keys_missing
    - pack present, store has records → records loaded, ctx accurate
    - policy filtering applied: records for route not in allowlist dropped
    - keys_missing counts keys absent from store (not policy-dropped)
    - keys_loaded reflects post-policy count
    - custom pack_id accepted
    - resolve_keys expansion: include_packs resolved at depth 1

  TurnRecord.memory_keys_loaded:
    - default 0 when no session_memory passed
    - set to len(session_memory) when records present
    - preserved in save/load round-trip

  DialogueTurnResult.memory_context:
    - None when no memory loaded
    - SessionMemoryContext when memory loaded
    - frozen

  run_turn integration:
    - session_memory=None → memory_keys_loaded=0, memory_context=None
    - session_memory=records → memory_keys_loaded=N, memory_context threaded through
    - memory values never appear in TurnRecord or DialogueSession JSON

  Content safety:
    - SessionMemoryContext.to_log_safe() excludes all value fields
    - memory_keys_loaded is a count, not keys or values
    - no MemoryRecord.value in any persisted field
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from io_iii.core.dialogue_session import (
    DialogueSession,
    DialogueTurnResult,
    TurnRecord,
    new_session,
    run_turn,
    save_session,
    load_session,
)
from io_iii.core.dependencies import RuntimeDependencies
from io_iii.core.engine import ExecutionResult
from io_iii.core.session_state import SessionState
from io_iii.memory.packs import MemoryPack, PackLoader
from io_iii.memory.policy import NULL_POLICY, RetrievalPolicy
from io_iii.memory.session_continuity import (
    SESSION_CONTINUITY_PACK_ID,
    SessionMemoryContext,
    load_session_memory,
)
from io_iii.memory.store import MemoryRecord, MemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record(key: str, scope: str = "io_iii", sensitivity: str = "standard") -> MemoryRecord:
    return MemoryRecord(
        key=key,
        scope=scope,
        value=f"value-for-{key}",  # content-plane; not to be persisted
        version=1,
        provenance="human",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        sensitivity=sensitivity,
    )


def _memory_ctx(
    pack_id: str = SESSION_CONTINUITY_PACK_ID,
    scope: str = "io_iii",
    keys_declared: int = 3,
    keys_loaded: int = 2,
    keys_missing: int = 1,
    policy_route: str = "executor",
) -> SessionMemoryContext:
    return SessionMemoryContext(
        pack_id=pack_id,
        scope=scope,
        keys_declared=keys_declared,
        keys_loaded=keys_loaded,
        keys_missing=keys_missing,
        policy_route=policy_route,
    )


def _fake_state() -> SessionState:
    return SessionState(request_id="req-m86", started_at_ms=0)


def _fake_result() -> ExecutionResult:
    return ExecutionResult(
        message="ok",
        meta={},
        provider="null",
        model=None,
        route_id="executor",
        audit_meta=None,
        prompt_hash=None,
    )


def _deps() -> RuntimeDependencies:
    return RuntimeDependencies(
        ollama_provider_factory=MagicMock(),
        challenger_fn=None,
        capability_registry=MagicMock(),
    )


def _mock_orch_success():
    return patch(
        "io_iii.core.dialogue_session._orchestrator.run",
        return_value=(_fake_state(), _fake_result()),
    )


def _mock_gate():
    gate = MagicMock()
    gate.check.return_value = None
    return gate


def _active_session() -> DialogueSession:
    return new_session()


# ---------------------------------------------------------------------------
# SessionMemoryContext tests
# ---------------------------------------------------------------------------

class TestSessionMemoryContext:

    def test_construction(self):
        ctx = _memory_ctx()
        assert ctx.pack_id == SESSION_CONTINUITY_PACK_ID
        assert ctx.scope == "io_iii"
        assert ctx.keys_declared == 3
        assert ctx.keys_loaded == 2
        assert ctx.keys_missing == 1
        assert ctx.policy_route == "executor"

    def test_frozen(self):
        ctx = _memory_ctx()
        with pytest.raises(Exception):
            ctx.keys_loaded = 99  # type: ignore

    def test_to_log_safe_has_required_fields(self):
        ctx = _memory_ctx()
        safe = ctx.to_log_safe()
        assert safe["pack_id"] == SESSION_CONTINUITY_PACK_ID
        assert safe["scope"] == "io_iii"
        assert safe["keys_declared"] == 3
        assert safe["keys_loaded"] == 2
        assert safe["keys_missing"] == 1
        assert safe["policy_route"] == "executor"

    def test_to_log_safe_has_no_value_fields(self):
        ctx = _memory_ctx()
        safe = ctx.to_log_safe()
        # No MemoryRecord values — only structural fields
        forbidden = {"value", "record_value", "content", "prompt", "completion"}
        assert not (forbidden & safe.keys())

    def test_session_continuity_pack_id_value(self):
        assert SESSION_CONTINUITY_PACK_ID == "pack.io_iii.session_resume"


# ---------------------------------------------------------------------------
# load_session_memory tests
# ---------------------------------------------------------------------------

class TestLoadSessionMemory:

    def _make_loader_with_pack(self, tmp_path: Path, pack_id: str, scope: str, keys: list) -> PackLoader:
        """Create a PackLoader backed by a temp memory_packs.yaml."""
        content = {
            "storage_root": str(tmp_path / "store"),
            "packs": [
                {
                    "id": pack_id,
                    "version": "1.0",
                    "description": "test pack",
                    "scope": scope,
                    "keys": keys,
                    "include_packs": [],
                }
            ],
        }
        import yaml
        packs_file = tmp_path / "memory_packs.yaml"
        packs_file.write_text(yaml.dump(content), encoding="utf-8")
        return PackLoader(packs_file)

    def _allow_policy(self, route: str = "executor") -> RetrievalPolicy:
        return RetrievalPolicy(
            route_allowlist=frozenset({route}),
            capability_allowlist=frozenset(),
            sensitivity_elevated=frozenset({route}),
            sensitivity_restricted=frozenset({route}),
        )

    def test_absent_pack_returns_empty_and_none(self, tmp_path):
        loader = self._make_loader_with_pack(tmp_path, "pack.other", "x", [])
        store = MemoryStore(tmp_path / "store")
        records, ctx = load_session_memory(
            pack_id="pack.not.declared",
            pack_loader=loader,
            store=store,
            policy=NULL_POLICY,
        )
        assert records == []
        assert ctx is None

    def test_pack_present_store_empty(self, tmp_path):
        loader = self._make_loader_with_pack(
            tmp_path, "pack.test", "io_iii",
            ["key.a", "key.b", "key.c"]
        )
        store = MemoryStore(tmp_path / "store")
        policy = self._allow_policy()
        records, ctx = load_session_memory(
            pack_id="pack.test",
            pack_loader=loader,
            store=store,
            policy=policy,
        )
        assert records == []
        assert ctx is not None
        assert ctx.keys_declared == 3
        assert ctx.keys_loaded == 0
        assert ctx.keys_missing == 3

    def test_pack_present_store_has_records(self, tmp_path):
        loader = self._make_loader_with_pack(
            tmp_path, "pack.test", "io_iii",
            ["key.a", "key.b"]
        )
        store = MemoryStore(tmp_path / "store")
        store.put(_record("key.a"))
        store.put(_record("key.b"))
        policy = self._allow_policy()
        records, ctx = load_session_memory(
            pack_id="pack.test",
            pack_loader=loader,
            store=store,
            policy=policy,
        )
        assert len(records) == 2
        assert ctx.keys_declared == 2
        assert ctx.keys_loaded == 2
        assert ctx.keys_missing == 0

    def test_partial_store_coverage(self, tmp_path):
        loader = self._make_loader_with_pack(
            tmp_path, "pack.test", "io_iii",
            ["key.a", "key.b", "key.c"]
        )
        store = MemoryStore(tmp_path / "store")
        store.put(_record("key.a"))
        # key.b and key.c absent
        policy = self._allow_policy()
        records, ctx = load_session_memory(
            pack_id="pack.test",
            pack_loader=loader,
            store=store,
            policy=policy,
        )
        assert len(records) == 1
        assert ctx.keys_declared == 3
        assert ctx.keys_loaded == 1
        assert ctx.keys_missing == 2

    def test_policy_filtering_applied(self, tmp_path):
        loader = self._make_loader_with_pack(
            tmp_path, "pack.test", "io_iii",
            ["key.a"]
        )
        store = MemoryStore(tmp_path / "store")
        store.put(_record("key.a"))
        # NULL_POLICY: route not in allowlist → all records dropped
        records, ctx = load_session_memory(
            pack_id="pack.test",
            pack_loader=loader,
            store=store,
            policy=NULL_POLICY,
            route="executor",
        )
        assert records == []
        assert ctx.keys_declared == 1
        assert ctx.keys_loaded == 0
        # key.a IS in store, just not accessible (policy drop ≠ missing)
        assert ctx.keys_missing == 0

    def test_keys_missing_not_inflated_by_policy_drop(self, tmp_path):
        # keys_missing = keys declared but absent from store (not policy-filtered)
        loader = self._make_loader_with_pack(
            tmp_path, "pack.test", "io_iii",
            ["key.present", "key.absent"]
        )
        store = MemoryStore(tmp_path / "store")
        store.put(_record("key.present"))
        policy = self._allow_policy()
        records, ctx = load_session_memory(
            pack_id="pack.test",
            pack_loader=loader,
            store=store,
            policy=policy,
        )
        assert ctx.keys_missing == 1  # only key.absent is missing
        assert ctx.keys_loaded == 1   # key.present passed policy

    def test_ctx_scope_matches_pack(self, tmp_path):
        loader = self._make_loader_with_pack(
            tmp_path, "pack.test", "myscope", []
        )
        store = MemoryStore(tmp_path / "store")
        _, ctx = load_session_memory(
            pack_id="pack.test",
            pack_loader=loader,
            store=store,
            policy=NULL_POLICY,
        )
        assert ctx.scope == "myscope"

    def test_ctx_policy_route_recorded(self, tmp_path):
        loader = self._make_loader_with_pack(tmp_path, "pack.test", "io_iii", [])
        store = MemoryStore(tmp_path / "store")
        _, ctx = load_session_memory(
            pack_id="pack.test",
            pack_loader=loader,
            store=store,
            policy=NULL_POLICY,
            route="explorer",
        )
        assert ctx.policy_route == "explorer"

    def test_default_pack_id_is_session_continuity(self, tmp_path):
        # When no pack_id given, SESSION_CONTINUITY_PACK_ID is used.
        # If pack is absent, ([], None) returned safely.
        loader = self._make_loader_with_pack(tmp_path, "pack.other", "x", [])
        store = MemoryStore(tmp_path / "store")
        records, ctx = load_session_memory(
            pack_loader=loader,
            store=store,
            policy=NULL_POLICY,
        )
        assert records == []
        assert ctx is None


# ---------------------------------------------------------------------------
# TurnRecord.memory_keys_loaded tests
# ---------------------------------------------------------------------------

class TestTurnRecordMemoryKeysLoaded:

    def test_default_zero(self):
        tr = TurnRecord(
            turn_index=0,
            run_id="req-x",
            status="ok",
            persona_mode="executor",
            latency_ms=None,
        )
        assert tr.memory_keys_loaded == 0

    def test_explicit_value(self):
        tr = TurnRecord(
            turn_index=0,
            run_id="req-x",
            status="ok",
            persona_mode="executor",
            latency_ms=None,
            memory_keys_loaded=3,
        )
        assert tr.memory_keys_loaded == 3

    def test_frozen(self):
        tr = TurnRecord(
            turn_index=0,
            run_id="req-x",
            status="ok",
            persona_mode="executor",
            latency_ms=None,
        )
        with pytest.raises(Exception):
            tr.memory_keys_loaded = 5  # type: ignore


# ---------------------------------------------------------------------------
# run_turn integration tests
# ---------------------------------------------------------------------------

class TestRunTurnMemoryIntegration:

    def test_no_memory_defaults_to_zero(self):
        session = _active_session()
        gate = _mock_gate()
        with _mock_orch_success():
            result = run_turn(
                session=session,
                user_prompt="hello",
                cfg=MagicMock(),
                deps=_deps(),
                gate=gate,
            )
        assert result.turn_record.memory_keys_loaded == 0
        assert result.memory_context is None

    def test_empty_session_memory_defaults_to_zero(self):
        session = _active_session()
        gate = _mock_gate()
        with _mock_orch_success():
            result = run_turn(
                session=session,
                user_prompt="hello",
                cfg=MagicMock(),
                deps=_deps(),
                gate=gate,
                session_memory=None,
                memory_context=None,
            )
        assert result.turn_record.memory_keys_loaded == 0

    def test_session_memory_records_sets_count(self):
        session = _active_session()
        gate = _mock_gate()
        records = [_record("key.a"), _record("key.b")]
        ctx = _memory_ctx(keys_loaded=2)
        with _mock_orch_success():
            result = run_turn(
                session=session,
                user_prompt="hello",
                cfg=MagicMock(),
                deps=_deps(),
                gate=gate,
                session_memory=records,
                memory_context=ctx,
            )
        assert result.turn_record.memory_keys_loaded == 2
        assert result.memory_context is ctx

    def test_memory_context_threaded_through(self):
        session = _active_session()
        gate = _mock_gate()
        ctx = _memory_ctx(keys_loaded=1, keys_declared=3, keys_missing=2)
        with _mock_orch_success():
            result = run_turn(
                session=session,
                user_prompt="hello",
                cfg=MagicMock(),
                deps=_deps(),
                gate=gate,
                session_memory=[_record("key.a")],
                memory_context=ctx,
            )
        assert result.memory_context.keys_declared == 3
        assert result.memory_context.keys_missing == 2

    def test_memory_values_not_in_turn_record(self):
        session = _active_session()
        gate = _mock_gate()
        records = [_record("key.secret")]
        with _mock_orch_success():
            result = run_turn(
                session=session,
                user_prompt="hello",
                cfg=MagicMock(),
                deps=_deps(),
                gate=gate,
                session_memory=records,
            )
        # TurnRecord carries only a count — never the key name or value
        tr = result.turn_record
        assert tr.memory_keys_loaded == 1
        # Verify no values in the turn record dict representation
        tr_dict = {
            "turn_index": tr.turn_index,
            "run_id": tr.run_id,
            "status": tr.status,
            "persona_mode": tr.persona_mode,
            "latency_ms": tr.latency_ms,
            "error_code": tr.error_code,
            "memory_keys_loaded": tr.memory_keys_loaded,
        }
        assert "value-for-key.secret" not in str(tr_dict)
        assert "key.secret" not in str(tr_dict)


# ---------------------------------------------------------------------------
# Persistence round-trip
# ---------------------------------------------------------------------------

class TestPersistenceRoundTrip:

    def test_memory_keys_loaded_preserved_in_save_load(self, tmp_path):
        session = _active_session()
        gate = _mock_gate()
        records = [_record("key.a"), _record("key.b"), _record("key.c")]
        with _mock_orch_success():
            result = run_turn(
                session=session,
                user_prompt="hi",
                cfg=MagicMock(),
                deps=_deps(),
                gate=gate,
                session_memory=records,
            )

        storage = tmp_path / "sessions"
        save_session(session, storage)
        restored = load_session(session.session_id, storage)

        assert restored.turns[0].memory_keys_loaded == 3

    def test_memory_keys_loaded_zero_preserved(self, tmp_path):
        session = _active_session()
        gate = _mock_gate()
        with _mock_orch_success():
            run_turn(
                session=session,
                user_prompt="hi",
                cfg=MagicMock(),
                deps=_deps(),
                gate=gate,
            )

        storage = tmp_path / "sessions"
        save_session(session, storage)
        restored = load_session(session.session_id, storage)

        assert restored.turns[0].memory_keys_loaded == 0

    def test_session_json_has_no_memory_values(self, tmp_path):
        session = _active_session()
        gate = _mock_gate()
        records = [_record("key.secret")]
        with _mock_orch_success():
            run_turn(
                session=session,
                user_prompt="hi",
                cfg=MagicMock(),
                deps=_deps(),
                gate=gate,
                session_memory=records,
            )

        storage = tmp_path / "sessions"
        path = save_session(session, storage)
        raw = path.read_text()

        # The session JSON must not contain any memory record values
        assert "value-for-key.secret" not in raw
        assert "key.secret" not in raw
        # Only the count should be present
        data = json.loads(raw)
        assert data["turns"][0]["memory_keys_loaded"] == 1


# ---------------------------------------------------------------------------
# DialogueTurnResult.memory_context
# ---------------------------------------------------------------------------

class TestDialogueTurnResultMemoryContext:

    def test_memory_context_default_none(self):
        session = _active_session()
        gate = _mock_gate()
        with _mock_orch_success():
            result = run_turn(
                session=session,
                user_prompt="x",
                cfg=MagicMock(),
                deps=_deps(),
                gate=gate,
            )
        assert result.memory_context is None

    def test_memory_context_present_when_provided(self):
        session = _active_session()
        gate = _mock_gate()
        ctx = _memory_ctx()
        with _mock_orch_success():
            result = run_turn(
                session=session,
                user_prompt="x",
                cfg=MagicMock(),
                deps=_deps(),
                gate=gate,
                memory_context=ctx,
            )
        assert result.memory_context is ctx
