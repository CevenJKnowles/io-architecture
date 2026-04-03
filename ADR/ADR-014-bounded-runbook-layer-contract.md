---
id: ADR-014
title: Bounded Runbook Layer Contract
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
  - bounded-execution
roles_focus:
  - executor
  - challenger
provenance: io-iii-runtime-development
milestone: M4.7
subordinate_to: ADR-012
---

# ADR-014 — Bounded Runbook Layer Contract

## Status

Accepted

## Subordination

This ADR subordinates itself entirely to **ADR-012 — Bounded Orchestration Layer Contract**.

Every constraint in ADR-012 applies to this layer without exception. This ADR defines
the specific contract for bounded multi-step runbook execution, as explicitly anticipated
in ADR-012 section "Scope Boundary":

> "Bounded multi-step runbooks may be introduced later in Phase 4, but only under a
> separate explicit contract and only as a fixed-order, finite, non-branching extension."

This is that separate explicit contract.

---

## Context

Phase 4 M4.2 introduced the `Orchestrator`, which executes a single `TaskSpec` as one
bounded engine run. M4.7 introduces the `Runbook` as an ordered, finite composition of
multiple `TaskSpec` steps, each executed by the same single-run orchestration path.

The motivation is bounded composition: the ability to declare that a sequence of
independent, deterministic engine runs should execute in a fixed order. This is not a
workflow engine. It is not a planner. It does not adapt or branch based on outputs.

Without a formal contract, even a simple multi-step loop risks:

- unbounded iteration
- output-driven step selection
- retry logic disguised as step progression
- planner semantics smuggled through step ordering
- kernel mutation through accumulated state

A formal contract is therefore required before any runbook layer is implemented.

---

## Decision

IO-III will introduce a **bounded runbook layer** above the frozen orchestration layer.

This layer is defined by the following contract.

### 1. Runbook Definition

A `Runbook` is an ordered, serialisable, finite list of `TaskSpec` steps.

Properties:

- immutable once constructed
- serialisable to and from a stable dict/YAML representation
- carries a stable `runbook_id` (machine-readable correlation identifier)
- contains an ordered list of `TaskSpec` objects (minimum 1, maximum `RUNBOOK_MAX_STEPS`)
- rejects construction with an empty step list
- rejects construction with a step count above `RUNBOOK_MAX_STEPS`
- rejects construction with any invalid step entry (non-`TaskSpec` objects)

### 2. Step Ceiling

`RUNBOOK_MAX_STEPS = 20`

This is an explicit constant, not a configurable value. Any runbook exceeding this
ceiling is rejected at construction time, not at execution time. This prevents silent
runtime overflow.

### 3. Execution Contract

The runbook runner executes steps in strict declared order:

- step 0 first, then step 1, then step 2, and so on
- no reordering
- no skipping
- no output-driven routing between steps

Each step is executed by exactly one call to `orchestrator.run()`.

The runner must never call `engine.run()` directly. All execution is delegated through
the orchestration layer, preserving all ADR-012 and ADR-009 bounds per step.

### 4. Termination Contract

- If all steps succeed: the runbook completes normally.
- If any step fails: the runbook terminates immediately at that step.
  - No subsequent steps are executed.
  - No retry of the failed step.
  - The failure is recorded deterministically in the result.
  - The `RunbookResult` reflects the exact termination point.

There is no recovery path, no partial restart, and no conditional continuation.

### 5. No Branching

Runbook step order is fixed at construction time. Runtime outputs from any step
must never alter:

- which step executes next
- whether a step is skipped
- whether any step is repeated
- the total number of steps executed (absent a failure)

This is a hard architectural constraint, not a recommendation.

### 6. No Retry and No Loops

The runner contains no retry logic, no backoff, no loop constructs driven by step
outcomes. A failed step terminates the runbook. There is no mechanism to re-execute
a step.

### 7. No Recursion

