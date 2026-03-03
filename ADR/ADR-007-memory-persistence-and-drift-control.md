---
id: "ADR-007"
title: "Memory, Persistence, and Drift Control"
type: "adr"
status: "active"
version: "v1.0"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-01-09"
updated: "2026-01-09"
tags:
  - "memory"
  - "persistence"
  - "drift-control"
  - "governance"
  - "privacy"
  - "state"
roles_focus:
  - "governance"
  - "challenger"
  - "executor"
  - "synthesizer"
provenance: "human"
---

# ADR-007 | Memory, Persistence, and Drift Control

## Context

IO-III’s quality depends on **stable persona behavior** and **consistent policy enforcement** over time.
However, persistent memory introduces risks:

- privacy leakage (storing sensitive content),
- compounding errors (bad facts becoming “memory”),
- behavioral drift (tone/style rules gradually erode),
- unclear provenance (human vs model-generated state).

This ADR defines what IO-III is allowed to persist, how it is stored, and how drift is detected and corrected.

## Decision

### 1) Default state is stateless per request

IO-III runs stateless by default:
- no long-term memory is assumed,
- each session explicitly opts into persistence.

This reduces risk and clarifies behavior.

### 2) Two-tier persistence model

**Tier A — Canonical Repo Memory (always allowed)**
Authoritative state lives in version-controlled files:
- ADRs (`./ADR/`)
- architecture docs (`./docs/architecture/`)
- governance docs (`./docs/governance/`)
- blueprint/strategy docs (`./IO-III/`)

This is the source of truth.

**Tier B — Runtime Session Memory (optional, local-only)**
Optional ephemeral storage for convenience:
- recent routing decisions
- short-lived task context
- temporary preferences for a session

This must be:
- local-only,
- time-bounded,
- easily purgeable.

### 3) No sensitive persistence by default

IO-III must not persist:
- personal identifiers
- secrets / API keys
- private user content unless explicitly requested
- health, legal, financial sensitive material
- raw prompt/response content (unless debugging and time-boxed per ADR-003)

### 4) Provenance labeling is mandatory

Any persisted datum must carry provenance:
- `human` (user-authored / user-confirmed)
- `llm:<slug>` (model-generated suggestion)
- `mixed` (combined)

Repo memory is implicitly human-approved (because committed).

### 5) Drift control: invariants + periodic audits

Drift is controlled via:
- invariant regression tests (ADR-005 Layer A),
- periodic “behavior audit” prompts (scheduled/manual),
- explicit “misalignment alert” mechanism:
  - if outputs violate rules, system must correct course immediately.

### 6) Correction policy: change via ADRs, not silent edits

If a persistent policy changes (routing, security, logging, persona rules):
- create a new ADR or update governance docs with traceability,
- do not rely on “memory” to override canonical text.

Canonical repo artifacts supersede runtime memory.

## Decision Drivers

- Minimize privacy risk
- Preserve portfolio-grade auditability
- Prevent error-compounding memory
- Keep system behavior predictable and testable

## Options Considered

### A) Always-on long-term memory
Rejected:
- privacy risk,
- drift risk,
- hard to audit.

### B) No persistence at all
Rejected:
- loses useful continuity,
- makes operational workflows harder.

### C) Repo-canonical memory + optional local session memory (selected)
Accepted:
- auditable source of truth,
- safe defaults,
- flexible when needed.

## Consequences

### Positive

- Clear “source of truth” hierarchy
- Reduced drift and privacy exposure
- Easier to reason about behavior changes
- Strong compatibility with regression testing

### Trade-offs

- Less convenience than always-on memory
- Requires explicit workflows for enabling session memory
- Requires discipline to label provenance and purge debug artifacts

## Implementation Notes (Non-normative)

Suggested future structure (paths are suggestions; create later if needed):
- Local session state: `./IO-III/runtime/state/` (gitignored)
- Local logs: `./IO-III/runtime/logs/` (gitignored, per ADR-003)
- Drift test prompts: `./IO-III/tests/corpus/`
- Add a “purge” command/script to wipe runtime state and logs safely

## Related

- `./ADR/ADR-003-telemetry-logging-and-retention-policy.md`
- `./ADR/ADR-004-cloud-provider-enablement-and-key-security.md`
- `./ADR/ADR-005-evaluation-and-regression-testing-policy.md`
- `./ADR/ADR-006-persona-binding-and-mode-governance.md`
- `./docs/governance/adr-policy.md`
