---
id: ADR-013
title: Deterministic Failure Semantics
type: adr
status: accepted
version: v1.0
canonical: true
scope: io-iii-phase-4
audience:
  - developer
  - maintainer
created: "2026-04-03"
updated: "2026-04-03"
tags:
  - io-iii
  - adr
  - phase-4
  - failure-semantics
  - observability
  - determinism
roles_focus:
  - executor
  - challenger
provenance: io-iii-runtime-development
milestone: M4.6
---

# ADR-013 — Deterministic Failure Semantics

## Status

Accepted

## Context

Prior to Phase 4 M4.6, IO-III failure handling was incidental. When the engine raised an exception, it propagated upward as a raw Python exception with no guaranteed structure. This meant:

- The execution trace was not guaranteed to reach a terminal state on failure.
- No typed lifecycle event was emitted on failure; callers could not observe a structured failure signal.
- Error codes logged by the CLI were `type(e).__name__` — an unstable, non-semantic identifier.
- No content-safe failure envelope existed to carry structured failure information through runtime surfaces.
- Callers could not distinguish provider failures from capability failures from contract violations.

This made failure analysis non-deterministic, difficult to reason about from trace output, and inconsistent with the rest of IO-III's governance-first design.

A formal decision is required to define the canonical failure contract for the IO-III runtime.

---

## Decision

IO-III will introduce a **canonical deterministic failure model** for the runtime.

The model consists of the following components:

### 1. Failure Categories (`RuntimeFailureKind`)

Six stable failure categories covering all known runtime failure modes:

| Kind | Code Prefix Examples | Description |
|------|---------------------|-------------|
| `route_resolution` | `ORCHESTRATOR_*`, `ROUTE_*` | Routing table lookup failed; no valid route |
| `provider_execution` | `PROVIDER_*` | Provider raised during generation or inference |
| `audit_challenger` | `AUDIT_*`, `REVISION_*` | Audit/challenger failed or exceeded bounded limit |
| `capability` | `CAPABILITY_*` | Capability raised, timed out, or exceeded bounds |
| `contract_violation` | `TRACE_*`, `CONTRACT_*` | Invalid state, invariant breach, or structural violation |
| `internal` | — | Unexpected failure not covered above |

These categories are stable. New categories require a future ADR update.

### 2. Typed Failure Envelope (`RuntimeFailure`)

A frozen, content-safe dataclass carrying structured failure information:

```
kind          — RuntimeFailureKind value
code          — stable machine-readable identifier (e.g. "PROVIDER_UNAVAILABLE")
summary       — short human-readable description (content-safe; no prompt/output)
request_id    — session linkage
task_spec_id  — upstream TaskSpec binding; None for CLI paths
retryable     — True only for PROVIDER_UNAVAILABLE
causal_code   — stable code extracted from cause; None if not available
```

**Content policy**: `summary` and `causal_code` must never contain user prompt text or model output text. `causal_code` carries structured error codes only — never free-form exception messages or stack traces.

### 3. Engine Failure Terminal Contract

The engine (`engine.run()`) adopts the following failure contract:

1. On **any** exception, the execution trace always reaches terminal state `'failed'`.
2. A `RUN_FAILED` lifecycle event is always emitted (content-safe).
3. A `RuntimeFailure` envelope is attached to the exception as `.runtime_failure`.
4. The original exception is re-raised (type preserved) to maintain caller contracts.
5. All failure-handling steps are fail-open — secondary failures are suppressed.

This means every run terminates with exactly one of `engine_run_complete` or `engine_run_failed` in the observability event log.

### 4. Failure Phase Tracking

The engine tracks execution phase with a `_phase` variable updated at key boundaries:

| Phase | Description |
|-------|-------------|
| `setup` | Pre-execution setup; no phase-specific context |
| `capability` | Capability invocation block |
| `provider` | Provider inference (`generate()`) |
| `audit` | Challenger audit pass |
| `revision` | Controlled revision pass |

`_phase` is passed as `phase_hint` to `classify_exception()` to disambiguate failures when the exception type alone is insufficient.

### 5. CLI Failure Logging

CLI exception handlers now use the typed failure code from `.runtime_failure` when available:

- `error_code` in metadata log uses `failure.code` (stable) instead of `type(e).__name__`
- `failure_kind` is logged as a new additive metadata field

---

## Scope Boundary

This ADR covers:

- canonical failure categories for the IO-III runtime
- typed failure envelope structure and content policy
- engine failure terminal contract (trace, events, exception attachment)
- CLI metadata logging improvement using typed failure codes
- execution phase tracking for failure classification

This ADR does **not** cover:

- retry subsystems or backoff logic
- circuit breakers
- failure recovery or resumption
- telemetry platforms or dashboards
- cross-run failure aggregation
- async failure handling

---

## Canonical Terminal Semantics

### Trace terminal state on failure

