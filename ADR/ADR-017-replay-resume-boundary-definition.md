---
id: ADR-017
title: Replay/Resume Boundary Definition
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
  - replay
  - resume
  - boundary
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M4.10
subordinate_to: ADR-016
---

# ADR-017 — Replay/Resume Boundary Definition

## Status

Accepted

## Subordination

This ADR subordinates itself entirely to **ADR-016 — CLI Runbook Execution Surface**
and, through it, to **ADR-015**, **ADR-014**, and **ADR-012**.

No constraint in any of those ADRs is loosened by this document. This ADR defines
an upper architectural boundary above ADR-016. It does not modify anything below it.

---

## Context

ADR-016 §10 explicitly anticipated this document:

> "M4.10 (if implemented) may introduce replay or resume semantics above the M4.9
> surface. M4.9 does not prepare for this: it introduces no checkpoint state, no run
> identifiers beyond `runbook_id`, and no persistence that could be consumed by a
> replay layer."

M4.10 is a **boundary ADR only**. It freezes the architectural layer definition and
deferral decision. It does not implement replay or resume.

The M4.7–M4.9 execution stack is complete, verified, and frozen. Replay and resume
are structurally distinct capabilities that require new contracts for persistence,
run identity, and partial-state representation. Introducing them without a separate
formal contract would risk silent pollution of the frozen bounded execution kernel.

---

## Decision

IO-III defers all replay and resume implementation beyond M4.10.

Replay and resume, if introduced, must be implemented as a separate upper layer above
the M4.9 CLI runbook execution surface. They must never be retrofitted into M4.7,
M4.8, or M4.9 contracts.

M4.11, if initiated, is the first implementation-safe milestone for this layer.

---

## 1. Layer Position

The replay/resume layer, if introduced, sits **above** the M4.9 CLI surface.

```
replay/resume layer (M4.11+)
  ↓
CLI runbook execution surface (ADR-016, M4.9)
  ↓
runbook_runner.run() (ADR-014, ADR-015, M4.7/M4.8)
  ↓
orchestrator.run() → engine.run() → ...
```

It does not extend any existing layer. It does not modify `cli.py`, `runbook_runner.py`,
`runbook.py`, or any lower-level contract. It introduces its own surface, its own
persistence contract, and its own test suite.

---

## 2. Why Implementation Is Deferred

The M4.7–M4.9 stack is frozen and verified. Replay and resume require structural
prerequisites that do not yet exist:

1. **Persistence contract** — no persistence exists anywhere in the current stack.
   Replay requires a durable run record. Resume requires durable step-level checkpoint
   state. Neither format has been defined.

2. **Run identity** — `runbook_id` is a structural identifier, not a run identifier.
   There is no concept of a run instance distinct from the runbook definition. Replay
   and resume require a stable run identity that is separate from the runbook schema.

3. **Partial-state representation** — resume requires that the state of an in-progress
   or failed runbook can be represented, stored, and restored at a specific step index.
   No such representation exists.

4. **Step-index anchoring** — `--from-step` / `--to-step` semantics were explicitly
   excluded from M4.9. Resuming from a step requires a formal anchoring contract that
   does not yet exist.

Implementing replay or resume without these contracts would require either (a) expanding
the frozen M4.9 surface or (b) adding implicit state to the bounded runner — both of
which are prohibited.

---

## 3. Non-Goals for M4.10

M4.10 **must not**:

- implement replay
- implement resume
- add persistence to any existing layer
- add checkpoint state to `runbook_runner.py`, `runbook.py`, or `cli.py`
- add `--from-step` / `--to-step` flags to the `runbook` CLI command
- add run identifiers beyond `runbook_id`
- add a second runbook execution path
- widen `Runbook`, `RunbookResult`, `RunbookStepOutcome`, or `RunbookLifecycleEvent`
- add replay-enabling fields to any M4.7/M4.8/M4.9 contract under the guise of
  "preparation" or "future-proofing"
- modify `io_iii/cli.py`, `io_iii/core/runbook.py`, or `io_iii/core/runbook_runner.py`

M4.10 **must only** produce this ADR.

---

## 4. Prohibition on Retrofitting

The M4.9 CLI surface (ADR-016) is frozen. The M4.8 observability layer (ADR-015) is
frozen. The M4.7 runner contract (ADR-014) is frozen.

