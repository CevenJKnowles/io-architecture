---
id: "ADR-010"
title: "Context Assembly Layer Definition"
type: "adr"
status: "active"
version: "v1.0"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-03-03"
updated: "2026-03-03"
tags:
  - "architecture"
  - "context"
  - "assembly"
  - "determinism"
roles_focus:
  - "synthesizer"
  - "executor"
  - "governance"
provenance: "human"
---

# ADR-010 — Context Assembly Layer Definition

## Status

Active

## Context

IO-III currently operates under a deterministic control plane:

CLI → routing resolution → provider execution → optional audit gate → unified output.

Prompt construction is implicitly distributed across routing, persona contract injection, and execution logic. As structural complexity increases, this implicit composition risks:

- Boundary ambiguity
- Tight coupling between routing and prompt logic
- Premature feature inflation (memory, tools, arbitration)

To preserve determinism and governance clarity, a formal structural boundary is required.

## Decision

Introduce a **Context Assembly Layer** as a thin, deterministic module responsible solely for constructing the final prompt envelope prior to provider execution.

The Context Assembly Layer will:

1. Accept immutable inputs:
   - SessionState (v0)
   - Route resolution metadata
   - Persona contract payload
   - Explicit user prompt
2. Compose a single structured prompt envelope.
3. Return a final prompt payload for execution.

The layer will NOT:

- Perform retrieval
- Access persistent memory
- Invoke tools
- Modify routing decisions
- Introduce dynamic arbitration
- Execute recursive calls

It is a composition boundary, not a capability layer.

## Rationale

Formalising context assembly:

- Preserves deterministic execution guarantees.
- Creates a clean abstraction seam before future envelope sophistication.
- Prevents premature integration of memory or tool surfaces.
- Improves testability by isolating prompt construction logic.

This aligns with IO-III’s governance-first evolution model.

## Consequences

### Positive

- Clear separation of concerns.
- Reduced coupling between CLI, routing, and prompt logic.
- Foundation for structured envelope expansion (future phase).

### Neutral

- No behavioural change at introduction.
- No runtime surface expansion.

### Explicit Non-Goals (Phase Boundary)

The following are deferred to later phases:

- Persistent memory systems
- Retrieval mechanisms
- Token pre-flight enforcement
- Capability gating logic
- Autonomous orchestration
- Multi-model arbitration

## Implementation Sequence

1. Define SessionState v0 (structural only).
2. Extract execution engine from CLI.
3. Introduce Context Assembly Layer (definition + wiring).
4. Freeze.
5. Only then consider envelope sophistication.

This ADR defines the boundary only. It does not introduce behavioural changes.