A runbook may not contain another runbook. A runbook step is exactly one `TaskSpec`.
Nesting, chaining, or self-referential runbooks are not supported.

### 8. ADR-009 Bounds Preserved Per Step

Each step executes via `orchestrator.run()`, which delegates to `engine.run()`.
ADR-009 bounds (max 1 audit pass, max 1 revision pass) apply independently to each
step. The runbook layer adds no new execution bounds and removes none.

### 9. Coordination Layer Only

The runbook layer is a coordination layer. It does not:

- reason about step content
- select capabilities autonomously
- construct prompts
- interpret model output
- make routing decisions
- alter `TaskSpec` objects at execution time

It iterates. It delegates. It records outcomes. Nothing more.

### 10. No Engine Contract Widening

The runbook layer must not modify, extend, or bypass the engine contract. The engine
receives exactly the same inputs it would receive from a single-step orchestrator call.

### 11. No Routing Contract Widening

Route resolution remains table-driven from `TaskSpec.mode` per step, via the
orchestrator. The runbook layer never calls `resolve_route()` directly.

### 12. No Kernel Mutation

The runbook layer must not modify any state in the runtime kernel:

- no routing table changes
- no provider configuration changes
- no capability registry changes
- no session state shared across steps (each step produces an independent `SessionState`)

### 13. Request Correlation

Each step execution produces an independent `SessionState` with its own `request_id`.
The `runbook_id` is the structural correlation key tying all step outcomes together.
No correlation field may carry prompt or model output content.

### 14. Result Structure

`RunbookResult` carries:

- `runbook_id` — matches the originating `Runbook`
- `step_outcomes` — ordered list of per-step outcome records
- `steps_completed` — count of fully successful steps
- `failed_step_index` — index of the failing step, or `None` if all succeeded
- `terminated_early` — `True` if a step failure caused early termination

Each `RunbookStepOutcome` carries:

- `step_index` — zero-based position in the runbook
- `task_spec_id` — correlation back to the originating `TaskSpec`
- `state` — the `SessionState` from the step execution, or `None` on failure
- `result` — the `ExecutionResult` from the step execution, or `None` on failure
- `success` — `True` if the step completed without exception
- `failure` — `RuntimeFailure` envelope if the step raised, or `None`

All fields are structural and bounded. No prompt or model output content may appear
in `RunbookResult` or `RunbookStepOutcome`.

---

## Scope Boundary

This ADR covers:

- the `Runbook` schema contract (immutable, serialisable, bounded, ordered)
- the step ceiling constant (`RUNBOOK_MAX_STEPS`)
- the `RunbookRunner` execution contract (fixed order, orchestrator delegation, termination)
- the `RunbookResult` and `RunbookStepOutcome` output structures
- invariant and test implications

This ADR does **not** cover:

- CLI surfaces for runbook execution (not required for M4.7 boundary integrity)
- dynamic step generation
- inter-step data passing or chaining
- conditional step execution
- partial runbook resumption
- runbook persistence or serialisation to disk
- retry or backoff subsystems

---

## Constraints

All constraints from ADR-012 apply. Additional runbook-specific constraints:

- **Step ceiling is a constant**, not a runtime parameter.
- **Empty runbooks are rejected** at construction — not silently treated as no-ops.
- **Step type is strictly `TaskSpec`** — no duck-typing, no subclasses, no dicts.
- **Failure terminates immediately** — no steps execute after a failure.
- **`orchestrator.run()` is the only permitted delegation path** — never `engine.run()` directly.
- **No shared mutable state across steps** — each step is independent.
- **`RunbookResult` fields must never carry content** — structural correlation only.

---

## Invariant and Test Implications

The following must be verifiable through automated tests:

