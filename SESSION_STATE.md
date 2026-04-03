# SESSION_STATE

# IO-III Session State

## Project
IO-III — Deterministic Local LLM Runtime Architecture

Repository
https://github.com/CevenJKnowles/io-architecture

Local Path
/home/cjk/Dev/IO-III/io-architecture

---

# Phase Status

Current Phase
Phase 4 — Post-Capability Architecture Layer

Status
Active (M4.6 complete; M4.7 next)

Tag
v0.3.2

Branch
main

---

# Phase 3 Goal

Establish the deterministic runtime kernel of IO-III while preserving all architectural invariants.

The runtime now provides:

- deterministic routing
- bounded execution
- explicit capability invocation
- content-safe telemetry
- audit traceability
- invariant-protected architecture
- deterministic prompt assembly through a single context boundary

---

# Phase 3 Milestones

## M3.1 — Capability architecture definition
Document architectural design for the capability system.

File
docs/architecture/DOC-ARCH-005-io-iii-capability-layer-definition.md

---

## M3.2 — Capability contracts
Introduce capability specification structures.

Core components introduced:

- CapabilitySpec
- CapabilityContext
- CapabilityResult
- CapabilityBounds

---

## M3.3 — Capability registry
Introduce deterministic registry system for capabilities.

Properties:

- deterministic ordering
- explicit registration
- no dynamic loading

---

## M3.4 — Capability invocation path
Integrate capability execution path into the IO-III engine.

Execution pipeline:

CLI
→ routing
→ engine
→ capability registry
→ capability execution
→ telemetry + trace

---

## M3.5 — Execution bounds enforcement
Introduce strict runtime bounds:

- max calls
- max input size
- max output size
- timeout

---

## M3.6 — Content safety guardrails
Ensure capability output cannot leak sensitive content into logs.

Only structured metadata may be logged.

---

## M3.7 — Execution trace integration
Capability execution is integrated into the IO-III execution trace system.

Trace stage:

capability_execution

---

## M3.8 — Metadata logging integration
Capability executions produce content-safe metadata records.

Log location

architecture/runtime/logs/metadata.jsonl

---

## M3.9 — CLI capability execution
Introduce CLI command:

python -m io_iii capability <capability_id> <payload>

---

## M3.10 — Capability registry exposure
CLI capability listing introduced:

python -m io_iii capabilities

---

## M3.11 — Capability JSON inspection
Machine-readable output added:

python -m io_iii capabilities --json

---

## M3.12 — Capability telemetry integration
Capability executions produce structured metadata:

- capability_id
- version
- duration
- success/failure

---

## M3.13 — Capability trace instrumentation
Execution trace records capability execution stage.

---

## M3.14 — Payload validation
Capability payload validation added.

---

## M3.15 — Capability bounds enforcement
Runtime guardrails ensure deterministic bounded execution.

---

## M3.16 — CLI capability command
Stable CLI execution command finalised.

---

## M3.17 — Demonstration capabilities
Introduce deterministic example capabilities.

- cap.echo_json
- cap.json_pretty
- cap.validate_json_schema

Purpose:

- demonstrate capability architecture
- provide deterministic runtime tools
- improve repository clarity

---

## M3.18 — Capability registry JSON inspection
Expose registry through deterministic CLI inspection.

Commands:

python -m io_iii capabilities
python -m io_iii capabilities --json

Purpose:

- allow tooling and automation
- enable runtime introspection
- improve system observability

---

## M3.19 — Session state enforcement
Wire `validate_session_state()` into the CLI execution path.

Purpose:

- fail fast on invalid runtime state
- strengthen runtime integrity
- align implementation with documented state model

---

## M3.20 — Invariant test integration
Integrate the invariant validator into pytest.

Purpose:

- make `pytest` a single-command architecture verification pass
- reduce drift between runtime and governance layer

---

## M3.21 — Routing determinism test
Add explicit routing determinism coverage.

Purpose:

- verify identical inputs produce identical route selection
- strengthen deterministic execution guarantees

---

## M3.22 — ADR-010 seam closure
Route challenger and revision prompt construction through the same context assembly boundary as executor prompts.

Execution path:

persona_contract
→ context_assembly
→ provider execution

Purpose:

