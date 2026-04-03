---
id: ADR-020
title: Replay/Resume Execution Contract
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
  - replay
  - resume
  - execution
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M4.10
subordinate_to: ADR-019
---

# ADR-020 — Replay/Resume Execution Contract

## Status

Accepted

## Subordination

This ADR subordinates itself entirely to **ADR-019 — Checkpoint Persistence Contract** and,
through it, to **ADR-018**, **ADR-017**, **ADR-016**, **ADR-015**, **ADR-014**, and **ADR-012**.

No constraint in any of those ADRs is loosened by this document. This ADR defines only
how the replay/resume layer consumes checkpoint state, generates lineage, and executes
within the bounds established by the frozen M4.7–M4.9 stack. It does not implement any
runtime behaviour.

---

## Context

ADR-017 §5.3 required this ADR as the final prerequisite before M4.11 can begin:

> "The execution semantics of replay and resume, including step-index anchoring, partial
> execution, and the relationship to the bounded runner, must be formalised in a separate
> ADR before any implementation."

ADR-018 §5.2 constrains the invocation contract:

> "Any replay invocation must: accept a `run_id` as explicit input identifying the run to
> replay; resolve the checkpoint record by that `run_id`; generate a new `run_id` for the
> replay execution; bind `source_run_id` of the new run to the input `run_id`."

ADR-019 §7 defines the six-step lookup algorithm that this contract must use before consuming
any checkpoint state. ADR-019 §9 explicitly deferred to this ADR: step-index anchoring,
behaviour on checkpoint status, CLI flags, and failure semantics specific to replay/resume.

This ADR closes the final contract gap and makes M4.11 the first implementation-safe
milestone.

---

## Decision

IO-III introduces two distinct execution modes above the frozen M4.9 surface: **replay**
and **resume**. Both modes consume checkpoint state via the ADR-019 §7 lookup algorithm,
generate a new `run_id`, and bind lineage through `source_run_id`. Both execute strictly
through the existing bounded runner — `runbook_runner.run()` — without modifying it.
Replay re-executes the full runbook from step 0. Resume continues from the first
incomplete step derived from the parent checkpoint.

---

## 1. Definitions

### 1.1 Replay

A **replay** is a re-execution of a runbook from step 0, driven by a prior run's
checkpoint. It uses the `runbook_snapshot` from the parent checkpoint as the runbook
definition. It generates a new `run_id` and sets `source_run_id` to the input `run_id`.
The source checkpoint status may be any value: a completed, failed, or in-progress run
may all be replayed.

### 1.2 Resume

A **resume** is a continuation of a prior run from the first incomplete step. It uses the
`runbook_snapshot` from the parent checkpoint as the runbook definition. It generates a
new `run_id` and sets `source_run_id` to the input `run_id`. The source checkpoint status
must be `"in_progress"` or `"failed"` — a completed run has no incomplete steps and cannot
be resumed.

### 1.3 Source Run

The **source run** is the prior execution identified by the input `run_id`. The source
checkpoint is located by that `run_id` and is treated as read-only throughout replay/resume.
The source checkpoint is never modified by this layer.

---

## 2. Checkpoint Resolution and Validation

Both replay and resume begin with the same checkpoint resolution sequence. This sequence
is mandatory before any execution or lineage binding.

### 2.1 Resolution algorithm

Apply the ADR-019 §7 six-step lookup algorithm in full:

1. Derive the file path: `<storage_root>/<run_id>.json`
2. Check existence — if absent, raise `CHECKPOINT_NOT_FOUND` (§6.2)
3. Read and parse JSON — if unparseable, raise `CHECKPOINT_INTEGRITY_ERROR` (§6.2)
4. Validate `checkpoint_schema_version = "1.0"` — mismatch raises `CHECKPOINT_INTEGRITY_ERROR`
5. Validate `run_id` in file matches the requested `run_id` — mismatch raises `CHECKPOINT_INTEGRITY_ERROR`
6. Validate `runbook_id` in file matches `runbook_id` in `runbook_snapshot` — mismatch raises
   `CHECKPOINT_INTEGRITY_ERROR`

Additionally, apply the ADR-019 §8 integrity checks before consuming progress or failure fields:

- §8.1 schema validity — already covered by step 3 above
- §8.2 identity consistency — already covered by steps 5–6 above
- §8.3 progress consistency (`last_completed_step_index` vs. `steps_completed`) — hard error on
  inconsistency → `CHECKPOINT_INTEGRITY_ERROR`
- §8.4 failure consistency (failure fields required when `status = "failed"`) — hard error on
  inconsistency → `CHECKPOINT_INTEGRITY_ERROR`
