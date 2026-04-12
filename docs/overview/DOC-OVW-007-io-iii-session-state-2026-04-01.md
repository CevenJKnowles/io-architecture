---
id: DOC-OVW-007
title: Session State | Current
type: overview
status: active
version: v0.4.0
canonical: true
scope: repository
audience: developer
created: "2026-04-01"
updated: "2026-04-12"
tags:
- io-iii
- runtime
- session-state
- architecture
- phase-3
- phase-4
roles_focus:
- executor
- challenger
provenance: io-iii-runtime-development
supersedes: DOC-OVW-006
---

# Session State | Current

---

## Overview

This document records the current architectural state of IO-III following the completion of Phase 3, the subsequent hardening pass, and a full post-release gap closure cycle performed on 2026-04-01.

All Phase 3 milestones (M3.1–M3.24) are complete.
All identified post-release gaps (G1–G7) have been closed.
The system has been verified operational end-to-end on local hardware.

This document supersedes DOC-OVW-006.

---

## Repository Version

```
Phase:   Phase 3 — Runtime Foundation
Tag:     v0.3.2
Branch:  main
Status:  Complete, hardened, and gap-closed
```

| Version | Meaning |
|---------|---------|
| v0.3.0  | Phase 3 completion milestone |
| v0.3.1  | Phase 3 hardening pass |
| v0.3.2  | Engine decomposition + ADR-010 seam removal |

---

## Verification Status

```
pytest:              44 passing
invariant validator: 8/8 PASS
capability registry: operational
metadata logging:    content-safe confirmed
end-to-end run:      confirmed operational on local hardware (Ollama / qwen3:8b)
```

Standard verification commands:

```bash
.venv/bin/python -m pytest
python architecture/runtime/scripts/validate_invariants.py
.venv/bin/python -m io_iii capabilities --json
```

---

## Architecture Status

### Deterministic execution

- deterministic routing (mode-driven, never content-inferred)
- deterministic capability invocation
- no dynamic routing
- no autonomous planning
- no recursive orchestration

### Bounded execution

Execution limits defined in ADR-009:

```
MAX_AUDIT_PASSES    = 1
MAX_REVISION_PASSES = 1
```

No recursion surfaces exist. Bounded execution is contract-tested.

### Explicit capability invocation

Capabilities must be invoked explicitly via the CLI or engine invocation path.

Properties enforced at invocation time (`_invoke_capability_once` in `engine.py`):

- `max_calls = 1` — one invocation per `engine.run()` call
- `max_input_chars` — checked before invocation (`CAPABILITY_INPUT_TOO_LARGE`)
- `timeout_ms` — enforced via `ThreadPoolExecutor` (`CAPABILITY_TIMEOUT`)
- `max_output_chars` — checked after invocation (`CAPABILITY_OUTPUT_TOO_LARGE`)

Capabilities currently registered:

```
cap.echo_json
cap.json_pretty
cap.validate_json_schema
```

### Content-safe observability

Runtime logs use metadata-only logging.

Forbidden log fields:

```
prompt
completion
draft
revision
content
```

Permitted log fields include:

```
prompt_hash
latency_ms
provider
model
route
capability metadata
audit metadata
```

All logging behaviour is verified via automated safety tests.

### Prompt construction discipline

All runtime prompts pass through a single deterministic assembly boundary (ADR-010):

```
persona_contract
      ↓
context_assembly
      ↓
provider execution
```

Applies to: executor prompts, challenger prompts, revision prompts.

---

## Post-Phase 3 Gap Closure — 2026-04-01

The following gaps were identified during a post-release review and closed in this session.

### G1 — CapabilityBounds docstring corrected

File: `io_iii/core/capabilities.py`

The `CapabilityBounds` docstring stated bounds were "NOT yet enforced by a dedicated capability runner." This was incorrect — enforcement was already present in `_invoke_capability_once` as part of M3.15. Docstring updated to accurately reflect enforcement points and error codes.

---

### G2 — Capability bounds test coverage completed

File: `tests/test_capability_invocation.py`

Input-too-large enforcement was tested. Timeout and output-too-large enforcement were not. Two tests added:

- `test_capability_enforces_timeout` — verifies `CAPABILITY_TIMEOUT` on a slow capability
- `test_capability_enforces_output_size` — verifies `CAPABILITY_OUTPUT_TOO_LARGE` on an oversized result

---

### G3 — ADR-003 promoted to active

File: `ADR/ADR-003-telemetry-logging-and-retention-policy.md`

Status promoted from `draft v0.1` to `active v1.0`. Implementation Notes updated from aspirational notes to a factual record of what was built (`metadata_logging.py`, `logging.yaml`, `content_safety.py`).

---

### G4 — `latency_ms` auto-capture in engine

File: `io_iii/core/engine.py`

`SessionState.latency_ms` was declared and validated but never populated by the engine. Both return paths in `engine.run()` (null route and ollama route) now compute and set `latency_ms` from `started_at_ms`. Test added:

- `test_engine_sets_latency_ms_on_returned_state`

---

### G5 — Provider health check (ADR-011)

