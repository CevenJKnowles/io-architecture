---
id: DOC-ARCH-012
title: Phase 4 Guide — Post-Capability Architecture Layer
type: architecture
status: active
version: v0.3
canonical: true
scope: phase-4
audience: developer
created: "2026-03-06"
updated: "2026-04-03"
tags:
- io-iii
- phase-4
- architecture
roles_focus:
- executor
- challenger
provenance: io-iii-runtime-development
---

# Phase 4 Guide — Post-Capability Architecture Layer

## Purpose

Phase 4 introduces the architectural layer above capabilities while preserving all IO-III invariants.

The runtime kernel (routing, engine, context assembly, capability registry) is **frozen**. Phase 4 builds a layer *above* it, not inside it.

The purpose of this phase is to introduce **bounded orchestration as a deterministic contract layer**, not to evolve IO-III into an agent, planner, or workflow engine.

---

## Invariants that must remain true

- deterministic routing (ADR-002)
- bounded execution (ADR-009: max 1 audit pass, max 1 revision pass)
- explicit capability invocation only
- content-safe logging (no prompts or model outputs)
- no agent behaviour
- no recursion
- no dynamic routing
- route resolution is static and table-driven from declared `TaskSpec.mode`
- runtime outputs must never alter routing or step order

---

## What Phase 4 may add

- a bounded orchestration layer that composes a single execution path
- explicit task specs or runbooks that compile to one bounded run
- stricter lifecycle contracts for execution traces and session state
- per-stage execution timing in the trace
- a CLI surface for task and runbook execution

---

## What Phase 4 must not add

- autonomous tool selection
- multi-step loops without an explicit ceiling
- planner or heuristic-driven routing
- self-directed recursion
- dynamic routing based on output content
- uncontrolled multi-step orchestration
- output-driven branching between runbook steps
- open-ended workflow execution semantics

---

## Milestones

### M4.0 — Phase 4 ADR and Milestone Definition

Author ADR-012: Bounded Orchestration Layer contract.  
Define all Phase 4 milestones formally in SESSION_STATE.md.  
Update this document from draft v0.2 to active v0.3 with milestone list.  
Define Definition of Done criteria for Phase 4 completion.

---

### M4.1 — Task Specification Schema

Define a serialisable `TaskSpec` contract object with explicit inputs, mode, and optional capability list.

Properties:

- `TaskSpec` compiles to exactly one `SessionState` and one static route
- Route resolution is deterministic from declared `mode`
- Must not encode loops, conditions, planner logic, or branching semantics
- Must support stable identifiers for `task_spec_id` linkage in `SessionState`
- Must define serialisation and validation rules for YAML/JSON transport

Documentation  
DOC-RUN-006

---

### M4.2 — Single-Run Bounded Orchestration Layer

Introduce an `Orchestrator` that accepts a `TaskSpec` and executes exactly one bounded run.

Execution path:

TaskSpec  
→ routing  
→ engine  
→ context assembly / capability registry  
→ bounded execution  
→ execution trace  
→ content-safe metadata projection

Hard bound: one executor pass, one optional challenger pass (ADR-009 preserved).

Must not introduce:

- multi-step loops
- recursion
- autonomous tool selection
- runtime-output-driven routing changes

---

### M4.3 — Execution Trace Lifecycle Contracts

Define explicit lifecycle states for `ExecutionTrace`:

created → running → completed | failed

Constraints:

- Cannot transition backwards
- Cannot skip terminal states
- Invalid transitions raise hard failures
- `ExecutionTrace` remains the canonical runtime record
- `metadata.jsonl` is a content-safe projection of trace metadata only

File  
`io_iii/core/execution_trace.py`

Documentation  
DOC-RUN-005 (Execution Trace Schema) updated

---

### M4.4 — SessionState v1 Contract

Promote `SessionState` from v0 to v1 with stricter lifecycle semantics.

Changes:

- Define which fields are write-once vs mutable
- Add `task_spec_id` field to link session state to originating task spec
- Define lifecycle-safe mutation boundaries
- Write migration note from v0 to v1

Documentation  
DOC-RUN-002 (SessionState Contract) updated

---

### M4.5 — Engine Observability Groundwork

Expose structured per-stage timing in `ExecutionTrace`:

- routing_ms
- assembly_ms
- provider_ms
- capability_ms

`SessionState.latency_ms` remains total latency.

The trace stores canonical timing data.  
`metadata.jsonl` stores only the content-safe projected timing fields.

Documentation  
DOC-ARCH-006 (Execution Observability) updated

---

### M4.6 — Deterministic Failure Semantics ✓ Complete

Introduce a canonical deterministic failure model for the IO-III runtime.

Contract:

