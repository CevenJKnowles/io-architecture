---
id: ADR-015
title: Runbook Traceability and Metadata Correlation
type: adr
status: accepted
version: v1.0
canonical: true
scope: io-iii-phase-4
audience:
  - developer
  - maintainer
created: "2026-04-03"
updated: "2026-04-03"
tags:
  - io-iii
  - adr
  - phase-4
  - runbook
  - observability
  - traceability
  - metadata
roles_focus:
  - executor
  - challenger
provenance: io-iii-runtime-development
milestone: M4.8
subordinate_to: ADR-014
---

# ADR-015 — Runbook Traceability and Metadata Correlation

## Status

Accepted

## Subordination

This ADR subordinates itself entirely to **ADR-014 — Bounded Runbook Layer Contract**
and, through it, to **ADR-012 — Bounded Orchestration Layer Contract**.

Every constraint in ADR-014 and ADR-012 applies to this layer without exception.

---

## Context

M4.7 (ADR-014) introduced the bounded runbook runner. After execution, the only way
to understand what happened inside a runbook is to inspect the `RunbookResult` and
its per-step `RunbookStepOutcome` records. These carry structural outcome data but
do not provide a temporally ordered, event-based view of the execution lifecycle.

This means:

- A reviewer cannot tell whether `runbook_started` preceded `runbook_step_started`
  without parsing the outcome list.
- There is no structured record of when steps began, ended, or failed.
- Step-level timing is absent; per-step duration cannot be derived from the result.
- There is no single, ordered event stream for a complete runbook execution.

A formal observability layer is required to make every bounded runbook execution path
reconstructable from metadata alone — without accessing prompt or model output content.

---

## Milestone Scope

M4.8 is an **observability-only milestone**.

Its purpose is to make every bounded runbook execution path structurally
reconstructable from metadata alone.

M4.8 **must not**:

- increase orchestration power
- introduce branching
- add retries
- add nested runbooks
- add persistence
- add resume or replay semantics
- add CLI runbook UX
- widen `TaskSpec`
- widen routing semantics
- widen engine semantics
- bypass orchestrator boundaries
- invent new failure taxonomies

---

## Decision

IO-III will introduce a deterministic, content-safe **runbook observability layer**
above the existing runbook runner.

This layer is implemented entirely within `io_iii/core/runbook_runner.py` as an
additive metadata projection. It does not alter the semantic behaviour of M4.7, M4.6,
or any lower runtime contract.

### 1. Canonical Truth Surfaces

`ExecutionTrace` remains the **canonical runtime truth surface** per ADR-003 and M4.3.

The runbook metadata projection (`RunbookMetadataProjection`) is
**projection-only**. It provides an ordered, structural event log for external
observability. It does not drive execution, does not alter routing, and cannot be used
to resume or replay a run.

The relationship is one-way:

```
ExecutionTrace (canonical truth)  →  RunbookMetadataProjection (read-only projection)
```

Inverting this relationship — making the projection influence execution — is
forbidden.

### 2. Frozen Lifecycle Event Taxonomy

Exactly six lifecycle event classes are defined. This taxonomy is frozen. New event
classes require a future ADR update.

| Event | Emitted When |
|-------|--------------|
| `runbook_started` | Immediately before step iteration begins |
| `runbook_step_started` | Immediately before each step's `orchestrator.run()` call |
| `runbook_step_completed` | Immediately after a successful step |
| `runbook_step_failed` | Immediately after a step raises an exception |
| `runbook_completed` | After all steps complete without failure |
| `runbook_terminated` | After a step failure causes early termination |

No additional event classes may be introduced without a governed ADR update.

### 3. Frozen Correlation Schema

Every `RunbookLifecycleEvent` carries only the following structural fields where
applicable. No field may carry prompt text, model output, or free-form exception
messages.

| Field | Type | Description |
|-------|------|-------------|
| `event` | `str` | One of the six frozen taxonomy values |
| `runbook_id` | `str` | Correlation to the originating `Runbook` |
| `steps_total` | `int` | Declared step count at construction time |
| `request_id` | `Optional[str]` | Per-step `SessionState` linkage when available |
| `task_spec_id` | `Optional[str]` | Step-level `TaskSpec` correlation identifier |
| `step_index` | `Optional[int]` | Zero-based step position within the runbook |
| `terminated_early` | `Optional[bool]` | True if runbook terminated before completion |
| `failed_step_index` | `Optional[int]` | Index of the failing step, if any |
| `duration_ms` | `Optional[int]` | Step-level wall-clock duration in milliseconds |
| `total_duration_ms` | `Optional[int]` | Runbook-level wall-clock duration in milliseconds |
| `failure_kind` | `Optional[str]` | `RuntimeFailureKind` value from ADR-013, if applicable |
| `failure_code` | `Optional[str]` | Stable failure code from ADR-013, if applicable |

Fields not applicable to a given event are set to `None`.

Content policy applies to all fields. See Section 8.

