---
id: "ADR-011"
title: "Provider Health Check Policy"
type: "adr"
status: "active"
version: "v1.0"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-04-01"
updated: "2026-04-01"
tags:
  - "providers"
  - "health-check"
  - "routing"
  - "determinism"
  - "observability"
roles_focus:
  - "executor"
  - "governance"
provenance: "human"
---

# ADR-011 — Provider Health Check Policy

## Status

Active

## Context

The IO-III routing table resolves a provider at execution time using static configuration
(ADR-001, ADR-002). If the selected provider is unavailable at invocation, the failure
surfaces late — inside the provider call — with no structured pre-flight signal.

This creates two problems:

1. **Late failure**: errors from an unavailable Ollama instance appear as opaque provider
   exceptions rather than a clean operational failure at the control-plane boundary.
2. **No observability signal**: the metadata log captures an error code, but there is no
   structured "provider unavailable" event distinct from other runtime exceptions.

A pre-flight health check at the CLI execution boundary (before routing and before
SessionState creation) addresses both.

## Decision

### 1) Pre-flight check location

The health check runs in the CLI execution path (`cmd_run`, `cmd_capability`) immediately
after config load and before routing resolution.

The check must NOT run inside:
- the routing layer
- the engine
- the context assembly layer
- the challenger pass

It is a CLI-boundary concern, not a runtime kernel concern.

### 2) What is checked

For the Ollama provider (the only enabled local provider):
- Reachability of `base_url` (from `providers.yaml`) via a lightweight HTTP request
- No model-level availability check (model listing is dynamic and out of scope)

For disabled providers (cloud):
- No check is performed (disabled means not in use; ADR-004 prohibits implicit cloud fallback)

### 3) Failure behaviour: fail fast, never silent fallback

If the selected provider fails the health check:
- Raise a structured error with code `PROVIDER_UNAVAILABLE: <provider_id>`
- Do NOT silently fall back to another provider
- Do NOT trigger cloud fallback (ADR-004: `allow_implicit_cloud_fallback: false`)
- Do NOT fall back to the null provider as a substitute for real execution

The null provider is a test/stub path, not a graceful degradation path.

### 4) Skipping the check

The health check is skipped when:
- The resolved provider is `null` (test/stub path; no network check needed)
- A `--no-health-check` CLI flag is explicitly passed (for offline test runs and CI)

### 5) Metadata logging

A failed health check is logged to the metadata channel before the error is raised:
- `status: "error"`
- `error_code: "PROVIDER_UNAVAILABLE"`
- `provider: <provider_id>`
- `latency_ms`: measured from `t0` in the CLI

Content is never logged.

## Decision Drivers

- Late provider failures produce opaque errors that are hard to distinguish from
  model-level or network errors mid-execution.
- ADR-002 defines fallback triggers as operational failures — a pre-flight check is the
  correct point to detect those triggers, not inside the routing or engine layers.
- ADR-004 prohibits implicit cloud fallback; a health check must never trigger it.
- ADR-007 prohibits persistent state — health check results must not be cached.

## Options Considered

### A) No health check (current state)
Rejected. Late failure is less informative and harder to observe cleanly.

### B) Health check inside the routing layer
Rejected. Routing is deterministic and stateless by design (ADR-002). Adding network I/O
there violates the separation of concerns between route selection and provider availability.

### C) Health check inside the engine
Rejected. The engine is the runtime kernel; availability checks belong at the CLI boundary
before execution begins.

### D) Pre-flight health check at CLI boundary (selected)
Accepted. Clean separation: config load → health check → routing → execution. Fail fast
with a structured error before any state is created.

## Consequences

### Positive
- Structured `PROVIDER_UNAVAILABLE` error code distinct from mid-execution failures
- Cleaner metadata log record for availability failures
- No change to routing, engine, or context assembly (ADR-001, ADR-002, ADR-010 unaffected)

### Neutral
- Adds a small network round-trip before every `run` and `capability` invocation
- Null provider path is explicitly excluded (no overhead in tests)

### Explicit Non-Goals

The following are out of scope for this ADR:
- Model-level availability checking (which models are loaded in Ollama)
- Provider capability negotiation
- Health-check caching or circuit-breaker patterns
- Cloud provider availability checks

## Implementation Notes (Non-normative)

- Check target: `GET <ollama.base_url>/` — lightweight endpoint, no model inference
- Timeout: short fixed timeout (e.g., 1000ms) — this is a reachability check, not load test
- CLI flag: `--no-health-check` suppresses the check for offline/CI environments
- Error raised as `RuntimeError("PROVIDER_UNAVAILABLE: ollama")` or equivalent
- Metadata log entry written before the raise, matching the existing error-path log pattern

## Related

- `ADR/ADR-001-llm-runtime-control-plane-selection.md` (provider abstraction)
- `ADR/ADR-002-model-routing-and-fallback-policy.md` (fallback trigger policy)
- `ADR/ADR-004-cloud-provider-enablement-and-key-security.md` (no implicit cloud fallback)
- `ADR/ADR-007-memory-persistence-and-drift-control.md` (no cached health state)
- `architecture/runtime/config/providers.yaml` (Ollama base_url)