- §8.5 no partial state recovery — if any check fails, stop; do not attempt to extract state

### 2.2 Source runbook

The runbook definition for execution is always extracted from the validated checkpoint's
`runbook_snapshot`. No external runbook file is loaded. This preserves the exact runbook
definition that the source run executed against.

---

## 3. Starting-Point Selection Rules

### 3.1 Replay starting point

Replay always starts from step index `0`, regardless of the source checkpoint's progress or
status. The full runbook is re-executed.

### 3.2 Resume starting point

Resume starts from the first incomplete step in the source run. The starting step index
is derived as follows:

- If `last_completed_step_index` is `null` (zero steps completed): starting step index = `0`
- If `last_completed_step_index` is an integer `N`: starting step index = `N + 1`

This means:

| Source checkpoint state | Resume starting step |
|---|---|
| `status = "in_progress"`, `steps_completed = 0` | step 0 (first step failed before completion or is mid-execution) |
| `status = "in_progress"`, `steps_completed = N` | step N+1 |
| `status = "failed"`, `failed_step_index = F` | step F (the step that failed is re-attempted) |

For a `"failed"` checkpoint: `failed_step_index` equals `last_completed_step_index + 1` by
the ADR-019 §8.3/8.4 consistency rules, so both derivations produce the same result.

### 3.3 Completed run constraint

A source checkpoint with `status = "completed"` cannot be resumed. Attempting to resume a
completed run raises `RESUME_INVALID_STATE` (§6.2) without loading or executing any step.
Replay of a completed run is permitted.

---

## 4. Lineage Behaviour

### 4.1 Identity generation

Both replay and resume generate a new `run_id` (UUIDv4, per ADR-018 §1.2) at the start of
the new execution — before any step runs, before any checkpoint is written, and before any
lifecycle event is emitted. The new `run_id` is immutable for the lifetime of the new run.

### 4.2 Source binding

The new run's `source_run_id` is set to the input `run_id` (the identifier of the source run,
per ADR-018 §3.2). This binding is immutable and is present in the new run's every checkpoint
write.

### 4.3 Source checkpoint immutability

The source checkpoint is read-only. The replay/resume layer must not write to, rename,
or delete the source checkpoint file. The source checkpoint continues to represent the source
run exclusively.

### 4.4 Lineage chain

If a replay or resume run is itself later replayed or resumed, the chain extends:

```
original_run (source_run_id = null)
  ↓
replay_1 (source_run_id = original_run.run_id)
  ↓
resume_1 (source_run_id = replay_1.run_id)
```

Each link points to the immediate parent only (ADR-018 §3.3). Full chain traversal is an
audit operation; no component is required to traverse it at execution time.

### 4.5 Lineage isolation

`source_run_id` must reference a run produced by the same `runbook_id`. Cross-runbook
lineage is prohibited (ADR-017 §6, ADR-018 §3.4).

---

## 5. Bounded Execution Guarantees

### 5.1 Execution path

Both replay and resume execute exclusively through `runbook_runner.run()`. No replay or
resume logic is added to `runbook_runner.py`, `runbook.py`, or any lower-level component.
The replay/resume layer is responsible for determining the start index and slicing the
runbook step list before passing it to the runner.

### 5.2 Step ceiling

The total steps passed to `runbook_runner.run()` must not exceed `RUNBOOK_MAX_STEPS`
(ADR-014). For a resume, only the remaining steps (from the starting step index to the end)
are passed to the runner. The step count for this call is:
`total_steps - start_step_index`. This value is always ≤ the original runbook's step count
and therefore ≤ `RUNBOOK_MAX_STEPS`.

### 5.3 Per-step bounds

ADR-009 audit constraints apply to every step in a replay or resume run identically to
a first-run execution: max 1 executor pass, max 1 challenger pass per step. No partial
audit bypass is permitted (ADR-017 §6).

### 5.4 No loops or autonomous retry

Replay and resume are single-pass bounded executions. There is no loop, no automatic
retry on failure, and no planner behaviour. A failure in any step terminates the
replay/resume run at that step, writes a terminal checkpoint, and exits.

---

## 6. Deterministic Failure Semantics

### 6.1 Failure model

All failures follow the ADR-013 `RuntimeFailure` contract: typed, content-safe failure
envelope with `kind`, `code`, `summary`, `request_id`, `retryable`, and `causal_code`.
No prompt text, model output, exception messages, or stack traces appear in any failure
field.

### 6.2 Replay/resume-specific failure codes

