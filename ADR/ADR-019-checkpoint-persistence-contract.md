---
id: ADR-019
title: Checkpoint Persistence Contract
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
  - checkpoint
  - persistence
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M4.10
subordinate_to: ADR-018
---

# ADR-019 — Checkpoint Persistence Contract

## Status

Accepted

## Subordination

This ADR subordinates itself entirely to **ADR-018 — Run Identity Contract** and,
through it, to **ADR-017**, **ADR-016**, **ADR-015**, **ADR-014**, and **ADR-012**.

No constraint in any of those ADRs is loosened by this document. This ADR defines
what is stored in a checkpoint, how it is identified, and how it is retrieved. It does
not define how checkpoint state is consumed by replay or resume execution — that is
ADR-020's contract.

---

## Context

ADR-018 §5.1 required that every checkpoint record carry `run_id`, `runbook_id`, and
`source_run_id`, and left the storage format and lifecycle to this document.

ADR-018 §6 explicitly deferred the following to ADR-019:

> "Checkpoint storage format; checkpoint file location, naming, and lifecycle; write
> and read policies for checkpoint state; serialisation of `run_id` within checkpoint
> records."

ADR-017 §6 permanently excluded distributed checkpoint storage.

Without a closed persistence contract, ADR-020 cannot specify how a replay execution
locates and validates a prior run's checkpoint. This ADR closes that gap without
introducing any execution or CLI behaviour.

---

## Decision

IO-III checkpoints are local JSON files, one per run, stored at a deterministic path
derived from `run_id`. A checkpoint is written atomically after each step completes.
The most recent checkpoint file for a given `run_id` is the authoritative record.
Identity fields within a checkpoint are immutable across writes. Lookup is always by
`run_id` — no index, no registry.

---

## 1. Checkpoint Identity Schema

A checkpoint record is a JSON object with the following top-level fields.

### 1.1 Identity fields (frozen at first write; never mutated)

| Field | Type | Requirement |
|---|---|---|
| `checkpoint_schema_version` | `string` | Always `"1.0"`. Hard error if mismatched on read. |
| `run_id` | `string` | UUIDv4; from ADR-018 §1.2. Always present. |
| `runbook_id` | `string` | From `Runbook.runbook_id`; always present. |
| `source_run_id` | `string \| null` | From ADR-018 §3; `null` for original runs. Always present. |
| `runbook_snapshot` | `object` | Full `Runbook.to_dict()` output captured at run start. Frozen. |
| `created_at` | `string` | ISO 8601 UTC timestamp of the first checkpoint write for this run. |

### 1.2 Progress fields (updated on each write)

| Field | Type | Requirement |
|---|---|---|
| `steps_completed` | `integer` | Count of steps that reached a terminal success state. `0` if none. |
| `last_completed_step_index` | `integer \| null` | Zero-based index of the last successful step. `null` if `steps_completed = 0`. |
| `total_steps` | `integer` | Total number of steps in the runbook. Derived from `runbook_snapshot`. |
| `status` | `string` | One of: `"in_progress"`, `"completed"`, `"failed"`. |
| `updated_at` | `string` | ISO 8601 UTC timestamp of the most recent write. |

### 1.3 Failure fields (present only when `status = "failed"`)

| Field | Type | Requirement |
|---|---|---|
| `failure_kind` | `string` | ADR-013 `RuntimeFailureKind.value`. Present iff `status = "failed"`. |
| `failure_code` | `string` | ADR-013 `RuntimeFailure.code`. Present iff `status = "failed"`. |
| `failed_step_index` | `integer` | Zero-based index of the step that failed. Present iff `status = "failed"`. |

### 1.4 Prohibited content

No checkpoint field may contain:

- prompt text
- model output or completion text
- free-form exception messages
- stack traces
- user-provided input payloads beyond what is already captured in `runbook_snapshot`

Content safety requirements from ADR-003 and ADR-013 apply to checkpoint records.

---

## 2. Binding Rules to `run_id` and `source_run_id`

These rules restate ADR-018 §4 as checkpointing-specific requirements.

1. A checkpoint record is exclusively bound to the `run_id` it was created for. It
   cannot be reassigned to a different `run_id`.

2. The `run_id` in a checkpoint must match the `run_id` under which the checkpoint
   file is stored (see §4). A mismatch is a hard integrity error.

3. The `runbook_id` in a checkpoint must match the `runbook_id` in the `runbook_snapshot`.
   A mismatch is a hard integrity error.

4. `source_run_id` must be `null` for original runs and a valid `run_id` string for
   replay runs. An absent `source_run_id` field is a hard integrity error.

