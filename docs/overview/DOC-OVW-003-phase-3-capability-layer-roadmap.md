---
id: DOC-OVW-005
title: IO-III Session Snapshot — Phase-3 Capability Layer — 2026-03-04
type: overview
status: active
version: 1.0.0
canonical: true
scope: repository
audience:
  - developers
  - reviewers
created: "2026-03-04"
updated: "2026-03-04"
tags:
  - io-iii
  - architecture
  - governance
  - capability-layer
  - phase-3
roles_focus:
  - systems-architect
  - runtime-engineer
provenance: session snapshot (authoritative only for stated date)
---

# IO-III Session Snapshot — 2026-03-04

## Purpose

This document captures the **current architectural state** of the IO-III repository as of **2026-03-04**.

It is intended to:
- reduce re-orientation cost across sessions
- provide a reviewable checkpoint for collaborators
- preserve architectural intent while Phase 3 is in progress

---

## System Definition

IO-III is a **governance-first deterministic runtime** for **local LLM orchestration**.

It is intentionally minimal and bounded.

It is **not** an agent system.

The runtime functions as a **control-plane execution engine**.

### Core principles

- deterministic routing
- bounded execution
- explicit dependency injection
- invariant-protected architecture
- ADR-driven governance
- content-safe observability
- explicit capability invocation only

### Explicitly avoided

- autonomous behaviour
- tool selection planning
- recursive orchestration
- dynamic routing
- multi-step agent loops

---

## Hard invariants

### Determinism

- no dynamic routing
- no autonomous capability selection
- no recursion surfaces

### Execution bounds (ADR-009)

- `MAX_AUDIT_PASSES = 1`
- `MAX_REVISION_PASSES = 1`

### Capability bounds

- `max_calls = 1`
- explicit invocation only
- bounded payload
- bounded output

### Content-safe logging

Logs must never contain prompts or model outputs.

Forbidden fields:

- `prompt`
- `completion`
- `draft`
- `revision`
- `content`

Allowed (examples):

- `prompt_hash`
- `latency`
- `route`
- `provider`
- `model`
- audit metadata
- capability summary metadata

---

## Repository structure

Two layers exist.

### 1) Governance / architecture layer

- `ADR/`
- `docs/`
- `history/`
- `ARCHITECTURE.md`
- `README.md`
- `architecture/runtime/*` (config, tests, scripts, logs)

These define the architectural contract.

### 2) Runtime implementation

- `io_iii/`
  - `cli.py`
  - `config.py`
  - `routing.py`
  - `metadata_logging.py`
  - `persona_contract.py`

- `io_iii/core/`
  - `engine.py`
  - `execution_context.py`
  - `session_state.py`
  - `context_assembly.py`
  - `capabilities.py`
  - `dependencies.py`
  - `execution_trace.py`

- `io_iii/providers/`
  - `provider_contract.py`
  - `null_provider.py`
  - `ollama_provider.py`

Tests:

- `io_iii/tests/`
- `tests/`

---

## Runtime execution pipeline

CLI\
↓\
RuntimeDependencies\
↓\
Execution Engine\
↓\
ExecutionContext\
↓\
Context Assembly\
↓\
Provider\
↓\
Optional Challenger\
↓\
ExecutionResult\
↓\
Metadata Logging


---

## Development status

### Phase 1 — Control Plane Stabilisation

Complete.

Includes:

- deterministic routing
- challenger enforcement
- invariant validation
- regression tests

### Phase 2 — Structural Consolidation

Complete.

Includes:

- execution engine extraction
- CLI → engine boundary
- SessionState v0
- ExecutionContext
- context assembly
- dependency injection seams
- deterministic runtime pipeline

### Phase 3 — Capability Layer

Current phase.

Goal:

Introduce capabilities as bounded extensions without compromising determinism.

Implemented milestone elements (verify in-repo):

- capability contracts: `io_iii/core/capabilities.py`
- provider contract hardening: `io_iii/providers/provider_contract.py`
- metadata logging schema: `io_iii/metadata_logging.py`
- dependency injection seams: `io_iii/core/dependencies.py`
- capability invocation: `io_iii/core/engine.py` (`engine.run(..., capability_id=...)`)
- structured execution traces: `io_iii/core/execution_trace.py`
- reference capability: `cap.echo_json`
- CLI capability listing: `python -m io_iii capabilities`
- content safety guardrails for logs

---

## Session change summary (2026-03-04)

### Fix applied: capability module import stability

Issue:

Capability layer tests failed due to a **syntax/import failure** originating in `io_iii/core/capabilities.py`.

Root cause:

Escaped triple-quote docstrings:

- `\"\"\" ... \"\"\"`

Impact:

- module import failure
- downstream CLI/test failures via collection/import cascade

Fix:

Corrected docstrings in:

- `CapabilitySpec.id`
- `CapabilityRegistry.list_capabilities`

Outcome:

- `python -m pytest` passes

---

## Next planned work

Recommended order (Phase 3 completion path):

### M3.13 — Capability execution trace integration

Add structured trace fields (no payload/output logging):

- `capability_id`
- `duration_ms`
- `success`
- `error_code`

### M3.15 — Capability bounds enforcement

Enforce:

- `max_calls`
- `max_input_chars`
- `max_output_chars`
- `timeout_ms`

Target area:

- `io_iii/core/engine.py`

### M3.16 — CLI capability invocation

Add explicit CLI command (no selection logic):
`python -m io\_iii capability cap.echo\_json '{"x":1}'`


Constraints:

- explicit invocation only
- strict JSON payload
- bounded execution
- deterministic output shape (as `ExecutionResult`)

---

## Verification checklist (for next session)

Run from repo root:

1. `tree -a -I ".git|__pycache__|*.pyc|.pytest_cache"`
2. `python -m pytest`
3. `python -m io_iii capabilities`
4. Confirm metadata logs contain no forbidden fields.

Expected:

- all tests pass
- capability list includes at least `cap.echo_json`
- logs remain content-safe