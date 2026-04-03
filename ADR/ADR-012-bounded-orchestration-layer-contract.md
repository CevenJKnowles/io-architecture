---
id: ADR-012
title: Bounded Orchestration Layer Contract
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
  - orchestration
  - bounded-execution
roles_focus:
  - executor
  - challenger
provenance: io-iii-runtime-development
---

# ADR-012 — Bounded Orchestration Layer Contract

## Status

Accepted

## Context

IO-III Phase 3 established the bounded runtime kernel:

- deterministic routing
- explicit capability invocation
- bounded engine execution
- content-safe metadata logging
- challenger enforcement under ADR-009
- execution trace and session state foundations

This kernel is intentionally small and governance-first. It exists to prove that routing, execution, challenger review, and observability can remain deterministic, bounded, and inspectable without drifting into agent behaviour.

Phase 4 introduces the next architectural layer above this kernel. The objective is to support explicit task execution contracts and bounded composition while preserving all existing invariants.

Without a formal contract, any orchestration addition creates architectural risk. In particular, it could introduce:

- planner behaviour
- runtime branching
- recursion
- output-driven route changes
- hidden multi-step loops
- workflow-engine creep

A formal decision is therefore required before any orchestration layer is implemented.

---

## Decision

IO-III will introduce a **bounded orchestration layer** above the frozen runtime kernel.

This layer is defined by the following contract:

1. The orchestration layer may accept a declarative execution contract such as a `TaskSpec`.
2. A `TaskSpec` must resolve to exactly one static route from declared mode.
3. Route resolution must remain table-driven and deterministic.
4. Runtime outputs must never alter routing.
5. A single orchestrated execution may perform:
   - one executor pass
   - one optional challenger pass
6. The orchestration layer must not introduce:
   - recursion
   - planner logic
   - heuristic routing
   - output-driven branching
   - autonomous tool selection
   - uncontrolled multi-step execution
7. The orchestration layer must remain a coordination layer, not a reasoning layer.
8. The existing runtime kernel remains frozen during Phase 4 and is extended only by adding a layer above it.

This means Phase 4 does **not** convert IO-III into an agent. It adds a deterministic contract for bounded execution.

---

## Scope Boundary

This ADR covers:

- single-run orchestration based on a declarative task contract
- deterministic route resolution from declared mode
- orchestration above the existing engine boundary
- preservation of ADR-002 and ADR-009 guarantees
- the architectural ceiling for future Phase 4 work

This ADR does **not** cover:

- open-ended workflow execution
- autonomous planning
- self-directed task decomposition
- adaptive routing based on generated outputs
- recursive or self-extending execution
- branching orchestration semantics

Bounded multi-step runbooks may be introduced later in Phase 4, but only under a separate explicit contract and only as a fixed-order, finite, non-branching extension.

---

## Constraints

The bounded orchestration layer must preserve the following constraints:

- **Deterministic routing** remains governed by ADR-002.
- **Bounded execution** remains governed by ADR-009.
- **Explicit capability invocation only** remains required.
- **Content-safe logging** remains mandatory. Prompts and model outputs must not be stored in logs.
- **No agent behaviour** remains a hard boundary.
- **No recursion** remains a hard boundary.
- **No dynamic routing** remains a hard boundary.
- **No output-driven orchestration changes** are permitted.

These are architectural constraints, not implementation suggestions.

---

## Kernel Preservation Rule

The following runtime kernel components are frozen for Phase 4 and must be treated as stable substrate:

- routing
- engine
- context assembly
- capability registry

Phase 4 may compose these components through an orchestration layer, but must not alter their architectural role or behavioural contract unless governed by a separate ADR and explicit milestone decision.

---

## Required Properties of `TaskSpec`

Any `TaskSpec` introduced under this ADR must satisfy all of the following:

- serialisable
- declarative
- schema-validated
- deterministic in route resolution
- bounded to one execution path
- free of loops, branching, and planner semantics
- linkable to session state through a stable identifier when applicable

A `TaskSpec` is therefore an execution contract, not a workflow language.

---

## Lifecycle Implications

The orchestration layer may create or enrich lifecycle information for:

- `SessionState`
- `ExecutionTrace`
- metadata projections

However:

- lifecycle tracking must remain explicit
- transitions must be finite and valid
- orchestration must not hide or compress execution stages in ways that reduce inspectability

The trace remains the canonical runtime record.
Metadata logs remain content-safe projections of allowed runtime facts.

---

## CLI Implications

Phase 4 may expose orchestration through CLI surfaces such as task execution commands.

Any such CLI surface must:

- preserve deterministic behaviour
- validate inputs before execution
- support dry-run inspection where applicable
- avoid introducing hidden execution paths
- remain compatible with offline and CI use

The CLI is allowed to expose orchestration. It is not allowed to invent orchestration semantics beyond this ADR.

---

## Consequences

### Positive

- establishes a clear architectural ceiling for Phase 4
- allows reusable declarative task execution
- preserves boundedness and inspectability
- improves reproducibility of runtime behaviour
- creates a clean bridge from kernel execution to controlled composition
- strengthens public architecture signal by demonstrating disciplined orchestration without agent drift

### Negative

- limits flexibility by design
- excludes adaptive workflow behaviour
- prevents output-driven optimisation paths
- may require additional explicit ADRs for any future increase in orchestration complexity

### Neutral

- pushes more design effort into contracts and schemas
- increases documentation and invariant burden
- makes Phase 4 governance heavier than a feature-first implementation approach

These are acceptable trade-offs. They align with IO-III’s stated purpose.

---

## Non-Goals

The bounded orchestration layer is not intended to provide:

- agent autonomy
- planning
- self-correction loops beyond ADR-009 bounds
- tool discovery
- dynamic capability selection
- conditional workflow branching
- long-running process management
- general-purpose automation engine behaviour

If those capabilities are ever considered in future, they must be treated as a separate architectural direction and must not be smuggled into IO-III under the label of orchestration.

---

## Invariant Impact

This ADR implies the need for Phase 4 invariants that verify:

- a `TaskSpec` resolves to exactly one route
- orchestration never exceeds declared bounds
- runtime outputs do not alter route or step order
- no orchestration step mutates routing configuration
- any future runbook step order remains fixed and non-branching

These invariants must be enforceable through tests and invariant specifications, not left as documentation-only claims.

---

## Implementation Guidance

Phase 4 implementation should proceed in this order:

1. define and freeze orchestration contract
2. define `TaskSpec` schema
3. implement single-run orchestration
4. formalise execution trace lifecycle
5. strengthen `SessionState` lifecycle semantics
6. add observability timing fields
7. only then consider bounded fixed-order runbooks under separate policy

This order preserves architectural clarity and reduces drift risk.

---

## Alternatives Considered

### 1. Add orchestration directly inside the engine

Rejected.

This would blur the engine boundary, weaken kernel clarity, and make later governance harder.

### 2. Allow limited output-driven next-step decisions

Rejected.

Even limited output-driven branching begins to shift the system from deterministic orchestration toward agent behaviour.

### 3. Introduce a planner with hard ceilings

Rejected.

Hard ceilings do not solve the core issue. Planner semantics still change the architectural nature of the system.

### 4. Postpone orchestration entirely

Rejected.

Phase 4 needs a controlled architectural layer above capabilities. Avoiding orchestration entirely would stall the roadmap and leave the system without a declarative execution contract.

---

## Relationship to Other ADRs

- **ADR-002** remains the authority for deterministic routing and route policy.
- **ADR-009** remains the authority for bounded audit and revision behaviour.
- **ADR-012** defines the orchestration layer that must operate within those existing boundaries.
- Any future ADR covering fixed-order runbooks must subordinate itself to this contract and must not weaken it.

---

## Decision Summary

IO-III will adopt a bounded orchestration layer in Phase 4.

This layer will:

- remain above the frozen runtime kernel
- execute declarative task contracts deterministically
- preserve all existing boundedness guarantees
- forbid recursion, branching, planning, and dynamic routing
- strengthen composition without changing the architectural nature of the system

This decision preserves IO-III as a governed execution architecture rather than allowing it to drift into an agent framework.