5. No consumer may alter the identity fields of a checkpoint after the first write.

---

## 3. Persistence Granularity

### 3.1 Write trigger

A checkpoint is written after each step reaches a terminal state (success or failure).
Writing occurs in the replay/resume layer (M4.11+), not inside the runbook runner or
any lower-layer component.

Trigger points:

- after each step completes successfully — `status = "in_progress"` (or `"completed"` if the last step)
- after a step fails — `status = "failed"`
- after all steps complete without failure — `status = "completed"`

### 3.2 Write policy

Each write is a **full replacement** of the checkpoint file for the given `run_id`.
There is no append or patch operation. The file for `run_id` always reflects the
state at the most recent write.

### 3.3 Atomicity

Each write must be atomic from the perspective of any concurrent reader. The canonical
implementation strategy is write-to-temp-file + atomic rename into the final path.

A partial write (e.g. due to process crash) must not leave a corrupt file at the
final path. If a partial write is detected on read, it must be treated as a missing
checkpoint — not as partial state.

### 3.4 First write

The first checkpoint write occurs after the first step reaches a terminal state. No
checkpoint file exists for a `run_id` before the first step completes.

A `run_id` with no checkpoint file has no recoverable state. Replay or resume
execution (ADR-020) must treat a missing file as a non-resumable run.

---

## 4. Storage Location and Naming

### 4.1 Storage root

Checkpoints are stored in a local directory. The default path is:

```
.io_iii/checkpoints/
```

relative to the working directory at invocation time. The storage root may be
overridden by configuration (exact key is implementation detail, not frozen here).

### 4.2 File naming

Each checkpoint is stored as a single JSON file:

```
<storage_root>/<run_id>.json
```

The filename is exactly the `run_id` value (lowercase hyphenated UUID, 36 characters)
with a `.json` extension. No subdirectories. No namespacing by `runbook_id`. No
date-based partitioning.

### 4.3 Deterministic lookup

Given a `run_id`, the checkpoint file path is fully derived:

```
<storage_root>/<run_id>.json
```

No index file. No registry. No database. Lookup is a direct file existence check
followed by a read and parse. If the file does not exist, no checkpoint exists for
that run.

---

## 5. Lifecycle

### 5.1 Creation

A checkpoint file is created on the first write for a `run_id`. The storage root
directory must already exist; the checkpoint writer must not silently create it.

### 5.2 Retention

Checkpoint files are retained indefinitely after the run completes or fails. There is
no automatic deletion or expiry.

### 5.3 Deletion

Deletion policy is out of scope for this ADR. Manual deletion is permitted. A deleted
checkpoint file is equivalent to a missing checkpoint (§3.4 applies).

### 5.4 Immutability after terminal state

Once a checkpoint reaches `status = "completed"` or `status = "failed"`, no further
writes are permitted for that `run_id`. The terminal state is the final record.

---

## 6. Immutable Metadata Contract

The identity fields listed in §1.1 are frozen at the time of the first checkpoint
write and must not change across subsequent writes for the same `run_id`. Specifically:

- `checkpoint_schema_version` — frozen at `"1.0"`
- `run_id` — frozen at generation time (ADR-018 §1.3)
- `runbook_id` — frozen from the runbook definition
- `source_run_id` — frozen at run start
- `runbook_snapshot` — frozen at run start; the full `Runbook.to_dict()` output
- `created_at` — frozen at first write

Any checkpoint writer that attempts to mutate an identity field on a subsequent write
is in violation of this contract. Consumers must validate identity field stability
between reads if performing multi-read workflows (ADR-020 concern).

---

## 7. Deterministic Replay Lookup

The replay/resume layer (ADR-020) locates a checkpoint by `run_id` as follows:

1. Derive the file path: `<storage_root>/<run_id>.json`
2. Check existence: if the file does not exist, the run has no checkpoint.
3. Read and parse: if the file exists, parse as JSON.
4. Validate schema version: `checkpoint_schema_version` must be `"1.0"`. Mismatch is
   a hard error — do not attempt to consume.
5. Validate identity binding: `run_id` in the file must match the requested `run_id`.
   Mismatch is a hard integrity error — do not attempt to consume.
6. Validate `runbook_id` consistency: `run_id` in the file must match `runbook_id` in
   `runbook_snapshot`. Mismatch is a hard integrity error.

Steps 4–6 must all pass before any consumer reads the progress or failure fields.

ADR-020 defines what to do with the validated checkpoint data. ADR-019 defines only
what constitutes a valid checkpoint and how to locate it.

---

## 8. Integrity and Consistency Guarantees