### 4. Deterministic Event Ordering

Event ordering is deterministic and contractual.

**Success path** (N steps, all succeed):

```
runbook_started
→ runbook_step_started   (step 0)
→ runbook_step_completed (step 0)
→ runbook_step_started   (step 1)
→ runbook_step_completed (step 1)
→ ...
→ runbook_step_started   (step N-1)
→ runbook_step_completed (step N-1)
→ runbook_completed
```

**Failure path** (step K fails):

```
runbook_started
→ runbook_step_started   (step 0)
→ runbook_step_completed (step 0)
→ ...
→ runbook_step_started   (step K)
→ runbook_step_failed    (step K)
→ runbook_terminated
```

No events are emitted after `runbook_terminated`. No events are emitted after
`runbook_completed`.

This ordering is test-asserted. Any implementation that emits events in a different
order fails the M4.8 contract.

### 5. Timing Contract

Timing is present in M4.8 as bounded numeric fields only.

- `duration_ms` — step-level wall-clock duration, emitted on `runbook_step_completed`
  and `runbook_step_failed`
- `total_duration_ms` — runbook-level wall-clock duration, emitted on
  `runbook_completed` and `runbook_terminated`

Timing is measured using `time.monotonic_ns()` and reported as an integer number
of milliseconds (nanoseconds `// 1_000_000`).

No richer profiling. No token statistics. No provider payload detail.

### 6. Failure Semantics Reuse

ADR-013 `RuntimeFailure` semantics are reused exactly as-is. No runbook-specific
failure taxonomy is introduced.

Where a step raises an exception that carries a `.runtime_failure` envelope (ADR-013),
the following fields from that envelope are surfaced in the metadata projection:

- `failure_kind` ← `RuntimeFailure.kind.value`
- `failure_code` ← `RuntimeFailure.code`

Where no `.runtime_failure` envelope is present, both fields are `None`.

The projection never classifies failures itself. It consumes ADR-013 classification
outputs only.

### 7. Metadata Projection Structure

`RunbookMetadataProjection` is a non-frozen dataclass carrying:

- `runbook_id` — correlation to the originating `Runbook`
- `events` — ordered `List[RunbookLifecycleEvent]` in emission order

It is attached to `RunbookResult` as an optional `metadata` field. All existing
`RunbookResult` fields remain unchanged; `metadata` defaults to `None` for
backward compatibility.

`RunbookLifecycleEvent` is a frozen dataclass. Events are immutable once emitted.

### 8. Content Safety

No field in `RunbookLifecycleEvent` or `RunbookMetadataProjection` may carry:

- prompt text
- model output
- capability payload content
- free-form exception messages
- stack traces

`failure_kind` and `failure_code` carry only structured, stable identifiers from
ADR-013. They are not derived from free-form exception message strings.

`task_spec_id` and `request_id` are machine-generated identifiers (UUID-derived).
They carry no user content.

### 9. Additive Contract

The observability layer is entirely additive.

It must not:

- alter the return value semantics of `RunbookResult` for existing fields
- change the exception propagation behaviour of the runner
- add conditional logic to the execution path based on event state
- call `engine.run()` directly or bypass the orchestrator
- change step ordering or step count
- affect the `terminated_early`, `failed_step_index`, or `steps_completed` values
  already governed by ADR-014

---

## Scope Boundary

This ADR covers:

- the `RunbookLifecycleEvent` schema and frozen content policy
- the `RunbookMetadataProjection` container structure
- the six-event frozen lifecycle taxonomy
- deterministic event ordering contract
- timing field contract (`duration_ms`, `total_duration_ms`)
- reuse of ADR-013 failure semantics in projection output
- `RunbookResult.metadata` field addition (additive, default `None`)
- focused M4.8 test strategy and verification expectations
- relationship to M4.9 and M4.10 boundaries

This ADR does **not** cover:

- writing events to `metadata.jsonl` or any persistent store (M4.9 boundary)
- structured log emission to external systems
- CLI surfaces for runbook traceability
- replay or resumption from metadata
- cross-run correlation or aggregation
- async event emission
- event filtering or sampling

---

## Relationship to M4.9 and M4.10

**M4.9 boundary**: `metadata.jsonl` persistence of runbook lifecycle events is
explicitly deferred to M4.9. M4.8 attaches the projection to `RunbookResult`; M4.9
may consume it and write it to disk. M4.8 does not write any files.

**M4.10 boundary**: Cross-run correlation, aggregation, dashboards, or any
structured analysis layer are deferred beyond M4.10. M4.8 provides the structural
foundation only.

The M4.8 projection is the source-of-truth input for any downstream persistence
or analysis layer introduced in M4.9 or later. Its schema must not be changed
without a new ADR.

---

## Implementation Order

