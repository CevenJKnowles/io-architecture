---
id: "ADR-004"
title: "ADR 004 | Cloud Provider Enablement and Key Security"
type: "adr"
status: "active"
version: "v1.0"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-01-09"
updated: "2026-01-09"
tags:
  - "security"
  - "cloud-providers"
  - "api-keys"
  - "privacy"
  - "governance"
  - "runtime-boundaries"
roles_focus:
  - "governance"
  - "executor"
  - "challenger"
provenance: "human"
---

# ADR-004 — Cloud Provider Enablement and Key Security

## Context

IO-III is **local-first** by design. Cloud models may be useful for:
- capability gaps (rare edge cases),
- benchmarking and evaluation,
- controlled experimentation.

Cloud use introduces risk:
- accidental disclosure of private content,
- credential leakage,
- silent drift of “local-first” guarantees,
- untraceable data flow.

ADR-001 established a control plane (LiteLLM) with local runtime (Ollama). ADR-002 established explicit routing and limited fallback triggers. ADR-003 established logging/retention defaults. This ADR defines the **security boundary** for enabling cloud providers and handling secrets.

## Decision

### 1) Cloud providers are disabled by default (explicit opt-in)

- Cloud providers are **OFF** by default.
- Enabling cloud requires an explicit config change plus a verified runtime check.
- No “auto-enable if key exists”.

### 2) No automatic local → cloud fallback (ever)

- ADR-002 fallback applies only within the **declared routing table**.
- Local failures do not silently route to cloud.
- If cloud is used, it must be **explicitly selected** (per-mode or per-request).

### 3) Hard separation in routing namespace

Routing must distinguish local vs cloud to prevent ambiguity:

- Local models: `local:<model>`
- Cloud models: `cloud:<provider>:<model>`

Example:
- `local:llama3.1`
- `cloud:openai:gpt-4.1-mini`

### 4) Audience-based boundary: internal stays local

Requests/documents labeled `audience: internal` (or internal routes) must not be sent to cloud unless:
- the user explicitly triggers an override, and
- the system logs an override event (metadata tier).

Default posture: **internal → local only**.

### 5) Secret handling: keys never in repo, never in logs

API keys must never appear in:
- repository files (including JSON/YAML/MD),
- committed `.env` files,
- logs (metadata or content),
- crash dumps / stack traces printed to console.

Keys must be provided only through:
- environment variables (preferred), or
- local secret store mechanisms (OS keyring), if introduced later.

### 6) Startup safety checks (fail closed)

If any cloud routing is enabled, IO-III must refuse to start unless:
- required env vars are present,
- provider enable flags are explicitly set,
- logging rules (ADR-003) are active and content logging remains OFF by default.

### 7) Auditability: cloud usage must be visible in metadata logs

For every cloud call, metadata logs must include:
- provider name
- model name
- request id
- mode
- routing decision source (`explicit` | `override`)
- timestamp
- latency
- error code (if any)

No prompt/response content is logged unless content logging is explicitly enabled (ADR-003).

## Decision Drivers

- **Local-first integrity**: prevent accidental erosion into cloud-by-default.
- **Least privilege**: keys and cloud access should be tightly bounded.
- **Predictability**: explicit routing is easier to test, debug, and trust.
- **Portfolio-grade governance**: auditable, defensible architecture decisions.

## Options Considered

### A) Automatic fallback from local to cloud
Rejected:
- violates explicit routing,
- increases accidental disclosure risk,
- makes cost and privacy unpredictable.

### B) Keys stored in config files
Rejected:
- high leakage risk,
- poor portability,
- violates standard secret hygiene.

### C) Explicit opt-in cloud enablement with strict boundaries (selected)
Accepted:
- intentional use only,
- auditable data flow,
- preserves local-first guarantees.

## Consequences

### Positive

- Clear security boundary between local and cloud.
- Minimal risk of accidental cloud leakage.
- Strong defaults (fail closed).
- Logs support accountability without capturing content.

### Trade-offs

- Slightly more setup effort when cloud is genuinely needed.
- No “silent rescue” if local inference fails.
- Requires discipline around overrides (but overrides are intentionally loud).

## Implementation Notes (Non-normative)

- Use provider flags like `CLOUD_OPENAI_ENABLED=false` by default.
- Load keys via env vars only (e.g., `OPENAI_API_KEY`), never from tracked files.
- Add `.env` to `.gitignore` if you use it locally.
- Consider a “cloud override” control requiring:
  - explicit user command, and
  - automatic reversion after a short session.

## Related

- `./ADR/ADR-001-llm-runtime-control-plane-selection.md`
- `./ADR/ADR-002-model-routing-and-fallback-policy.md`
- `./ADR/ADR-003-telemetry-logging-and-retention-policy.md`
- `./docs/governance/adr-policy.md`
