---
id: DOC-ARCH-006
title: IO-III Execution Observability (Content-Safe Trace)
type: architecture
status: active
version: v1.0
canonical: true
scope: io-iii
audience: engineers
created: "2026-03-04"
updated: "2026-03-04"
tags:
  - architecture
  - runtime
  - observability
  - trace
roles_focus:
  - executor
  - challenger
provenance: human
---

# IO-III Execution Observability (Content-Safe Trace)

---

## Purpose

IO-III provides **content-safe observability** via a structured execution trace.

The trace exists to support:

- deterministic debugging (what stage ran, in what order)
- performance profiling (per-stage timing)
- governance auditing (whether bounded audit/revision ran)

The trace must preserve IO-III’s architectural constraints:

- deterministic routing
- bounded execution
- explicit invocation only
- no autonomous behaviour

---

## Scope

The execution trace is **engine-local** and is attached to the user-facing result:

- `ExecutionResult.meta["trace"]`

It is not a content log.

---

## Content-Safety Rules

The trace must never include:

- user prompts
- assembled prompts
- model outputs
- drafts or revisions
- capability output payloads

Allowed trace metadata is structural only:

- stage identifiers
- provider name / model identifier
- booleans (audit enabled)
- stable error codes
- durations

---

## Architectural Integration

Trace recording is implemented as a passive recorder.

Constraints:

- the trace must not affect execution decisions
- no branching depends on trace state
- trace recording must be bounded and small

The engine records steps in deterministic order for a given execution path.

Example (null route):

1. `provider_run`

Example (ollama route):

1. `context_assembly`
2. `provider_inference`
3. `challenger_audit` (optional)
4. `revision_inference` (optional)

Capability invocation (if explicitly requested) is recorded as:

- `capability_invoke`

---

## Contracts

The canonical schema for the trace is defined in:

- `docs/runtime/DOC-RUN-005-execution-trace-schema.md`

---

## Acceptance Criteria

M3.8 is complete when:

1. The runtime attaches `meta["trace"]` to every `ExecutionResult`.
2. The trace contains an ordered list of steps with per-step `duration_ms`.
3. Tests enforce:
   - trace presence
   - stable schema identifiers
   - stage ordering for at least one deterministic path
   - absence of forbidden content keys