- remove inline prompt construction seam
- enforce structural consistency across runtime prompt paths

---

## M3.23 — Runtime kernel hardening
Decompose `engine.run()` into named helper paths and align state replacement to stdlib `dataclasses.replace()`.

Purpose:

- prevent kernel monolith growth
- prepare cleanly for Phase 4
- improve maintainability without changing behaviour

---

## M3.24 — Phase 3 polish and readiness docs
Add the remaining project-readiness artefacts:

- CONTRIBUTING.md
- DOC-ARCH-012 Phase 4 guide
- doc guardrail tests
- fail-open challenger policy note

Purpose:

- improve public professionalism
- reduce process drift
- create a clean entry point for Phase 4

---

# Phase 3 Result

IO-III now includes a complete deterministic runtime kernel.

The runtime can now:

- resolve deterministic routes
- execute bounded provider calls
- execute bounded capabilities
- assemble prompts through a single context boundary
- trace execution stages
- log content-safe metadata
- enforce runtime invariants through tests and validators

Execution architecture:

CLI
→ routing
→ engine
→ context assembly / capability registry
→ bounded execution
→ execution trace
→ content-safe metadata logging

---

# Verification

Verification status:

- pytest passing
- invariant validator passing
- capability registry functioning
- metadata logging content-safe

Standard verification commands:

python -m pytest
python architecture/runtime/scripts/validate_invariants.py
python -m io_iii capabilities --json

All invariants PASS.

---

# Current Repository State

Branch
main

Tag
v0.3.2

Pull request
Phase 3 Hardening merged. Phase 4 implementation active on `main`.

Repository state
Phase 4 active. M4.0–M4.6 complete. M4.7 (Multi-Step Bounded Runbook Layer) in progress.

---

# Runtime Guarantees

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

Forbidden logging fields:

- prompt
- completion
- draft
- revision
- content

---

# Post-Phase 3 Gap Closure — 2026-04-01

Work performed against gaps identified during Phase 3 review.

---

## G1 — Capability bounds docstring corrected

File
`io_iii/core/capabilities.py`

The `CapabilityBounds` docstring stated that bounds were "NOT yet enforced by a dedicated capability runner." This was incorrect. Enforcement was already present in `_invoke_capability_once` (engine.py) as part of M3.15. Docstring updated to accurately describe enforcement points and error codes.

---

## G2 — Capability bounds test coverage completed

File
`tests/test_capability_invocation.py`

Input-too-large enforcement was tested. Timeout and output-too-large enforcement were not. Two tests added:

- `test_capability_enforces_timeout` — verifies `CAPABILITY_TIMEOUT` on a slow capability
- `test_capability_enforces_output_size` — verifies `CAPABILITY_OUTPUT_TOO_LARGE` on an oversized result

---

## G3 — ADR-003 promoted to active

File
`ADR/ADR-003-telemetry-logging-and-retention-policy.md`

Status promoted from `draft v0.1` to `active v1.0`. Implementation Notes updated from aspirational notes to a factual record of what was built (`metadata_logging.py`, `logging.yaml`, `content_safety.py`).

---

## G4 — `latency_ms` auto-capture in SessionState

File
`io_iii/core/engine.py`

`SessionState.latency_ms` was declared and validated but never populated by the engine. Both return paths in `engine.run()` (null route and ollama route) now compute and set `latency_ms` from `started_at_ms` before returning the final state. Test added:

- `test_engine_sets_latency_ms_on_returned_state`

---

## G5 — Provider health check (ADR-011)

Files
`ADR/ADR-011-provider-health-check-policy.md`
`io_iii/providers/ollama_provider.py`
`io_iii/cli.py`
`io_iii/tests/test_provider_health_check.py`

New ADR written and indexed. Adds a pre-flight provider reachability check at the CLI boundary (between routing resolution and SessionState creation). Key properties:

- Lightweight `GET <host>/` check on Ollama root endpoint
- Raises `PROVIDER_UNAVAILABLE: ollama` on failure with metadata log entry
- No implicit cloud fallback (ADR-004 preserved)
- Skipped for null provider and via `--no-health-check` flag (offline/CI use)
- `check_reachable()` method added to `OllamaProvider`
- Three tests added covering reachable, connection error, and timeout cases