1. Runbook construction rejects empty step lists.
2. Runbook construction rejects step counts above `RUNBOOK_MAX_STEPS`.
3. Runbook construction rejects non-`TaskSpec` step entries.
4. `Runbook` is serialisable to and from dict without data loss.
5. Runner executes steps in declared order (not reversed, not reordered).
6. Runner calls `orchestrator.run()` exactly once per step.
7. Runner does not execute additional steps after a step failure.
8. Runner produces a `RunbookResult` with `terminated_early=True` on failure.
9. Runner produces a `RunbookResult` with correct `failed_step_index` on failure.
10. No output-driven branching — runner does not inspect step result content.
11. No retry — a failed step is not re-executed.
12. `runbook_id`, `task_spec_id`, and `request_id` correlation fields are structural only.
13. All existing M4.2 / M4.4 / M4.6 contracts remain unbroken.

---

## Implementation Order

1. Define `RUNBOOK_MAX_STEPS` constant and `Runbook` schema in `io_iii/core/runbook.py`.
2. Implement `RunbookStepOutcome`, `RunbookResult`, and `run()` in `io_iii/core/runbook_runner.py`.
3. Add focused tests in `tests/test_runbook_m47.py`.
4. Update `DOC-ARCH-012` to mark M4.7 in progress.
5. Update `SESSION_STATE.md` to reflect M4.7 implementation started.

CLI runbook execution is explicitly out of scope for M4.7.

---

## Consequences

### Positive

- Establishes a hard bounded ceiling on IO-III's maximum orchestration complexity.
- Enables sequential multi-step runs without introducing agent behaviour.
- Preserves all existing ADR-012 and ADR-009 guarantees.
- Makes composition deterministic, inspectable, and testable.
- Prevents open-ended workflow creep by design.

### Negative

- No inter-step data passing — each step must be fully self-contained.
- No recovery from step failures — the runbook terminates unconditionally.
- No dynamic step count — caller must declare all steps upfront.

### Neutral

- Step ceiling of 20 is a governance decision. Increasing it requires a future ADR update.
- Runbook serialisation is structural (dict/YAML) only — not a persistent format.

These trade-offs are acceptable. They preserve IO-III's governance-first character.

---

## Alternatives Considered

### 1. Allow output-driven conditional step selection

Rejected. Any output-driven step selection begins to shift the system toward agent
behaviour. ADR-012 forbids output-driven routing changes; this ADR preserves that
constraint at the runbook level.

### 2. Allow retry on transient step failure

Rejected. Retry logic belongs in a separate retry subsystem if ever introduced. The
runbook layer is coordination only. Adding retry here would widen its contract beyond
coordination into recovery semantics.

### 3. Allow inter-step data passing (result chaining)

Rejected. Passing step results as inputs to subsequent steps introduces implicit
dependency graphs and output-content inspection. Both are forbidden by this contract.

### 4. Make the step ceiling configurable at construction time

Rejected. A configurable ceiling is not a ceiling — it is a parameter. The ceiling
must be a constant to remain a hard architectural bound.

---

## Relationship to Other ADRs

- **ADR-009** — bounded execution per step. Preserved unchanged per `orchestrator.run()`.
- **ADR-012** — orchestration layer contract. This ADR fully subordinates itself to it.
- **ADR-013** — failure semantics. `RuntimeFailure` is used to capture step failures.
- **ADR-014** (this document) — defines the runbook coordination layer above ADR-012.

---

## Decision Summary

IO-III will adopt a bounded runbook layer in Phase 4 M4.7.

This layer will:

- accept an immutable, serialisable, finite list of `TaskSpec` steps
- enforce an explicit step ceiling of `RUNBOOK_MAX_STEPS = 20`
- execute steps strictly in declared order via `orchestrator.run()`
- terminate deterministically on step failure with no retry
- produce a bounded, content-safe `RunbookResult`
- add no planner semantics, no branching, no recursion, no kernel mutation

This decision preserves IO-III as a governed execution architecture and establishes
the maximum orchestration complexity ceiling for Phase 4.