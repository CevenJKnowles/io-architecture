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

## Phase 6 — Memory Architecture (Complete)

**Status: Complete. Governed by DOC-ARCH-014.**

Phase 6 introduced governed, deterministic memory into the IO-III runtime. The execution
stack remained frozen. Memory is a governed input to context assembly, not a new
execution layer.

Milestones: M6.0–M6.7 delivered (memory store, packs, retrieval policy, injection, safety
invariants, write contract, SessionState snapshot export). Tagged v0.6.0.

**Cross-phase note:** M6.7 is a prerequisite for Phase 8 M8.3 (session shell `continue`
command). The session shell requires a portable session object to resume from.

---

## Phase 7 — Initialisation & Distribution Layer (Complete)

**Status: Complete. Governed by DOC-ARCH-015.**

Phase 7 made the IO-III runtime distributable and self-initialising for external users.
It formalised the boundary between structural artefacts (owned by the architecture) and
configurable values (owned by the user).

Milestones: M7.0–M7.5 delivered (init contract, init command, default templates including
a `chat_session.yaml` session template, portability validation pass with
`PORTABILITY_CHECK_FAILED` failure code, Work Mode / Steward Mode ADR-024). Tagged v0.7.0.

**Cross-phase note:** M7.5 (ADR-024 — Work Mode / Steward Mode) is a prerequisite for
Phase 8 M8.1 (implementation). ADR accepted. Phase 8 may begin.

---

## Phase 8 — Governed Dialogue Layer (Complete)

**Status: Complete. Tagged v0.8.0.**

Phase 8 made IO-III conversational. It introduced a bounded dialogue loop above the frozen
execution stack, using all prior infrastructure (memory, session snapshots, replay/resume,
telemetry) as its substrate. The execution stack was not modified.

Milestones:

- M8.1 — Work Mode / Steward Mode (`SessionMode`, `StewardGate`, `StewardThresholds`;
  `session_mode` field added to `SessionState`)
- M8.2 — Bounded session loop (`DialogueSession`, `TurnRecord`, `run_turn()`; hard
  `SESSION_MAX_TURNS` ceiling; steward gate at each turn boundary)
- M8.3 — Session shell CLI (`session start`, `session continue`, `session status`,
  `session close`; content-safe turn output; pause/approve/redirect/close flow)
- M8.4 — Steward approval gates (combined with M8.1; `PauseState`, `ModeTransitionEvent`,
  threshold-gated pauses with `approve` / `redirect` / `close` user actions)
- M8.5 — Conditional runbook branches (`WhenCondition`, `RunbookStep`, `ConditionalRunbook`,
  `WhenContext`, `run_with_context()`; `when:` evaluated against structural fields only;
  max 1 branch level structurally enforced)
- M8.6 — Session continuity via memory (`SessionMemoryContext`, `load_session_memory()`;
  `pack.io_iii.session_resume` auto-loaded on `session continue`; `TurnRecord.memory_keys_loaded`)

Tagged: v0.8.0. Test count at close: 916 passing.

---

## Phase 9 — API & Integration Surface (Planned)

**Status: Planned. ADR to be authored at M9.0.**

Phase 9 wraps the existing CLI and session layer in a thin, content-safe HTTP surface.
No new execution semantics. All invariants preserved. The API is a transport adapter only.

Milestones:

- M9.0 — Phase 9 ADR + milestone definition; API-as-transport-adapter contract established
- M9.1 — HTTP API layer (`POST /run`, `POST /runbook`, `POST /session/start`,
  `POST /session/{id}/turn`, `GET /session/{id}/state`, `DELETE /session/{id}`)
- M9.2 — Event streaming (Server-Sent Events on `/session/{id}/stream`; content-safe
  event schema; no raw model output in events)
- M9.3 — External integration contracts (webhooks on `SESSION_COMPLETE`,
  `RUNBOOK_COMPLETE`, `STEWARD_GATE_TRIGGERED`; content-safe payloads)
- M9.4 — CLI surface improvements (`--output json` flag; structured exit codes;
  machine-readable output for shell pipeline and CI/CD integration)
- M9.5 — Self-hosted web UI (thin frontend over M9.1 API + M9.2 SSE streaming;
  chat-style session interface; governed entry point only — all requests route
  through the session layer; no execution bypass permitted)

Target: v0.9.0.

---

## Non-Goals (Active)

The following remain explicitly out of scope across all phases:

- Retrieval systems (embedding-based search or ranking)
- Auto-audit policies
- Dynamic routing (output-driven or telemetry-driven)
- Multi-model arbitration
- Autonomous meta-agents
- Recursive orchestration
- Memory values in any log field

Items previously listed as non-goals that are now phased:

- Persistent memory → Phase 6
- Steward mode → Phase 7 (ADR) / Phase 8 (implementation)
- API surface → Phase 9

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