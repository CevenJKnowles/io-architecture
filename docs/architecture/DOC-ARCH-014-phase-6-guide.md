---
id: DOC-ARCH-014
title: Phase 6 Guide | Memory Architecture
type: architecture
status: planned
version: v0.1
canonical: true
scope: phase-6
audience: developer
created: "2026-04-11"
updated: "2026-04-12"
tags:
- io-iii
- phase-6
- architecture
- memory
roles_focus:
- executor
- challenger
- governance
provenance: io-iii-runtime-development
---

# Phase 6 Guide | Memory Architecture

## Purpose

Phase 6 introduces governed, deterministic memory into the IO-III runtime.

The execution stack (routing, engine, context assembly, capability registry,
runbook runner, replay/resume) remains **frozen**. Phase 6 introduces memory
as a governed input to context assembly — not as a new execution layer.

The purpose of this phase is to allow curated, scoped context to be injected
into execution without introducing retrieval autonomy, persistent session state,
or dynamic routing.

---

## Invariants That Must Remain True

- deterministic routing (ADR-002)
- bounded execution (ADR-009: max 1 audit pass, max 1 revision pass)
- explicit capability invocation only
- content-safe logging — no prompts, no model output, no memory values (ADR-003)
- no agent behaviour
- no recursion
- no dynamic routing
- memory injection is bounded and deterministic — not retrieval-driven
- all Phase 1–5 invariants preserved in full

---

## Phase Prerequisite

Phase 6 M6.4 (memory injection via context assembly) **requires Phase 5 M5.1**
(token pre-flight estimator) to be complete. Memory injection adds tokens to
the context window. Without a pre-flight bound in place, memory subsets cannot
be safely constrained to the available context budget.

Phase 6 must not begin M6.4 implementation until M5.1 is active and tested.

---

## What Phase 6 May Add

- a governed memory store with atomic, scoped records
- a named memory pack system — curated bundles declared in config
- a deterministic memory retrieval policy gated by route and capability allowlists
- bounded memory injection into `ExecutionContext` via the context assembly layer
- a user-confirmed write path for adding records to the memory store
- content-safe memory logging (counts, keys, and record sizes — never values)

---

## What Phase 6 Must Not Add

- autonomous memory writes — all writes require explicit user confirmation
- retrieval-driven routing or dynamic context selection
- open-ended memory search or embedding-based lookup
- memory values in any log field
- cross-session memory without an explicit scope contract
- memory systems that alter routing or step execution order

---

## Milestones

### M6.0 — Phase 6 ADR and Milestone Definition

Author ADR governing the memory architecture contract.
Define all Phase 6 milestones formally in SESSION_STATE.md.
Confirm Phase 5 M5.1 is complete before proceeding to M6.4.

---

### M6.1 — Memory Architecture Definition

Define the memory store structure and governance rules.

#### M6.1 Properties

- atomic records — each record is a discrete, versioned unit
- scoped access — records are bound to explicit scope identifiers
- deterministic retrieval — lookup is by key, not by search or ranking
- no embedding, no similarity search, no ranking logic

---

### M6.2 — Memory Pack System

Introduce named memory bundles as the primary delivery mechanism for curated
context.

#### M6.2 Properties

- packs are declared in `architecture/runtime/config/memory_packs.yaml`
- each pack is a named, versioned collection of memory record keys
- packs are author-controlled — not runtime-generated
- pack resolution is deterministic from pack name

#### M6.2 Example

`pack.io_iii.session_resume` — curated context for session continuation

#### M6.2 Portability Note

Pack config must use a configurable storage root, not a hardcoded repository
path. This is a Phase 7 prerequisite — see DOC-ARCH-015.

---

### M6.3 — Memory Retrieval Policy

Define access rules governing which routes and capabilities may retrieve which
memory records.

#### M6.3 Rules

- `route_allowlist` — memory access permitted only on declared routes
- `capability_allowlist` — memory access permitted only for declared capabilities
- `sensitivity_classification` — records classified by sensitivity tier;
  higher tiers require explicit allowlist entries

No memory record is accessible by default. Access is opt-in and declared.

---

### M6.4 — Memory Injection via Context Assembly

Inject a bounded memory subset into `ExecutionContext` during context assembly.

**Requires:** Phase 5 M5.1 (token pre-flight estimator) complete.

#### M6.4 Pipeline

```text
memory store
  -> retrieval policy (M6.3)
  -> selector (pack or explicit key list)
  -> bounded subset (token budget enforced via M5.1 estimator)
  -> ExecutionContext.memory
  -> context assembly
```

#### M6.4 Contract

- injection occurs after routing, before provider call
- subset size is bounded by token budget from M5.1
- no memory values appear in logs — counts and key names only
- injection is skipped gracefully if no memory is configured for the route

---

### M6.5 — Memory Safety Invariants

Enforce content-safe memory logging across all memory lifecycle events.

#### M6.5 Allowed Log Fields

```text
memory_keys_released
memory_records_count
memory_total_chars
pack_id
```

#### M6.5 Never Log

```text
memory values
record content
free-text record fields
```

Invariants added to the invariant validator suite.

---

### M6.6 — Memory Write Contract

Define the user-confirmed write path for adding records to the memory store.

#### M6.6 Contract

- all writes require explicit user confirmation — no runtime-initiated writes
- writes are atomic: single record, single operation
- write path is separate from the execution path — no writes during a run
- write produces a stable record identifier for subsequent retrieval
- write failures are surfaced as `contract_violation` failures (ADR-013)
- no memory value is logged on write — key and confirmation status only

---

### M6.7 — SessionState Snapshot Export

Define a governed export/import contract for a portable session artefact.

#### M6.7 Purpose

- enable cross-machine session continuity without requiring a shared file system
- produce a portable, self-describing snapshot that carries workflow position and
  memory pack state
- provide the portability primitive required by Phase 8 M8.3 (`session continue`)

#### M6.7 Contract

- export is user-initiated — no automatic or runtime-triggered exports
- export artefact contains: `run_id`, `workflow_position` (last completed step index),
  `active_memory_pack_ids`, `governance_mode`, `schema_version`
- export artefact never contains memory values, model output, or prompt content
- import validates `schema_version` and all required fields before restoring state
- import failure raises `contract_violation` with a stable `SNAPSHOT_SCHEMA_INVALID` code
- artefact is a single JSON file; path is user-specified or defaults to
  `<root>/<run_id>.snapshot.json`

**Cross-phase note:** This milestone is a prerequisite for Phase 8 M8.3 (session shell
`continue` command). The session shell requires a portable session object to resume from.

---

## Definition of Done

Phase 6 is complete when:

- Phase 6 governing ADR accepted and indexed
- M6.1–M6.6 milestones delivered and tested
- memory injection active and bounded by Phase 5 M5.1
- memory values absent from all log output (invariant validator confirms)
- `pytest` passing
- invariant validator passing
- SESSION_STATE.md updated with phase close state
- repository tagged `v0.6.0`