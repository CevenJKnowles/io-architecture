---
id: DOC-ARCH-006
title: Phase 3.8 | Execution Observability (Content-Safe Trace)
type: architecture
status: active
version: v1.2
canonical: true
scope: io-iii
audience: engineers
created: "2026-03-04"
updated: "2026-04-12"
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

# Phase 3.8 | Execution Observability (Content-Safe Trace)

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

---

## Phase 4 Extensions

### M4.5 — Engine Lifecycle Events

`EngineObservabilityLog` records structured per-run lifecycle events emitted by `engine.run()`.

Each event carries: `kind`, `request_id`, `task_spec_id`, `timestamp_ms`, `meta`.

Event sequence (successful run):

1. `engine_run_started`
2. `route_resolved`
3. `provider_execution_complete`
4. `challenger_audit_complete` (audit path only)
5. `revision_complete` (revision path only)
6. `output_emitted`
7. `engine_run_complete`

Events are content-safe. Meta fields carry only structural values (provider name, model identifier, audit verdict, step counts). No prompt or model output text.

Events are attached to `ExecutionResult.meta["engine_events"]` on the success path.

### M4.6 — Deterministic Failure Semantics

On any exception, the engine guarantees:

1. `ExecutionTrace.status` reaches `'failed'` (terminal state).
2. `engine_run_failed` is emitted as the terminal lifecycle event in place of `engine_run_complete`. Meta carries `failure_kind`, `failure_code`, `phase`.
3. A typed `RuntimeFailure` envelope is classified and attached to the original exception as `.runtime_failure`.
4. The original exception type is preserved on re-raise — no wrapper exception.

`RuntimeFailure` fields:

| Field | Description |
| --- | --- |
| `kind` | `RuntimeFailureKind` — one of six stable categories |
| `code` | Stable machine-readable identifier (e.g. `PROVIDER_UNAVAILABLE`) |
| `summary` | Fixed category-level string; no prompt or model output text |
| `request_id` | Session linkage |
| `task_spec_id` | Upstream `TaskSpec` binding; `None` for CLI paths |
| `retryable` | `True` only for `PROVIDER_UNAVAILABLE` |
| `causal_code` | Stable code extracted from cause; `None` if unavailable |

Failure categories:

| Kind | Description |
| --- | --- |
| `route_resolution` | Routing table lookup failed |
| `provider_execution` | Provider raised during generation or inference |
| `audit_challenger` | Audit/revision pass failed or exceeded bounded limit |
| `capability` | Capability raised, timed out, or exceeded bounds |
| `contract_violation` | Invalid state, invariant breach, or structural violation |
| `internal` | Unexpected failure not covered above |

Every run terminates with exactly one terminal event: `engine_run_complete` (success) or `engine_run_failed` (failure).

ADR: ADR-013 — Deterministic Failure Semantics