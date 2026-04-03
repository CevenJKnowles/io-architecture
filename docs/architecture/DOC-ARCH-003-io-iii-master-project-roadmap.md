---
id: "DOC-ARCH-003"
title: "IO-III Master Project Roadmap"
type: "architecture"
status: "active"
version: "v1.0"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-03-03"
updated: "2026-04-03"
tags:
  - "architecture"
  - "roadmap"
  - "governance"
  - "sequencing"
roles_focus:
  - "synthesizer"
  - "executor"
  - "governance"
provenance: "human"
---

## Purpose

This document defines the authoritative roadmap for IO-III development.

It consolidates:

- Deterministic runtime foundations
- Structural abstraction sequencing
- Governance boundaries
- Explicit non-goals
- Long-term architectural elevation constraints

This roadmap governs scope decisions.

---

## Phase 1 — Deterministic Core (Complete)

### Objectives

- Deterministic routing
- Provider resolution
- Challenger enforcement
- Audit gate with bounded passes
- Unified output surface
- Invariant validation
- Metadata logging policy
- Canonical documentation discipline
- YAML automation
- ADR sequencing discipline

### State

Stable.
Frozen.
No behavioural expansion.

---

## Phase 2 — Structural Consolidation (Complete)

### Steps

1. Define `SessionState v0` (definition only).
2. Extract execution engine from CLI.
3. Implement Context Assembly Layer (ADR-010).
4. Freeze.

### Constraints

- No behavioural expansion.
- No memory systems.
- No retrieval.
- No arbitration.
- No autonomy.
- Determinism preserved.

### Deliverables

- `io_iii/runtime/session_state.py`
- `io_iii/runtime/engine.py`
- `io_iii/runtime/context_assembly.py`
- Structural tests (non-behavioural)

---

## Phase 3 — Envelope Sophistication (Deferred)

Only after Phase 2 freeze.

Potential work:

- Structured prompt envelopes
- Role registry abstraction
- Deterministic capability exposure
- Token estimation utilities (non-enforcing)
- Telemetry schema refinement

Still excluded:

- Persistent memory
- Retrieval systems
- Autonomous tool loops

---

## Phase 4 — Post-Capability Architecture Layer (Active)

**Status: Active as of 2026-04-03. Governed by ADR-012.**

Phase 4 introduces a bounded orchestration layer above the frozen runtime kernel.
Scope is strictly bounded by ADR-012. It does not introduce the capability expansion
categories deferred here — those remain out of scope.

Active milestones: M4.0–M4.10 complete. M4.11 next (implementation-safe; all prerequisite ADRs accepted).

This phase must never expand beyond its ADR-governed surface.

---

## Governance Invariants

At all times IO-III must remain:

- Deterministic
- Bounded
- Auditable
- Non-autonomous
- Explicitly versioned
- Invariant-validated

No structural change without ADR.

No feature expansion without phase approval.

---

## Non-Goals (Active)

The following remain explicitly out of scope:

- Persistent memory implementation
- Retrieval systems
- Verification modules
- Auto-audit policies
- Dynamic routing
- Multi-model arbitration
- Autonomous meta-agents
- Recursive orchestration

---

## Evolution Model

IO-III evolves by:

Stability → Abstraction → Freeze → Expand

Never by uncontrolled feature accumulation.

---

## Review Discipline

Before introducing new architectural surfaces:

1. Check Phase alignment.
2. Check ADR coverage.
3. Check invariant impact.
4. Check determinism.
5. Check bounded execution.

If any of these fail, expansion is deferred.

---

## Summary

This roadmap formalises IO-III's evolution discipline.

It protects architectural clarity, sequencing integrity, and governance-first design.

All future development must reference this document.