1. Add `RunbookLifecycleEvent` frozen dataclass to `io_iii/core/runbook_runner.py`.
2. Add `RunbookMetadataProjection` dataclass to `io_iii/core/runbook_runner.py`.
3. Add `metadata: Optional[RunbookMetadataProjection] = None` field to `RunbookResult`.
4. Modify `run()` to build and populate the projection during execution.
5. Write focused M4.8 contract tests in `tests/test_runbook_m48.py`.
6. Update `ADR/ADR-015` (this document).
7. Update `docs/architecture/DOC-ARCH-012-phase-4-guide.md` — mark M4.7 complete, add M4.8.
8. Update `SESSION_STATE.md` — reflect M4.7 complete, M4.8 complete.
9. Update `ADR/README.md` — add ADR-015 entry.

---

## Verification Expectations

The following must be provable through the M4.8 test suite:

1. Lifecycle event presence — all expected events are emitted on success and failure paths.
2. Lifecycle event ordering — event sequence matches the deterministic contract exactly.
3. Success path correctness — `runbook_completed` is the final event; no extra events.
4. Failure path correctness — `runbook_terminated` is the final event; no extra events.
5. No extra events after terminal failure — emission stops at `runbook_terminated`.
6. Correlation field correctness — `runbook_id`, `task_spec_id`, `step_index`, `steps_total` match.
7. Timing field presence and sanity — `duration_ms` and `total_duration_ms` are non-negative integers.
8. Failure propagation consistency — `failure_kind` and `failure_code` match ADR-013 envelope.
9. No prompt/model-output leakage — event fields contain no content-bearing strings.
10. No regression to M4.7 boundedness guarantees — all M4.7 tests remain passing.

---

## Constraints

- **Taxonomy is frozen**: no event outside the six defined classes may be emitted.
- **Schema is frozen**: no content-bearing field may be added to `RunbookLifecycleEvent`.
- **Projection is read-only**: events never feed back into execution decisions.
- **Timing is bounded**: only `duration_ms` (per step) and `total_duration_ms` (per runbook).
- **Failure fields are structural**: `failure_kind` and `failure_code` only; no message text.
- **Backward compatibility**: `RunbookResult.metadata` defaults to `None`; existing callers unaffected.

---

## Consequences

### Positive

- Every bounded runbook execution path is now reconstructable from metadata alone.
- Lifecycle event ordering is deterministic and test-asserted.
- Step-level and runbook-level timing is available without requiring trace inspection.
- ADR-013 failure information surfaces at the runbook coordination layer.
- Foundation is in place for M4.9 persistence without further schema changes.

### Negative

- `run()` carries additional timing and event-emission logic; adds minor overhead.
- `RunbookResult` has a new `metadata` field — consumers must tolerate additive fields.

### Neutral

- Projection is not persisted in M4.8 (M4.9 scope).
- Projection does not replace `ExecutionTrace`; both coexist.

---

## Alternatives Considered

### 1. Use a separate observer/callback pattern

Rejected. A callback-based emission pattern adds interface surface, parameter coupling,
and runtime branching based on observer presence. The additive inline approach is
simpler, test-assertable, and requires no new interfaces.

### 2. Emit events to metadata.jsonl directly from the runner

Rejected. File I/O in the runner would cross a concern boundary (coordination vs
persistence) and introduce side effects that are harder to test. Persistence belongs
in M4.9. The runner produces the projection; a downstream layer persists it.

### 3. Add runbook lifecycle events to the existing EngineObservabilityLog

Rejected. The engine observability log (M4.5) operates at the single-step engine
level. Runbook-level lifecycle events are a coordination-layer concern. Mixing these
would violate the layer boundary between the engine and the runbook runner.

### 4. Use structured logging (e.g., logging.getLogger) to emit events

Rejected. Structured logging introduces environment coupling (log handlers, formatters,
file paths) and makes test assertion harder. Attaching the projection to `RunbookResult`
keeps it deterministic, fully testable, and decoupled from I/O infrastructure.

---

## Relationship to Other ADRs

- **ADR-009** — per-step bounded execution bounds. Unaffected by this ADR.
- **ADR-012** — orchestration layer contract. This ADR adds observation above it.
- **ADR-013** — failure semantics. `failure_kind` and `failure_code` reuse these exactly.
- **ADR-014** — bounded runbook layer. This ADR adds observability above it.
- **ADR-015** (this document) — runbook traceability and metadata correlation.

---

## Decision Summary

IO-III will adopt a deterministic runbook observability layer in Phase 4 M4.8.

This layer will:

- emit exactly six frozen lifecycle event classes in deterministic order
- carry only structural, content-safe correlation fields
- attach per-step `duration_ms` and per-runbook `total_duration_ms` timing
- surface ADR-013 `failure_kind` and `failure_code` at the runbook coordination layer
- attach the ordered projection to `RunbookResult.metadata`
- remain projection-only — `ExecutionTrace` remains canonical runtime truth
- add no orchestration power, no branching, no persistence, no new failure taxonomy

A reviewer must be able to reconstruct any bounded runbook lifecycle path from the
`RunbookMetadataProjection` alone, without accessing prompt or model output content.