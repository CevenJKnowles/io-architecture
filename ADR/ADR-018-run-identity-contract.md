---
id: ADR-018
title: Run Identity Contract
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
  - identity
  - lineage
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M4.10
subordinate_to: ADR-017
---

# ADR-018 — Run Identity Contract

## Status

Accepted

## Subordination

This ADR subordinates itself entirely to **ADR-017 — Replay/Resume Boundary Definition**
and, through it, to **ADR-016**, **ADR-015**, **ADR-014**, and **ADR-012**.

No constraint in any of those ADRs is loosened by this document. This ADR defines
the run identity contract required before checkpoint persistence (ADR-019) and replay
execution (ADR-020) can be specified. It does not implement any runtime behaviour.

---

## Context

ADR-017 §2 identified the absence of run identity as a structural prerequisite for
replay and resume:

> "`runbook_id` is a structural identifier, not a run identifier. There is no concept
> of a run instance distinct from the runbook definition. Replay and resume require a
> stable run identity that is separate from the runbook schema."

ADR-017 §5 defined this document's obligation:

> "A stable, durable run identity scheme must be defined. It must specify how a run
> instance is identified distinct from the runbook definition, how run identifiers are
> generated, and how they are scoped."

Without a closed run identity contract, checkpoint persistence (ADR-019) cannot specify
which run a checkpoint belongs to, and replay execution (ADR-020) cannot unambiguously
reference a prior run. This ADR closes that gap without implementing any storage or
execution behaviour.

---

## Decision

IO-III adopts a stable, immutable `run_id` as the canonical identity of a single
bounded runbook execution. The `run_id` is structurally separate from `runbook_id`.
It is generated once at execution start and never mutated. Lineage between original
and replay runs is encoded through an explicit `source_run_id` field. Checkpoint and
replay contracts must bind to `run_id` as the stable correlation key.

---

## 1. `run_id` Contract

### 1.1 Definition

A `run_id` identifies one discrete, bounded execution of a runbook. One `run_id` is
produced per invocation of the runbook execution path. A single `runbook_id` may
produce many distinct `run_id` values across multiple executions.

### 1.2 Format

A `run_id` is a canonical UUID string in lowercase hyphenated form:

```
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

The value is 36 characters. It must be valid UUIDv4 (randomly generated, RFC 4122).
No other format is permitted. No compressed, base64, or prefixed variants.

### 1.3 Generation Policy

A `run_id` is generated exactly once per execution, at the point the execution path
is entered — before any step runs, before any checkpoint is written, and before any
lifecycle event is emitted.

Generation is always explicit. The generation source is always the replay/resume
layer (M4.11+). No lower-layer component (engine, orchestrator, runbook runner) is
responsible for generating or consuming `run_id`. The frozen M4.7–M4.9 stack is
unaffected.

### 1.4 Immutability

A `run_id` is immutable for the lifetime of the run. It may not be:

- reassigned after generation
- mutated during execution
- reused across distinct executions of the same or different runbook
- derived from or overwritten by any step output or engine result

---

## 2. Uniqueness Scope

A `run_id` is globally unique within the scope of a single IO-III runtime installation.

Uniqueness is guaranteed by the UUIDv4 generation policy (probabilistic collision
resistance sufficient for local, non-distributed use). No distributed coordination
or central registry is required.

A `run_id` is never reused:

- completing a run does not release its `run_id` for reuse
- replaying a run produces a new `run_id`; the original `run_id` remains stable and
  permanently associated with the original run

---

## 3. Lineage Identity Rules

### 3.1 Original Run

An original run carries:

```
run_id:        <generated UUID>
source_run_id: null
```

`source_run_id = null` is the canonical marker of an original (non-replay) run.

### 3.2 Replay Run

A replay of any prior run carries:

```
run_id:        <newly generated UUID>
source_run_id: <run_id of the immediate parent run>
```

A replay always produces a new `run_id`. It never inherits the `run_id` of the
run it replays. The `source_run_id` always points to the immediate parent, not the
original ancestor.

### 3.3 Lineage Chain

Full lineage is reconstructable by following the `source_run_id` trail:

```
original_run (source_run_id = null)
  ↓ replayed as
replay_1 (source_run_id = original_run.run_id)
  ↓ replayed as
