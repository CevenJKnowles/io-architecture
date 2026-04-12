"""
test_memory_injection_m64.py — Phase 6 M6.4 memory injection tests (ADR-022 §5).

Verifies:

  Unit — ExecutionContext.memory field
  - memory defaults to empty tuple when not provided
  - memory field accepts tuple of MemoryRecord instances
  - ExecutionContext is frozen (memory field cannot be reassigned)

  Unit — assemble_context without memory
  - no '=== Memory ===' section in system_prompt when memory absent
  - no '=== Memory ===' section when memory is empty list
  - assembly_metadata.memory_records_count == 0 when no memory
  - assembly_metadata.memory_total_chars == 0 when no memory
  - assembly_metadata.memory_keys_released == [] when no memory

  Unit — assemble_context with memory
  - system_prompt contains '=== Memory ===' when records provided
  - system_prompt contains record key identifier
  - system_prompt contains record value (content-plane injection)
  - records appear in declaration order in system_prompt
  - prompt_hash differs when memory differs (same other inputs)
  - assembly_metadata.memory_records_count matches injected count
  - assembly_metadata.memory_total_chars matches sum of value lengths
  - assembly_metadata.memory_keys_released contains scope/key identifiers

  Unit — budget enforcement (_select_bounded_memory)
  - all records included when total chars within budget
  - record exceeding budget is dropped; prior records kept
  - zero budget drops all records
  - exactly budget-filling record is included (boundary)
  - custom memory_budget_chars respected end-to-end in assemble_context
  - budget overflow drops tail records silently (no error)

  Unit — content safety
  - assembly_metadata.memory_keys_released contains no record values
  - assembly_metadata never contains a key named 'value'
  - memory section is present in system_prompt (content-plane); not in metadata
"""
from __future__ import annotations