### 8.1 Schema validity

A checkpoint file that does not parse as valid JSON is treated as missing. A checkpoint
that parses as valid JSON but fails schema validation (missing required fields, wrong
types) is a hard integrity error — the consumer must not attempt to reconstruct state.

### 8.2 Identity consistency

A checkpoint whose `run_id` does not match its filename is a hard integrity error.
A checkpoint whose `runbook_id` does not match the `runbook_id` in `runbook_snapshot`
is a hard integrity error. These checks are mandatory before any progress field is read.

### 8.3 Progress consistency

`last_completed_step_index` must be consistent with `steps_completed`:

- if `steps_completed = 0`, then `last_completed_step_index` must be `null`
- if `steps_completed > 0`, then `last_completed_step_index` must be a non-negative
  integer less than `total_steps`

Inconsistency between these fields is a hard integrity error.

### 8.4 Failure consistency

If `status = "failed"`, then `failure_kind`, `failure_code`, and `failed_step_index`
must all be present and non-null. Absent failure fields when `status = "failed"` is
a hard integrity error.

### 8.5 No partial state recovery

If any integrity check fails, the checkpoint must be treated as unrecoverable. The
consumer must not attempt to extract partial state from a checkpoint that has failed
validation. The failure must be reported as a checkpoint integrity error to the caller
(ADR-020 defines the error surface).

---

## 9. Explicit Non-Goals

### Deferred to ADR-020

- How the replay/resume layer consumes checkpoint state
- Step-index anchoring for partial resume (`--from-step` semantics)
- What happens when a checkpoint indicates a `"failed"` or `"in_progress"` state
- CLI flags for replay or resume
- Failure semantics specific to replay/resume execution

### Out of scope permanently (ADR-017 §6)

- Remote or distributed checkpoint storage
- Encrypted checkpoint storage
- Access control on checkpoint files
- Cross-run or cross-runbook checkpoint sharing

### Not implementation work

- Python implementation of the checkpoint writer or reader
- Tests
- Configuration key definitions
- Storage root creation policy

---

## Scope Boundary

This ADR covers:

- the full checkpoint identity schema (§1)
- binding rules to `run_id` and `source_run_id` (§2)
- persistence granularity and write policy (§3)
- storage location and deterministic naming (§4)
- checkpoint lifecycle (§5)
- immutable metadata contract (§6)
- deterministic replay lookup algorithm (§7)
- integrity and consistency guarantees (§8)

This ADR does **not** cover:

- replay or resume execution semantics (ADR-020)
- CLI surface for replay or resume
- any implementation

---

## Relationship to Other ADRs

- **ADR-003** — telemetry and logging. Content safety requirements apply to checkpoint fields.
- **ADR-013** — failure semantics. `failure_kind` and `failure_code` in §1.3 are sourced from ADR-013.
- **ADR-014** — bounded runbook runner. Frozen; the checkpoint writer sits above this layer.
- **ADR-017** — replay/resume boundary. Distributed storage excluded by §6.
- **ADR-018** — run identity. `run_id`, `source_run_id`, and binding rules consumed from this contract.
- **ADR-019** (this document) — checkpoint persistence.
- **ADR-020** — replay/resume execution. Must locate and validate checkpoints per §7 before consuming §1.2–1.3.

---

## Consequences

### Positive

- ADR-020 can now specify replay/resume execution against a fully defined, unambiguous
  checkpoint format.
- The deterministic lookup rule (§4.3 + §7) means replay needs no index or registry.
- The frozen identity schema (§6) prevents checkpoint corruption from run to run.
- No existing runtime surface is modified.

### Negative

- Checkpoint files accumulate indefinitely without a deletion policy (lifecycle §5.3).
  A future policy ADR may address this.
- Atomic write-via-rename requires the temp file and final path to be on the same
  filesystem — this is a local constraint, consistent with ADR-017 §6.

### Neutral

- This ADR produces no code, no tests, and no changes to any existing runtime surface.

---

## Decision Summary

IO-III checkpoints are local JSON files stored at `<storage_root>/<run_id>.json`,
written atomically after each step completes. Each checkpoint carries frozen identity
fields (`run_id`, `runbook_id`, `source_run_id`, `runbook_snapshot`) and mutable
progress fields (`steps_completed`, `last_completed_step_index`, `status`). Identity
fields are immutable across writes. Lookup is deterministic: path derived from
`run_id`, no index required. All consumers must validate schema version, `run_id`
binding, and progress consistency before reading state. ADR-020 owns consumption
semantics; ADR-019 owns only what is stored and how it is found.