- Six stable failure categories (`RuntimeFailureKind`): `route_resolution`, `provider_execution`, `audit_challenger`, `capability`, `contract_violation`, `internal`
- Typed, content-safe failure envelope (`RuntimeFailure`): frozen dataclass carrying `kind`, `code`, `summary`, `request_id`, `task_spec_id`, `retryable`, `causal_code`
- On any engine exception, `RuntimeFailure` is attached to the original exception as `.runtime_failure`
- Original exception type is preserved on re-raise (no wrapper exception)
- Execution trace always reaches terminal `'failed'` state on exception
- `engine_run_failed` lifecycle event always emitted on the failure path
- CLI logs stable `failure.code` and `failure_kind` in metadata when available
- `retryable=True` permitted only for `PROVIDER_UNAVAILABLE`
- Content policy: `summary` and `causal_code` never carry prompt or model output text

ADR  
ADR-013 — Deterministic Failure Semantics

---

### M4.7 — Multi-Step Bounded Runbook Layer ✓ Complete

Define `Runbook` as an ordered, serialisable, finite list of `TaskSpec` steps with no branching.

ADR: ADR-014 — Bounded Runbook Layer Contract (subordinate to ADR-012)

Properties:

- Explicit step count ceiling (`RUNBOOK_MAX_STEPS = 20`)
- Each step is exactly one bounded engine execution via `orchestrator.run()`
- ADR-009 remains preserved per step
- No conditional branching between steps
- No output-driven reordering
- Termination is deterministic on step failure (no retry, no recovery)
- Runbooks exist for bounded composition only, never open workflow execution

Files:

- `io_iii/core/runbook.py` — `Runbook` schema, validation, serialisation
- `io_iii/core/runbook_runner.py` — `RunbookRunner`, `RunbookResult`, `RunbookStepOutcome`
- `tests/test_runbook_m47.py` — focused M4.7 contract tests

This milestone defines the **maximum orchestration complexity ceiling** for IO-III.

---

### M4.8 — Runbook Traceability and Metadata Correlation ✓ Complete

Add a deterministic, content-safe observability layer above the M4.7 runbook runner.
Every bounded runbook execution path is structurally reconstructable from metadata alone,
without accessing prompt or model output content.

ADR: ADR-015 — Runbook Traceability and Metadata Correlation (subordinate to ADR-014)

This is an **observability-only milestone**. It does not increase orchestration power,
add branching, retries, persistence, or any new failure taxonomy.

Contract:

- Frozen lifecycle event taxonomy (exactly six event classes — no additions without an ADR update):
  `runbook_started`, `runbook_step_started`, `runbook_step_completed`,
  `runbook_step_failed`, `runbook_completed`, `runbook_terminated`
- Deterministic, test-asserted event ordering for success and failure paths
- Frozen correlation schema: structural fields only (`runbook_id`, `request_id`,
  `task_spec_id`, `step_index`, `steps_total`, `terminated_early`, `failed_step_index`,
  `duration_ms`, `total_duration_ms`, `failure_kind`, `failure_code`)
- Per-step `duration_ms` and per-runbook `total_duration_ms` timing (integer milliseconds)
- ADR-013 `failure_kind` and `failure_code` surfaced at the runbook coordination layer
- `ExecutionTrace` remains canonical runtime truth; `RunbookMetadataProjection` is projection-only
- Attached to `RunbookResult.metadata`; existing `RunbookResult` fields unchanged
- No prompt text, model output, or free-form exception content in any event field

Files:

- `io_iii/core/runbook_runner.py` — `RunbookLifecycleEvent`, `RunbookMetadataProjection`,
  `RunbookResult.metadata` field, observability emission in `run()`
- `tests/test_runbook_m48.py` — focused M4.8 contract tests

---

### M4.9 — CLI Runbook Execution Surface ✓ Complete

Expose the already-bounded runbook execution contract through a deterministic CLI surface.

ADR: ADR-016 — CLI Runbook Execution Surface (subordinate to ADR-015)

This is a **CLI exposure milestone only**. It does not increase orchestration power,
add persistence, add replay/resume semantics, or alter any M4.7/M4.8 contract.

Command surface (frozen — no aliases, no additional flags beyond `--audit`):

```text
python -m io_iii runbook <json-file>
python -m io_iii runbook <json-file> --audit
```

Contract:

- Input boundary: JSON file only; deserialised via `Runbook.from_dict()`
- Frozen validation order: file exists → valid JSON → valid schema → execute → emit result
- Execution path: thin veneer only; delegates to `runbook_runner.run()` (never `engine.run()` directly)
- Audit passthrough: `--audit` threads to runner without adding CLI semantics
- Output: single stable JSON object (success or error); no colour, no prose, no streaming
- Failure: surfaces `failure_kind`, `failure_code`, `failed_step_index`, `terminated_early` from ADR-013 envelope
- Metadata: surfaces M4.8 `RunbookMetadataProjection` summary (`runbook_id`, `event_count`)
- Exit code: 0 on success, 1 on any failure
- Frozen non-goals: no YAML, no inline JSON, no `--from-step`/`--to-step`, no replay, no persistence

Files:

- `io_iii/cli.py` — `cmd_runbook()` and `runbook` subparser registration
- `tests/test_runbook_m49.py` — focused M4.9 CLI contract tests
- `ADR/ADR-016-cli-runbook-execution-surface.md` — governing ADR

---

### M4.10 — Replay/Resume Boundary Definition ✓ Complete

