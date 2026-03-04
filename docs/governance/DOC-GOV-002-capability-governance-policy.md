---
id: "DOC-GOV-002"
title: "Capability Governance Policy"
type: "governance"
status: "active"
version: ""
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-03-04"
updated: "2026-03-04"
tags:
  - "governance"
  - "capabilities"
  - "phase-3"
roles_focus:
  - "governance"
  - "executor"
  - "challenger"
provenance: "human"
---

# Capability Governance Policy

## Purpose

Capabilities are **bounded, explicitly invoked runtime extensions**.
They exist to extend IO-III in carefully controlled ways **without turning it into an agent**.

This policy defines:
- what qualifies as a capability
- how capabilities are identified and registered
- what invariants must hold at runtime
- how capabilities are tested, documented, and evolved

---

## Definitions

- **Capability**: a single, bounded function exposed via an explicit `capability_id` and invoked at most once per execution.
- **Registry**: `CapabilityRegistry` is the sole lookup surface. No discovery, no search, no auto-selection.
- **Invocation**: an explicit engine call: `engine.run(..., capability_id=..., capability_payload=...)`.

---

## Non-goals (capability layer)

Capabilities must **not** become:
- a tool planner
- a multi-step workflow engine
- an auto-router
- a retrieval / RAG pipeline
- a recursive execution surface

---

## Capability requirements

### 1) Deterministic identity

Each capability MUST have a stable ID:
- lowercase
- dot-separated namespace format: `<namespace>.<name>[.<subname>]`
- examples:
  - `text.normalize`
  - `io.fs.readonly_stat`
  - `test.echo` (tests only)

Rules:
- IDs MUST NOT be derived dynamically.
- IDs MUST NOT embed environment-specific values (paths, usernames, timestamps).

### 2) Explicit registration only

A capability MUST be registered in a `CapabilityRegistry` provided via dependency injection:
- `RuntimeDependencies.capability_registry`
- no global registries
- no import-side effects that auto-register

### 3) Single bounded invocation

At runtime, a capability MUST be invoked at most once per `engine.run(...)` call.

Bounds MUST be specified in `CapabilityBounds`:
- `max_calls` (must remain `1` for v0)
- `timeout_ms`
- `max_input_chars`
- `max_output_chars`

Capabilities MUST enforce bounds (or rely on engine enforcement where already present).

### 4) Content safety

Capabilities MUST:
- avoid logging payloads or outputs
- ensure any metadata they return is content-safe
- return structured `CapabilityResult` only

Capabilities MUST NOT:
- store raw prompts/completions/drafts/revisions in logs or metadata
- emit raw content into observability paths

### 5) No recursive surfaces

Capabilities MUST NOT:
- invoke the engine
- access the registry to invoke other capabilities
- trigger provider calls directly unless explicitly designed as a provider-adjacent capability and documented as such

If a capability needs LLM output, the correct pattern is:
- keep it out of the capability layer, or
- define a provider-level extension with ADR coverage (future work)

---

## Documentation requirements

Each non-test capability MUST have:
1. A short entry in the capability registry documentation.
2. A one-paragraph description of:
   - intent
   - bounds rationale
   - allowed failure modes
3. A small example payload shape (schematic, not sensitive content).

---

## Testing requirements

Each capability MUST have at least:
- a contract test that:
  - validates `spec` fields (id/version/category/bounds)
  - validates bounded behavior (input/output size, call count)
- an engine integration test that:
  - confirms explicit invocation attaches `ExecutionResult.meta["capability"]`
  - confirms behavior when `capability_id` is missing/unknown

---

## Versioning and lifecycle

### Versions
- `CapabilitySpec.version` MUST be a stable string (e.g. `v0`, `v1`).
- Breaking changes require a new major version and (preferably) a new capability ID.

### Deprecation
A capability can be deprecated by:
- keeping it registered
- returning `CapabilityResult(ok=False, error=...)` with a clear message
- updating docs to signal removal targets

Removal should only occur with:
- ADR coverage if externally referenced
- a full test + doc sweep

---

## Review checklist

Before merging any new capability:
- [ ] ID follows policy and is stable
- [ ] bounds are explicit and justified
- [ ] no recursion surfaces
- [ ] tests cover contract + engine integration
- [ ] docs updated
- [ ] metadata output is content-safe