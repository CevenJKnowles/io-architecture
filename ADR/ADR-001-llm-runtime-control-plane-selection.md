---
id: "ADR-001"
title: "LLM Runtime Control Plane Selection"
type: "adr"
status: "active"
version: "v1.0"
canonical: true
scope: "io-iii"
audience: "internal"
created: "2026-01-09"
updated: "2026-01-09"
tags:
  - "llm-runtime"
  - "control-plane"
  - "routing"
  - "local-llm"
  - "api-compatibility"
roles_focus:
  - "executor"
  - "synthesizer"
  - "governance"
provenance: "human"
---

# ADR-001 — LLM Runtime Control Plane Selection

## Context

IO‑III requires a **single, stable control plane** to route prompts across multiple model backends while keeping:
- **portable interfaces** (OpenAI-compatible where possible),
- **swap‑ability** (models/providers can change without rewriting app logic),
- **local-first execution** (run on laptop hardware by default),
- **observable behavior** (logging, rate limits, routing rules),
- **future expansion** (cloud models, eval harnesses, guardrails).

The repo already separates **architecture**, **implementation**, and **governance** documents, and ADRs are treated as canonical decisions that prevent silent divergence.

## Decision

Adopt a **two-layer runtime**:

1. **Ollama** as the **local model runtime** (model hosting + local inference).
2. **LiteLLM** as the **control plane / router** (single API endpoint, provider abstraction, routing, retries, logging hooks).

The IO‑III application targets **LiteLLM’s OpenAI‑compatible endpoint** as the primary integration surface.

## Decision Drivers

- **Interface stability:** OpenAI-compatible surface minimizes integration churn.
- **Provider abstraction:** Easy to add/remove local + cloud providers.
- **Routing support:** Central place for “mode → model” mapping and fallbacks.
- **Operational clarity:** One endpoint for clients; one place for logs + policies.
- **Local-first:** Ollama supports laptop-friendly local inference.

## Options Considered

### A) Direct-to-Ollama (no control plane)
**Pros**
- Minimal moving parts
- Fast to start

**Cons**
- Harder multi-provider routing
- App becomes tightly coupled to a single runtime API
- No clean, central policy layer

### B) LiteLLM-only (without Ollama)
**Pros**
- Strong abstraction + routing
- Clean endpoint for IO‑III

**Cons**
- Still needs actual local runtime for local inference
- You end up choosing a runtime anyway

### C) vLLM / TGI / llama.cpp as runtime (instead of Ollama)
**Pros**
- Potentially higher throughput / advanced serving options

**Cons**
- Higher setup complexity on a laptop
- More ops overhead than necessary for current phase

### D) LangChain/LangGraph as “control plane”
**Pros**
- Rich agent/tooling ecosystem

**Cons**
- Not a control plane per se; still need runtime + provider abstraction
- Risk of framework lock-in at this stage

## Consequences

### Positive
- IO‑III can standardize on **one client interface** (OpenAI-like).
- Routing rules become a **config-level concern** (not app rewrites).
- Easier to integrate:
  - evaluation harnesses,
  - usage logging,
  - fallback logic,
  - guardrails/policies.

### Negative / Tradeoffs
- More components to maintain (Ollama + LiteLLM).
- Debugging spans layers (client → LiteLLM → Ollama/provider).
- Needs a disciplined config strategy to avoid “routing drift”.

## Implementation Notes

### Baseline contract
- **Client code** calls LiteLLM (OpenAI-compatible).
- LiteLLM routes to:
  - **Ollama** for local models by default,
  - optional cloud providers when explicitly enabled.

### Configuration strategy (recommended)
- Keep a single routing config file (e.g., `IO-III/runtime/litellm.yaml`)
- Store mode routing table in the same config or an adjacent canonical file.
- Add a lightweight health check:
  - `GET /health` for LiteLLM
  - verify Ollama is reachable and at least one model is loaded

### Logging & privacy
- Default to **local logs only**.
- If cloud models are enabled, ensure prompts marked “internal” remain local unless explicitly overridden.

## Related

- `docs/architecture/io-iii-llm-architecture.md`
- `IO-III/strategy/` (routing & persona binding notes)
- Future ADRs:
  - ADR-002: Model routing table & fallback policy
  - ADR-003: Telemetry/logging policy and retention
  - ADR-004: Security posture for cloud provider keys