No replay or resume requirement may be satisfied by modifying these layers. Any
implementation that requires changes to frozen surfaces is out of scope for this
boundary definition and must be escalated as a structural revision with its own
ADR update.

Specifically prohibited modifications under the guise of replay/resume preparation:

- Adding `run_id`, `checkpoint_id`, or any equivalent field to `RunbookResult`,
  `RunbookStepOutcome`, `RunbookLifecycleEvent`, or `RunbookMetadataProjection`
- Adding optional persistence parameters to `runbook_runner.run()`
- Adding `--resume`, `--replay`, `--from-step`, or `--to-step` to `cmd_runbook()`
- Writing checkpoint files, sidecar files, or run journals from any existing module
- Adding a second deserialisaton path to `Runbook.from_dict()` for resumable formats

---

## 5. Dependency-Safe Path to M4.11

M4.11 is the first implementation-safe milestone for the replay/resume layer.

Before M4.11 can be initiated, the following must be true:

1. **ADR-018 — Run Identity Contract** — A stable, durable run identity scheme must
   be defined. This is a separate ADR. It must specify how a run instance is identified
   distinct from the runbook definition, how run identifiers are generated, and how
   they are scoped.

2. **ADR-019 — Checkpoint Persistence Contract** — The persistence format, storage
   location, and lifecycle of checkpoint state must be defined as a separate ADR.
   This contract must specify the step-level checkpoint schema, write policy, and
   read/restore semantics.

3. **ADR-020 — Replay/Resume Execution Contract** — The execution semantics of replay
   and resume, including step-index anchoring, partial execution, and the relationship
   to the bounded runner, must be formalised in a separate ADR before any implementation.

No implementation may begin until all three prerequisite ADRs are accepted.

M4.11 scope is bounded to introducing the replay/resume layer surface only, using
the contracts from ADR-018, ADR-019, and ADR-020. It does not modify lower layers.

---

## 6. Explicit Non-Goals (Permanent)

The following are permanently excluded from the replay/resume layer regardless of
milestone:

- autonomous re-execution decisions (the system never decides to replay on its own)
- speculative pre-execution (running steps ahead of their declared position)
- branching or conditional step selection during replay
- partial audit bypass during resume (audit constraints from ADR-009 always apply)
- cross-runbook state sharing (each runbook execution is isolated)
- distributed checkpoint storage (persistence scope is local and explicit)

---

## Scope Boundary

This ADR covers:

- the layer position of replay/resume above the M4.9 surface
- the structural reasons for deferral
- the explicit non-goals for M4.10
- the prohibition on retrofitting replay state into frozen layers
- the prerequisite ADR chain before M4.11 can begin

This ADR does **not** cover:

- the run identity contract (ADR-018)
- the checkpoint persistence contract (ADR-019)
- the replay/resume execution contract (ADR-020)
- any implementation

---

## Relationship to Other ADRs

- **ADR-012** — bounded orchestration layer. Unaffected; replay sits above it.
- **ADR-014** — bounded runbook runner. Frozen; must not be modified for replay.
- **ADR-015** — runbook traceability. Frozen; `RunbookMetadataProjection` is not a replay checkpoint.
- **ADR-016** — CLI runbook execution surface. Frozen; replay layer sits above it.
- **ADR-017** (this document) — architectural boundary only.
- **ADR-018/019/020** — prerequisite contracts before M4.11.

---

## Consequences

### Positive

- The M4.7–M4.9 kernel remains frozen and unambiguous.
- Replay/resume cannot silently expand lower-layer contracts.
- The prerequisite ADR chain creates a clear, governed entry gate for M4.11.
- No implementation pressure is introduced by the boundary definition itself.

### Negative

- Replay and resume are not available until at least M4.11, which requires three
  prerequisite ADRs.

### Neutral

- M4.10 produces only this ADR — no code, no tests, no new CLI surface.

---

## Decision Summary

IO-III defers all replay and resume implementation to M4.11 and beyond.

M4.10 freezes the upper architectural boundary above ADR-016. The M4.7–M4.9 execution
stack is sealed. Replay and resume require a new persistence contract, a run identity
scheme, and a formal execution contract — none of which exist. These must be introduced
as separate ADRs (ADR-018, ADR-019, ADR-020) before M4.11 implementation can begin.

The frozen-kernel doctrine is preserved. The replay/resume layer is a future upper layer,
not an extension of any existing contract.