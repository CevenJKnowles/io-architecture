---
id: "DOC-ARCH-002"
title: "IO-III Structural Elevation Roadmap"
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
  - "sequencing"
  - "governance"
roles_focus:
  - "synthesizer"
  - "executor"
  - "governance"
provenance: "human"
---

## Purpose

This document defines the sequencing discipline for IO-III architectural evolution.

It prevents premature capability expansion and ensures governance-first progression.

This is a structural roadmap, not a feature roadmap.

---

## Current State (Phase 1 — Deterministic Core)

IO-III currently provides:

- Deterministic routing
- Provider resolution
- Optional bounded audit gate
- Unified output
- Invariant validation
- Metadata logging policy (content disabled)

Characteristics:

- No persistent memory
- No retrieval
- No autonomous orchestration
- No dynamic arbitration
- No multi-model reasoning loops

The system is structurally stable.

---

## Phase 2 — Structural Consolidation

Objectives:

1. Define `SessionState` v0 (definition only).
2. Extract execution engine from CLI.
3. Introduce Context Assembly Layer (ADR-010).

Constraints:

- No behavioural expansion.
- No new capability surfaces.
- No autonomy.
- Determinism preserved.

This phase introduces clean abstraction boundaries without expanding scope.

---

## Phase 3 — Envelope Sophistication (Deferred)

Only after Phase 2 freeze:

Potential future considerations:

- Structured prompt envelopes
- Role registry abstraction
- Deterministic capability exposure
- Token estimation utilities (non-enforcing)
- Expanded telemetry schema

Still excluded:

- Persistent memory
- Retrieval systems
- Autonomous loops

---

## Phase 4 — Post-Capability Architecture Layer (Complete)

**Status: Complete. ADR-012 governs the bounded orchestration layer contract.**

Phase 4 introduces a bounded orchestration layer above the frozen runtime kernel.
It does not introduce memory systems, retrieval, or autonomous capability expansion
as originally deferred here. The scope is strictly bounded by ADR-012.

Governed surface:

- bounded orchestration (ADR-012)
- explicit task specifications (`TaskSpec`)
- deterministic failure model (ADR-013)
- bounded multi-step runbook layer (ADR-014, M4.7)
- runbook traceability and metadata correlation (ADR-015, M4.8)
- CLI runbook execution surface (ADR-016, M4.9)
- replay/resume upper boundary freeze (ADR-017, M4.10)
- run identity contract — `run_id` UUIDv4, lineage via `source_run_id` (ADR-018, M4.10)
- checkpoint persistence contract — local JSON, deterministic lookup by `run_id` (ADR-019, M4.10)
- replay/resume execution contract — bounded replay from step 0, resume from first incomplete step (ADR-020, M4.10)
- replay/resume layer implementation — `replay_resume.py`, CLI subcommands, checkpoint I/O (M4.11 — Phase 4 closed)

This phase must never expand beyond the ADR-012 contract without a new explicit ADR.

---

## Governance Principle

IO-III evolves by:

Stability → Abstraction → Freeze → Expand

Not by:

Feature Accumulation → Refactor → Complexity Inflation

Each phase requires:

- Clean test state
- Invariant validation
- Explicit ADR coverage
- Deterministic guarantees

---

## Explicit Non-Goals (Current)

The following are explicitly out of scope at present:

- Retrieval systems (embedding-based search or ranking)
- Verification modules
- Auto-audit policies
- Dynamic routing (output-driven or telemetry-driven)
- Multi-model arbitration
- Autonomous meta-agents
- Recursive orchestration

Items previously listed as non-goals that are now phased:

- Persistent memory → Phase 6 (governed memory architecture)
- Steward mode → Phase 7 ADR / Phase 8 implementation
- API surface → Phase 9

---

## Summary

This roadmap formalises sequencing discipline.

It ensures IO-III remains:

- Deterministic
- Bounded
- Governance-first
- Structurally intelligible

Future architectural elevation must reference this document before introducing new surfaces.