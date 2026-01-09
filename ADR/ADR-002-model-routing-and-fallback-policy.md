---
id: "ADR-002"
title: "Model Routing and Fallback Policy"
type: "adr"
status: "active"
version: "v1.0"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-01-09"
updated: "2026-01-09"
tags:
  - "routing"
  - "fallback"
  - "llm-policy"
  - "resilience"
roles_focus:
  - "executor"
  - "challenger"
  - "governance"
provenance: "human"
---

# ADR-002 — Model Routing and Fallback Policy

## Context

IO-III is a local-first, multi-model system in which **models are treated as cognitive organs**, coordinated through a deterministic runtime layer. Routing must therefore be:

- **Explicit and mode-driven**
- **Deterministic and debuggable**
- **Capable of primary/secondary fallback**
- **Able to enforce internal-only model boundaries**

This ADR defines the routing contract that the runtime control plane must implement.

## Decision

### 1) Mode-driven routing only (no inference)

Routing is selected exclusively by **IO-III mode** (Executor, Explorer, Challenger, Synthesizer, Visionary).  
Routing is **never inferred** from content, topic, or user intent.

### 2) Canonical routing table (primary + secondary)

The routing table is:

| Mode | Primary | Secondary |
|------|---------|-----------|
| Executor | `ministral-3` | `mistral` |
| Explorer | `llama3.1` | `gemma` |
| Challenger | `deepseek-r1` | `llama3.1` |
| Synthesizer | `llama3.1` | `ministral-3` |
| Visionary | `llama3.1` | `deepseek-r1` |

This table is **explicit, deterministic, and mode-driven**.  
(Reference architecture routing table.) :contentReference[oaicite:3]{index=3}

### 3) Fallback triggers (strict, minimal)

Fallback from Primary → Secondary occurs only when one of these conditions is met:

- **Transport / runtime failure** (connection refused, host unreachable, 5xx)
- **Timeout** (exceeds configured request timeout)
- **Context overflow** (context-length error)
- **Model unavailable** (not loaded / not present / provider returns “not found”)

Fallback does **not** occur for:
- “low quality output”
- disagreement between models
- stylistic mismatch

Quality and adjudication belong to **cognitive governance**, not runtime governance. :contentReference[oaicite:4]{index=4}:contentReference[oaicite:5]{index=5}

### 4) Internal-only boundary enforcement

- **Challenger mode outputs never go directly to the user.**
- Challenger responses are treated as **internal critique artifacts**, consumed by IO-III Core and/or Synthesizer, then adjudicated.
- Only one model produces user-facing final output per request cycle (“single-voice guarantee” via governance loop).

This preserves the architecture principle: runtime enforces routing and isolation; cognition and adjudication remain in IO-III Core. :contentReference[oaicite:6]{index=6}:contentReference[oaicite:7]{index=7}

## Decision Drivers

- **Predictability is a feature** (professional systems favor constraint) :contentReference[oaicite:8]{index=8}
- **Determinism and debuggability** via declarative routing and observable paths :contentReference[oaicite:9]{index=9}
- **Governance boundaries**: runtime governance ≠ cognitive governance :contentReference[oaicite:10]{index=10}
- **Hardware realism**: 7B–9B class models are the default envelope; heavier models must be used sparingly :contentReference[oaicite:11]{index=11}

## Options Considered

### A) Heuristic routing (content-based)
**Rejected.**  
Violates “explicit, never inferred” routing and increases drift/debug ambiguity. :contentReference[oaicite:12]{index=12}

### B) Application-level routing only (no centralized policy)
**Rejected.**  
Collapses architectural layers and reduces traceability; makes fallback ad hoc. :contentReference[oaicite:13]{index=13}

### C) Mode-driven routing with deterministic fallback (selected)
**Accepted.**  
Matches the declared architecture: explicit mode mapping + controlled fallback. :contentReference[oaicite:14]{index=14}:contentReference[oaicite:15]{index=15}

## Consequences

### Positive
- Routing is stable, inspectable, and testable.
- Failure handling is consistent across models/providers.
- Cognitive governance stays in IO-III Core (no “policy leakage” into runtime).
- Clear portfolio-grade separation of concerns.

### Trade-offs
- Requires disciplined config management to avoid routing drift. :contentReference[oaicite:16]{index=16}
- Secondary model behavior may differ; IO-III Core must tolerate variation.
- “Quality fallback” is not automatic (by design).

## Implementation Notes (Non-normative)

- Represent each mode as a **logical model alias** in the control plane.
- Store routing config in a single canonical location (one file, versioned).
- Log routing decisions (mode, primary/secondary used, failure trigger).
- Add a small regression test suite asserting:
  - each mode maps to intended primary/secondary
  - fallback triggers behave exactly as specified

## Related

- `./ADR/ADR-001-llm-runtime-control-plane-selection.md`
- `./docs/architecture/io-iii-llm-architecture.md`
- `./docs/governance/adr-policy.md`

