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
updated: "2026-04-12"
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

## Phase 4 — Post-Capability Architecture Layer (Complete)

**Status: Complete. Governed by ADR-012.**

Phase 4 introduces a bounded orchestration layer above the frozen runtime kernel.
Scope is strictly bounded by ADR-012. It does not introduce the capability expansion
categories deferred here — those remain out of scope.

All milestones complete: M4.0–M4.11 delivered. Phase 4 closed. Tagged v0.4.0.

---

## Phase 5 — Runtime Observability and Optimisation (Complete)

**Status: Complete. Governed by ADR-021.**

Phase 5 introduced measurement and governance signals without expanding the execution
surface. All three milestones delivered: M5.0 (governance freeze), M5.1 (token
pre-flight estimator), M5.2 (execution telemetry), M5.3 (constellation integrity guard).
Tagged v0.5.0.

A post-phase hardening pass was performed after close (2026-04-12):

- 96 tests added (test gaps in context_assembly, routing fallback, engine revision paths)
- `_heuristic_input_tokens` renamed to `_heuristic_char_count` for precision
- `_do_challenger_pass` and `_do_revision` extracted from `engine.run()`
- `mypy` and `ruff` added to dev tooling; `pytest` testpaths declared

Test count after hardening: 515 passing (was 419 at phase close).

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