- `ExecutionTrace.status` reaches `'failed'` on every controlled failure path.
- The transition is `created → failed` or `running → failed` depending on how far execution progressed before the exception.
- No execution path may leave the trace in a non-terminal state when the engine raises.

### Engine lifecycle events on failure

- `engine_run_failed` is emitted as the terminal event on all failure paths.
- `engine_run_complete` is emitted only on successful completion.
- Exactly one of these two terminal events is present per run.
- `engine_run_failed` event meta contains: `failure_kind`, `failure_code`, `phase`.

### ExecutionResult on failure

- `ExecutionResult` is **not** returned on failure.
- The engine raises an exception (with `.runtime_failure` attached).
- This preserves the existing return-type contract for callers.

### Null path vs provider path

- Both null and ollama paths are wrapped by the same failure handler.
- On failure in either path, the trace reaches `'failed'`.
- The `RUN_FAILED` event is emitted regardless of which path raised.

### Audit path failures

- Audit and revision limit violations (`AUDIT_LIMIT_EXCEEDED`, `REVISION_LIMIT_EXCEEDED`) are classified as `AUDIT_CHALLENGER`.
- Challenger unavailability is fail-open by design (ADR-008 policy); it never reaches the failure handler.
- Only hard failures in the challenger/revision block produce `AUDIT_CHALLENGER` classification.

---

## Constraints

The failure model must preserve the following constraints:

- **Content safety**: failure envelopes must never carry prompt or response content.
- **Bounded behaviour**: no nested exception cascades; failure handler is always fail-open.
- **Deterministic classification**: the same exception type and phase always maps to the same failure kind.
- **Backward compatibility**: original exception types are preserved; existing `pytest.raises(ValueError, ...)` contracts are not broken.
- **No stack trace leakage**: `causal_code` carries structured codes only.
- **No retry logic**: `retryable` is a flag only; no retry behaviour is implemented.

---

## Consequences

### Positive

- Failure paths are now deterministic, typed, and inspectable.
- Trace always reaches a terminal state — no orphaned traces.
- CLI metadata logging uses stable error codes instead of Python class names.
- Observability consumers can distinguish `engine_run_complete` from `engine_run_failed`.
- `failure_kind` enables future tooling to categorise failure distributions by type.
- `request_id` and `task_spec_id` linkage in `RuntimeFailure` enables cross-surface correlation.

### Negative

- Adds a try/except wrapper to the engine's hot path (minimal overhead).
- `failure_kind` is a new metadata field — consumers must tolerate new fields.

### Neutral

- Does not implement retry, recovery, or backoff (deferred by design).
- `retryable` flag is informational only until a retry subsystem is introduced.

---

## Non-Goals

This ADR does not provide:

- Retry logic or backoff
- Circuit breakers
- Failure recovery paths
- Multi-failure aggregation
- Telemetry pipelines
- Dashboard integrations
- Any form of autonomous failure response

---

## Relationship to Other ADRs

- **ADR-009** bounds audit/revision passes. Violations are classified as `AUDIT_CHALLENGER`.
- **ADR-012** defines the orchestration layer. Orchestration errors propagate through this failure model.
- **ADR-013** (this document) defines the failure contract for the runtime kernel and above.

---

## Invariant Impact

This ADR implies:

- Every engine execution that raises must produce a `engine_run_failed` event in the observability log.
- No `RuntimeFailure` envelope may contain a forbidden content key.
- `retryable=True` is permitted only for `PROVIDER_UNAVAILABLE`.
- The `causal_code` field, when present, must begin with a known stable prefix.

---

## Implementation Notes

**Files introduced:**
- `io_iii/core/failure_model.py` — `RuntimeFailureKind`, `RuntimeFailure`, `classify_exception`, `_extract_causal_code`

**Files modified:**
- `io_iii/core/engine_observability.py` — `RUN_FAILED` event kind added to `EngineEventKind`
- `io_iii/core/engine.py` — phase tracker (`_phase`), try/except wrapper, failure terminal handler
- `io_iii/cli.py` — typed failure code in metadata logging; `failure_kind` field added

**Tests:**
- `tests/test_failure_model_m46.py` — full M4.6 failure semantics test suite

---

## Acceptance Criteria

M4.6 is complete when:

1. `RuntimeFailureKind` defines all six required categories.
2. `RuntimeFailure` is frozen, content-safe, and carries `request_id` / `task_spec_id` linkage.
3. On any engine failure, the execution trace reaches `'failed'` terminal state.
4. On any engine failure, a `engine_run_failed` event is in the observability log.
5. The raised exception has `.runtime_failure` with the correct `kind` and `code`.
6. The original exception type is preserved on re-raise.
7. No forbidden content keys appear in any `RuntimeFailure` field.
8. CLI metadata logs `error_code` from `failure.code` when available.
9. All existing Phase 4 tests pass without modification.
10. All new M4.6 tests pass.