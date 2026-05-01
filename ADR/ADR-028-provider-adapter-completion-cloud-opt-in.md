---
id: ADR-028
title: Provider Adapter Completion and Cloud Opt-In Contract
type: adr
status: accepted
version: v1.0
canonical: true
scope: io-iii-phase-10
audience:
  - developer
  - maintainer
  - operator
created: "2026-05-01"
updated: "2026-05-01"
tags:
  - io-iii
  - adr
  - phase-10
  - providers
  - cloud
  - governance
roles_focus:
  - executor
  - governance
provenance: io-iii-runtime-development
milestone: M10.0
---

# ADR-028 — Provider Adapter Completion and Cloud Opt-In Contract

## Status

Accepted

---

## 1. Context

`providers.yaml` lists OpenAI, Anthropic, and Google as disabled-by-default provider
entries governed by ADR-004 (cloud provider enablement and key security policy). These
entries have existed since Phase 1 as placeholders signalling planned cloud support.

No adapter implementation exists for any of these providers. Only `ollama_provider.py`
and `null_provider.py` are implemented. A user who reads `providers.yaml`, sets
`enabled: true`, and supplies an API key will find no code behind the entry. The provider
instantiation path in `core/engine.py` has no branch for these providers and will fail
at runtime with a non-descriptive error.

This gap must be resolved before public release. The resolution must not introduce real
cloud provider implementations prematurely, as those require testing, key management
validation, and their own scope of work. The resolution must also not mislead operators
about what the runtime currently supports.

ADR-004 remains the governing policy document for cloud provider enablement. This ADR
resolves only the gap between the policy (providers exist as opt-in entries) and the
reality (no implementation backs them).

---

## 2. Decision

### §1 Phase 10 resolution — stub adapters

For the Phase 10 public release, stub adapter modules are introduced for OpenAI and
Anthropic. Each stub raises `NotImplementedError` at instantiation time with a
structured message directing the operator to the project roadmap.

Stub files introduced:

- `io_iii/providers/openai_provider.py`
- `io_iii/providers/anthropic_provider.py`

Each stub implements the provider protocol (defined in `provider_contract.py`) at the
interface level only. No HTTP calls are made. No API keys are read. The stub raises:

```
NotImplementedError(
    "PROVIDER_NOT_IMPLEMENTED: openai — cloud provider adapters are not yet "
    "available in this release. See ROADMAP.md for Phase 11 timeline."
)
```

The `providers.yaml` entries for OpenAI, Anthropic, and Google retain their existing
structure. A `status: stub` field is added to each cloud entry to make the current
state machine-readable.

Google is not given a stub adapter in Phase 10. The Google entry in `providers.yaml`
retains `enabled: false` and `status: stub` but has no corresponding module. This is
acceptable: the stub field communicates the gap, and the engine instantiation path
will fail with a clear error if an operator enables it. A full adapter for Google is
out of scope for Phase 10 and Phase 11.

### §2 ADR-004 policy — unchanged

ADR-004 remains fully governing:

- All cloud providers default to `enabled: false`
- `allow_implicit_cloud_fallback: false` is preserved
- `internal_to_cloud_requires_override: true` is preserved
- No automatic local-to-cloud fallback is introduced under any circumstance

### §3 Phase 11 path

Phase 11 introduces real adapter implementations for OpenAI and Anthropic (Option C
as defined in the Phase 10 planning record). The stub modules introduced here are
replaced by full implementations at that time. The stub interface ensures the provider
protocol contract is already satisfied, reducing Phase 11 integration surface.

Phase 11 cloud adapter work requires a dedicated ADR before implementation begins,
scoped to the specific providers being implemented.

---

## 3. Consequences

- A user who enables a cloud provider in `providers.yaml` receives a structured
  `NotImplementedError` with a roadmap reference rather than a non-descriptive
  runtime failure.
- `providers.yaml` accurately represents provider status via the `status` field.
- The provider protocol surface is unchanged. Phase 11 can implement real adapters
  without modifying the engine or routing layers.
- `engine.py` requires a minor update to its provider instantiation branch to
  handle stub providers explicitly, raising the `NotImplementedError` at a
  meaningful boundary rather than mid-execution.

---

## 4. Non-goals

- This ADR does not implement real cloud provider HTTP adapters.
- This ADR does not modify ADR-004 cloud provider policy.
- This ADR does not add API key management, rotation, or validation logic.
- This ADR does not introduce any cloud provider to the routing table.
- This ADR does not add Google as a stub adapter with a corresponding module.