| Code | Kind | Condition |
|---|---|---|
| `CHECKPOINT_NOT_FOUND` | `contract_violation` | Checkpoint file absent for the requested `run_id` |
| `CHECKPOINT_INTEGRITY_ERROR` | `contract_violation` | Any ADR-019 §7/§8 validation check fails |
| `RESUME_INVALID_STATE` | `contract_violation` | Source checkpoint `status = "completed"` — no steps to resume |

All three codes are `retryable = False`. No `CHECKPOINT_NOT_FOUND` or `CHECKPOINT_INTEGRITY_ERROR`
is retryable: the underlying data state will not change without explicit user action.

### 6.3 Step-level failures during replay/resume

A step failure during execution uses the existing ADR-013 `RuntimeFailureKind` taxonomy
unchanged. The failure is recorded in the new run's checkpoint at the failed step index
and the run exits with a terminal `"failed"` status. The source checkpoint is not modified.

### 6.4 Failure surface

Replay/resume failure is reported to the CLI as the same stable JSON object defined in
§8.2, carrying `failure_kind`, `failure_code`, and — for step failures — `failed_step_index`
and `terminated_early`. Exit code is `1` on any failure.

---

## 7. Checkpoint Continuity for Replay/Resume Runs

### 7.1 New run checkpoint

Both replay and resume write checkpoints under the new `run_id` (not the source `run_id`).
The checkpoint lifecycle follows ADR-019 §3 in full: written atomically after each step
reaches a terminal state, full replacement per write.

### 7.2 Checkpoint identity for a resume run

A resume run's checkpoint carries:

