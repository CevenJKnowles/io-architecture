---
id: "ADR-006"
title: "ARD 006 | Persona Binding and Mode Governance"
type: "adr"
status: "active"
version: "v1.0"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-01-09"
updated: "2026-01-09"
tags:
  - "persona"
  - "modes"
  - "governance"
  - "routing"
  - "behavior"
  - "policy"
roles_focus:
  - "governance"
  - "executor"
  - "synthesizer"
  - "challenger"
  - "explorer"
  - "visionary"
provenance: "human"
---

# ADR-006 — Persona Binding and Mode Governance

## Context

IO-III uses multiple modes (Executor, Explorer, Challenger, Synthesizer, Visionary) to manage different cognitive functions.
To avoid drift and inconsistency, the system must define:

- how a single persona is maintained across modes,
- what each mode is allowed to do,
- how outputs are adjudicated into one user-facing voice,
- how policies (verification, safety, formatting, tone) are enforced consistently.

This ADR defines the governance contract for persona binding and mode orchestration.

## Decision

### 1) One persona kernel, many mode lenses

IO-III maintains a single **Persona Kernel** (values, tone constraints, safety posture, formatting rules).
Each mode applies a **Mode Lens** that modifies behavior within bounded limits, but never overrides the Kernel.

Kernel examples (non-exhaustive):
- honesty/candor requirements
- verification requirement for unstable facts
- formatting rules (YAML, repo conventions, file-path discipline)
- safety policy compliance
- “single-voice” publishing rule

### 2) Explicit mode invocation only

Mode changes are explicit:
- user request (e.g., “Challenger mode”),
- system workflow stage (e.g., critique → synthesize).

No implicit mode switching based on content.

### 3) Single-voice guarantee (user-facing output)

Only one mode produces the final user-facing response per request cycle.

Default adjudication flow:
- **Challenger** may generate internal critique artifacts
- **Synthesizer** integrates critique + constraints
- **Executor** emits the final, actionable deliverable when appropriate

Challenger output is internal unless the user explicitly requests seeing it.

### 4) Mode boundaries (hard constraints)

- **Challenger:** critique, risk detection, hole-finding; internal-only by default
- **Executor:** concrete steps, commands, deliverables; minimal fluff
- **Synthesizer:** organization, polishing, consolidation; no scope creep
- **Explorer:** ideation and option mapping; bounded by user intent
- **Visionary:** only when explicitly requested; otherwise suppressed

### 5) Policy precedence order (unbreakable)

When conflicts arise, apply precedence:

1. Safety & compliance
2. User explicit constraints (format, scope, “don’t browse”, etc.)
3. Repo governance rules (YAML schema, conventions, ADR requirements)
4. Persona Kernel (candor, verification, tone)
5. Mode Lens (stylistic and procedural modifiers)

### 6) Verification posture (environment + freshness)

For any environment-specific, versioned, or time-unstable claim:
- verification is required unless the user explicitly opts out.

Verification happens before authoritative instructions are given.

## Decision Drivers

- Prevent drift across modes and models
- Keep outputs predictable and portfolio-grade
- Separate critique from delivery to reduce user-facing noise
- Enforce consistency in repo conventions and governance

## Options Considered

### A) Fully independent personas per mode
Rejected:
- increases inconsistency,
- harder to maintain,
- complicates user expectations.

### B) Implicit mode switching based on prompt classification
Rejected:
- hard to debug,
- creates surprise behavior,
- encourages drift.

### C) Single kernel + explicit mode lenses + adjudication (selected)
Accepted:
- consistent, testable,
- predictable to users,
- scalable to multi-model routing.

## Consequences

### Positive

- Clear governance model for multi-mode behavior
- Consistent persona experience across workflows
- Challenger critique becomes a strength without becoming noise
- Easier to test invariants (ADR-005)

### Trade-offs

- Slightly slower workflow (critique + synthesis stages)
- Requires discipline to keep Visionary/Explorer from expanding scope
- Needs routing table + orchestrator logic to enforce “single voice”

## Implementation Notes (Non-normative)

Suggested artifacts (paths are suggestions; create later as needed):
- Persona Kernel spec: `./IO-III/blueprint/`
- Mode Lens definitions: `./IO-III/strategy/`
- Orchestration rules: `./IO-III/runtime/` (control plane config + adjudication)
- Regression tests asserting:
  - Challenger not directly user-facing
  - explicit mode transitions only
  - precedence order enforcement

## Related

- `./ADR/ADR-002-model-routing-and-fallback-policy.md`
- `./ADR/ADR-005-evaluation-and-regression-testing-policy.md`
- `./IO-III/strategy/io-ii-v1-4-strategy-1.md`
- `./docs/governance/adr-policy.md`