replay_2 (source_run_id = replay_1.run_id)
```

No component is required to traverse the full chain at execution time. The chain is
an audit artefact, not a runtime dependency.

### 3.4 Lineage Isolation

Lineage is always scoped to a single `runbook_id`. A `source_run_id` must reference
a run that was produced by an execution of the same runbook definition. Cross-runbook
lineage is prohibited (ADR-017 §6).

---

## 4. Metadata Correlation Binding

Any checkpoint or replay record that references a `run_id` is exclusively bound to
that `run_id`. The binding is:

- **injective** — one checkpoint/replay record maps to exactly one `run_id`
- **immutable** — the binding cannot be changed after the record is created
- **non-transferable** — a record bound to `run_id` A cannot be consumed by a replay
  invocation presenting `run_id` B

Any consumer of a checkpoint (ADR-019) or replay record (ADR-020) must validate that
the `run_id` in the record matches the `run_id` of the current execution before
consuming the record's state. Mismatched `run_id` is a hard contract violation.

The following fields must co-occur wherever run identity is recorded:

| Field | Requirement |
|---|---|
| `run_id` | always present |
| `runbook_id` | always present alongside `run_id` |
| `source_run_id` | always present; `null` for original runs |

No record may carry `runbook_id` without `run_id` in any checkpoint or replay surface.

---

## 5. Stable Replay Reference Requirements

These requirements constrain ADR-019 and ADR-020 without specifying their
implementation.

### 5.1 Checkpoint reference (constrains ADR-019)

Every checkpoint record must:

- carry the `run_id` of the run that produced it
- carry the `runbook_id` of the runbook definition being executed
- carry the `source_run_id` (or `null`) so the checkpoint's lineage position is
  unambiguous

The checkpoint storage format is not defined here. ADR-019 owns that contract.

### 5.2 Replay invocation reference (constrains ADR-020)

Any replay invocation must:

- accept a `run_id` as an explicit input identifying the run to replay
- resolve the checkpoint record by that `run_id`
- generate a new `run_id` for the replay execution
- bind `source_run_id` of the new run to the input `run_id`

The replay execution contract is not defined here. ADR-020 owns that contract.

---

## 6. Explicit Non-Goals

### Not covered by this ADR — deferred to ADR-019

- Checkpoint storage format
- Checkpoint file location, naming, and lifecycle
- Write and read policies for checkpoint state
- Serialisation of `run_id` within checkpoint records

### Not covered by this ADR — deferred to ADR-020

- Replay CLI surface and flag contract
- Step-index anchoring for partial resume
- How a replay execution resolves a prior run by `run_id`
- Failure semantics specific to replay/resume execution

### Not covered by this ADR — explicitly excluded from all milestones (ADR-017 §6)

- Autonomous replay triggering
- Cross-runbook lineage
- Distributed run identity coordination
- Partial audit bypass during replay

### Not covered by this ADR — implementation

- Python type or dataclass for `run_id` / `source_run_id`
- UUID generation library or function
- Injection point into any execution path
- Tests

---

## Scope Boundary

This ADR covers:

- the canonical definition and format of `run_id`
- the generation policy and immutability guarantee
- the uniqueness scope
- the lineage identity rules (original vs. replay, `source_run_id`)
- the metadata correlation binding requirements
- the stable replay reference requirements that constrain ADR-019 and ADR-020

This ADR does **not** cover:

- checkpoint persistence format or storage (ADR-019)
- replay execution semantics or CLI surface (ADR-020)
- any implementation

---

## Relationship to Other ADRs

- **ADR-012** — bounded orchestration layer. Unaffected.
- **ADR-014** — bounded runbook runner. Frozen; `run_id` is not added to this layer.
- **ADR-015** — runbook traceability. Frozen; `RunbookMetadataProjection` is not a run record.
- **ADR-016** — CLI runbook execution surface. Frozen; `run_id` is not added to this layer.
- **ADR-017** — replay/resume boundary. ADR-018 satisfies the run identity prerequisite.
- **ADR-019** — checkpoint persistence. Must bind checkpoint records to `run_id` per §5.1.
- **ADR-020** — replay/resume execution. Must consume `run_id` per §5.2.

---

## Consequences

### Positive

- ADR-019 can now specify checkpoint storage without ambiguity about which run a
  checkpoint belongs to.
- ADR-020 can now specify replay execution without ambiguity about lineage or identity.
- The frozen M4.7–M4.9 stack is not modified.
- Audit trails referencing `run_id` are unambiguous and permanently stable.

### Negative

- `run_id` generation and injection require a new module in the replay/resume layer
  (M4.11+), not in any existing module.

### Neutral

- This ADR produces no code, no tests, and no changes to any existing runtime surface.

---

## Decision Summary

IO-III adopts a UUIDv4-based `run_id` as the stable, immutable identity of a single
runbook execution, distinct from the structural `runbook_id`. Lineage between original
and replay runs is tracked through an explicit `source_run_id` field — `null` for
original runs, pointing to the immediate parent for replays. Any checkpoint (ADR-019)
or replay invocation (ADR-020) must bind to `run_id` as the exclusive correlation key.
No existing runtime surface is modified.