Files:
- `ADR/ADR-011-provider-health-check-policy.md` (new ADR)
- `io_iii/providers/ollama_provider.py`
- `io_iii/cli.py`
- `io_iii/tests/test_provider_health_check.py`

Pre-flight provider reachability check added at the CLI boundary (between routing resolution and `SessionState` creation).

Key properties:

- Lightweight `GET <host>/` check on the Ollama root endpoint
- Raises `PROVIDER_UNAVAILABLE: ollama` on failure with metadata log entry
- No implicit cloud fallback (ADR-004 preserved)
- Skipped for null provider and via `--no-health-check` flag (offline / CI use)
- `check_reachable()` method added to `OllamaProvider`
- Three tests added: reachable, connection error, and timeout cases

---

### G6 — ADR-011 added to ADR index

File: `ADR/README.md`

ADR-011 added to the index. (ADR-010 was already present.)

---

### G7 — Provider config key mismatch corrected

File: `io_iii/providers/ollama_provider.py`

`OllamaProvider.from_config()` was reading `cfg.get("host")` but `providers.yaml` defines the canonical key as `base_url`. The config value was silently ignored at runtime; the provider always fell back to the hardcoded default or `OLLAMA_HOST` env var. Fixed to read `base_url`, aligning code with the canonical config schema and ADR-011.

---

## Test Suite Status

```
Total tests:  44
Status:       all passing
```

Coverage areas:

- capability invocation (including timeout, output-size, and input-size bounds)
- routing determinism
- dependency injection
- audit gate enforcement (bounded passes)
- metadata logging safety
- content-safety guards (forbidden-key enforcement)
- execution tracing
- invariant validation
- provider health check (reachable, connection error, timeout)
- engine latency capture

---

## Architectural Verification Model

| Architectural Guarantee | Verification Type | Coverage Area |
|---|---|---|
| Deterministic routing behaviour | unit / contract tests | routing determinism |
| Explicit capability invocation boundaries | behavioural tests | capability invocation |
| Capability bounds enforcement (timeout, size) | contract tests | capability invocation |
| Dependency injection integrity | integration tests | provider dependency injection |
| Audit gate execution limits | contract tests | audit gate enforcement |
| Content-safe observability | safety tests | metadata logging safeguards |
| Execution trace integrity | behavioural tests | execution tracing |
| Runtime invariant enforcement | invariant validation | repository invariants |
| Provider health check policy | unit tests | provider reachability |
| Latency capture | behavioural tests | engine state output |

---

## Runtime Guarantees

The runtime currently guarantees:

- deterministic routing
- bounded execution
- max audit passes = 1
- max revision passes = 1
- explicit capability invocation only
- no autonomous tool selection
- no recursive orchestration
- no dynamic routing
- no prompt or completion content in logs
- pre-flight provider reachability check at CLI boundary

---

## Repository Health

| Category | Status |
|---|---|
| Architecture integrity | strong |
| Runtime safety | strong |
| Determinism | enforced |
| Governance documentation | strong |
| Test discipline | strong |
| Operational verification | confirmed |

---

## Known Non-Goals

The IO-III runtime intentionally does not implement:

- agent behaviour
- tool planning
- recursive execution loops
- dynamic routing
- autonomous decision-making
- implicit cloud fallback
- streaming provider responses

The system is a strictly deterministic LLM runtime control-plane.

---

## Next Phase

```
Phase 4 — Context Architecture Formalisation
```

Focus areas:

- bounded orchestration above the runtime kernel
- explicit task specifications or runbooks
- structured execution pipelines without agent behaviour
- preserving all Phase 3 invariants

Phase 4 must not introduce:

- autonomous behaviour
- recursive execution loops
- dynamic routing
- planner behaviour
- uncontrolled multi-step orchestration

---

## Snapshot Purpose

This document serves as:

- the authoritative project checkpoint at end of Phase 3 gap closure
- the handoff state for the start of Phase 4
- the starting point for Phase 4 architecture work

---

## Phase 4 Progress Update — 2026-04-03

**Current phase:** Phase 4 — Post-Capability Architecture Layer  
**Governed by:** ADR-012 (Bounded Orchestration Layer Contract)

### Milestones complete

| Milestone | Title |
|-----------|-------|
| M4.0 | Phase 4 ADR and milestone definition (ADR-012, DOC-ARCH-012) |
| M4.1 | Task Specification Schema (`TaskSpec`) |
| M4.2 | Single-Run Bounded Orchestration Layer (`Orchestrator`) |
| M4.3 | Execution Trace Lifecycle Contracts |
| M4.4 | SessionState v1 Contract (`task_spec_id` linkage) |
| M4.5 | Engine Observability Groundwork (`EngineEventKind`, per-stage events) |
| M4.6 | Deterministic Failure Semantics (ADR-013, `RuntimeFailure`, `RuntimeFailureKind`) |

### Next milestone

**M4.7 — Multi-Step Bounded Runbook Layer** (in progress as of 2026-04-03)

Governed by ADR-014. Introduces `Runbook` and `RunbookRunner` above the frozen
orchestration layer with fixed-order execution, explicit step ceiling, no branching,
and deterministic termination on step failure.

### Verification snapshot (M4.6 close)

```
pytest:              174 passing
invariant validator: 1/1 PASS
```

---