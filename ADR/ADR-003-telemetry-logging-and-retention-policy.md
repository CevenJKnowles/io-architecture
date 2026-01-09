---
id: "ADR-003"
title: "Telemetry, Logging, and Retention Policy"
type: "adr"
status: "draft"
version: "v0.1"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-01-09"
updated: "2026-01-09"
tags:
  - "telemetry"
  - "logging"
  - "retention"
  - "privacy"
  - "observability"
roles_focus:
  - "governance"
  - "executor"
  - "challenger"
provenance: "human"
---

# ADR-003 — Telemetry, Logging, and Retention Policy

## Context

IO-III routes requests across multiple model backends via a control plane.
Routing + fallback are only trustworthy if the system is observable.
At the same time, IO-III is local-first and must minimize data exposure.

This ADR defines what is logged, where it is stored, how long it is retained,
and what must never be logged by default.

## Decision

### 1) Local-first logging only (default)

By default, IO-III logs are stored **locally on disk** only.
No external telemetry is enabled unless explicitly configured.

### 2) Two-tier logging: metadata vs content

**Tier A — Metadata logs (default ON)**
Log operational metadata needed for debugging and regression testing:
- timestamp
- request id
- mode
- selected primary model
- fallback used (yes/no)
- fallback reason (enum)
- latency (ms)
- token counts (if available)
- error codes (if any)

**Tier B — Content logs (default OFF)**
Prompt/response content logging is OFF by default.
It can be enabled only for targeted debugging sessions.

### 3) Redaction and secret hygiene

When any content logging is enabled:
- redact API keys / secrets
- redact filesystem paths that contain usernames (optional but recommended)
- redact environment variables by default

### 4) Retention policy (default)

- Metadata logs retained for: **30 days**
- Content logs retained for: **7 days** (only if enabled)
- Manual “debug sessions” should be time-boxed and disabled immediately after use

### 5) Cloud boundary rule

If cloud providers are enabled:
- internal docs and “internal” audience prompts stay local unless explicitly overridden
- cloud calls must be opt-in per provider and auditable in logs (metadata tier)

## Decision Drivers

- Observability is required for routing determinism and regression tests.
- Local-first posture reduces privacy risk and accidental leakage.
- Content logs create disproportionate risk vs benefit in steady-state.

## Options Considered

### A) Log everything by default
Rejected (privacy and noise).

### B) No logging by default
Rejected (breaks debuggability and undermines routing/ADR guarantees).

### C) Metadata logging by default + content logging opt-in (selected)
Accepted (balanced, testable, low-risk).

## Consequences

### Positive
- Debuggability without content exposure
- Clear privacy defaults
- Supports regression testing and routing audits

### Trade-offs
- Harder to diagnose “quality” issues without temporary content logging
- Requires discipline to avoid leaving debug content logging on

## Implementation Notes (Non-normative)

- Define a single log schema version (e.g., `log_schema: v1`)
- Store logs under a dedicated directory (e.g., `./IO-III/runtime/logs/`)
- Consider log rotation to enforce retention automatically

## Related

- `./ADR/ADR-001-llm-runtime-control-plane-selection.md`
- `./ADR/ADR-002-model-routing-and-fallback-policy.md`
- `./docs/architecture/io-iii-llm-architecture.md`
- `./docs/governance/adr-policy.md`