- `run_id`: the newly generated UUID for this resume execution
- `source_run_id`: the input `run_id` (the source run's identifier)
- `runbook_id`: the same `runbook_id` as the source run (from `runbook_snapshot`)
- `runbook_snapshot`: full `Runbook.to_dict()` — the complete runbook, not a slice
- `steps_completed`: count of steps completed in this resume run only (does not include
  steps inherited from the source run)
- `last_completed_step_index`: absolute step index within the full runbook of the last
  successfully completed step in this resume run
- `total_steps`: total steps in the full runbook (from `runbook_snapshot`)

The full execution picture for a resumed runbook is reconstructable by joining the source
checkpoint's progress record with the resume run's progress record via `source_run_id`.
This is an audit capability; no component is required to join them at runtime.

### 7.3 Checkpoint continuity invariant

After a successful resume, the union of `[0, source.last_completed_step_index]` and
`[start_step_index, resume.last_completed_step_index]` must cover `[0, total_steps - 1]`
without gaps. The implementation is responsible for maintaining this invariant; the ADR
records it as a correctness requirement.

---

## 8. CLI Surface

### 8.1 Commands

Two new top-level subcommands are introduced in M4.11 (not in M4.10):

```text
python -m io_iii replay <run_id>
python -m io_iii replay <run_id> --audit

python -m io_iii resume <run_id>
python -m io_iii resume <run_id> --audit
```

`--audit` threads to the runner identically to the M4.9 `runbook --audit` flag (ADR-016 §6).
No other flags are introduced. Frozen non-goals: no `--from-step`, no `--to-step`, no
`--dry-run`, no `--force`.

These commands do not modify `io_iii/cli.py`'s existing `runbook` subcommand surface.
They introduce a new surface above it.

### 8.2 Output contract

Output is a single stable JSON object. No colour, no prose, no streaming.

Success fields:

| Field | Type | Description |
|---|---|---|
| `status` | `"success"` | Terminal success |
| `run_id` | string | New `run_id` for this execution |
| `source_run_id` | string | Input `run_id` (the source run) |
| `runbook_id` | string | Runbook definition identifier |
| `steps_completed` | integer | Steps completed in this execution |
| `total_steps` | integer | Total steps in the full runbook |
| `metadata` | object | `RunbookMetadataProjection` summary: `runbook_id`, `event_count` |

Failure fields (in addition to `run_id`, `source_run_id`, `runbook_id` when available):

| Field | Type | Description |
|---|---|---|
| `status` | `"error"` | Terminal failure |
| `failure_kind` | string | ADR-013 `RuntimeFailureKind.value` |
| `failure_code` | string | ADR-013 or §6.2 failure code |
| `failed_step_index` | integer \| null | Absolute step index of failure; `null` for pre-execution failures |
| `terminated_early` | boolean | Always `true` on failure |

### 8.3 Exit codes

- `0` — execution completed successfully
- `1` — any failure: checkpoint resolution, integrity, or step execution

---

## 9. Audit and Trace Continuity

### 9.1 Per-step execution traces

Each step executed during replay or resume produces its own `ExecutionTrace` through the
existing engine path. These traces are distinct from the source run's traces and are
associated with the new `run_id`.

### 9.2 Metadata correlation

`RunbookLifecycleEvent` records emitted during replay or resume carry the new run's
`run_id`. `source_run_id` is available in the checkpoint record for cross-run correlation.
No `RunbookLifecycleEvent` or `RunbookMetadataProjection` field is modified to add
`source_run_id` directly — the lineage is implicit in the checkpoint record.

### 9.3 Content safety

ADR-003 content safety requirements apply in full to all metadata, lifecycle events, and
checkpoint fields produced by the replay/resume layer. No step input, model output, or
exception content appears in any field.

---

## 10. Explicit Non-Goals

### Deferred — not in scope for this ADR

- Python implementation of replay or resume
- Tests
- Configuration key definitions for storage root
- Cleanup or deletion policy for source checkpoints

### Out of scope permanently (ADR-017 §6)

- Autonomous replay triggering — the system never decides to replay on its own
- Speculative pre-execution — no steps run ahead of their declared position
- Branching or conditional step selection during replay
- Partial audit bypass during resume — ADR-009 constraints apply in full
- Cross-runbook state sharing or lineage
- Distributed checkpoint storage

### Not modified by this ADR

- `io_iii/core/runbook.py`
- `io_iii/core/runbook_runner.py`
- `io_iii/cli.py` (existing `runbook` subcommand surface)
- Any ADR-014, ADR-015, or ADR-016 contract

---

## Scope Boundary

This ADR covers:

- definitions of replay and resume (§1)
- checkpoint resolution and validation procedure (§2)
- starting-point selection rules for both modes (§3)
- lineage generation, source binding, and chain extension (§4)
- bounded execution guarantees and step ceiling (§5)
- deterministic failure semantics and failure codes (§6)
- checkpoint continuity for replay/resume runs (§7)
- CLI surface: commands, output contract, and exit codes (§8)
- audit and trace continuity expectations (§9)

This ADR does **not** cover:

- checkpoint storage format or location (ADR-019)
- run identity format (ADR-018)
- any implementation

---

## Relationship to Other ADRs

- **ADR-003** — content safety. All metadata and checkpoint fields produced by this layer
  must comply.
- **ADR-009** — audit gate contract. Per-step audit constraints apply identically during
  replay and resume.
- **ADR-013** — failure semantics. Failure envelope and taxonomy extended by §6.2.
- **ADR-014** — bounded runbook runner. Frozen; replay/resume executes through it, not around it.
- **ADR-015** — runbook traceability. Frozen; metadata correlation is via checkpoint lineage,
  not via modified lifecycle events.
- **ADR-016** — CLI runbook execution surface. Frozen; replay/resume CLI is a new surface above it.
- **ADR-017** — replay/resume boundary. This ADR satisfies the ADR-020 prerequisite from §5.3.
- **ADR-018** — run identity. `run_id` generation, immutability, and `source_run_id` binding
  consumed from this contract.
- **ADR-019** — checkpoint persistence. Lookup algorithm (§7) and integrity checks (§8)
  consumed from this contract.

---

## Consequences

### Positive

- M4.11 is now implementation-safe. All four prerequisite contracts are accepted (ADR-017
  through ADR-020).
- The frozen M4.7–M4.9 stack is not modified. The bounded runner remains unchanged.
- Replay and resume are structurally isolated from the core execution path.
- The failure taxonomy extension (§6.2) is backward-compatible: new codes within existing
  `RuntimeFailureKind.contract_violation`.
- Full runbook lineage is reconstructable from checkpoint records without runtime traversal.

### Negative

- The resume checkpoint continuity invariant (§7.3) is a correctness obligation on the
  M4.11 implementation — it is not enforced by the ADR layer itself.
- Accumulation of source checkpoint files is governed by ADR-019 §5.2–5.3; no automatic
  cleanup policy exists.

### Neutral

- This ADR produces no code, no tests, and no changes to any existing runtime surface.

---

## Decision Summary

IO-III introduces two bounded execution modes above the frozen M4.9 surface: replay
(full re-execution from step 0) and resume (continuation from the first incomplete step).
Both modes resolve checkpoints via the ADR-019 §7 six-step algorithm, generate a new
`run_id`, and bind lineage through `source_run_id`. Both execute through the existing
`runbook_runner.run()` without modifying it. A completed run cannot be resumed. Three
new failure codes (`CHECKPOINT_NOT_FOUND`, `CHECKPOINT_INTEGRITY_ERROR`,
`RESUME_INVALID_STATE`) extend the ADR-013 taxonomy under `contract_violation`. CLI
surface (`replay` and `resume` subcommands) is introduced in M4.11 only. No existing
ADR-014, ADR-015, or ADR-016 surface is modified.