from io_iii.core.context_assembly import (
    _DEFAULT_MEMORY_BUDGET_CHARS,
    _select_bounded_memory,
    assemble_context,
)
from io_iii.core.execution_context import ExecutionContext
from io_iii.core.session_state import AuditGateState, RouteInfo, SessionState
from io_iii.memory.store import (
    SENSITIVITY_STANDARD,
    MemoryRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state() -> SessionState:
    return SessionState(
        request_id="20260412T000000Z-test",
        started_at_ms=0,
        mode="executor",
        config_dir="./architecture/runtime/config",
        route=RouteInfo(
            mode="executor",
            primary_target="executor",
            secondary_target=None,
            selected_target="executor",
            selected_provider="null",
            fallback_used=False,
            fallback_reason=None,
            boundaries={"single_voice_output": True},
        ),
        audit=AuditGateState(audit_enabled=False, audit_passes=0, revision_passes=0),
        status="ok",
        provider="null",
        model=None,
        route_id="executor",
        persona_contract_version="0.2.0",
        persona_id="io-ii:v1.4.2",
        logging_policy={"content": "disabled"},
    )


def _make_record(key: str, value: str = "test-value", scope: str = "test") -> MemoryRecord:
    return MemoryRecord(
        key=key,
        scope=scope,
        value=value,
        version=1,
        provenance="human",
        created_at="2026-04-12T00:00:00Z",
        updated_at="2026-04-12T00:00:00Z",
        sensitivity=SENSITIVITY_STANDARD,
    )


def _assemble(
    memory=None,
    memory_budget_chars: int = _DEFAULT_MEMORY_BUDGET_CHARS,
):
    return assemble_context(
        session_state=_make_state(),
        user_prompt="Hello.",
        persona_contract="Be precise.",
        memory=memory,
        memory_budget_chars=memory_budget_chars,
    )


# ---------------------------------------------------------------------------
# ExecutionContext.memory field
# ---------------------------------------------------------------------------

def test_execution_context_memory_defaults_to_empty_tuple() -> None:
    from io_iii.core.context_assembly import AssembledContext
    ctx = ExecutionContext(
        cfg=None,
        session_state=_make_state(),
        provider=None,
        route=None,
        prompt_hash=None,
        assembled_context=None,
    )
    assert ctx.memory == ()


def test_execution_context_memory_accepts_records() -> None:
    from io_iii.core.context_assembly import AssembledContext
    records = (_make_record("k1"), _make_record("k2"))
    ctx = ExecutionContext(
        cfg=None,
        session_state=_make_state(),
        provider=None,
        route=None,
        prompt_hash=None,
        assembled_context=None,
        memory=records,
    )
    assert ctx.memory == records
    assert len(ctx.memory) == 2


def test_execution_context_memory_field_is_frozen() -> None:
    import pytest
    ctx = ExecutionContext(
        cfg=None,
        session_state=_make_state(),
        provider=None,
        route=None,
        prompt_hash=None,
        assembled_context=None,
    )
    with pytest.raises((AttributeError, TypeError)):
        ctx.memory = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# assemble_context — no memory
# ---------------------------------------------------------------------------

def test_no_memory_section_when_memory_absent() -> None:
    ctx = _assemble(memory=None)
    assert "=== Memory ===" not in ctx.system_prompt


def test_no_memory_section_when_memory_empty_list() -> None:
    ctx = _assemble(memory=[])
    assert "=== Memory ===" not in ctx.system_prompt


def test_metadata_memory_records_count_zero_when_no_memory() -> None:
    ctx = _assemble(memory=None)
    assert ctx.assembly_metadata["memory_records_count"] == 0


def test_metadata_memory_total_chars_zero_when_no_memory() -> None:
    ctx = _assemble(memory=None)
    assert ctx.assembly_metadata["memory_total_chars"] == 0


def test_metadata_memory_keys_released_empty_when_no_memory() -> None:
    ctx = _assemble(memory=None)
    assert ctx.assembly_metadata["memory_keys_released"] == []


# ---------------------------------------------------------------------------
# assemble_context — with memory
# ---------------------------------------------------------------------------

def test_memory_section_present_when_records_provided() -> None:
    ctx = _assemble(memory=[_make_record("note")])
    assert "=== Memory ===" in ctx.system_prompt


def test_memory_section_contains_record_key_identifier() -> None:
    ctx = _assemble(memory=[_make_record("my-note", scope="test")])
    assert "test/my-note" in ctx.system_prompt


def test_memory_section_contains_record_value() -> None:
    ctx = _assemble(memory=[_make_record("k", value="important context here")])
    assert "important context here" in ctx.system_prompt


def test_memory_records_appear_in_declaration_order() -> None:
    records = [
        _make_record("alpha", value="AAA"),
        _make_record("beta", value="BBB"),
        _make_record("gamma", value="CCC"),
    ]
    ctx = _assemble(memory=records)
    pos_a = ctx.system_prompt.index("test/alpha")
    pos_b = ctx.system_prompt.index("test/beta")
    pos_c = ctx.system_prompt.index("test/gamma")
    assert pos_a < pos_b < pos_c


def test_prompt_hash_differs_when_memory_differs() -> None:
    ctx_no_mem = _assemble(memory=None)
    ctx_with_mem = _assemble(memory=[_make_record("k", value="context")])
    assert ctx_no_mem.prompt_hash != ctx_with_mem.prompt_hash


def test_prompt_hash_differs_between_different_memory_records() -> None:
    ctx_a = _assemble(memory=[_make_record("k", value="value-A")])
    ctx_b = _assemble(memory=[_make_record("k", value="value-B")])
    assert ctx_a.prompt_hash != ctx_b.prompt_hash


def test_metadata_memory_records_count_matches_injected() -> None:
    records = [_make_record("r1"), _make_record("r2"), _make_record("r3")]
    ctx = _assemble(memory=records)
    assert ctx.assembly_metadata["memory_records_count"] == 3


def test_metadata_memory_total_chars_matches_value_sum() -> None:
    records = [
        _make_record("k1", value="abc"),    # 3
        _make_record("k2", value="de"),     # 2
    ]
    ctx = _assemble(memory=records)
    assert ctx.assembly_metadata["memory_total_chars"] == 5


def test_metadata_memory_keys_released_contains_identifiers() -> None:
    records = [
        _make_record("note", scope="io_iii"),
        _make_record("ctx", scope="test"),
    ]
    ctx = _assemble(memory=records)
    assert ctx.assembly_metadata["memory_keys_released"] == ["io_iii/note", "test/ctx"]


# ---------------------------------------------------------------------------
# _select_bounded_memory — budget enforcement
# ---------------------------------------------------------------------------

def test_select_bounded_all_within_budget() -> None:
    records = [_make_record("a", value="xx"), _make_record("b", value="yy")]
    result = _select_bounded_memory(records, budget_chars=100)
    assert [r.key for r in result] == ["a", "b"]


def test_select_bounded_drops_record_exceeding_budget() -> None:
    records = [
        _make_record("a", value="x" * 10),
        _make_record("b", value="y" * 10),  # would push total to 20
    ]
    result = _select_bounded_memory(records, budget_chars=15)
    assert [r.key for r in result] == ["a"]


def test_select_bounded_zero_budget_drops_all() -> None:
    records = [_make_record("a", value="x")]
    result = _select_bounded_memory(records, budget_chars=0)
    assert result == []


def test_select_bounded_exactly_budget_fills_is_included() -> None:
    records = [_make_record("a", value="x" * 10)]
    result = _select_bounded_memory(records, budget_chars=10)
    assert len(result) == 1
    assert result[0].key == "a"


def test_select_bounded_one_over_budget_drops_that_record() -> None:
    records = [_make_record("a", value="x" * 11)]
    result = _select_bounded_memory(records, budget_chars=10)
    assert result == []


def test_select_bounded_empty_input_returns_empty() -> None:
    assert _select_bounded_memory([], budget_chars=100) == []


def test_custom_budget_respected_in_assemble_context() -> None:
    records = [
        _make_record("short", value="x" * 5),
        _make_record("long", value="y" * 100),
    ]
    ctx = _assemble(memory=records, memory_budget_chars=20)
    assert ctx.assembly_metadata["memory_records_count"] == 1
    assert "test/short" in ctx.system_prompt
    assert "test/long" not in ctx.system_prompt


def test_budget_overflow_dropped_silently_no_error() -> None:
    records = [_make_record(f"k{i}", value="x" * 100) for i in range(10)]
    ctx = _assemble(memory=records, memory_budget_chars=50)
    # Should not raise; only first record fits
    assert ctx.assembly_metadata["memory_records_count"] <= len(records)


# ---------------------------------------------------------------------------
# Content safety
# ---------------------------------------------------------------------------

def test_metadata_keys_released_contains_no_record_values() -> None:
    records = [_make_record("k", value="SECRET_VALUE")]
    ctx = _assemble(memory=records)
    for identifier in ctx.assembly_metadata["memory_keys_released"]:
        assert "SECRET_VALUE" not in identifier


def test_metadata_has_no_value_key_for_memory_records() -> None:
    records = [_make_record("k", value="some content")]
    ctx = _assemble(memory=records)
    # The assembly_metadata dict must not contain a key named 'value'
    assert "value" not in ctx.assembly_metadata


def test_metadata_memory_total_chars_is_int_not_content() -> None:
    records = [_make_record("k", value="hello world")]
    ctx = _assemble(memory=records)
    # total_chars must be a plain integer, not the string content itself
    assert isinstance(ctx.assembly_metadata["memory_total_chars"], int)
    assert ctx.assembly_metadata["memory_total_chars"] == 11