---

## G6 — ADR-011 added to index

File
`ADR/README.md`

ADR-011 added to the index. (ADR-010 was already present.)

---

## G7 — Provider config key mismatch corrected

File
`io_iii/providers/ollama_provider.py`

`OllamaProvider.from_config()` was reading `cfg.get("host")` but `providers.yaml` defines the key as `base_url`. The config value was silently ignored at runtime; the provider always fell back to the hardcoded default or `OLLAMA_HOST` env var. Fixed to read `base_url`, aligning code with the canonical config schema and ADR-011.

---

## Verification

Tests: **44 passing**

Invariant validator: **8/8 PASS**

Standard verification commands:

python -m pytest
python architecture/runtime/scripts/validate_invariants.py
python -m io_iii capabilities --json

---

# Next Phase

Phase 4 — Post-Capability Architecture Layer

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

# Session Reset Point

This document serves as the canonical session alignment file.

Future sessions should read this file first before performing any architectural work.

It should be treated as the authoritative handoff state between Phase 3 and Phase 4.

---

End of Phase 3

---

## Phase 4 Progress Update — M4.6 Complete

**Status:** Active  
**Phase:** 4 — Post-Capability Architecture Layer  
**Current Milestone:** M4.6 complete — M4.7 next

### Completed
- M4.0 governance freeze completed through ADR-012, `DOC-ARCH-012`, and canonical milestone definition
- M4.1 `TaskSpec` introduced as a serialisable declarative execution contract
- M4.2 single-run bounded `Orchestrator` implemented and tested
- M4.3 `ExecutionTrace` lifecycle contracts added with explicit transition guards
- M4.4 `SessionState` promoted to v1 with explicit `task_spec_id` linkage
- M4.5 Engine Observability Groundwork — structured per-stage `EngineEventKind` lifecycle events, `EngineObservabilityLog`, engine events in `ExecutionResult.meta`
- M4.6 Deterministic Failure Semantics — canonical typed failure model across engine, trace, observability, and CLI surfaces

### M4.6 Contract Summary

- `RuntimeFailureKind` defines six stable failure categories: `route_resolution`, `provider_execution`, `audit_challenger`, `capability`, `contract_violation`, `internal`
- `RuntimeFailure` is a frozen, content-safe dataclass carrying `kind`, `code`, `summary`, `request_id`, `task_spec_id`, `retryable`, `causal_code`
- On any engine exception, `RuntimeFailure` is classified and attached as `.runtime_failure` on the original exception
- Original exception type is preserved on re-raise — no wrapper exception
- Execution trace always reaches terminal `’failed’` state on any exception
- `engine_run_failed` lifecycle event always emitted on the failure path (content-safe)
- CLI logs stable `failure.code` and `failure_kind` in metadata when available
- `retryable=True` permitted only for `PROVIDER_UNAVAILABLE`
- Content policy: `summary` and `causal_code` never carry prompt or model output text
- ADR: ADR-013 — Deterministic Failure Semantics

### Verification Snapshot (M4.6)

- `pytest`: 174 passing
- invariant validator: 1/1 passing

### M4.7 Implementation — In Progress (2026-04-03)

**ADR:** ADR-014 — Bounded Runbook Layer Contract (subordinate to ADR-012)

**Files introduced:**
- `io_iii/core/runbook.py` — `Runbook` schema, `RUNBOOK_MAX_STEPS = 20`, validation, serialisation
- `io_iii/core/runbook_runner.py` — `run()`, `RunbookResult`, `RunbookStepOutcome`
- `tests/test_runbook_m47.py` — focused M4.7 contract and regression tests

**Contract:**
- `Runbook` is immutable/serialisable with a stable `runbook_id`
- Ordered finite list of `TaskSpec` steps; ceiling enforced at construction
- Runner executes steps strictly in declared order via `orchestrator.run()` only
- Exactly one `orchestrator.run()` per step; ADR-009 bounds preserved per step
- Step failure terminates deterministically — no retry, no branching, no recovery
- `RunbookResult` is bounded and content-safe; no prompt/output text in any field

**Status:** Implementation complete. Verification in progress.

### Next Execution Target
M4.7 acceptance verification — then M4.7 complete