Freeze the upper architectural boundary above the M4.9 CLI runbook execution surface.

ADR: ADR-017 — Replay/Resume Boundary Definition (subordinate to ADR-016)

This is a **boundary ADR milestone only**. No code, no tests, no new CLI surface.

The M4.7–M4.9 execution stack is sealed. Replay and resume are deferred to M4.11 and
beyond, contingent on three prerequisite ADRs (ADR-018 run identity, ADR-019 checkpoint
persistence, ADR-020 replay/resume execution contract).

Key constraints frozen by this milestone:

- Replay/resume must be introduced as a separate upper layer above ADR-016
- No replay-enabling state may be retrofitted into any M4.7/M4.8/M4.9 contract
- `runbook.py`, `runbook_runner.py`, and `cli.py` must not be modified for replay
- M4.11 is code-safe only after ADR-018, ADR-019, and ADR-020 are accepted

Files:

- `ADR/ADR-017-replay-resume-boundary-definition.md` — governing ADR

---

### M4.10 (cont.) — Run Identity Contract ✓ Complete

Freeze the canonical `run_id` contract required before checkpoint persistence and
replay execution can be specified.

ADR: ADR-018 — Run Identity Contract (subordinate to ADR-017)

This is a **contract ADR only**. No code, no tests, no changes to any existing surface.

Contract frozen by this milestone:

- `run_id` is a UUIDv4 string; generated once at execution start; immutable
- `run_id` is distinct from `runbook_id` (definition identity vs. execution identity)
- Original runs: `source_run_id = null`; replay runs: `source_run_id = <parent run_id>`
- Lineage chain reconstructable via `source_run_id` trail; each link is the immediate parent
- Checkpoint records (ADR-019) must bind to `run_id` as the exclusive correlation key
- Replay invocations (ADR-020) must accept `run_id`, generate a new `run_id`, and set `source_run_id`
- Cross-runbook lineage prohibited; lineage scoped to a single `runbook_id`
- No frozen M4.7–M4.9 surface is modified

Files:

- `ADR/ADR-018-run-identity-contract.md` — governing ADR

---

### M4.10 (cont.) — Checkpoint Persistence Contract ✓ Complete

Freeze the checkpoint storage schema and lifecycle bound to deterministic run identity.

ADR: ADR-019 — Checkpoint Persistence Contract (subordinate to ADR-018)

This is a **contract ADR only**. No code, no tests, no changes to any existing surface.

Contract frozen by this milestone:

- Checkpoint is a JSON file at `<storage_root>/<run_id>.json`; one file per run
- Identity fields frozen at first write: `checkpoint_schema_version`, `run_id`, `runbook_id`, `source_run_id`, `runbook_snapshot`, `created_at`
- Progress fields updated on each write: `steps_completed`, `last_completed_step_index`, `total_steps`, `status`, `updated_at`
- Failure fields present iff `status = "failed"`: `failure_kind`, `failure_code`, `failed_step_index` (sourced from ADR-013)
- Written atomically (write-to-temp + rename) after each step terminal state
- Full replacement per write — no append; terminal state (`"completed"` or `"failed"`) is final
- Deterministic lookup: derive path from `run_id`; no index, no registry
- Five mandatory validation checks before state consumption: schema version, `run_id` binding, `runbook_id` consistency, progress consistency, failure field consistency
- No prompt text, model output, or exception messages in any field (ADR-003 content safety)
- No existing M4.7–M4.9 surface is modified

Files:

- `ADR/ADR-019-checkpoint-persistence-contract.md` — governing ADR

---

### M4.10 (cont.) — Replay/Resume Execution Contract ✓ Complete

Freeze the replay/resume execution semantics as the final M4.10 contract layer.

ADR: ADR-020 — Replay/Resume Execution Contract (subordinate to ADR-019)

This is a **contract ADR only**. No code, no tests, no changes to any existing surface.
M4.11 is now the first implementation-safe milestone.

Contract frozen by this milestone:

- Two bounded execution modes above the frozen M4.9 surface: replay (from step 0) and resume (from first incomplete step)
- Checkpoint resolved via ADR-019 §7 six-step algorithm before any execution
- Source runbook always derived from checkpoint `runbook_snapshot` — no external file
- Both modes generate new `run_id`; `source_run_id` bound to the input `run_id` (ADR-018)
- Completed runs (`status = "completed"`) can be replayed but not resumed (`RESUME_INVALID_STATE`)
- Resume starting step: `last_completed_step_index + 1` (or 0 if none completed)
- Execution through `runbook_runner.run()` unchanged — step slice passed from the replay/resume layer
- ADR-009 audit constraints apply per step; no partial audit bypass
- Three new failure codes under `contract_violation`: `CHECKPOINT_NOT_FOUND`, `CHECKPOINT_INTEGRITY_ERROR`, `RESUME_INVALID_STATE`
- CLI surface (`replay` and `resume` subcommands, `--audit` passthrough) introduced in M4.11 only
- No existing M4.7–M4.9 surface is modified

Files:

- `ADR/ADR-020-replay-resume-execution-contract.md` — governing ADR