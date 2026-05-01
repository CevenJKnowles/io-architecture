---
id: "ADR-006"
title: "Persona Binding and Mode Governance"
type: "adr"
status: "active"
version: "v1.1"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-01-09"
updated: "2026-05-01"
tags:
  - "persona"
  - "modes"
  - "governance"
  - "routing"
  - "behavior"
  - "policy"
  - "identity"
  - "user-profile"
roles_focus:
  - "governance"
  - "executor"
  - "synthesizer"
  - "challenger"
  - "explorer"
  - "visionary"
provenance: "human"
---

# ADR-006 | Persona Binding and Mode Governance

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

## Amendment — Phase 10 (v1.1)

### 7) Io identity configuration surface

A new `identity:` block in `persona.yaml` provides the user-configurable surface for
Io's conversational presentation. It is injected into the system prompt header by
`context_assembly.py` as the opening section, before the persona contract.

Governed fields:

| Field | Purpose | Default |
|---|---|---|
| `identity.name` | The name Io uses in conversation | `IO-III` |
| `identity.description` | One-sentence description of what this assistant does | _(empty)_ |
| `identity.style` | Preferred communication style | _(empty)_ |

All fields are optional. If the `identity:` block is absent or unparseable, the runtime
falls back to defaults silently — a missing block never raises and never causes a
governance failure.

The identity block does not affect routing, audit gates, execution semantics, or any
invariant established in §1–§6. It is a presentation layer only.

### 8) User profile configuration surface

A new `user_profile.yaml` in `architecture/runtime/config/` provides an operator-
configurable surface for the user's context. It is injected into the system prompt as
a `=== User Profile ===` section, positioned after the persona contract and before
runtime boundaries.

Governed fields:

| Field | Purpose |
|---|---|
| `user.name` | How Io addresses the user |
| `user.role` | User's professional role or context |
| `user.expertise` | List of domains; informs vocabulary and response depth |
| `user.preferences` | Communication preferences (language, style, etc.) |
| `user.notes` | Free-text context |

All fields are optional. If `user_profile.yaml` is absent or the `user:` block is empty,
the section is omitted from the system prompt entirely — no default text is injected.
The runtime never raises on a missing or malformed user profile.

The user profile does not affect routing, audit gates, execution semantics, or any
invariant established in §1–§6. It is a context layer only.

### Implementation

Both surfaces are loaded by `load_identity()` and `load_user_profile()` in
`io_iii/persona_contract.py`. Both are consumed exclusively in
`io_iii/core/context_assembly.py` — `_build_system_prompt()`. No other module is
affected.

---

## Related

- `./ADR/ADR-002-model-routing-and-fallback-policy.md`
- `./ADR/ADR-005-evaluation-and-regression-testing-policy.md`
- `./ADR/ADR-023-open-source-initialisation-contract.md`
- `./IO-III/strategy/io-ii-v1-4-strategy-1.md`
- `./docs/governance/adr-policy.md`

---

## Changelog

| Version | Date       | Change                                                              |
|---------|------------|---------------------------------------------------------------------|
| v1.0    | 2026-01-09 | Initial persona binding and mode governance contract                |
| v1.1    | 2026-05-01 | Added §7 identity config surface and §8 user profile config surface |