---
id: DOC-ARCH-013
title: Phase 5 Guide | Runtime Observability & Optimisation
type: architecture
status: active
version: v0.1
canonical: true
scope: phase-5
audience: developer
created: "2026-04-11"
updated: "2026-04-11"
tags:
- io-iii
- phase-5
- architecture
- observability
roles_focus:
- executor
- challenger
provenance: io-iii-runtime-development
---

# Phase 5 Guide | Runtime Observability & Optimisation

## Purpose

Phase 5 introduces measurement and governance signals into the IO-III runtime
without expanding its execution surface.

The execution stack (routing, engine, context assembly, capability registry,
runbook runner, replay/resume) is **frozen**. Phase 5 operates *alongside* it,
not above or inside it.

The purpose of this phase is to improve visibility into runtime behaviour and
enforce pre-execution cost constraints — not to introduce new orchestration
semantics, memory systems, or execution paths.

---

## Invariants That Must Remain True

- deterministic routing (ADR-002)
- bounded execution (ADR-009: max 1 audit pass, max 1 revision pass)
- explicit capability invocation only
- content-safe logging — no prompts, no model output (ADR-003)
- no agent behaviour
- no recursion
- no dynamic routing
- no output-driven routing or branching
- all Phase 1–4 invariants preserved in full

---

## What Phase 5 May Add

- a token pre-flight estimator that runs before model invocation
- structured execution telemetry fields attached to existing result objects
- a constellation integrity guard that validates architecture-level constraints
  against runtime configuration at execution time
- new content-safe metadata fields in `metadata.jsonl` (counts and durations
  only — no content)

---

## What Phase 5 Must Not Add

- new execution paths or engine entry points
- persistent session state or cross-run history
- memory systems or retrieval mechanisms
- dynamic routing based on telemetry signals
- autonomous retry or remediation behaviour
- new CLI subcommands beyond telemetry inspection
- output-driven branching or adaptive execution

---

## Cross-Phase Dependency

M5.1 (token pre-flight estimator) is a **prerequisite for Phase 6 M6.4**
(memory injection via context assembly). Memory injection adds tokens to the
context window; without a pre-flight bound in place, injection cannot be
safely constrained.

This dependency must be noted in the Phase 6 ADR when M6.4 is formalised.

---

## Milestones

### M5.0 — Phase 5 ADR and Milestone Definition

Author ADR-021: Runtime Observability & Optimisation contract.
Define all Phase 5 milestones formally in SESSION_STATE.md.
Set the governance freeze boundary above the M4.11 replay/resume layer.
Tag v0.4.0 if not already applied.

---

### M5.1 — Token Pre-flight Estimator

Introduce a token estimation function that runs before model invocation.

#### M5.1 Purpose

- prevent oversized context calls reaching the provider
- enforce thin prompt discipline at the execution boundary

#### M5.1 Contract

- estimation runs after context assembly, before provider call
- estimation is non-blocking: raises a bounded failure if limit exceeded
- estimator is heuristic-based (character/word count) — no tokenizer dependency
- limit is configurable via runtime config; no hardcoded ceiling
- failure code: `CONTEXT_LIMIT_EXCEEDED` under `contract_violation` kind (ADR-013)
- no prompt content logged on failure — count and limit only

**Cross-phase note:** This milestone is a prerequisite for Phase 6 M6.4.

---

### M5.2 — Execution Telemetry Metrics

Add structured performance fields to the execution result surface.

#### M5.2 Fields

- `call_count` — number of provider calls in the execution
- `input_tokens` — estimated input token count (from M5.1 estimator)
- `output_tokens` — token count of provider response where available
- `latency_ms` — total execution duration (already present in SessionState; formalised here)
- `model_used` — resolved model identifier from routing

#### M5.2 Contract

- fields attached to `ExecutionResult.meta` under a `telemetry` key
- all fields are counts or durations — no content
- fields projected to `metadata.jsonl` under content-safe policy (ADR-003)
- `output_tokens` is best-effort: populated if provider returns it, `null` otherwise

---

### M5.3 — Constellation Integrity Guard

Introduce a configuration-time integrity check that detects architecture drift
in the model constellation.

#### M5.3 Purpose

- enforce that distinct roles are not silently collapsed onto the same model
- detect call chain configurations that violate bounded execution constraints
- surface drift before execution rather than after

#### M5.3 Example Signals

- executor and challenger resolved to the same model
- runbook step count approaching or exceeding `RUNBOOK_MAX_STEPS`
- provider config missing required role-to-model bindings

#### M5.3 Contract

- guard runs at CLI startup after config load, before routing resolution
- guard is a validation pass only — no remediation, no retry
- failures raise a `contract_violation` with a stable `CONSTELLATION_DRIFT` code
- guard is bypassable via `--no-constellation-check` for offline/CI use
- no runtime-state data consumed — config layer only

---

## Definition of Done

Phase 5 is complete when:

- ADR-021 accepted and indexed
- M5.1 token estimator integrated and tested
- M5.2 telemetry fields present in `ExecutionResult.meta` and `metadata.jsonl`
- M5.3 constellation guard active at CLI startup
- `pytest` passing
- invariant validator passing
- SESSION_STATE.md updated with phase close state
- repository tagged `v0.5.0`